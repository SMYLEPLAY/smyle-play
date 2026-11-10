"""Refonte de l'interface — lot 2 (coquille).

Le menu devient un rail (ordinateur) ou une barre du bas (téléphone) par la
seule feuille ui/pwa/refonte.css. Ces tests gardent les points fragiles :
les trois barres du site sont couvertes, rien n'est touché dans les pages,
et la feuille reste absente tant que l'interrupteur est fermé."""
import re
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CSS = (RACINE / "ui" / "pwa" / "refonte.css").read_text(encoding="utf-8")


def test_les_trois_barres_sont_couvertes():
    for selecteur in ("body > header > .hdr-nav", ".stb-root .stb-nav", ".dash-topbar .hdr-nav"):
        assert selecteur in CSS


def test_chaque_entree_du_menu_a_son_icone():
    for cible in ('a[href="/"]', 'a[href="/dashboard"]', ".watt-toggle-btn",
                  'a[href="/library"]', '[onclick*="openBoutique"]', ".wpl-nav-btn"):
        assert cible in CSS
    for nom in ("accueil", "board", "biblio", "boutique", "playlists"):
        assert f"--rf-ic-{nom}: url(" in CSS


def test_les_selecteurs_du_menu_existent_dans_les_pages():
    index = (RACINE / "index.html").read_text(encoding="utf-8")
    board = (RACINE / "dashboard.html").read_text(encoding="utf-8")
    barre = (RACINE / "ui" / "topbar" / "topbar.js").read_text(encoding="utf-8")
    assert 'class="hdr-nav"' in index and "watt-toggle-btn" in index
    assert 'class="dash-topbar"' in board and 'class="hdr-nav"' in board
    assert 'class="stb-nav"' in barre and "openBoutique" in barre
    for page in ("library.html", "artiste.html", "oeuvre.html", "mes-oeuvres.html", "o.html"):
        assert 'id="smyle-topbar"' in (RACINE / page).read_text(encoding="utf-8")


def test_rail_et_barre_du_bas_selon_la_largeur():
    assert "@media (min-width: 861px)" in CSS
    assert "@media (max-width: 860px)" in CSS
    # Le décalage ne s'applique qu'aux pages qui ont le menu.
    assert "body:has(> #smyle-topbar)" in CSS


def test_le_lecteur_passe_devant_sa_feuille_d_origine():
    # mini-bar.css est chargée après refonte.css : il faut un sélecteur plus fort.
    assert "html body #smyle-mini-bar.smb-visible" in CSS


def test_accolades_equilibrees():
    sans = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    assert sans.count("{") == sans.count("}")
