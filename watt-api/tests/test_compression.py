"""F1-2 — compression HTTP de la page partagée.

Le modèle est creator-led : /u/<slug> s'ouvre depuis une story, sur un
téléphone, en 4G. Mesuré au 02/08 : 415 Ko de texte non compressé
(HTML+JS+CSS), ramenés à ~101 Ko par gzip (-76 %).

⚠️ Le test le plus important de ce fichier est le DERNIER : les routes de
proxy binaire (audio/images R2, requêtes Range) ne doivent JAMAIS être
compressées. L'incident des pochettes disparues (24/07) venait d'un
middleware qui touchait au corps de ces réponses.
"""

import gzip
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]


def _client() -> TestClient:
    return TestClient(create_app())


def test_html_est_compresse():
    r = _client().get("/", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_pas_de_compression_si_le_client_n_en_veut_pas():
    r = _client().get("/", headers={"Accept-Encoding": "identity"})
    assert r.status_code == 200
    assert "content-encoding" not in r.headers


def test_proxy_binaire_jamais_compresse():
    """Regression de l'incident du 24/07 : ne pas toucher au streaming R2.

    Teste le middleware isolement, sur une app minimale : on ne depend ainsi
    ni de la config R2 ni des routes reelles.
    """
    from fastapi.responses import Response

    from app.main import _SEC_SKIP_PREFIXES, SelectiveGZipMiddleware

    app = FastAPI()

    @app.get("/watt/stream/{key}")
    async def _binaire(key: str):
        return Response(content=b"x" * 5000, media_type="audio/mpeg")

    @app.get("/page")
    async def _texte():
        return Response(content="y" * 5000, media_type="text/html")

    app.add_middleware(SelectiveGZipMiddleware, skip_prefixes=_SEC_SKIP_PREFIXES)
    c = TestClient(app)

    binaire = c.get("/watt/stream/abc", headers={"Accept-Encoding": "gzip"})
    assert binaire.status_code == 200
    assert "content-encoding" not in binaire.headers, (
        "les routes de proxy binaire doivent rester non compressees"
    )

    texte = c.get("/page", headers={"Accept-Encoding": "gzip"})
    assert texte.headers.get("content-encoding") == "gzip", (
        "le reste doit bien etre compresse (sinon le test ci-dessus ne prouve rien)"
    )


def test_auth_jamais_compresse():
    """BREACH (CVE-2013-3587) — /auth/* ne doit jamais etre compresse.

    Une reponse qui contient a la fois un SECRET (le JWT) et une portion
    controlee par l'attaquant permet de deviner le secret octet par octet en
    observant la taille compressee. Les reponses d'authentification sont
    minuscules : la compression n'y gagnait rien, elle ne coutait qu'un risque.

    Teste sur une app minimale (comme le proxy binaire) pour ne dependre ni de
    la base ni du rate-limit — mais avec la MEME constante que create_app.
    """
    from fastapi.responses import JSONResponse

    from app.main import _GZIP_SKIP_PREFIXES, SelectiveGZipMiddleware

    assert "/auth" in _GZIP_SKIP_PREFIXES, (
        "create_app doit exclure /auth de la compression"
    )

    app = FastAPI()

    @app.post("/auth/login")
    async def _login():
        # Forme realiste : un jeton long, tres compressible.
        return JSONResponse({"access_token": "a" * 4000, "token_type": "bearer"})

    @app.get("/page")
    async def _texte():
        from fastapi.responses import Response

        return Response(content="y" * 5000, media_type="text/html")

    app.add_middleware(SelectiveGZipMiddleware, skip_prefixes=_GZIP_SKIP_PREFIXES)
    c = TestClient(app)

    login = c.post("/auth/login", headers={"Accept-Encoding": "gzip"})
    assert login.status_code == 200
    assert "content-encoding" not in login.headers, (
        "BREACH : une reponse d'authentification ne doit pas etre compressee"
    )

    assert c.get("/page", headers={"Accept-Encoding": "gzip"}).headers.get(
        "content-encoding"
    ) == "gzip", "le reste doit rester compresse (sinon le test ne prouve rien)"


def test_gain_reel_sur_la_page_partagee():
    """Verrouille l'ordre de grandeur : la page partagée doit passer sous
    250 Ko compressés (critère de fini F1-2)."""
    total_gz = 0
    for f in ("artiste.html", "artiste.js", "artiste.css", "watt.css"):
        p = REPO_ROOT / f
        if p.exists():
            total_gz += len(gzip.compress(p.read_bytes(), 6))
    assert total_gz < 250 * 1024, f"{total_gz / 1024:.0f} Ko compressés — trop lourd"


def test_images_du_profil_differees():
    src = (REPO_ROOT / "artiste.js").read_text(encoding="utf-8")
    balises = src.count("<img ")
    lazy = src.count('loading="lazy"')
    assert lazy >= balises, f"{balises - lazy} <img> sans loading=lazy"
