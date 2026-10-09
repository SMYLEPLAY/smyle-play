"""
Service Cloudflare R2 — port FastAPI de la logique Flask (P1-F5).

R2 est l'API S3-compatible de Cloudflare ; on l'utilise via boto3 en pointant
endpoint_url sur l'URL R2 du compte. La logique reproduit fidèlement celle de
flask_app.py:64-81 (init client) et flask_app.py:636-644 (delete object) tout
en restant dégradable :

  - Si une var R2 manque côté config (cas dev local sans secrets), tous les
    helpers retournent False et loggent un warning unique au lieu de crash.
  - boto3 est synchrone : on l'enveloppe dans `asyncio.to_thread` pour éviter
    de bloquer la boucle async ASGI sur l'I/O réseau.

Le client est créé en lazy via lru_cache : 1 instance par process, partagée
entre toutes les requêtes (boto3 client est thread-safe). Pas besoin de
gérer son cycle de vie via lifespan handler — le process FastAPI se charge
de tear down.

Exposé :
  - is_configured() -> bool : vrai ssi les 3 secrets sont définis
  - delete_r2_object(key) -> bool : supprime, idempotent, log warning sur err
  - appel_r2(fn, ...) : exécute un appel boto3 HORS de la boucle asyncio
    (thread) et classe l'échec : objet absent (R2Absent) ou stockage
    indisponible (R2Indisponible) ;
  - ouvrir_objet(key) : get_object prêt pour une route (503 si R2 est en
    panne ou non configuré, 404 seulement si l'objet n'existe pas) ;
  - flux_objet(obj) : itérateur par morceaux du corps d'un objet.

Lot E (tenue en charge) : client à délais COURTS (connexion 3 s, lecture
10 s, une seule nouvelle tentative). Une panne R2 ne doit ni geler les
workers (appels bloquants dans la boucle) ni se déguiser en « introuvable » :
elle répond 503 et laisse une ligne de log.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

# Délais du client (secondes) et nombre total d'essais par appel (1 = aucun
# nouvel essai). Courts exprès : mieux vaut un 503 rapide qu'un worker figé.
R2_CONNECT_TIMEOUT = 3
R2_READ_TIMEOUT = 10
R2_MAX_ATTEMPTS = 2

# Codes d'erreur S3 qui signifient « l'objet n'existe pas ».
_CODES_ABSENT = {"NoSuchKey", "404", "NotFound", "NoSuchBucket"}


class R2Absent(Exception):
    """L'objet demandé n'existe pas dans le bucket."""


class R2Indisponible(Exception):
    """Stockage injoignable, trop lent ou en erreur (réseau, 5xx, délai)."""

# Flag pour ne logger le warning "R2 non configuré" qu'une seule fois par
# process (évite de polluer les logs sur chaque DELETE en dev local).
_warned_unconfigured = False


def is_configured() -> bool:
    """
    Vrai ssi les 3 secrets R2 obligatoires sont définis.
    Accepte les deux conventions de nommage Railway :
      - moderne  : R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ENDPOINT_URL
      - legacy   : R2_ACCESS_KEY / R2_SECRET_KEY / R2_ACCOUNT_ID
    """
    return all([
        settings.effective_r2_access_key_id,
        settings.effective_r2_secret_access_key,
        settings.effective_r2_endpoint_url,
    ])


@lru_cache(maxsize=1)
def _get_client() -> Any | None:
    """
    Retourne le client boto3 R2 partagé pour ce process.

    Lazy + cached : la 1re requête qui arrive paye l'init, les suivantes
    réutilisent. Si la config est incomplète, on retourne None (le caller
    loggue un warning et skip).
    """
    if not is_configured():
        global _warned_unconfigured
        if not _warned_unconfigured:
            logger.warning(
                "[R2] Service non configuré (R2_ACCESS_KEY_ID / "
                "R2_SECRET_ACCESS_KEY / R2_ENDPOINT_URL manquants). "
                "Les opérations R2 seront skippées."
            )
            _warned_unconfigured = True
        return None

    try:
        import boto3  # import différé : la dépendance n'est tirée que si configurée
    except ImportError:
        logger.error(
            "[R2] boto3 non installé (vérifier requirements.txt)."
        )
        return None

    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.effective_r2_endpoint_url,
        aws_access_key_id=settings.effective_r2_access_key_id,
        aws_secret_access_key=settings.effective_r2_secret_access_key,
        region_name="auto",  # R2 ignore la region mais boto3 l'exige
        config=Config(
            connect_timeout=R2_CONNECT_TIMEOUT,
            read_timeout=R2_READ_TIMEOUT,
            retries={"total_max_attempts": R2_MAX_ATTEMPTS, "mode": "standard"},
            # Sommes de contrôle seulement quand l'opération les exige
            # (comportement boto3 < 1.36, cf. routers/reports.py).
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            max_pool_connections=20,
        ),
    )


def get_r2_client():
    """
    Expose le client boto3 R2 pour les routes qui veulent streamer un objet.
    Retourne None si non configuré — le caller doit gérer.
    """
    return _get_client()


async def delete_r2_object(key: str) -> bool:
    """
    Supprime un objet R2 par clé (ex 'tracks/sl-foo.wav').

    Comportement :
      - key vide / None → no-op (log debug, return False)
      - service non configuré → no-op (log warning unique, return False)
      - boto3 raise → log warning + swallow → return False
      - succès → True

    On NE LAISSE JAMAIS un échec R2 casser une opération applicative
    (suppression DB, achat, etc.) : c'est le pattern du flask_app.py
    historique. Un fichier orphelin dans R2 sera ramassé par un script
    de cleanup périodique (TODO post-alpha).

    Async wrapper sur boto3 sync : on déporte l'I/O réseau dans le default
    executor pour ne pas bloquer la boucle asyncio.
    """
    if not key:
        return False

    client = _get_client()
    if client is None:
        return False

    bucket = settings.R2_BUCKET

    def _sync_delete() -> bool:
        try:
            client.delete_object(Bucket=bucket, Key=key)
            logger.info("[R2] delete_object ok bucket=%s key=%s", bucket, key)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[R2] delete_object failed bucket=%s key=%s err=%s",
                bucket, key, e,
            )
            return False

    return await asyncio.to_thread(_sync_delete)


# ── Appels hors boucle + classement des échecs (Lot E) ─────────────────────

def est_absent(exc: BaseException) -> bool:
    """Vrai si l'exception boto3 signifie « objet inexistant »."""
    reponse = getattr(exc, "response", None)
    if isinstance(reponse, dict):
        err = reponse.get("Error") or {}
        code = str(err.get("Code") or "")
        statut = (reponse.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        return code in _CODES_ABSENT or statut == 404
    return type(exc).__name__ in ("NoSuchKey", "NoSuchBucket")


async def appel_r2(fn, /, *args, operation: str = "appel", key: str = "", **kwargs):
    """Exécute `fn(*args, **kwargs)` (appel boto3 bloquant) dans un thread.

    Lève R2Absent si l'objet n'existe pas, R2Indisponible pour toute autre
    erreur (réseau, délai dépassé, 5xx, identifiants refusés…), avec une
    ligne de log. Ne bloque jamais la boucle asyncio.
    """
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        if est_absent(exc):
            raise R2Absent(key) from exc
        logger.warning(
            "[R2] %s en échec key=%s err=%s: %s",
            operation, key, type(exc).__name__, str(exc)[:200],
        )
        raise R2Indisponible(operation) from exc


def http_503_r2() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Stockage des fichiers momentanément indisponible. Réessaie dans un instant.",
        headers={"Retry-After": "30"},
    )


