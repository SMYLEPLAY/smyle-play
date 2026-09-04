"""F3-3 — mesure de l'intention de payer (avant Stripe).

Stripe n'est pas branché : le clic sur « recharger » est la SEULE mesure
disponible de la disposition réelle à payer. C'est l'un des cinq chiffres
qui décideront d'un go / pivot à la fin de la beta — s'il n'est pas émis,
la question reste sans réponse et la beta n'aura rien tranché.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CREDITS_JS = (REPO_ROOT / "ui" / "modals" / "credits-buy.js").read_text(encoding="utf-8")
BALANCE_JS = (REPO_ROOT / "ui" / "smyle-balance.js").read_text(encoding="utf-8")


def test_modale_recharge_emet_topup_click():
    i = CREDITS_JS.index("function openCreditsBuyModal()")
    assert "'topup_click'" in CREDITS_JS[i : i + 800]


def test_widget_solde_emet_aussi_en_repli():
    assert "'topup_click'" in BALANCE_JS
    assert "balance-widget" in BALANCE_JS


def test_sources_distinctes():
    """Deux points d'entrée = deux sources, sinon on ne sait pas d'où ça vient."""
    assert "'credits-buy'" in CREDITS_JS
    assert "'balance-widget'" in BALANCE_JS


def test_mesure_non_bloquante():
    for src, name in ((CREDITS_JS, "credits-buy.js"), (BALANCE_JS, "smyle-balance.js")):
        i = src.index("'topup_click'")
        contexte = src[i - 250 : i + 250]
        assert "try" in contexte and "catch" in contexte, name
