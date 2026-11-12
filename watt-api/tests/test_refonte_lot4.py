"""Refonte de l'interface — lot 4 (page profil).

Habillage par ui/pwa/refonte.css, limité à .ap-page ; un petit script marque
la page du compte officiel. Rien n'est renommé dans artiste.html."""
import re
from pathlib import Path

from app.config import settings
from app.routers.pages import injecter_pwa

RACINE = Path(__file__).resolve().parents[2]
CSS = (RACINE / "ui" / "pwa" / "refonte.css").read_text(encoding="utf-8")
JS = (RACINE / "ui" / "refonte" / "profil.js").read_text(encoding="utf-8")
PAGE = (RACINE / "artiste.html").read_text(encoding="utf-8")
AVEC = '<html><head></head><body><main id="ap-profile"></main></body></html>'
SANS = "<html><head></head><body></body></html>"


def test_script_charge_seulement_sur_un_profil(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_REFONTE", True)
    assert "/ui/refonte/profil.js?v=" in injecter_pwa(AVEC, actif=False)
    assert "refonte/profil.js" not in injecter_pwa(SANS, actif=False)
    monkeypatch.setattr(settings, "SHOW_REFONTE", False)
    assert "refonte/profil.js" not in injecter_pwa(AVEC, actif=False)


def test_le_script_se_garde_et_ne_marque_que_smyle():
    assert "window.WATT_LAUNCH.refonte" in JS
    assert "slug === 'smyle'" in JS and "rf-officiel" in JS


def test_les_elements_habilles_existent_dans_la_page():
    assert 'class="ap-page"' in PAGE and 'id="ap-profile"' in PAGE
    for motif in ('class="ap-hero"', 'class="ap-hero-banner"', 'id="ap-avatar"',
                  'id="ap-artist-name"', 'class="ap-stat-value"', "ap-relic-unlock-btn",
                  'id="player"', 'id="player-info"'):
        assert motif in PAGE


def test_les_regles_du_profil_restent_dans_la_page_profil():
    bloc = CSS.split("LOT 4", 1)[1].split("*/", 1)[1]
    bloc = re.sub(r"/\*.*?\*/", "", bloc, flags=re.S)
    for selecteur in re.findall(r"(?m)^([^{}@\n][^{}]*)\{", bloc):
        for partie in selecteur.split(","):
            partie = partie.strip()
            if partie and not partie[0].isdigit() and partie not in ("from", "to"):
                assert partie.startswith(".ap-page"), partie
