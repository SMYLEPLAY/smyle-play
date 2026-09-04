"""F1-1 — apercu social (Open Graph / Twitter Card) sur les pages partagees.

Le modele d'acquisition est creator-led : un createur partage /u/<slug> ou
/oeuvre/<slug> sur ses reseaux. Sans balises og:, le lien s'affiche nu.

Trois etages : helpers purs (sans base), presence des routes (sans base), et
bout de chaine sur base reelle (L-03) — voir la note de la section « Routes ».
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import update

from app.database import SessionLocal
from app.models.user import User
from app.routers.pages import (
    _absolute,
    _clip,
    _social_head,
    _tag,
    router,
)


# ── Helpers purs ───────────────────────────────────────────────────────────

def test_tag_echappe_les_guillemets():
    out = _tag("og:title", 'Rock "n" roll & co')
    assert 'content="Rock &quot;n&quot; roll &amp; co"' in out
    assert out.startswith('<meta property="og:title"')


def test_tag_vide_ne_produit_rien():
    assert _tag("og:image", None) == ""
    assert _tag("og:image", "") == ""


def test_clip_tronque_et_normalise():
    assert _clip("  a\n\n  b ") == "a b"
    assert _clip("x" * 300).endswith("…")
    assert len(_clip("x" * 300)) <= 158
    assert _clip(None) == ""


def test_absolute_conserve_les_urls_completes():
    class _Req:
        headers = {"x-forwarded-proto": "https", "host": "watt.test"}

        class url:
            scheme = "https"
            netloc = "watt.test"

    assert _absolute(_Req(), "https://cdn.test/a.png") == "https://cdn.test/a.png"
    assert _absolute(_Req(), "/media/a.png") == "https://watt.test/media/a.png"
    assert _absolute(_Req(), "media/a.png") == "https://watt.test/media/a.png"
    assert _absolute(_Req(), None) is None


def test_social_head_degrade_en_summary_sans_image():
    head = _social_head(
        title="T", description="D", url="https://watt.test/u/x", image=None
    )
    assert 'name="twitter:card" content="summary"' in head
    assert "og:image" not in head
    assert 'property="og:title" content="T"' in head


def test_social_head_large_image_si_image():
    head = _social_head(
        title="T",
        description="D",
        url="https://watt.test/u/x",
        image="https://cdn.test/a.png",
    )
    assert 'content="summary_large_image"' in head
    assert 'property="og:image" content="https://cdn.test/a.png"' in head


# ── Routes (sans base de donnees) ──────────────────────────────────────────
#
# Historique (PR #489, 2026-08-05) : tout appel HTTP sur /u/<slug>, /@<slug> ou
# /oeuvre/<slug> depuis un client de test faisait echouer EN CASCADE tous les
# fichiers de tests suivants (playlists, reports, reserve, smyle_buckets, tiers,
# tracks, users) avec des MissingGreenlet / InterfaceError.
#
# Cause elucidee (L-03) : tests/test_pages_flag.py monte ce router sur un
# TestClient SYNCHRONE, qui execute l'app sur SA PROPRE boucle asyncio. La
# connexion asyncpg ouverte la par SessionLocal() etait rendue au pool partage
# de app.database.engine, puis reutilisee par les tests suivants sur la boucle
# de session pytest-asyncio. Corrige a la source : `poolclass=NullPool` quand
# ENVIRONMENT=test (app/database.py) — plus aucune connexion ne traverse les
# boucles. Les appels HTTP sont donc de nouveau surs (voir « Bout de chaine »).

def _chemins() -> set[str]:
    return {getattr(r, "path", None) for r in router.routes}


def test_route_profil_existe():
    assert "/u/{slug}" in _chemins()
    assert "/@{slug}" in _chemins()


def test_route_oeuvre_existe():
    # Regression P0-b : /oeuvre/<slug> n'avait plus de route de page -> 404
    # depuis le 30/07, alors que c'est la page qu'un createur partage.
    assert "/oeuvre/{slug}" in _chemins()


def test_page_index_existe():
    assert "/" in _chemins()


# ── Bout de chaine (base reelle) — L-03 ────────────────────────────────────
#
# « Livre ≠ branche » : on verifie que la page servie contient VRAIMENT les
# balises, via la resolution canonique du slug (follows._find_artist_by_slug).

async def _set_profile(user_id, **values) -> None:
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == user_id).values(**values))
        await db.commit()


async def test_profil_public_injecte_les_balises_og(
    client: AsyncClient, test_user: dict
) -> None:
    # artist_name deja en forme de slug (alphanumerique minuscule) : le slug
    # derive par _derive_artist_slug est donc exactement ce nom.
    name = f"ogtest{uuid.uuid4().hex[:10]}"
    await _set_profile(
        test_user["id"],
        artist_name=name,
        bio="Bio de test pour la carte sociale.",
        profile_public=True,
    )
    try:
        r = await client.get(f"/u/{name}")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert f'property="og:title" content="{name} \u2014 WATT"' in r.text
        assert 'property="og:type" content="profile"' in r.text
        assert f'property="og:url" content="http://test/u/{name}"' in r.text
        assert "Bio de test pour la carte sociale." in r.text
        assert r.text.count('property="og:') >= 4
        # /@<slug> : meme page, memes balises.
        assert 'property="og:title"' in (await client.get(f"/@{name}")).text
    finally:
        await _set_profile(test_user["id"], profile_public=False)


async def test_profil_prive_sert_la_page_brute_sans_fuite(
    client: AsyncClient, test_user: dict
) -> None:
    name = f"privtest{uuid.uuid4().hex[:10]}"
    await _set_profile(
        test_user["id"], artist_name=name, bio="Secret.", profile_public=False
    )
    r = await client.get(f"/u/{name}")
    assert r.status_code == 200          # la page brute, jamais 404 ni 500
    assert 'property="og:' not in r.text  # aucune donnee du profil prive
    assert "Secret." not in r.text


async def test_slug_inconnu_sert_la_page_brute(client: AsyncClient) -> None:
    for path in ("/u/slug-inexistant-l03", "/oeuvre/slug-inexistant-l03"):
        r = await client.get(path)
        assert r.status_code == 200, path
        assert 'property="og:' not in r.text, path
