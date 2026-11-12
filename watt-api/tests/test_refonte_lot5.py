"""Refonte de l'interface — lot 5 (Board, Bibliothèque, Boutique, Playlists).

Habillage par ui/pwa/refonte.css uniquement : aucun script, rien de renommé.
Ces tests vérifient que les éléments visés existent toujours dans le site."""
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CSS = (RACINE / "ui" / "pwa" / "refonte.css").read_text(encoding="utf-8")
LOT5 = CSS.split("LOT 5", 1)[1]


def _lire(*chemin):
    return (RACINE.joinpath(*chemin)).read_text(encoding="utf-8")


def test_board_elements_presents():
    source = _lire("dashboard.html") + _lire("wattboard-v3.js") if (RACINE / "wattboard-v3.js").exists() else _lire("dashboard.html")
    css = _lire("wattboard-v3.css")
    for classe in ("wb3-hero", "wb3-hero-avatar", "wb3-create-btn", "wb3-tile-btn--primary",
                   "wb3-monde-btn", "wb3-tile"):
        assert f".{classe}" in LOT5
        assert f".{classe}" in css, classe
    assert "wb3-board" in source


def test_bibliotheque_elements_presents():
    page = _lire("library.html") + _lire("library.js")
    for classe in ("lib-hero", "lib-hero-badge", "lib-hero-title", "lib-mode-btn",
                   "lib-adn-col", "lib-empty-cta"):
        assert f".{classe}" in LOT5
        assert classe in page, classe


def test_boutique_reste_une_fenetre():
    js = _lire("ui", "modals", "boutique.js")
    for ident in ("bqBoutiqueModal", "bqPackModal", "bqBody", "bqBuySmyles", "bqOpenBtn"):
        assert f"#{ident}" in LOT5
        assert ident in js, ident


def test_playlists_reste_un_panneau():
    js = _lire("ui", "watt-playlists.js")
    for classe in ("wpl-sheet", "wpl-hd", "wpl-title", "wpl-tab", "wpl-btn--main"):
        assert f".{classe}" in LOT5
        assert classe in js, classe
    # La feuille du panneau est écrite après refonte.css : sélecteur plus fort.
    assert "html body .wpl-sheet" in LOT5


def test_accolades_equilibrees():
    sans = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    assert sans.count("{") == sans.count("}")
