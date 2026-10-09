"""Pages & statiques servis par FastAPI — P0-b « Sortie Flask » (2026-07-30).

Réplique le comportement de flask_app.py (routes de pages + launch-flags +
statiques racine), derrière le drapeau SERVE_STATIC_FROM_FASTAPI :
  • False (défaut) → ce module n'est PAS monté, rien ne change (Flask sert).
  • True → FastAPI sert pages + statiques ; le mount Flask (main.py racine)
    n'est plus posé → plus aucun trafic n'atteint Flask. Réversible par env.

Parité route par route (source : OBSIDIAN/05_TECH/Flask_routes_inventory.md) :
  /ui/core/launch-flags.js   JS dynamique no-cache — source de vérité du
                             MODE_LANCEMENT, prioritaire sur le fichier disque
  /                          index.html
  /watt                      301 → / (legacy)
  /dashboard /tarifs /library /legal /reset → page HTML dédiée
  /verifier-email            page HTML de vérification d'email (Phase A) —
                             cible du lien envoyé par email, miroir de /reset
  /comment-ca-marche         comment-ca-marche.html (lien de l'onboarding)
  /offres                    gate « paliers » : 302 → / si masqué
  /u/{slug} /@{slug}         artiste.html (profil) ; /artiste/{slug} 301 → /u/
  /collection/{slug}         oeuvre.html (Collection = playlist + album, C3),
                             aperçu social ; cachée avec les albums (Lot 2)
  /oeuvre/{slug}             301 → /collection/{slug} (ancienne adresse C3)
  /o/{id}                    o.html — Œuvre 1 son + 1 image (C4), aperçu social
  /sons /beats /artistes     shell index.html (vue pilotée par marketplace.js)
  /voix                      gate « voix » : 302 → / si masqué, sinon shell

  NB /images : PAS de route page ici. GET /images est l'API JSON (images.py)
  et les routes FastAPI ont TOUJOURS eu précédence sur le mount Flask — la
  route page Flask /images était donc déjà éclipsée en prod. Parité conservée.

Statiques : mount "/" posé en DERNIER (toutes les routes API gardent la
précédence), racine du repo comme Flask (static_url_path='') MAIS avec liste
blanche d'extensions : Flask exposait n'importe quel fichier du repo en HTTP
(flask_app.py, models.py… téléchargeables) — on ferme ce trou au passage.
"""

import hashlib
import html as _html
import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from app.config import settings
from app.database import SessionLocal
from app.models.album import Album
from app.models.playlist import Playlist
from app.models.prompt import Prompt

# pages.py → routers → app → watt-api → RACINE DU REPO (même convention
# que images.py : parents[3]).
REPO_ROOT = Path(__file__).resolve().parents[3]

router = APIRouter(tags=["pages"])

# ── launch-flags.js — JS dynamique généré depuis l'environnement ──────────

def launch_flags_js_body() -> str:
    """Corps JS posant window.WATT_LAUNCH — identique à Flask launch_flags_js
    (flask_app.py) : mêmes clés, même sérialisation JSON."""
    return "window.WATT_LAUNCH = " + json.dumps(settings.launch_flags_dict()) + ";\n"


