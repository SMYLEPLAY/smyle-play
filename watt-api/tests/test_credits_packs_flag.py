"""S-11 (annexe A §M5) — `GET /credits/packs` suit l'item `achatSmyles`.

La grille de packs est une route PUBLIQUE qui annonce des prix en euros. Tant
que l'achat n'existe pas (Stripe non branché, `POST /credits/grant` réservé
à `is_official`), la servir revient à afficher une tarification que rien ne
peut honorer — et à laisser croire qu'un paiement va aboutir.

Test DB-free : mini-app FastAPI avec le seul routeur credits (la route
`/packs` n'a ni dépendance d'authentification ni session).
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.routers.credits import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_packs_vides_quand_achat_masque(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", False)
    r = _client().get("/credits/packs")
    assert r.status_code == 200
    assert r.json()["packs"] == []


def test_packs_servis_quand_achat_rallume(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", True)
    r = _client().get("/credits/packs")
    assert r.status_code == 200
    packs = r.json()["packs"]
    assert packs, "la grille doit revenir dès que SHOW_ACHAT_SMYLES est vrai"
    assert all("price_eur_display" in p for p in packs)


def test_packs_servis_hors_mode_lancement(monkeypatch):
    """Fin du lancement = tout est rallumé, sans toucher aux SHOW_*."""
    monkeypatch.setattr(settings, "MODE_LANCEMENT", False)
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", False)
    assert _client().get("/credits/packs").json()["packs"]
