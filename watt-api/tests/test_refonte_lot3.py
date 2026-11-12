"""Refonte de l'interface — lot 3 (accueil).

Le script de l'accueil n'est chargé que si l'interrupteur est ouvert ET que
la page contient la vitrine. Il ne renomme rien : il s'appuie sur les id
existants de la vitrine SMYLE."""
from pathlib import Path

from app.config import settings
from app.routers.pages import injecter_pwa

RACINE = Path(__file__).resolve().parents[2]
JS = (RACINE / "ui" / "refonte" / "accueil.js").read_text(encoding="utf-8")
CSS = (RACINE / "ui" / "pwa" / "refonte.css").read_text(encoding="utf-8")
INDEX = (RACINE / "index.html").read_text(encoding="utf-8")
AVEC = '<html><head></head><body><section id="smyle-vitrine"></section></body></html>'
SANS = "<html><head></head><body></body></html>"


def test_script_absent_quand_interrupteur_ferme(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_REFONTE", False)
    assert "refonte/accueil.js" not in injecter_pwa(AVEC, actif=False)


def test_script_charge_seulement_sur_la_page_de_la_vitrine(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_REFONTE", True)
    assert "/ui/refonte/accueil.js?v=" in injecter_pwa(AVEC, actif=False)
    assert "refonte/accueil.js" not in injecter_pwa(SANS, actif=False)


def test_le_script_se_garde_lui_meme():
    assert "window.WATT_LAUNCH.refonte" in JS


def test_les_id_utilises_existent_dans_l_accueil():
    for ident in ("smyle-vitrine", "smyle-vitrine-avatar", "smyle-vitrine-name",
                  "smyle-vitrine-bio", "smyle-vitrine-followers", "smyle-vitrine-tracks",
                  "smyle-vitrine-plays", "smyle-vitrine-link"):
        assert f"'{ident}'" in JS
        assert f'id="{ident}"' in INDEX


def test_regle_du_bloc_profil_en_ligne_sinon_smyle():
    # Le profil de la personne ne remplace SMYLE que s'il est en ligne.
    assert "a.profilePublic" in JS and "afficherSmyle" in JS
    assert "Poster un son" in JS and "Voir ma page" in JS
    # On ne débloque rien depuis l'accueil.
    assert "bloquer" not in JS.lower().replace("débloque", "")


def test_accueil_garde_le_titre_sans_accroche():
    # WATT et « World Artist Ties Talent » restent ; l'accroche est masquée.
    assert ".mp-hero-sub,\n.mp-hero-search-hint { display: none; }" in CSS
    masques = CSS.split(".mp-hero-sub,")[0].rsplit("}", 1)[-1]
    assert ".mp-hero-title" not in masques and ".mp-hero-acronym" not in masques
    for classe in ("mp-hero-title", "mp-hero-acronym", "mp-hero-sub"):
        assert f'class="{classe}"' in INDEX
    assert "#ap-playlists-root { display: none !important; }" in CSS
