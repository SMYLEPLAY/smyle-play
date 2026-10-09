"""
Lot E — application installable (PWA) + correctifs mobiles (2026-10-09).

  • /manifest.webmanifest, /sw.js, /apple-touch-icon.png : statut, type,
    en-têtes ;
  • injection du bloc PWA dans les pages HTML (routes de pages, aperçus
    sociaux, pages servies par leur nom de fichier) ;
  • service worker : ne met JAMAIS en cache l'API, l'authentification,
    l'audio ni les pages (tests de contenu) ; arrêt à distance PWA_ACTIVE.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest
from PIL import Image

from app.config import settings

pytestmark = pytest.mark.asyncio(loop_scope="session")

RACINE = Path(__file__).resolve().parents[2]
SW = (RACINE / "ui" / "pwa" / "sw.js").read_text(encoding="utf-8")


# ── Fichiers à la racine ──────────────────────────────────────────────────

async def test_manifeste(client):
    r = await client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    m = json.loads(r.text)
    assert m["name"] == "WATT" and m["short_name"] == "WATT"
    assert m["display"] == "standalone"
    assert m["start_url"] == "/?source=pwa"
    assert m["scope"] == "/"
    assert re.fullmatch(r"#[0-9a-f]{6}", m["theme_color"])
    assert re.fullmatch(r"#[0-9a-f]{6}", m["background_color"])
    tailles = {(i["sizes"], i.get("purpose", "any")) for i in m["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= tailles
    for icone in m["icons"]:
        ri = await client.get(icone["src"])
        assert ri.status_code == 200, icone["src"]
        assert ri.headers["content-type"] == "image/png"
        w, h = Image.open(io.BytesIO(ri.content)).size
        assert f"{w}x{h}" == icone["sizes"]


async def test_apple_touch_icon_et_favicon(client):
    for chemin in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
        r = await client.get(chemin)
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        img = Image.open(io.BytesIO(r.content))
        assert img.size == (180, 180)
        assert img.mode == "RGB"  # iOS : pas de transparence
    r = await client.get("/favicon.ico")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


async def test_service_worker_route(client, monkeypatch):
    monkeypatch.delenv("PWA_ACTIVE", raising=False)
    r = await client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    cc = r.headers["cache-control"]
    assert "no-cache" in cc and "no-store" in cc
    assert r.headers["service-worker-allowed"] == "/"
    assert "__WATT_SW_" not in r.text
    assert "const ACTIF = true;" in r.text
    assert re.search(r"const VERSION = '[0-9a-f]{12}';", r.text)


async def test_service_worker_arret_a_distance(client, monkeypatch):
    monkeypatch.setenv("PWA_ACTIVE", "false")
    r = await client.get("/sw.js")
    assert "const ACTIF = false;" in r.text
    # L'interrupteur d'arrêt : désinscription + caches vidés.
    assert "registration.unregister()" in r.text
    assert "caches.delete" in r.text
    page = await client.get("/dashboard")
    assert 'data-sw="off"' in page.text


async def test_fichiers_pwa_dans_la_liste_blanche(client):
    for chemin in ("/ui/pwa/pwa.js", "/ui/pwa/mobile.css", "/ui/pwa/hors-ligne.html",
                   "/ui/pwa/hors-ligne.css", "/ui/pwa/icones/icone-192.png"):
        r = await client.get(chemin)
        assert r.status_code == 200, chemin
    # Le modèle brut du worker n'est pas servi (seulement via /sw.js).
    assert (await client.get("/ui/pwa/sw.js")).status_code == 404
    # La page hors ligne ne reçoit pas le bloc PWA.
    r = await client.get("/ui/pwa/hors-ligne.html")
    assert 'rel="manifest"' not in r.text
    assert "Pas de connexion" in r.text


# ── Injection dans les pages HTML ─────────────────────────────────────────

def _verifier_bloc(html: str) -> None:
    low = html.lower()
    assert low.count('rel="manifest"') == 1
    assert '<link rel="manifest" href="/manifest.webmanifest" />' in html
    assert 'rel="apple-touch-icon"' in low
    assert 'name="apple-mobile-web-app-capable"' in low
    assert 'name="apple-mobile-web-app-status-bar-style"' in low
    assert low.count('name="theme-color"') == 1
    assert re.search(r'<link rel="stylesheet" href="/ui/pwa/mobile\.css\?v=[0-9a-f]{10}" />', html)
    assert re.search(r'<script src="/ui/pwa/pwa\.js\?v=[0-9a-f]{10}" data-sw="on" defer></script>', html)
    # Injecté dans <head>, avant </head>.
    tete = low[: low.index("</head>")]
    assert "/ui/pwa/pwa.js" in tete and 'rel="manifest"' in tete
    # Aucun script inline ajouté (compatibilité CSP).
    bloc = html[html.index("<!-- WATT : application installable"):html.lower().index("</head>")]
    assert re.findall(r"<script(?![^>]*\bsrc=)", bloc) == []


async def test_injection_dans_les_pages(client, monkeypatch):
    monkeypatch.delenv("PWA_ACTIVE", raising=False)
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    for chemin in ("/", "/dashboard", "/library", "/legal", "/reset", "/verifier-email",
                   "/comment-ca-marche", "/gestion", "/u/inconnu-pwa", "/o/inconnue",
                   "/sons", "/legal.html", "/analytics.html"):
        r = await client.get(chemin)
        assert r.status_code == 200, chemin
        assert r.headers["content-type"].startswith("text/html"), chemin
        _verifier_bloc(r.text)


async def test_pas_de_doublon_des_balises_existantes(client):
    # index.html déclare déjà theme-color et la barre d'état iOS : conservées.
    r = await client.get("/")
    assert r.text.lower().count('name="apple-mobile-web-app-status-bar-style"') == 1
    assert 'content="black-translucent"' in r.text


async def test_page_etag_304(client):
    r = await client.get("/dashboard")
    etag = r.headers["etag"]
    r2 = await client.get("/dashboard", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.content == b""


async def test_csp_inchangee(client):
    r = await client.get("/")
    csp = r.headers.get("content-security-policy-report-only") or r.headers.get(
        "content-security-policy"
    )
    assert "script-src 'self'" in csp
    assert "default-src 'self'" in csp  # manifeste et worker : même origine


# ── Service worker : ce qui n'est JAMAIS mis en cache ─────────────────────

def _regex_statique() -> re.Pattern:
    m = re.search(r"const STATIQUE = /(.+)/;", SW)
    assert m, "regex STATIQUE introuvable dans sw.js"
    return re.compile(m.group(1).replace("\\/", "/"))


def test_sw_ne_cache_que_les_statiques():
    statique = _regex_statique()
    for chemin in ("/style.css", "/dashboard.js", "/ui/core/api.js",
                   "/ui/pwa/icones/icone-192.png", "/ui/modals/auth.js"):
        assert statique.match(chemin), chemin
    for chemin in ("/watt/stream/tracks/a.mp3", "/watt/images/images/previews/a.jpg",
                   "/images/previews/a.jpg", "/auth/login", "/auth/register",
                   "/users/me", "/me/library/prompts", "/watt/tracks-catalog",
                   "/dashboard", "/", "/u/luna", "/o/123", "/admin/x.js/y",
                   "/watt/x.js", "/images/1/download"):
        assert not statique.match(chemin), chemin


def test_sw_regles_de_securite():
    # Requêtes authentifiées, partielles (audio) et non-GET : jamais touchées.
    assert "req.headers.has('Authorization')" in SW
    assert "req.headers.has('Range')" in SW
    assert "req.method !== 'GET'" in SW
    # Drapeaux de lancement dynamiques et worker exclus explicitement.
    assert "'/ui/core/launch-flags.js'" in SW and "'/sw.js'" in SW
    # Seulement les adresses versionnées (?v=) ou les icônes de l'app.
    assert "url.searchParams.has('v')" in SW
    # Réponses privées jamais stockées.
    assert "no-store" in SW and "private" in SW
    # Un seul endroit écrit dans le cache des statiques, derrière le filtre.
    assert SW.count("cache.put(") == 1
    i_put = SW.index("cache.put(")
    i_filtre = SW.index("if (!estStatiqueVersionne(url)) return;")
    assert i_filtre < i_put
    # Pages : réseau d'abord, jamais mises en cache (pas de put dans la
    # branche « navigate »).
    nav = SW[SW.index("if (req.mode === 'navigate')"):i_filtre]
    assert "fetch(req)" in nav and ".put(" not in nav
    # Désactivable à distance, mise à jour immédiate maîtrisée.
    assert "self.skipWaiting()" in SW and "self.clients.claim()" in SW
    assert "if (!ACTIF) return;" in SW


def test_mobile_css_et_pwa_js_sans_dependance():
    css = (RACINE / "ui" / "pwa" / "mobile.css").read_text(encoding="utf-8")
    js = (RACINE / "ui" / "pwa" / "pwa.js").read_text(encoding="utf-8")
    assert "@import" not in css and "http" not in css.replace("https://", "")
    assert "beforeinstallprompt" in js
    assert "display-mode: standalone" in js
    assert "Sur l’écran d’accueil" in js
    assert "14 * 24 * 60 * 60 * 1000" in js
    # localStorage toujours protégé (navigation privée, stockage bloqué).
    for m in re.finditer(r"localStorage\.(getItem|setItem)", js):
        avant = js[max(0, m.start() - 120):m.start()]
        assert "try" in avant, m.group(0)
