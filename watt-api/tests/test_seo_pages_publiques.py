"""SEO des pages publiques (2026-11-25) — audit Movento, chantier 2.

Les pages partagées (/u/<slug>, /@<slug>, /o/<id>, /collection/<slug>)
avaient déjà leur aperçu social (F1-1). Il leur manquait ce que Google lit :
  - un <title> propre à l'entité (au lieu de « Artiste · WATT ») ;
  - un lien canonique (/@slug et /u/slug = une seule page) ;
  - des données structurées schema.org (JSON-LD) ;
  - un texte lisible sans JavaScript ;
  - un noindex sur les pages d'entités privées / introuvables (soft 404) ;
  - un robots.txt qui laisse Google charger les données publiques (/watt/) ;
  - un plan du site sans pages vides ni adresses en double.
"""

import json
import re
import uuid

from httpx import AsyncClient
from sqlalchemy import update

from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.routers.pages import _jsonld, _seo_page, _social_head


# ── Helpers purs ───────────────────────────────────────────────────────────

def test_social_head_pose_le_lien_canonique():
    head = _social_head(title="T", description="D", url="https://watt.test/u/x")
    assert '<link rel="canonical" href="https://watt.test/u/x" />' in head


def test_jsonld_ne_peut_pas_fermer_la_balise_script():
    out = _jsonld({"name": "</script><script>alert(1)</script>"})
    assert out.startswith('<script type="application/ld+json">')
    assert out.count("</script>") == 1          # seule la vraie fermeture
    corps = out[len('<script type="application/ld+json">'):-len("</script>")]
    assert json.loads(corps)["name"] == "</script><script>alert(1)</script>"
    assert _jsonld(None) == ""


def test_seo_page_titre_robots_et_texte_sans_js():
    gabarit = (
        "<html><head><title>Collection · WATT</title>\n"
        '<meta name="robots" content="noindex, nofollow" />\n</head>'
        '<body class="x"><main></main></body></html>'
    )
    out = _seo_page(gabarit, "Night City <3 — WATT", "Une description.")
    assert "<title>Night City &lt;3 — WATT</title>" in out
    assert "noindex" not in out
    assert '<body class="x">\n<noscript><h1>Night City &lt;3 — WATT</h1>' in out
    assert "<p>Une description.</p></noscript>" in out


# ── Bout de chaîne (base réelle) ───────────────────────────────────────────

async def _set_profile(user_id, **values) -> None:
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == user_id).values(**values))
        await db.commit()


def _jsonld_de(html: str) -> dict:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert m, "JSON-LD absent"
    return json.loads(m.group(1))


async def test_profil_public_titre_canonique_et_jsonld(
    client: AsyncClient, test_user: dict
) -> None:
    name = f"seotest{uuid.uuid4().hex[:10]}"
    await _set_profile(
        test_user["id"], artist_name=name, bio="Bio SEO.", profile_public=True
    )
    try:
        for chemin in (f"/u/{name}", f"/@{name}"):
            html = (await client.get(chemin)).text
            assert f"<title>{name} — WATT</title>" in html, chemin
            # /@slug renvoie à l'adresse de référence /u/slug.
            assert f'<link rel="canonical" href="http://test/u/{name}" />' in html, chemin
            assert 'name="robots"' not in html, chemin
            assert f"<noscript><h1>{name} — WATT</h1><p>Bio SEO.</p></noscript>" in html
            data = _jsonld_de(html)
            assert data["@type"] == "ProfilePage"
            assert data["mainEntity"]["name"] == name
            assert data["mainEntity"]["description"] == "Bio SEO."
    finally:
        await _set_profile(test_user["id"], profile_public=False)


async def test_domaine_officiel_fait_foi(
    client: AsyncClient, test_user: dict, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://watt.example/")
    name = f"seodom{uuid.uuid4().hex[:10]}"
    await _set_profile(test_user["id"], artist_name=name, profile_public=True)
    try:
        html = (await client.get(f"/@{name}")).text
        assert f'<link rel="canonical" href="https://watt.example/u/{name}" />' in html
        assert f'property="og:url" content="https://watt.example/u/{name}"' in html
    finally:
        await _set_profile(test_user["id"], profile_public=False)


async def test_entites_absentes_ou_privees_en_noindex(
    client: AsyncClient, test_user: dict, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "SHOW_ALBUMS", True)
    name = f"seopriv{uuid.uuid4().hex[:10]}"
    await _set_profile(test_user["id"], artist_name=name, profile_public=False)
    for chemin in (
        f"/u/{name}",                              # profil privé
        "/u/slug-inexistant-seo",                  # profil introuvable
        f"/o/{uuid.uuid4()}",                      # Œuvre introuvable
        "/o/pas-un-uuid",                          # adresse invalide
        "/collection/slug-inexistant-seo",         # Collection introuvable
    ):
        r = await client.get(chemin)
        assert r.status_code == 200, chemin        # la page brute, comme avant
        assert '<meta name="robots" content="noindex' in r.text, chemin
        assert 'property="og:' not in r.text, chemin


async def test_robots_laisse_charger_les_donnees_publiques(client: AsyncClient) -> None:
    txt = (await client.get("/robots.txt")).text
    assert "Disallow: /watt/" not in txt
    for prive in ("/gestion", "/pret-a-sortir", "/me/", "/admin", "/auth/"):
        assert f"Disallow: {prive}" in txt, prive


async def test_sitemap_profils_nommes_sans_doublon(
    client: AsyncClient, test_user: dict
) -> None:
    name = f"seomap{uuid.uuid4().hex[:10]}"
    await _set_profile(test_user["id"], artist_name=name, profile_public=True)
    try:
        xml = (await client.get("/sitemap.xml")).text
        assert xml.count(f"/u/{name}</loc>") == 1
        assert "/artistes</loc>" in xml
        assert "/u/membre-" not in xml
        locs = re.findall(r"<loc>(.*?)</loc>", xml)
        assert len(locs) == len(set(locs))           # aucune adresse en double
    finally:
        await _set_profile(test_user["id"], profile_public=False)
