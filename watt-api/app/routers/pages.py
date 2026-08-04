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
  /offres                    gate « paliers » : 302 → / si masqué
  /u/{slug} /@{slug}         artiste.html (profil) ; /artiste/{slug} 301 → /u/
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

import html as _html
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from app.config import settings
from app.database import SessionLocal
from app.models.album import Album
from app.models.playlist import Playlist
from app.models.prompt import Prompt
from app.models.user import User

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
        body = text[:idx] + block + text[idx:]
        return HTMLResponse(
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
        # Import tardif : evite un cycle avec le routeur watt_compat.
        from app.routers.watt_compat import _derive_artist_slug

        async with SessionLocal() as db:
            users = (await db.execute(select(User))).scalars().all()
        matches = [
            u
            for u in users
            if _derive_artist_slug(u) == slug and bool(u.profile_public)
        ]
        if not matches:
            return None
        # Meme resolution deterministe que GET /watt/artists/{slug} :
        # compte officiel d'abord, puis le plus ancien (incident homonymes).
        matches.sort(key=lambda u: (not bool(u.is_official), u.created_at))
        user = matches[0]
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
            ) or f"\u0152uvre \u00ab {title} \u00bb sur {_BRAND}."
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
                "url": f"{_base_url(request)}/oeuvre/{slug}",
                "image": image or _DEFAULT_OG_IMAGE,
                "page_type": "article",
            }
    except Exception:  # noqa: BLE001
        return None


# ── Pages ──────────────────────────────────────────────────────────────────

def _page(filename: str) -> FileResponse:
    return FileResponse(REPO_ROOT / filename, media_type="text/html")


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
    return _page("tarifs.html")


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


@router.get("/oeuvre/{slug}", include_in_schema=False)
async def oeuvre_page(slug: str, request: Request):
    # ROUTE MANQUANTE (regression P0-b) : oeuvre.js sert /oeuvre/<slug> et
    # appelle GET /watt/oeuvre/<slug>, mais aucune route de page ne servait
    # oeuvre.html → 404 sur la page meme d'une oeuvre. Retablie ici, avec
    # son apercu social (c'est LA page qu'un createur partage).
    meta = await _oeuvre_meta(slug, request)
    if meta is None:
        return _page("oeuvre.html")
    return _page_social("oeuvre.html", **meta)


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


@router.get("/sons", include_in_schema=False)
async def sons_page():
    return _page("index.html")


@router.get("/beats", include_in_schema=False)
async def beats_page():
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


# ── Statiques (mount "/" en dernier) ───────────────────────────────────────

# Liste blanche : uniquement des assets front. Tout le reste (sources .py,
# configs, dumps, dotfiles…) répond 404 au lieu d'être téléchargeable.
_ALLOWED_STATIC_SUFFIXES = {
    ".html", ".css", ".js", ".mjs", ".map", ".json",
    ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".wav", ".ogg", ".m4a", ".webm", ".mp4",
    ".webmanifest", ".xml",
}


class _AllowlistStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        p = Path(path)
        hidden = any(part.startswith(".") for part in p.parts)
        allowed = p.suffix.lower() in _ALLOWED_STATIC_SUFFIXES
        if hidden or not allowed:
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)


def mount_static(app) -> None:
    """Pose le mount statique — à appeler en DERNIER dans create_app pour
    que toutes les routes (API + pages ci-dessus) gardent la précédence."""
    app.mount(
        "/",
        _AllowlistStaticFiles(directory=str(REPO_ROOT), html=True),
        name="static",
    )
