"""F4-1 — aucune promesse vide a l'ecran avant l'ouverture des paiements.

Regle produit de Tom : « copywriting honnete, aucune promesse de resultat ».
Un badge « Bientot » sans date, ou une page de tarifs faite de boutons
desactives, sont exactement cela — et c'est la premiere chose que verrait un
visiteur arrivant du lien partage par un createur.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.routers.pages import mount_static, router

REPO_ROOT = Path(__file__).resolve().parents[2]


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    mount_static(app)
    return TestClient(app, follow_redirects=False)


def test_tarifs_ferme_quand_euros_masques(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_EUROS", False)
    r = _client().get("/tarifs")
    assert r.status_code == 302
    assert r.headers["location"] == "/"


def test_tarifs_ouvre_quand_euros_visibles(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_EUROS", True)
    r = _client().get("/tarifs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_pages_marchandes_fermees_par_defaut(monkeypatch):
    """Defauts du mode lancement : ni /tarifs ni /offres ne doivent s'ouvrir.

    K-08 : les deux pages ne suivent PAS le meme drapeau (/offres → paliers,
    /tarifs → euros), mais les deux sont masquees par defaut — c'est l'etat
    qui compte pour un visiteur.
    """
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_PALIERS", False)
    monkeypatch.setattr(settings, "SHOW_EUROS", False)
    c = _client()
    assert c.get("/tarifs").status_code == c.get("/offres").status_code == 302


def test_plus_de_badge_bientot_sur_offres():
    src = (REPO_ROOT / "offres.html").read_text(encoding="utf-8")
    assert "off-badge\">Bientôt" not in src
