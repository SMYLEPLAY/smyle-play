"""
Rate-limiting — Tier 1 sécurité (marathon 2026-06-11), étape 5 (2026-10-02).

Protège les endpoints sensibles contre le brute-force (auth), le spam
(achats, envois de fichiers, emails) via slowapi.

Stockage du compteur (étape 5) :
  • REDIS_URL défini → compteur dans Redis, PARTAGÉ entre les 2 workers
    uvicorn et conservé entre deux redéploiements. Si Redis devient
    injoignable, slowapi bascule tout seul sur un compteur mémoire (repli
    `in_memory_fallback_enabled`) et revient à Redis quand il répond à
    nouveau : une panne Redis ne bloque JAMAIS une connexion.
  • REDIS_URL absent (cas actuel en prod) → compteur en mémoire, propre à
    chaque worker (limite effective ≈ 2× la valeur affichée, remise à zéro
    au redéploiement). Comportement historique, avec un avertissement dans
    les logs au démarrage.

Clé = vraie IP du client. En prod, l'app est derrière le mesh Railway :
`request.client.host` renvoie une IP interne 100.64.0.x qui CHANGE à
chaque requête (constaté en prod le 2026-06-11). Voir client_ip().
Vérifiable en prod via GET /health/client-echo.

Seules les routes décorées par @limiter.limit sont limitées (aucune limite
par défaut, pas de SlowAPIMiddleware) : /health n'est jamais compté.

Désactivé quand ENVIRONMENT=test (CI pytest enchaîne les requêtes).
"""

import logging
import math
import time

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# ── Limites par famille d'endpoints (réglables par variables d'env) ─────────
# Auth : strictes (cible du brute-force).
LIMIT_LOGIN = settings.RATE_LIMIT_LOGIN                    # essais de mot de passe
LIMIT_REGISTER = settings.RATE_LIMIT_REGISTER              # création de comptes en masse
LIMIT_FORGOT_PASSWORD = settings.RATE_LIMIT_FORGOT_PASSWORD  # emails (coût Resend + spam)
LIMIT_RESEND_VERIFICATION = settings.RATE_LIMIT_RESEND_VERIFICATION  # idem
LIMIT_RESET_PASSWORD = settings.RATE_LIMIT_RESET_PASSWORD  # essais de jetons

# Envois de fichiers (images, sons, voix, vidéos) : disque + stockage R2.
LIMIT_UPLOAD = settings.RATE_LIMIT_UPLOAD

# Achats : un humain ne les atteint jamais, un script oui.
LIMIT_PURCHASE = settings.RATE_LIMIT_PURCHASE

# Check-in quotidien : une seule réclamation par jour est possible (garde
# atomique dans services/streak.py). La limite coupe le martèlement d'un
# script qui tenterait la course — 5/minute laisse largement passer un
# humain qui reclique (S-07, audit A §M2).
LIMIT_CHECKIN = "5/minute"

# Rapports de violation CSP envoyés par les navigateurs (étape 5).
LIMIT_CSP_REPORT = "30/minute"

# Préfixe des clés côté Redis (évite toute collision avec un autre usage).
_KEY_PREFIX = "watt-rl"


def client_ip(request: Request) -> str:
    """
    IP réelle du client derrière l'edge Railway — robuste au spoofing.

    Durcissement (2026-07-24) : l'ancienne version prenait `x-real-ip` ou la
    PREMIÈRE entrée de X-Forwarded-For, toutes deux fournissables par le client
    → un attaquant faisait tourner cet en-tête pour obtenir un compteur de
    rate-limit neuf à chaque requête (contournement du brute-force login/reset).

    Sur Railway, X-Forwarded-For observé = "…entrées client (spoofables)…,
    VRAI_CLIENT, proxy_railway" : l'edge AJOUTE le vrai client puis son propre
    proxy. Le vrai client est donc l'AVANT-DERNIÈRE entrée — un client peut
    préfixer des IP bidon à gauche mais ne peut pas altérer ce que l'edge ajoute
    à droite. On la prend comme clé de confiance.
    """
    xff = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[-2]           # vrai client, juste avant le proxy Railway
    if len(parts) == 1:
        return parts[0]
    real = request.headers.get("x-real-ip")
    if real and real.strip():
        return real.strip()
    return get_remote_address(request)


