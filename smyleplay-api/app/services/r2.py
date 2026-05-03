"""
Service Cloudflare R2 — port FastAPI de la logique Flask (P1-F5).

R2 est l'API S3-compatible de Cloudflare ; on l'utilise via boto3 en pointant
endpoint_url sur l'URL R2 du compte. La logique reproduit fidèlement celle de
flask_app.py:64-81 (init client) et flask_app.py:636-644 (delete object) tout
en restant dégradable :

  - Si une var R2 manque côté config (cas dev local sans secrets), tous les
    helpers retournent False et loggent un warning unique au lieu de crash.
  - boto3 est synchrone : on l'enveloppe dans `run_in_executor` pour éviter
    de bloquer la boucle async ASGI sur l'I/O réseau.

Le client est créé en lazy via lru_cache : 1 instance par process, partagée
entre toutes les requêtes (boto3 client est thread-safe). Pas besoin de
gérer son cycle de vie via lifespan handler — le process FastAPI se charge
de tear down.

Exposé :
  - is_configured() -> bool : vrai ssi les 3 secrets sont définis
  - delete_r2_object(key) -> bool : supprime, idempotent, log warning sur err
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Flag pour ne logger le warning "R2 non configuré" qu'une seule fois par
# process (évite de polluer les logs sur chaque DELETE en dev local).
_warned_unconfigured = False


def is_configured() -> bool:
    """
    Vrai ssi les 3 secrets R2 obligatoires sont définis. Le bucket a un
    défaut, donc seuls access_key + secret + endpoint_url sont required.
    """
    return all([
        settings.R2_ACCESS_KEY_ID,
        settings.R2_SECRET_ACCESS_KEY,
        settings.R2_ENDPOINT_URL,
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

    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",  # R2 ignore la region mais boto3 l'exige
    )


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

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_delete)
