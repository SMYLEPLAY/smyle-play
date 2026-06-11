"""
Rate-limiting — Tier 1 sécurité (marathon 2026-06-11).

Protège les endpoints sensibles contre le brute-force (auth) et le spam
(achats) via slowapi. Stockage en mémoire : avec 2 workers uvicorn, chaque
worker a son propre compteur → la limite effective est ~2× la valeur
affichée. Acceptable pour un anti-abus (passage à Redis si besoin futur).

Clé = vraie IP du client. En prod, l'app est derrière le proxy Railway :
`request.client.host` renvoie l'IP du proxy (la même pour tout le monde !),
il faut donc lire `X-Forwarded-For`. On prend la DERNIÈRE entrée de la
liste : c'est celle ajoutée par le proxy Railway lui-même, donc non
falsifiable par le client (les premières entrées peuvent être forgées).

Désactivé quand ENVIRONMENT=test (CI pytest enchaîne les requêtes).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

# ── Limites par famille d'endpoints ──────────────────────────────────────────
# Auth : strictes (cible du brute-force).
LIMIT_LOGIN = "10/minute"            # essais de mot de passe
LIMIT_REGISTER = "20/hour"           # création de comptes en masse
LIMIT_FORGOT_PASSWORD = "5/15minutes"  # envoi d'emails (coût Resend + spam)
LIMIT_RESET_PASSWORD = "10/hour"     # essais de jetons

# Achats : généreuses — un humain ne les atteint jamais, un script oui.
LIMIT_PURCHASE = "30/minute"


def client_ip(request: Request) -> str:
    """IP réelle du client derrière le proxy Railway (sinon fallback direct)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        last = xff.split(",")[-1].strip()
        if last:
            return last
    return get_remote_address(request)


limiter = Limiter(
    key_func=client_ip,
    headers_enabled=True,  # X-RateLimit-* + Retry-After dans les réponses
    enabled=settings.ENVIRONMENT != "test",
)


def rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    """429 JSON propre (le front affiche `detail` tel quel)."""
    response = JSONResponse(
        status_code=429,
        content={
            "detail": (
                "Trop de tentatives. Patiente un peu avant de réessayer."
            )
        },
    )
    # Injecte X-RateLimit-* + Retry-After calculés par slowapi (best-effort).
    try:
        response = request.app.state.limiter._inject_headers(
            response, request.state.view_rate_limit
        )
    except Exception:
        response.headers["Retry-After"] = "60"
    return response
