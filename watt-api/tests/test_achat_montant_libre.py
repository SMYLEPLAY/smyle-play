"""Achat de Smyles au montant libre, prix par tranche (02/11/2026).

Règle d'or (ARCHITECTURE-ECONOMIE) : on ne rachète jamais un Smyle plus cher
que ce qu'il rapporte net. Un Smyle gagné se retire PAYOUT_RATE_CENTS ; au
pire (commission 10 %, TVA 20 %, carte hors UE 3,25 %) WATT reste gagnant.
"""
from pathlib import Path

import pytest

from app.config import settings
from app.services.credits import (
    ACHAT_MAX_SMYLES,
    ACHAT_MIN_SMYLES,
    CREDIT_PACKS,
    TRANCHES_PRIX,
    get_pack_by_id,
    offre_sur_mesure,
    prix_smyle_millieme,
)
from app.services.reserve import PAYOUT_RATE_CENTS

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("credits,cents", [
    (100, 800), (490, 3920), (500, 3500), (1000, 7000), (1990, 13930), (2000, 13000),
    (3000, 19500), (5000, 31000), (10000, 60000), (25000, 147500), (50000, 295000),
])
def test_prix_par_tranche(credits, cents):
    assert get_pack_by_id(f"pack_{credits}")["price_eur_cents"] == cents


@pytest.mark.parametrize("pid", ["pack_90", "pack_105", "pack_50010", "pack_0", "pack_-100",
                                 "pack_abc", "libre_100", "", "pack_1000000"])
def test_montants_refuses(pid):
    assert get_pack_by_id(pid) is None


def test_anciens_identifiants():
    assert get_pack_by_id("pack_10")["credits"] == 100
    assert get_pack_by_id("pack_200")["price_eur_cents"] == 13000
    assert offre_sur_mesure(True) is None


def test_tranches_degressives_et_raccourcis():
    prix = [m for _, m in TRANCHES_PRIX]
    assert prix == sorted(prix, reverse=True) and len(set(prix)) == len(prix) == 6
    assert [p["credits"] for p in CREDIT_PACKS] == [100, 1000, 5000, 25000]
    assert TRANCHES_PRIX[0][0] == ACHAT_MIN_SMYLES


@pytest.mark.parametrize("seuil,m", TRANCHES_PRIX)
def test_jamais_sous_le_plancher(seuil, m):
    net = (m / 10) / 1.20 * (1 - 0.0325)          # centimes par Smyle
    assert net > PAYOUT_RATE_CENTS * (1 - 0.10)
    assert prix_smyle_millieme(seuil) == m


async def test_api_grille(client, monkeypatch):
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", True)
    d = (await client.get("/credits/packs")).json()
    assert d["min_smyles"] == ACHAT_MIN_SMYLES and d["max_smyles"] == ACHAT_MAX_SMYLES
    assert d["pas_smyles"] == 10
    assert [t["remise_pct"] for t in d["tranches"]] == [0, 12, 19, 22, 25, 26]
    assert d["tranches"][2]["prix_display"] == "0,065 €"
    packs = {p["id"]: p for p in d["packs"]}
    assert packs["pack_25000"]["price_eur_display"] == "1 475,00 €"


async def test_api_grille_masquee_tant_que_achat_ferme(client, monkeypatch):
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", False)
    d = (await client.get("/credits/packs")).json()
    assert d["packs"] == [] and d["tranches"] == []


def test_cgv_citent_la_grille():
    legal = (ROOT / "legal.html").read_text(encoding="utf-8")
    assert "de <strong>100 à 50 000 Smyles par paiement</strong>" in legal
    for seuil, m in TRANCHES_PRIX:
        euros = f"{m / 1000:.3f}".rstrip("0").replace(".", ",")
        assert f"<strong>{euros} €</strong> TTC le Smyle" in legal