@router.get("/ui/core/launch-flags.js")
async def launch_flags_js() -> Response:
    # no-cache strict : les drapeaux doivent changer sans purge navigateur.
    # Route explicite = prioritaire sur le fichier ui/core/launch-flags.js du
    # disque (le mount statique est posé APRÈS ce router).
    return Response(
        content=launch_flags_js_body(),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ── Aperçu social (Open Graph / Twitter Card) — F1-1, 2026-08-02 ──────────
#
# Le modèle d'acquisition est creator-led : un créateur partage son lien
# /u/<slug> (ou /oeuvre/<slug>) sur ses réseaux. Sans balises og:, le lien
# s'affiche NU (ni vignette ni titre) et ne convertit pas. Les pages étant
# du HTML statique hydraté en JS, les balises doivent être injectées ICI,
# côté serveur, avec les données de l'entité concernée.
#
# Principe de sûreté : l'enrichissement ne doit JAMAIS casser une page.
# Toute erreur de lecture / DB retombe silencieusement sur la page brute.

_BRAND = "WATT"
# Wording neutre et factuel (règle « copywriting honnête ») — à affiner par Tom.
_BRAND_DESC = "WATT — plateforme de creations audiovisuelles generatives."
# Image de marque par defaut : aucune pour l'instant (il faut un asset
# 1200x630). Sans image, on degrade proprement en twitter:card=summary.
_DEFAULT_OG_IMAGE: str | None = None

_HEAD_CLOSE = "</head>"


@lru_cache(maxsize=32)
def _read_page_cached(path: str, mtime_ns: int) -> str:
    """Lit une page HTML. La cle inclut le mtime : une edition invalide le cache."""
    return Path(path).read_text(encoding="utf-8")


def _base_url(request: Request) -> str:
    """Origine publique, en tenant compte du proxy Railway."""
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https")
    proto = proto.split(",")[0].strip()
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{proto}://{host}"


def _absolute(request: Request, url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip()
    if not u:
        return None
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return _base_url(request) + ("" if u.startswith("/") else "/") + u


def _clip(text: str | None, limit: int = 158) -> str:
    t = " ".join((text or "").split())
    if not t:
        return ""
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "\u2026"


def _tag(key: str, value: str | None, *, name: bool = False) -> str:
    if not value:
        return ""
    attr = "name" if name else "property"
    return f'<meta {attr}="{key}" content="{_html.escape(value, quote=True)}" />'


def _social_head(
    *,
    title: str,
    description: str,
    url: str,
    image: str | None = None,
    page_type: str = "website",
) -> str:
    parts = [
        _tag("description", description, name=True),
        _tag("og:type", page_type),
        _tag("og:site_name", _BRAND),
        _tag("og:title", title),
        _tag("og:description", description),
        _tag("og:url", url),
        _tag("og:image", image),
        _tag(
            "twitter:card",
            "summary_large_image" if image else "summary",
            name=True,
        ),
        _tag("twitter:title", title, name=True),
        _tag("twitter:description", description, name=True),
        _tag("twitter:image", image, name=True),
    ]
    return "\n".join(p for p in parts if p) + "\n"


def _page_social(filename: str, **meta) -> Response:
    """Sert une page HTML avec ses balises d'apercu social injectees dans <head>."""
    try:
        path = REPO_ROOT / filename
        text = _read_page_cached(str(path), path.stat().st_mtime_ns)
        block = _social_head(**meta)
        low = text.lower()
        idx = low.find(_HEAD_CLOSE)
        if idx == -1:
            return _page(filename)
        body = injecter_pwa(text[:idx] + block + text[idx:])
        return _PageHTML(
            content=body,
            headers={"Cache-Control": "public, max-age=60"},
        )
    except Exception:  # noqa: BLE001 - jamais casser une page pour des meta
        return _page(filename)


async def _artist_meta(slug: str, request: Request) -> dict | None:
    """Metadonnees sociales d'un profil PUBLIC. None si introuvable/prive.

    La session est ouverte ICI (pas via Depends) : une base indisponible doit
    degrader vers la page brute, jamais renvoyer 500 sur une page publique.
    """
    try:
        # Import tardif : evite un cycle (follows → watt_compat → …).
        from app.routers.follows import _find_artist_by_slug

        async with SessionLocal() as db:
            # Resolution CANONIQUE, partagee avec /watt/users/{slug}/playlists,
            # /albums, /images (follows._find_artist_by_slug) : scan borne aux
            # artistes potentiels (artist_name renseigne OU email univers) au
            # lieu de TOUTE la table users, homonymes departages officiel >
            # plus ancien, et gate profile_public — sans viewer, un profil
            # prive ou introuvable leve 404, rattrape ci-dessous → page brute.
            user = await _find_artist_by_slug(db, slug)
        name = (user.artist_name or slug).strip() or slug
        desc = _clip(user.bio) or f"Profil de {name} sur {_BRAND}."
        image = _absolute(request, user.avatar_url or user.cover_photo_url)
        return {
            "title": f"{name} \u2014 {_BRAND}",
            "description": desc,
            "url": f"{_base_url(request)}/u/{slug}",
            "image": image or _DEFAULT_OG_IMAGE,
            "page_type": "profile",
        }
    except Exception:  # noqa: BLE001
        return None


async def _oeuvre_meta(slug: str, request: Request) -> dict | None:
    """Metadonnees sociales d'une oeuvre PUBLIQUE (album + playlist jumeaux)."""
    try:
        async with SessionLocal() as db:
            album = (
                await db.execute(
                    select(Album).where(
                        Album.oeuvre_slug == slug, Album.visibility == "public"
                    )
                )
            ).scalars().first()
            playlist = (
                await db.execute(
                    select(Playlist).where(
                        Playlist.oeuvre_slug == slug, Playlist.visibility == "public"
                    )
                )
            ).scalars().first()
            if album is None and playlist is None:
                return None
            title = (
                getattr(album, "title", None)
                or getattr(playlist, "title", None)
                or slug
            ).strip()
            desc = _clip(
                getattr(album, "dna_description", None)
                or getattr(playlist, "dna_description", None)
            ) or f"Collection \u00ab {title} \u00bb sur {_BRAND}."
            image = None
            cover_prompt_id = getattr(album, "cover_prompt_id", None)
            if cover_prompt_id is not None:
                prompt = (
                    await db.execute(
                        select(Prompt).where(Prompt.id == cover_prompt_id)
                    )
                ).scalars().first()
                key = getattr(prompt, "preview_r2_key", None) if prompt else None
                base = settings.effective_r2_public_base_url
                if key and base:
                    image = f"{base.rstrip('/')}/{str(key).lstrip('/')}"
            return {
                "title": f"{title} \u2014 {_BRAND}",
                "description": desc,
                "url": f"{_base_url(request)}/collection/{slug}",
                "image": image or _DEFAULT_OG_IMAGE,
                "page_type": "article",
            }
    except Exception:  # noqa: BLE001
        return None


def _preview_image_url(request: Request, key: str | None) -> str | None:
    """URL ABSOLUE de l'aperçu d'une image (jamais l'original) : R2 public si
    configuré, sinon le proxy same-origin /watt/images/{key}."""
    if not key:
        return None
    base = settings.effective_r2_public_base_url
    if base:
        return f"{base.rstrip('/')}/{str(key).lstrip('/')}"
    return _absolute(request, f"/watt/images/{str(key).lstrip('/')}")


async def _oeuvre_c4_meta(oeuvre_id: str, request: Request) -> dict | None:
    """Metadonnees sociales d'une ŒUVRE (1 son + 1 image, Lot 2). None si
    introuvable / non publique → page brute, aucune fuite."""
    try:
        import uuid as _uuid

        from app.services.links import public_oeuvre

        oid = _uuid.UUID(str(oeuvre_id))
        async with SessionLocal() as db:
            data = await public_oeuvre(db, oid)
        if data is None:
            return None
        title = (data.get("title") or "\u0152uvre").strip()
        name = (data["creator"].get("name") or "").strip()
        desc = (
            f"\u0152uvre de {name} sur {_BRAND} \u2014 un son et une image."
            if name else f"\u0152uvre sur {_BRAND} \u2014 un son et une image."
        )
        return {
            "title": f"{title} \u2014 {name}" if name else f"{title} \u2014 {_BRAND}",
            "description": desc,
            "url": f"{_base_url(request)}/o/{data['id']}",
            "image": _preview_image_url(request, data["image"].get("previewKey"))
            or _DEFAULT_OG_IMAGE,
            "page_type": "music.song",
        }
    except Exception:  # noqa: BLE001
        return None


# ── Application installable (PWA) + correctifs mobiles — Lot E ───────────
#
# Objectif : « Installer WATT » depuis Safari (iPhone) et Chrome (Android) —
# icône sur l'écran d'accueil, ouverture en plein écran.
#
# Les fichiers vivent dans ui/pwa/ (manifeste, service worker, script, icônes,
# correctifs mobiles). Plutôt que de modifier chaque page HTML, le serveur
# ajoute, au moment de servir une page, juste avant </head> :
#   <link rel="manifest">, les balises iOS (apple-mobile-web-app-*,
#   apple-touch-icon), theme-color, ui/pwa/mobile.css et ui/pwa/pwa.js.
# Les balises déjà présentes dans une page ne sont pas dupliquées. Aucun
# script inline : compatible avec la CSP (script-src 'self').
#
# Interrupteur PWA_ACTIVE (variable Railway, défaut true). À false :
#   • /sw.js devient un « interrupteur d'arrêt » (vide ses caches, se
#     désinscrit, recharge les onglets) ;
#   • pwa.js désinscrit tout worker installé au chargement de la page.
# C'est la garantie qu'un bug de cache ne bloque jamais les utilisateurs.

_PWA_DIR = REPO_ROOT / "ui" / "pwa"
_THEME_COLOR = "#050508"  # --sp-bg (ui/core/tokens.css), fond de l'accueil

# Fichiers servis À LA RACINE du site (hors du mount statique) :
# chemin public → (fichier dans ui/pwa/, type, Cache-Control).
PWA_ROOT_FILES: dict[str, tuple[str, str, str]] = {
    "/manifest.webmanifest": (
        "manifest.webmanifest", "application/manifest+json", "public, max-age=3600",
    ),
    "/apple-touch-icon.png": (
        "icones/apple-touch-icon.png", "image/png", "public, max-age=86400",
    ),
    # Safari demande aussi cette variante historique.
    "/apple-touch-icon-precomposed.png": (
        "icones/apple-touch-icon.png", "image/png", "public, max-age=86400",
    ),
    "/favicon.ico": ("icones/favicon-32.png", "image/png", "public, max-age=86400"),
}


def pwa_active() -> bool:
    """Interrupteur PWA_ACTIVE (lu à chaque requête, comme les drapeaux)."""
    return os.getenv("PWA_ACTIVE", "true").strip().lower() not in (
        "0", "false", "non", "no", "off",
    )


def _commit() -> str:
    return os.getenv("RAILWAY_GIT_COMMIT_SHA", "")[:12]


@lru_cache(maxsize=32)
def _empreinte(path: str, mtime_ns: int) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:10]


def _version(rel: str) -> str:
    """Empreinte du contenu d'un fichier de ui/pwa/ (« ?v= » des adresses)."""
    path = _PWA_DIR / rel
    try:
        return _empreinte(str(path), path.stat().st_mtime_ns)
    except OSError:
        return "0"


def _bloc_pwa(low: str, actif: bool) -> str:
    """Balises à injecter ; `low` = page en minuscules (anti-doublons)."""
    parts = ['<link rel="manifest" href="/manifest.webmanifest" />']
    if 'name="theme-color"' not in low:
        parts.append(f'<meta name="theme-color" content="{_THEME_COLOR}" />')
    if 'name="mobile-web-app-capable"' not in low:
        parts.append('<meta name="mobile-web-app-capable" content="yes" />')
    if 'name="apple-mobile-web-app-capable"' not in low:
        parts.append('<meta name="apple-mobile-web-app-capable" content="yes" />')
    if 'name="apple-mobile-web-app-status-bar-style"' not in low:
        parts.append('<meta name="apple-mobile-web-app-status-bar-style" content="black" />')
    if 'name="apple-mobile-web-app-title"' not in low:
        parts.append('<meta name="apple-mobile-web-app-title" content="WATT" />')
    if 'rel="apple-touch-icon"' not in low:
        parts.append('<link rel="apple-touch-icon" href="/apple-touch-icon.png" />')
    if 'rel="icon"' not in low:
        parts.append(
            '<link rel="icon" type="image/png" sizes="32x32" '
            f'href="/ui/pwa/icones/favicon-32.png?v={_version("icones/favicon-32.png")}" />'
        )
    parts.append(
        f'<link rel="stylesheet" href="/ui/pwa/mobile.css?v={_version("mobile.css")}" />'
    )
    parts.append(
        f'<script src="/ui/pwa/pwa.js?v={_version("pwa.js")}" '
        f'data-sw="{"on" if actif else "off"}" defer></script>'
    )
    return "<!-- WATT : application installable + correctifs mobiles -->\n" + "\n".join(parts) + "\n"


def injecter_pwa(html_text: str, actif: bool | None = None) -> str:
    """Ajoute le bloc PWA juste avant </head> (une seule fois)."""
    low = html_text.lower()
    if 'rel="manifest"' in low:
        return html_text
    idx = low.find(_HEAD_CLOSE)
    if idx == -1:
        return html_text
    if actif is None:
        actif = pwa_active()
    return html_text[:idx] + _bloc_pwa(low, actif) + html_text[idx:]


@lru_cache(maxsize=64)
def _page_injectee(path: str, mtime_ns: int, actif: bool, commit: str) -> str:
    # `commit` dans la clé : un déploiement recalcule les « ?v= ».
    return injecter_pwa(_read_page_cached(path, mtime_ns), actif)


class _PageHTML(HTMLResponse):
    """Page HTML avec ETag : un rechargement sans changement répond 304
    (FileResponse le faisait ; on garde ce gain sur mobile)."""

    def __init__(self, content: str, **kw):
        super().__init__(content=content, **kw)
        self.headers["ETag"] = '"' + hashlib.sha256(self.body).hexdigest()[:20] + '"'

    async def __call__(self, scope, receive, send):
        demande = Headers(scope=scope).get("if-none-match", "")
        etag = self.headers["ETag"]
        if demande and etag in [v.strip() for v in demande.split(",")]:
            entetes = [(k, v) for k, v in self.raw_headers
                       if k.lower() not in (b"content-length", b"content-type")]
            await send({"type": "http.response.start", "status": 304, "headers": entetes})
            await send({"type": "http.response.body", "body": b""})
            return
        await super().__call__(scope, receive, send)


@lru_cache(maxsize=8)
def _sw_corps(mtime_ns: int, actif: bool, commit: str) -> str:
    modele = (_PWA_DIR / "sw.js").read_text(encoding="utf-8")
    version = hashlib.sha256(
        (modele + commit + _version("mobile.css") + _version("pwa.js")).encode()
    ).hexdigest()[:12]
    return (
        modele.replace("__WATT_SW_VERSION__", version)
        .replace("__WATT_SW_ACTIF__", "true" if actif else "false")
    )


@router.api_route("/sw.js", methods=["GET", "HEAD"], include_in_schema=False)
async def service_worker() -> Response:
    # Jamais mis en cache par le navigateur : une nouvelle version (ou
    # l'interrupteur d'arrêt) doit être vue dès la visite suivante.
    path = _PWA_DIR / "sw.js"
    return Response(
        content=_sw_corps(path.stat().st_mtime_ns, pwa_active(), _commit()),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/",
        },
    )


