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
