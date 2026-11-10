"""Refonte de l'interface — lot 1 (socle).

L'interrupteur `refonte` est fermé par défaut, indépendant du mode
lancement, et ne fait qu'ajouter une feuille de jetons au bloc commun."""
from pathlib import Path

from app.config import Settings, settings
from app.routers.pages import injecter_pwa

PAGE = "<html><head><title>x</title></head><body></body></html>"
RACINE = Path(__file__).resolve().parents[2]


def test_refonte_fermee_par_defaut():
    assert Settings.model_fields["SHOW_REFONTE"].default is False
    assert settings.launch_flags_dict()["refonte"] is False


def test_refonte_independante_du_mode_lancement(monkeypatch):
    monkeypatch.setattr(settings, "MODE_LANCEMENT", False)
    monkeypatch.setattr(settings, "SHOW_REFONTE", False)
    assert settings.launch_flags_dict()["refonte"] is False


def test_feuille_absente_quand_fermee(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_REFONTE", False)
    assert "refonte.css" not in injecter_pwa(PAGE, actif=False)


def test_feuille_chargee_apres_le_lissage_quand_ouverte(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_REFONTE", True)
    html = injecter_pwa(PAGE, actif=False)
    assert "/ui/pwa/refonte.css?v=" in html
    assert html.index("lissage.css") < html.index("refonte.css")


def test_repli_statique_declare_refonte_fermee():
    js = (RACINE / "ui" / "core" / "launch-flags.js").read_text(encoding="utf-8")
    assert "refonte: false" in js


def test_socle_declare_les_jetons():
    css = (RACINE / "ui" / "pwa" / "refonte.css").read_text(encoding="utf-8")
    for jeton in ("--rf-fond: #050508", "--rf-violet: #8800ff", "--rf-argent: #c9d0d6",
                  "--rf-or: #ffd700", "--rf-rail-largeur", "--rf-barre-bas-hauteur"):
        assert jeton in css
