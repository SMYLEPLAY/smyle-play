"""F1-1 — apercu social (Open Graph / Twitter Card) sur les pages partagees.

Le modele d'acquisition est creator-led : un createur partage /u/<slug> ou
/oeuvre/<slug> sur ses reseaux. Sans balises og:, le lien s'affiche nu.

Tests DB-free : mini-app avec le seul router pages. Aucune base n'est
joignable dans ce contexte, ce qui verifie AUSSI la degradation propre
(une panne DB ne doit jamais renvoyer 500 sur une page publique).
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.pages import (
    _absolute,
    _clip,
    _social_head,
    _tag,
    mount_static,
    router,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    mount_static(app)
    return TestClient(app, follow_redirects=False)


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


# ── Routes ─────────────────────────────────────────────────────────────────

def test_index_porte_les_meta_de_marque():
    r = _client().get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'property="og:title"' in r.text
    assert 'property="og:site_name" content="WATT"' in r.text
    assert 'name="description"' in r.text


def test_meta_injectees_avant_head_close():
    body = _client().get("/").text
    assert body.count("</head>") >= 1
    assert body.index('property="og:title"') < body.index("</head>")


def test_profil_sert_la_page_meme_sans_base():
    # Aucune DB joignable ici : la page doit rester servie (degradation propre).
    for path in ("/u/inconnu", "/@inconnu"):
        r = _client().get(path)
        assert r.status_code == 200, path
        assert "text/html" in r.headers["content-type"], path


def test_route_oeuvre_existe_et_sert_la_page():
    # Regression P0-b : /oeuvre/<slug> n'avait plus de route de page -> 404.
    r = _client().get("/oeuvre/mon-oeuvre")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
