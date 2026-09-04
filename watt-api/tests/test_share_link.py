"""F1-3 — bouton « Partager mon lien » (canal d'acquisition creator-led).

Le partage du lien créateur EST le mécanisme d'acquisition du modèle. Ces
tests verrouillent trois invariants faciles à casser lors d'un refactor :
  1. le bouton existe dans le dashboard ;
  2. il partage la forme CANONIQUE /u/<slug> — la seule qui porte l'aperçu
     social injecté côté serveur (la forme courte /@<slug> ne l'a pas) ;
  3. il émet `share_click`, sinon on ne saura jamais qui partage.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASH_HTML = (REPO_ROOT / "dashboard.html").read_text(encoding="utf-8")
DASH_JS = (REPO_ROOT / "dashboard.js").read_text(encoding="utf-8")


def test_bouton_present_dans_le_menu():
    assert 'id="dashDropShare"' in DASH_HTML
    assert "Partager mon lien" in DASH_HTML


def test_partage_l_url_canonique_u_slug():
    assert "'/u/' + encodeURIComponent(slug)" in DASH_JS, (
        "le lien partagé doit être /u/<slug> (forme portant l'aperçu social)"
    )


def test_emet_share_click():
    assert "'share_click'" in DASH_JS


def test_mesure_non_bloquante():
    """Une erreur de télémétrie ne doit jamais empêcher le partage."""
    i = DASH_JS.index("'share_click'")
    contexte = DASH_JS[i - 300 : i + 300]
    assert "try" in contexte and "catch" in contexte


def test_bouton_masque_sans_slug():
    assert "shareEl.hidden = !slug" in DASH_JS
