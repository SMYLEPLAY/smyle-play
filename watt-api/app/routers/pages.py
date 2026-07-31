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

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse, Response
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from app.config import settings

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


# ── Pages ──────────────────────────────────────────────────────────────────

def _page(filename: str) -> FileResponse:
    return FileResponse(REPO_ROOT / filename, media_type="text/html")


@router.get("/", include_in_schema=False)
async def index_page():
    return _page("index.html")


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
async def user_page(slug: str):
    # Profil membre unique (création / édition / vue publique).
    return _page("artiste.html")


@router.get("/@{slug}", include_in_schema=False)
async def user_page_at(slug: str):
    # URL courte — même page profil, artiste.js extrait le slug des 2 formes.
    return _page("artiste.html")


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
