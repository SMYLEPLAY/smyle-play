"""Étape 3 — objectif collectif « 1000 actifs » (FEATURE_GOAL).

  - flag OFF (défaut) : GET /objectif/actifs → 404 (rien n'est révélé) ;
  - flag ON : chiffre = définition UNIQUE des actifs (compter_actifs), texte
    public attendu, paliers 500 / 1000 / 2500, en-tête de cache ~60 s ;
  - un palier franchi est seulement AFFICHÉ « atteint » : aucun retrait ;
  - cache : un seul calcul par fenêtre de 60 s ;
  - la barre est posée sur l'accueil et le tableau de bord.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.services import objectif_actifs as oa
from app.services.launch_readiness import compter_actifs

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _cache_vide():
    oa.vider_cache()
    yield
    oa.vider_cache()


def test_defaut_off_et_valeurs():
    from app.config import Settings
    s = Settings()
    assert s.FEATURE_GOAL is False
    assert s.GOAL_CIBLE_ACTIFS == 1000
    assert s.GOAL_PALIERS == [500, 1000, 2500]
    assert s.GOAL_RETRAIT_AU_PLUS_TARD == "2027-05-01"


def test_date_en_francais():
    assert oa.date_en_francais("2027-05-01") == "1er mai 2027"
    assert oa.date_en_francais("2026-11-12") == "12 novembre 2026"
    assert oa.date_en_francais("pas une date") == "pas une date"


def test_payload_paliers_affichage_seulement():
    d = oa.objectif_payload(640)
    assert d["texte"] == (
        "640 / 1000 actifs — à 1000, le retrait en euros s'ouvre pour tous "
        "(au plus tard le 1er mai 2027)"
    )
    assert d["paliers"] == [
        {"seuil": 500, "atteint": True},
        {"seuil": 1000, "atteint": False},
        {"seuil": 2500, "atteint": False},
    ]
    assert d["progression"] == 0.64 and d["cible_atteinte"] is False
    d = oa.objectif_payload(1200)
    assert d["cible_atteinte"] is True and d["progression"] == 1.0
    # Aucune clé qui ouvrirait quoi que ce soit : pur affichage.
    assert not any("ouvert" in k or "payout" in k for k in d)


async def test_endpoint_404_quand_off(client, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_GOAL", False)
    r = await client.get("/objectif/actifs")
    assert r.status_code == 404


async def test_endpoint_public_quand_on(client, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_GOAL", True)
    r = await client.get("/objectif/actifs")  # sans authentification
    assert r.status_code == 200, r.text
    d = r.json()
    async with SessionLocal() as db:
        assert d["actifs"] == await compter_actifs(db)  # définition unique
    assert d["cible"] == 1000
    assert [p["seuil"] for p in d["paliers"]] == [500, 1000, 2500]
    assert d["texte"].startswith(f"{d['actifs']} / 1000 actifs — à 1000, le retrait en euros")
    assert "max-age=60" in r.headers.get("cache-control", "")


async def test_cache_60_secondes(monkeypatch):
    appels = {"n": 0}

    async def _compte(db):
        appels["n"] += 1
        return 42

    monkeypatch.setattr(oa, "compter_actifs", _compte)
    async with SessionLocal() as db:
        assert await oa.actifs_en_cache(db) == 42
        assert await oa.actifs_en_cache(db) == 42
    assert appels["n"] == 1
    # Fenêtre expirée → recalcul.
    oa._cache["t"] -= oa.CACHE_SECONDES + 1
    async with SessionLocal() as db:
        await oa.actifs_en_cache(db)
    assert appels["n"] == 2


def test_barre_posee_accueil_et_tableau_de_bord():
    js = (REPO_ROOT / "ui" / "goal-bar.js").read_text(encoding="utf-8")
    assert "/objectif/actifs" in js and "innerHTML" not in js
    for page in ("index.html", "dashboard.html"):
        src = (REPO_ROOT / page).read_text(encoding="utf-8")
        assert "data-goal-bar hidden" in src, page
        assert "/ui/goal-bar.js" in src, page
