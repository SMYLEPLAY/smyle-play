"""Textes légaux (Lot F) — la page /legal reste alignée sur le code.

Chaque chiffre publié dans les CGU/CGV doit venir des constantes du code :
si une constante change, ce test casse et rappelle de mettre le texte à jour
(et la version des CGU, pour que chacun les accepte à nouveau).
"""
import re
from pathlib import Path

from app.config import settings
from app.schemas.marketplace import PROMPT_PRICE_MAX, PROMPT_PRICE_MIN
from app.services.credits import CREDIT_PACKS
from app.services.escrow import EARNINGS_MATURITY_DAYS
from app.services.pioneer import PIONEER_SLOTS
from app.services.referrals import REFERRAL_REWARD_CREDITS
from app.services.reserve import PAYOUT_RATE_CENTS
from app.services.tiers import PIONEER_COMMISSION_PCT, TIER_COMMISSION_PCT, UserTier
from app.services.users import WELCOME_BONUS_CREDITS

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL = (REPO_ROOT / "legal.html").read_text(encoding="utf-8")
TEXTE = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", LEGAL))


def _fr(n: int) -> str:
    """2000 -> « 2 000 » (séparateur de milliers à la française)."""
    return f"{n:,}".replace(",", " ")


def test_aucun_reste_de_brouillon():
    for interdit in ("À COMPLÉTER", "crédits", "bêta", "réinitialis", "recharger"):
        assert interdit.lower() not in LEGAL.lower(), interdit


def test_ancres_utilisees_par_le_site():
    for ancre in ("mentions", "cgu", "smyles", "cgv-smyles", "confidentialite",
                  "contenu", "mediateur", "suppression"):
        assert f'id="{ancre}"' in LEGAL, ancre


def test_chiffres_alignes_sur_le_code():
    assert f"{WELCOME_BONUS_CREDITS} Smyles" in TEXTE
    assert f"{REFERRAL_REWARD_CREDITS} Smyles offerts" in TEXTE
    for _, smyles in settings.QUETES_PARRAINAGE_PALIERS:
        assert f"{smyles} Smyles" in TEXTE
    for seuil, _ in settings.QUETES_PARRAINAGE_PALIERS:
        assert f"{seuil} filleuls actifs" in TEXTE
    assert f"entre {PROMPT_PRICE_MIN} et {PROMPT_PRICE_MAX} Smyles" in TEXTE
    assert f"0,{PAYOUT_RATE_CENTS:02d} € par Smyle gagné" in TEXTE
    assert f"{EARNINGS_MATURITY_DAYS} jours" in TEXTE
    assert "1er mai 2027" in TEXTE and settings.GOAL_RETRAIT_AU_PLUS_TARD == "2027-05-01"
    assert f"{_fr(settings.GOAL_CIBLE_ACTIFS)} utilisateurs actifs" in TEXTE
    for pack in CREDIT_PACKS:
        euros = pack["price_eur_cents"] // 100
        assert f"{_fr(pack['credits'])} Smyles : {euros} € TTC" in TEXTE
    for tier in UserTier:
        assert f"{TIER_COMMISSION_PCT[tier]} %" in TEXTE
    assert f"{PIONEER_COMMISSION_PCT} % à vie" in TEXTE
    assert f"places sur {PIONEER_SLOTS}" in TEXTE
    for _, abonnes in settings.SELL_GATE_PALIERS:
        assert f"{abonnes} abonnés" in TEXTE


def test_version_des_cgu():
    assert "1er novembre 2026" in TEXTE
