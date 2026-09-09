"""N-07 (09/09) — le bouton « Boutique » de la topbar doit fonctionner partout.

`ui/topbar/topbar.js` rend un bouton `onclick="if(window.openBoutique)…"` :
si `ui/modals/boutique.js` (qui expose `window.openBoutique`) et
`ui/modals/engagement.js` (qui expose `window.openStreakPanel`, appelé par la
boutique pour le check-in) ne sont pas chargés, le bouton ne fait RIEN — sans
erreur. C'était le cas sur `oeuvre.html` (annexe D, F6). Test DB-free.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Pages de parcours où la boutique doit s'ouvrir (topbar sur 4 d'entre elles,
# menu de auth.js sur l'accueil).
PAGES_BOUTIQUE = [
    "index.html",
    "artiste.html",
    "oeuvre.html",
    "dashboard.html",
    "library.html",
]


def _src(page: str) -> str:
    return (REPO_ROOT / page).read_text(encoding="utf-8")


@pytest.mark.parametrize("page", PAGES_BOUTIQUE)
def test_page_charge_boutique_et_engagement(page: str):
    html = _src(page)
    assert "ui/modals/boutique.js" in html, f"{page} : boutique.js non chargé"
    assert "ui/modals/engagement.js" in html, f"{page} : engagement.js non chargé"


def test_topbar_appelle_open_boutique():
    js = (REPO_ROOT / "ui" / "topbar" / "topbar.js").read_text(encoding="utf-8")
    assert "window.openBoutique" in js
    assert "window.openBoutique = " in (REPO_ROOT / "ui" / "modals" / "boutique.js").read_text(encoding="utf-8")
