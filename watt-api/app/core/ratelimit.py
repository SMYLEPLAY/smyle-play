"""
Rate-limiting — Tier 1 sécurité (marathon 2026-06-11).

Protège les endpoints sensibles contre le brute-force (auth) et le spam
(achats) via slowapi. Stockage en mémoire : avec 2 workers uvicorn, chaque
worker a son propre compteur → la limite effective est ~2× la valeur
affichée. Acceptable pour un anti-abus (passage à Redis si besoin futur).

Clé = vraie IP du client. En prod, l'app est derrière le mesh Railway :
`request.client.host` renvoie une IP interne 100.64.0.x qui CHANGE à
chaque requête (constaté en prod le 2026-06-11 — prendre la dernière
entrée XFF donnait un compteur neuf par requête, donc aucun blocage).
Ordre de résolution : `X-Real-IP` / `X-Envoy-External-Address` (posés par
l'edge Railway), sinon PREMIÈRE entrée de `X-Forwarded-For`, sinon IP
directe. Vérifiable en prod via GET /health/client-echo.

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
    """IP réelle du client derrière l'edge Railway (sinon fallback direct)."""
    real = (
        request.headers.get("x-real-ip")
        or request.headers.get("x-envoy-external-address")
    )
    if real and real.strip():
        return real.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return get_remote_address(request)


# ⚠️ headers_enabled DOIT rester False : avec True, slowapi tente d'injecter
# les en-têtes X-RateLimit-* dans la valeur de retour de l'endpoint — or nos
# endpoints renvoient des dicts/modèles Pydantic (pas des Response), ce qui
# faisait planter en 500 TOUTES les réponses RÉUSSIES des endpoints décorés
# (bug prod du 2026-06-12 : login correct → 500, mauvais mdp → 401 normal).
limiter = Limiter(
    key_func=client_ip,
    headers_enabled=False,
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