def client_ou_503():
    """Client R2 prêt, sinon HTTPException 503 (non configuré / indisponible)."""
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 storage not configured",
        )
    client = get_r2_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 client unavailable",
        )
    return client


async def ouvrir_objet(
    key: str,
    *,
    bucket: str | None = None,
    detail_404: str = "Ressource introuvable.",
) -> dict:
    """get_object pour une route : 404 si absent, 503 si R2 est en panne."""
    client = client_ou_503()
    try:
        return await appel_r2(
            client.get_object,
            Bucket=bucket or settings.R2_BUCKET,
            Key=key,
            operation="get_object",
            key=key,
        )
    except R2Absent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail_404)
    except R2Indisponible:
        raise http_503_r2()


async def envoyer_objet(key: str, data: bytes, content_type: str, *, bucket: str | None = None) -> None:
    """put_object hors boucle ; R2Indisponible si l'envoi échoue."""
    client = client_ou_503()
    try:
        await appel_r2(
            client.put_object,
            Bucket=bucket or settings.R2_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
            operation="put_object",
            key=key,
        )
    except R2Absent as exc:  # bucket introuvable : panne de configuration
        raise R2Indisponible("put_object") from exc


def flux_objet(obj: dict, chunk_size: int = 65536):
    """Itérateur (synchrone, lu par Starlette dans un thread) du corps."""
    body = obj["Body"]
    try:
        for chunk in body.iter_chunks(chunk_size=chunk_size):
            yield chunk
    except Exception as exc:  # noqa: BLE001 — coupure en cours de lecture
        logger.warning("[R2] lecture interrompue err=%s", type(exc).__name__)
        raise
    finally:
        try:
            body.close()
        except Exception:
            pass
