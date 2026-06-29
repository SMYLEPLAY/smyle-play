"""
Négociation de contenu sur GET /images (fix 2026-06-25).

Le chemin /images sert à la fois l'API JSON (listing public) et l'URL de la
page vitrine. Une navigation navigateur (Accept: text/html) doit recevoir la
PAGE HTML ; un appel data (Accept: application/json) doit recevoir le JSON.
Avant le fix, l'API JSON masquait la page → un lien direct /images affichait
du JSON brut.
"""
import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_images_html_navigation_returns_page(client):
    """Accept: text/html → page HTML (le shell marketplace), pas du JSON."""
    r = await client.get("/images", headers={"Accept": "text/html"})
    assert r.status_code == 200, r.text[:200]
    assert "text/html" in r.headers.get("content-type", "").lower()
    # Marqueur de la page marketplace (index.html).
    assert "mp-hero-title" in r.text or "<html" in r.text.lower()


async def test_images_json_request_returns_listing(client):
    """Accept: application/json → listing JSON {images:[...]}."""
    r = await client.get("/images", headers={"Accept": "application/json"})
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert "images" in body and isinstance(body["images"], list)