def _storage_uri() -> str:
    """URI du stockage des compteurs : Redis si REDIS_URL, sinon mémoire.

    Ne lève jamais : toute impossibilité d'utiliser Redis (paquet `redis`
    absent, URL d'un schéma inconnu) retombe sur la mémoire avec une erreur
    explicite dans les logs — le site démarre toujours.
    """
    url = (settings.REDIS_URL or "").strip()
    if not url:
        if settings.ENVIRONMENT != "test":
            logger.warning(
                "[ratelimit] REDIS_URL absent : compteur anti-attaques en "
                "MÉMOIRE, propre à chaque worker (limite effective ≈ 2× avec 2 "
                "workers) et remis à zéro à chaque redéploiement. Ajouter un "
                "service Redis sur Railway et définir REDIS_URL pour le partager."
            )
        return "memory://"
    if not url.startswith(("redis://", "rediss://")):
        logger.error(
            "[ratelimit] REDIS_URL ignoré (doit commencer par redis:// ou "
            "rediss://) : repli sur le compteur en mémoire."
        )
        return "memory://"
    try:
        import redis  # noqa: F401 — vérifie seulement que le client est installé
    except ImportError:
        logger.error(
            "[ratelimit] REDIS_URL défini mais le paquet `redis` n'est pas "
            "installé : repli sur le compteur en mémoire."
        )
        return "memory://"
    return url


# Délais courts : Redis est sur le réseau privé Railway (réponse en ~1 ms).
# S'il ne répond pas, on préfère basculer vite sur la mémoire que de faire
# attendre une connexion.
_REDIS_OPTIONS = {"socket_connect_timeout": 1, "socket_timeout": 1}


def build_limiter(storage_uri: str | None = None, *, enabled: bool | None = None) -> Limiter:
    """Construit le limiteur (exposé pour les tests).

    ⚠️ headers_enabled DOIT rester False : avec True, slowapi tente d'injecter
    les en-têtes X-RateLimit-* dans la valeur de retour de l'endpoint — or nos
    endpoints renvoient des dicts/modèles Pydantic (pas des Response), ce qui
    faisait planter en 500 TOUTES les réponses RÉUSSIES des endpoints décorés
    (bug prod du 2026-06-12 : login correct → 500, mauvais mdp → 401 normal).
    Le 429 pose lui-même son Retry-After (rate_limit_handler).
    """
    uri = storage_uri or _storage_uri()
    options = dict(_REDIS_OPTIONS) if uri.startswith(("redis://", "rediss://")) else {}
    try:
        return Limiter(
            key_func=client_ip,
            headers_enabled=False,
            enabled=(settings.ENVIRONMENT != "test") if enabled is None else enabled,
            storage_uri=uri,
            storage_options=options,
            # Redis injoignable → compteur mémoire temporaire, puis retour
            # automatique à Redis (slowapi re-teste le stockage périodiquement).
            in_memory_fallback_enabled=True,
            key_prefix=_KEY_PREFIX,
        )
    except Exception as exc:  # URI invalide, dépendance manquante…
        logger.error(
            "[ratelimit] stockage %r inutilisable (%s) : repli sur la mémoire.",
            "redis" if uri.startswith("redis") else uri,
            type(exc).__name__,
        )
        return Limiter(
            key_func=client_ip,
            headers_enabled=False,
            enabled=(settings.ENVIRONMENT != "test") if enabled is None else enabled,
            storage_uri="memory://",
            key_prefix=_KEY_PREFIX,
        )


def storage_kind(lim: Limiter) -> str:
    """« redis » ou « memoire » — pour les logs et les tests."""
    uri = getattr(lim, "_storage_uri", "") or ""
    return "redis" if uri.startswith(("redis://", "rediss://")) else "memoire"


limiter = build_limiter()


def _retry_after_seconds(request: Request) -> int:
    """Secondes avant que la fenêtre dépassée se rouvre (60 par défaut)."""
    try:
        lim, args = request.state.view_rate_limit
        reset_at, _remaining = request.app.state.limiter.limiter.get_window_stats(
            lim, *args
        )
        return max(1, math.ceil(reset_at - time.time()))
    except Exception:
        return 60


def _attente_lisible(secondes: int) -> str:
    if secondes < 60:
        return "moins d'une minute"
    minutes = math.ceil(secondes / 60)
    if minutes < 60:
        return f"{minutes} minute" + ("s" if minutes > 1 else "")
    heures = math.ceil(minutes / 60)
    return f"{heures} heure" + ("s" if heures > 1 else "")


def rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    """429 JSON propre en français (le front affiche `detail` tel quel),
    avec Retry-After pour les clients qui savent attendre."""
    secondes = _retry_after_seconds(request)
    return JSONResponse(
        status_code=429,
        content={
            "detail": (
                f"Trop de tentatives. Réessaie dans {_attente_lisible(secondes)}."
            )
        },
        headers={"Retry-After": str(secondes)},
    )