def _pwa_root_route(public: str, rel: str, media_type: str, cache: str):
    async def _servir() -> FileResponse:
        return FileResponse(
            _PWA_DIR / rel, media_type=media_type, headers={"Cache-Control": cache}
        )

    router.add_api_route(public, _servir, methods=["GET", "HEAD"], include_in_schema=False)


for _public, (_rel, _type, _cache) in PWA_ROOT_FILES.items():
    _pwa_root_route(_public, _rel, _type, _cache)


# ── Pages ──────────────────────────────────────────────────────────────────

def _page(filename: str) -> Response:
    """Sert une page HTML du dépôt, avec le bloc « application installable »
    + correctifs mobiles injecté avant </head> (Lot E, voir plus bas)."""
    path = REPO_ROOT / filename
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        raise HTTPException(status_code=404)
    return _PageHTML(
        content=_page_injectee(str(path), mtime_ns, pwa_active(), _commit()),
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/", include_in_schema=False)
async def index_page(request: Request):
    return _page_social(
        "index.html",
        title=_BRAND,
        description=_BRAND_DESC,
        url=_base_url(request),
        image=_DEFAULT_OG_IMAGE,
    )


@router.get("/watt", include_in_schema=False)
async def watt_page_legacy():
    # Phase 3 refonte marketplace : /watt → marketplace unifiée sur /.
    return RedirectResponse("/", status_code=301)


@router.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    return _page("dashboard.html")


@router.get("/tarifs", include_in_schema=False)
async def tarifs_page():
    # F4-1 / K-08 (annexe B §5) — la page tarifs n'affiche que des packs
    # « — € » et des boutons « Bientot disponible » : des promesses vides,
    # atteignables par URL directe et liees depuis offres.html. Elle est
    # fermee (302 accueil) tant que l'item `euros` n'est pas VISIBLE.
    # Gate sur `euros` et non `paliers` : ce sont deux choses distinctes —
    # les paliers peuvent s'ouvrir (commission, mise en avant) sans qu'aucun
    # euro ne soit encaissable.
    if not settings.launch_flags_dict()["euros"]:
        return RedirectResponse("/", status_code=302)
    return _page("tarifs.html")


@router.get("/comment-ca-marche", include_in_schema=False)
async def comment_ca_marche_page():
    # K-03 (2026-09-04) — LIEN MORT : ui/core/onboarding.js:78 pointe vers
    # /comment-ca-marche, mais aucune route de page ne servait le fichier
    # (le mount statique ne resout que /comment-ca-marche.html) → 404 depuis
    # l'onboarding. Page publique non gatee, comme /tarifs et /legal.
    return _page("comment-ca-marche.html")


@router.get("/offres", include_in_schema=False)
async def offres_page():
    # MODE LANCEMENT — PALIERS masqués : page non servie tant que l'item
    # n'est pas VISIBLE (302 accueil), comme côté Flask.
    if not settings.launch_flags_dict()["paliers"]:
        return RedirectResponse("/", status_code=302)
    return _page("offres.html")


@router.get("/u/{slug}", include_in_schema=False)
async def user_page(slug: str, request: Request):
    # Profil membre unique (création / édition / vue publique).
    # F1-1 : apercu social injecte pour les profils PUBLICS (le lien partage
    # par le createur est le canal d'acquisition n°1). Profil prive ou
    # introuvable → page brute, aucune fuite de donnees.
    meta = await _artist_meta(slug, request)
    if meta is None:
        return _page("artiste.html")
    return _page_social("artiste.html", **meta)


@router.get("/@{slug}", include_in_schema=False)
async def user_page_at(slug: str, request: Request):
    # URL courte — même page profil, artiste.js extrait le slug des 2 formes.
    meta = await _artist_meta(slug, request)
    if meta is None:
        return _page("artiste.html")
    return _page_social("artiste.html", **meta)


@router.get("/collection/{slug}", include_in_schema=False)
async def collection_page(slug: str, request: Request):
    # Lot 2 (décision 23/09) : le regroupement playlist + album (C3) s'appelle
    # « Collection » ; « Œuvre » = uniquement 1 son + 1 image (/o/{id}).
    # Page servie par oeuvre.html (même fichier, libellés « Collection »),
    # avec son aperçu social. Cachée avec les albums (SHOW_ALBUMS).
    if not settings.launch_flags_dict()["albums"]:
        return RedirectResponse("/", status_code=302)
    meta = await _oeuvre_meta(slug, request)
    if meta is None:
        return _page("oeuvre.html")
    return _page_social("oeuvre.html", **meta)


@router.get("/oeuvre/{slug}", include_in_schema=False)
async def oeuvre_page_legacy(slug: str):
    # Ancienne adresse des collections (C3) : liens déjà partagés conservés.
    return RedirectResponse(f"/collection/{slug}", status_code=301)


@router.get("/o/{oeuvre_id}", include_in_schema=False)
async def oeuvre_c4_page(oeuvre_id: str, request: Request):
    # Lot 2 — page à partager d'une ŒUVRE (1 son + 1 image). C'est le lien
    # que le créateur poste : aperçu social (image + titre) injecté ici.
    meta = await _oeuvre_c4_meta(oeuvre_id, request)
    if meta is None:
        return _page("o.html")
    return _page_social("o.html", **meta)


@router.get("/gestion", include_in_schema=False)
async def gestion_page():
    # Étape 2 — page admin « Gestion » (Pionniers, contenus retirés, achats
    # par carte). Page vide sans compte admin : les données viennent des
    # routes /admin/… (réservées).
    return _page("gestion.html")


@router.get("/pret-a-sortir", include_in_schema=False)
async def pret_a_sortir_page():
    # Lot 2 — tableau admin « Prêt à sortir ». La page est publique mais vide :
    # ses données viennent de GET /admin/pret-a-sortir (réservé à l'admin).
    return _page("pret-a-sortir.html")


@router.get("/artiste/{slug}", include_in_schema=False)
async def artiste_page_legacy(slug: str):
    # Alias rétro-compat : anciens liens /artiste/<slug> → /u/<slug>.
    return RedirectResponse(f"/u/{slug}", status_code=301)


@router.get("/library", include_in_schema=False)
async def library_page():
    return _page("library.html")


@router.get("/legal", include_in_schema=False)
async def legal_page():
    return _page("legal.html")


@router.get("/reset", include_in_schema=False)
async def reset_page():
    return _page("reset.html")


@router.get("/verifier-email", include_in_schema=False)
async def verifier_email_page():
    # Phase A (2026-09-11) — page de vérification d'email, miroir de /reset.
    # C'est la cible du lien envoyé par email (services/email_verification.py::
    # build_verification_link → {base}/verifier-email#token=...) : le jeton
    # voyage en FRAGMENT, le front lit location.hash et POSTe /auth/verify-email.
    return _page("verifier-email.html")


@router.get("/sons", include_in_schema=False)
async def sons_page():
    return _page("index.html")


@router.get("/beats", include_in_schema=False)
async def beats_page():
    # Lot 1 — BEATS masqués : 302 accueil tant que non VISIBLE (même modèle
    # que /voix).
    if not settings.launch_flags_dict()["beats"]:
        return RedirectResponse("/", status_code=302)
    return _page("index.html")


@router.get("/voix", include_in_schema=False)
async def voix_page():
    # MODE LANCEMENT — VOIX masquée : 302 accueil tant que non VISIBLE.
    if not settings.launch_flags_dict()["voix"]:
        return RedirectResponse("/", status_code=302)
    return _page("index.html")


@router.get("/artistes", include_in_schema=False)
async def artistes_page():
    return _page("index.html")


# ── Parcours V1 — anciennes adresses directes des pages masquées ─────────
# /tarifs.html, /offres.html et /oeuvre.html ne s'ouvrent plus « à la main » :
# redirection vers l'accueil tant que la page est masquée (ou obsolète), vers
# son adresse officielle sinon. /oeuvre.html sans identifiant de collection
# n'affiche rien d'utile : toujours l'accueil.

@router.get("/tarifs.html", include_in_schema=False)
async def tarifs_html_legacy():
    cible = "/tarifs" if settings.launch_flags_dict()["euros"] else "/"
    return RedirectResponse(cible, status_code=302)


@router.get("/offres.html", include_in_schema=False)
async def offres_html_legacy():
    cible = "/offres" if settings.launch_flags_dict()["paliers"] else "/"
    return RedirectResponse(cible, status_code=302)


@router.get("/oeuvre.html", include_in_schema=False)
async def oeuvre_html_legacy():
    return RedirectResponse("/", status_code=302)


# ── Statiques (mount "/" en dernier) ───────────────────────────────────────

# Lot A (2026-10-07) — LISTE BLANCHE DE CHEMINS (et plus seulement
# d'extensions). Avant : toute la racine du dépôt était servie dès que
# l'extension était autorisée — y compris `.json` (données internes,
# scripts, tests e2e…). Désormais seuls sont publics :
#   - les pages et assets front À LA RACINE (un seul segment) : .html, .css,
#     .js — sauf les pages de démonstration et les pages masquées ;
#   - le dossier `ui/` (modules front) : .js, .css et images/polices.
# Tout le reste répond 404 : dossiers `data/`, `e2e/`, `scripts/`,
# `agents/`, `watt-api/`, `assets/`, fichiers `.json` (aucun n'est lu par le
# front : le catalogue passe par /watt/tracks-catalog), sources, dotfiles.
_ROOT_STATIC_SUFFIXES = {".html", ".css", ".js"}
_UI_STATIC_SUFFIXES = {
    ".js", ".mjs", ".css",
    ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
    ".woff", ".woff2", ".ttf", ".otf",
}
_PUBLIC_STATIC_DIRS = {"ui"}
# Pages HTML publiques HORS racine (Lot E) : la page « hors ligne » de
# l'application installable, précachée par /sw.js.
_PUBLIC_NESTED_FILES = {"ui/pwa/hors-ligne.html"}
# Modèle du service worker : servi uniquement par la route /sw.js (qui
# remplace ses marqueurs), jamais tel quel.
_DENIED_NESTED_FILES = {"ui/pwa/sw.js"}
# Pages jamais publiques (démo interne).
_DENIED_ROOT_FILES = {"banner-demo.html"}
# Pages derrière un interrupteur de lancement : l'accès direct au fichier
# suit la même règle que la route de page (/tarifs, /offres, /collection).
_GATED_ROOT_FILES = {
    "tarifs.html": "euros",
    "offres.html": "paliers",
    "oeuvre.html": "albums",
}


def static_path_allowed(path: str) -> bool:
    """Le chemin (relatif à la racine du dépôt) est-il public ?"""
    p = Path(path)
    parts = p.parts
    if not parts or any(part.startswith(".") or part == ".." for part in parts):
        return False
    if p.as_posix() in _PUBLIC_NESTED_FILES:
        return True
    if p.as_posix() in _DENIED_NESTED_FILES:
        return False
    suffix = p.suffix.lower()
    if len(parts) == 1:
        name = parts[0]
        if name in _DENIED_ROOT_FILES or suffix not in _ROOT_STATIC_SUFFIXES:
            return False
        flag = _GATED_ROOT_FILES.get(name)
        if flag is not None and not settings.launch_flags_dict()[flag]:
            return False
        return True
    return parts[0] in _PUBLIC_STATIC_DIRS and suffix in _UI_STATIC_SUFFIXES


class _AllowlistStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        if not static_path_allowed(path):
            raise HTTPException(status_code=404)
        # Lot E : une page .html servie par son nom de fichier reçoit aussi
        # le bloc « application installable » (mêmes règles que _page).
        if (
            path.lower().endswith(".html")
            and len(Path(path).parts) == 1  # pages racine (pas la page hors ligne)
            and scope.get("method") in ("GET", "HEAD")
            and (REPO_ROOT / path).is_file()
        ):
            return _page(path)
        return await super().get_response(path, scope)


def mount_static(app) -> None:
    """Pose le mount statique — à appeler en DERNIER dans create_app pour
    que toutes les routes (API + pages ci-dessus) gardent la précédence."""
    app.mount(
        "/",
        _AllowlistStaticFiles(directory=str(REPO_ROOT), html=True),
        name="static",
    )
