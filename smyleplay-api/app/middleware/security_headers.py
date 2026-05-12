"""
Middleware Security Headers — Smyleplay
========================================

Ajoute les headers HTTP de sécurité standards à toutes les réponses API.

Ferme directement les risques OWASP suivants :
- A05 Misconfiguration (headers manquants)
- A03 Injection XSS (mitigée par CSP)
- Clickjacking (X-Frame-Options)
- MIME sniffing (X-Content-Type-Options)
- Downgrade HTTPS (Strict-Transport-Security)
- Fuite via referrer (Referrer-Policy)

Référence : OWASP Secure Headers Project (https://owasp.org/www-project-secure-headers/)

Notes V1 :
- CSP volontairement PERMISSIVE pour ne pas casser le frontend Flask + dashboard.js
  inline. À durcir progressivement avec hash/nonce une fois le front migré.
- HSTS activé en prod uniquement (sinon dev local en HTTP casse).
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


# CSP volontairement large pour V1 — à durcir après migration front
_CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "media-src 'self' https://*.r2.dev https://pub-*.r2.dev; "
    "connect-src 'self' https://*.r2.dev https://pub-*.r2.dev; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


_PERMISSIONS_POLICY = (
    "geolocation=(), "
    "microphone=(), "
    "camera=(), "
    "payment=(self), "
    "usb=(), "
    "magnetometer=(), "
    "gyroscope=()"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Ajoute les headers de sécurité à toutes les réponses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Anti-XSS / Anti-injection JS
        response.headers["Content-Security-Policy"] = _CSP_POLICY

        # Empêche le browser de "deviner" le type MIME (anti-XSS)
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Anti-clickjacking : interdit d'iframer Smyleplay
        response.headers["X-Frame-Options"] = "DENY"

        # Ne pas leak l'URL complète aux sites externes
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Désactive les API navigateur non utilisées (réduit la surface d'attaque)
        response.headers["Permissions-Policy"] = _PERMISSIONS_POLICY

        # HSTS : force HTTPS sur Smyleplay pendant 1 an, inclus les sous-domaines
        # Activé uniquement en prod pour ne pas casser le dev local en HTTP
        if settings.ENVIRONMENT in ("production", "prod"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Header legacy mais inoffensif, encore lu par certains scanners
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response
