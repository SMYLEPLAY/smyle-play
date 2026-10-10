"""
En-têtes de sécurité HTTP + garde-fous d'envoi — étape 5 (2026-10-02).

Regroupe ce qui était défini dans `create_app` (en-têtes, F-02) et les
ajouts de l'étape 5 :

  • CSP « qui bloque » derrière l'interrupteur CSP_ENFORCE (défaut false =
    Report-Only, comportement actuel). La politique est la MÊME dans les deux
    modes ; seul le nom de l'en-tête change. Relu à CHAQUE requête.
  • Rapports de violation : `report-uri /securite/csp-rapport` → une ligne
    de log par violation (adresse sans paramètres, pour ne jamais écrire un
    jeton de réinitialisation dans les logs). C'est ce qui permet à Tom de
    vérifier « zéro violation » avant d'allumer CSP_ENFORCE.
  • Permissions-Policy : caméra, micro, géolocalisation, paiement intégré,
    USB et ciblage publicitaire coupés (aucune page ne s'en sert).
  • Cookies : tout Set-Cookie reçoit HttpOnly + SameSite=Lax s'ils manquent,
    et Secure quand la requête est arrivée en HTTPS. (Aujourd'hui l'API ne
    pose AUCUN cookie — le jeton vit dans localStorage — ; filet pour demain.)
  • Plafond d'une requête d'envoi (multipart) : refusée en 413 AVANT d'être
    écrite sur le disque du serveur (UPLOAD_MAX_REQUEST_MB).

Tout est en ASGI PUR (pas de BaseHTTPMiddleware) : on ne touche qu'aux
en-têtes de `http.response.start`, jamais au corps — c'est ce qui préserve le
streaming des proxys R2 (incident des pochettes disparues du 24/07).
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response
from starlette.datastructures import Headers, MutableHeaders

from app.config import settings
from app.core.ratelimit import LIMIT_CSP_REPORT, limiter

logger = logging.getLogger(__name__)

CSP_REPORT_PATH = "/securite/csp-rapport"

# ── Inventaire des ressources chargées par les pages (2026-10-02) ──────────
# Relevé sur les 88 fichiers HTML/JS/CSS servis (hors e2e/ et archives) :
#   • scripts, feuilles de style, polices : TOUS servis par le site lui-même
#     (aucun CDN, aucune Google Font, aucun Stripe.js, aucun Sentry navigateur,
#     aucun outil d'analytics tiers).
#   • beaucoup de code « inline » (onclick=, <style>, style=) → 'unsafe-inline'
#     reste nécessaire pour script-src et style-src.
#   • images : site + domaine public R2 (pub-….r2.dev, via la redirection de
#     /watt/images) + aperçus locaux data:/blob: (FileReader) + avatars
#     éventuellement hébergés ailleurs en https → img-src https:.
#   • sons / vidéos : /watt/stream (site) + audio_url R2 public en https +
#     aperçu local blob: (vidéo de couverture de playlist) → media-src https:.
#   • fetch / sendBeacon : uniquement le site (API même origine) → 'self'.
#   • Stripe : simple redirection de page vers checkout.stripe.com
#     (window.location) — non concernée par la CSP.
#   • aucun eval / new Function, aucune iframe, aucun <form action> externe.
_CSP_DIRECTIVES = (
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "media-src 'self' blob: https:",
    "connect-src 'self'",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
    f"report-uri {CSP_REPORT_PATH}",
)
POLITIQUE_CSP = "; ".join(_CSP_DIRECTIVES)

PERMISSIONS_POLICY = (
    "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
    "browsing-topics=()"
)

# Préfixes de proxy binaire : réponse transmise telle quelle (streaming R2).
SEC_SKIP_PREFIXES = ("/watt/images", "/watt/stream", "/images")


def nom_entete_csp() -> str:
    """Bloquant si CSP_ENFORCE, sinon Report-Only (relu à chaque requête)."""
    return (
        "Content-Security-Policy"
        if settings.CSP_ENFORCE
        else "Content-Security-Policy-Report-Only"
    )


def _requete_https(scope) -> bool:
    if scope.get("scheme") == "https":
        return True
    proto = Headers(scope=scope).get("x-forwarded-proto", "")
    return proto.split(",")[0].strip().lower() == "https"


def durcir_cookie(valeur: str, *, https: bool) -> str:
    """Ajoute HttpOnly / SameSite=Lax / Secure (si HTTPS) quand ils manquent."""
    attributs = {a.strip().split("=", 1)[0].lower() for a in valeur.split(";")[1:]}
    if "httponly" not in attributs:
        valeur += "; HttpOnly"
    if "samesite" not in attributs:
        valeur += "; SameSite=Lax"
    if https and "secure" not in attributs:
        valeur += "; Secure"
    return valeur


class SecurityHeadersMiddleware:
    """Pose les en-têtes de sécurité sur toutes les réponses, sauf proxys R2."""

    def __init__(self, asgi_app, skip_prefixes: tuple[str, ...] = SEC_SKIP_PREFIXES):
        self.asgi_app = asgi_app
        self.skip_prefixes = tuple(skip_prefixes)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or any(
            scope.get("path", "").startswith(p) for p in self.skip_prefixes
        ):
            await self.asgi_app(scope, receive, send)
            return

        https = _requete_https(scope)
        entete_csp = nom_entete_csp()

        async def _send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "SAMEORIGIN")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault(
                    "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
                )
                headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
                headers.setdefault(entete_csp, POLITIQUE_CSP)
                cookies = headers.getlist("set-cookie")
                if cookies:
                    del headers["set-cookie"]
                    for c in cookies:
                        headers.append("set-cookie", durcir_cookie(c, https=https))
            await send(message)

        await self.asgi_app(scope, receive, _send)


# ── Plafond des requêtes d'envoi (multipart) ───────────────────────────────

_REPONSE_413 = json.dumps(
    {"detail": "Envoi trop lourd. Envoie tes fichiers en plusieurs fois."},
    ensure_ascii=False,
).encode("utf-8")


async def _envoyer_413(send) -> None:
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(_REPONSE_413)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": _REPONSE_413})


class LimiteTailleEnvoiMiddleware:
    """Refuse (413) une requête multipart plus lourde que UPLOAD_MAX_REQUEST_MB.

    • Content-Length annoncé trop grand → 413 immédiat, rien n'est lu.
    • Corps envoyé « en morceaux » sans Content-Length → on compte les octets
      reçus ; au-delà du plafond on coupe la lecture (fin de corps simulée) et
      la réponse de l'application est REMPLACÉE par le 413.
    Les requêtes non multipart (JSON, pages) ne sont pas concernées.
    """

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            await self.asgi_app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if not headers.get("content-type", "").lower().startswith("multipart/"):
            await self.asgi_app(scope, receive, send)
            return

        plafond = int(settings.UPLOAD_MAX_REQUEST_MB) * 1024 * 1024
        annonce = headers.get("content-length", "")
        if annonce.isdigit() and int(annonce) > plafond:
            await _envoyer_413(send)
            return

        recu = 0
        depasse = False

        async def _receive():
            nonlocal recu, depasse
            if depasse:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                recu += len(message.get("body", b""))
                if recu > plafond:
                    depasse = True
                    return {"type": "http.disconnect"}
            return message

        reponse_remplacee = False

        async def _send(message):
            nonlocal reponse_remplacee
            if depasse:
                if not reponse_remplacee:
                    reponse_remplacee = True
                    await _envoyer_413(send)
                return
            await send(message)

        try:
            await self.asgi_app(scope, _receive, _send)
        except Exception:
            if depasse and not reponse_remplacee:
                await _envoyer_413(send)
                return
            raise


# ── Réception des rapports de violation CSP ────────────────────────────────

router = APIRouter(tags=["securite"])

_MAX_RAPPORT = 16 * 1024
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _adresse_sans_secret(valeur) -> str:
    """Adresse réduite à schéma + hôte + chemin (pas de ?jeton=… ni #…)."""
    if not isinstance(valeur, str) or not valeur:
        return "-"
    v = _CTRL.sub("", valeur)[:500]
    try:
        p = urlsplit(v)
    except ValueError:
        return "-"
    if p.scheme in ("http", "https"):
        return f"{p.scheme}://{p.netloc}{p.path}"[:200]
    # 'inline', 'eval', 'self', 'data', 'blob'… : mots-clés, pas des adresses.
    return (p.scheme or v.split(":", 1)[0])[:40]


def _champ(valeur) -> str:
    if not isinstance(valeur, str):
        return "-"
    return _CTRL.sub("", valeur)[:80] or "-"


@router.post(CSP_REPORT_PATH, status_code=204, include_in_schema=False)
@limiter.limit(LIMIT_CSP_REPORT)
async def recevoir_rapport_csp(request: Request) -> Response:
    """Reçoit un rapport de violation CSP envoyé par le navigateur et l'écrit
    dans les logs (une ligne « [csp] violation … »). Toujours 204."""
    corps = b""
    async for morceau in request.stream():
        corps += morceau
        if len(corps) > _MAX_RAPPORT:
            return Response(status_code=204)
    try:
        donnees = json.loads(corps or b"{}")
    except ValueError:
        return Response(status_code=204)
    rapport = donnees.get("csp-report") if isinstance(donnees, dict) else None
    if not isinstance(rapport, dict):
        return Response(status_code=204)
    logger.warning(
        "[csp] violation (%s) directive=%s ressource=%s page=%s",
        "bloquée" if settings.CSP_ENFORCE else "signalée",
        _champ(rapport.get("effective-directive") or rapport.get("violated-directive")),
        _adresse_sans_secret(rapport.get("blocked-uri")),
        _adresse_sans_secret(rapport.get("document-uri")),
    )
    return Response(status_code=204)
