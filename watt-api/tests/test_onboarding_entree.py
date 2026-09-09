"""N-03 (09/09) — l'entrée du produit : onboarding premier-run + page d'aide.

Constat (annexe D, D1.2/D1.4) : `ui/core/onboarding.js` n'était chargé par
AUCUNE page depuis #403 (juin), et `/comment-ca-marche` n'avait aucun lien
entrant (son seul lien vivait dans ce script mort). Un testeur arrivait sur le
hero sans une phrase qui dise quoi faire de ses Smyles.

Tests DB-free (lecture des sources) : régression silencieuse sinon.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_accueil_charge_l_onboarding():
    html = _src("index.html")
    assert "ui/core/onboarding.js" in html, "onboarding.js n'est plus chargé sur l'accueil (#403 bis)"
    # Après le solde : la modale affiche les Smyles de bienvenue via SmyleBalance.
    assert html.index("ui/smyle-balance.js") < html.index("ui/core/onboarding.js")


def test_onboarding_flag_et_lien_aide():
    js = _src("ui/core/onboarding.js")
    assert "smyle_onboarded_v1" in js          # une seule ouverture
    assert 'href="/comment-ca-marche"' in js
    # Au-dessus des tiroirs (purchase-drawer 1300) : sinon la modale se cache.
    m = re.search(r"z-index:\s*(\d+)", js)
    assert m and int(m.group(1)) > 1300


def test_comment_ca_marche_a_des_liens_entrants():
    """Footer (toutes les pages, connecté ou non) + menu compte de la topbar."""
    assert 'href="/comment-ca-marche"' in _src("ui/core/legal-footer.js")
    assert 'href="/comment-ca-marche"' in _src("ui/topbar/topbar.js")


def test_e2e_helper_neutralise_l_onboarding():
    """Les smokes authentifiés bootent un compte NEUF sur `/` : sans ce drapeau
    la modale #obWelcome (z-index 1400) recouvrirait l'en-tête et le tiroir
    d'achat (1300) — même piège que #streakModal (D10)."""
    helpers = _src("e2e/tests/_helpers.js")
    assert "smyle_onboarded_v1" in helpers
