"""F3-1b — la mesure doit être CHARGÉE sur les pages publiques.

Constat du 02/08 : ui/core/telemetry.js n'était inclus que dans 2 pages
(oeuvre.html, comment-ca-marche.html). Ni l'accueil, ni le profil créateur
/u/<slug> (artiste.html), ni le dashboard, ni la bibliothèque ne chargeaient
l'émetteur — le journal `analytics_events` restait donc vide sur tout le
parcours qui compte, y compris la page d'atterrissage du modèle creator-led.

Ces tests empêchent la régression : mesurer sans charger l'émetteur est un
échec SILENCIEUX (aucune erreur, juste zéro donnée).
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Pages publiques ou de parcours qui doivent mesurer.
PAGES = [
    "index.html",
    "artiste.html",   # /u/<slug> — page d'atterrissage du lien partagé
    "oeuvre.html",    # /oeuvre/<slug>
    "dashboard.html",
    "library.html",
    "comment-ca-marche.html",
]


@pytest.mark.parametrize("page", PAGES)
def test_page_charge_l_emetteur(page: str):
    src = (REPO_ROOT / page).read_text(encoding="utf-8")
    assert "ui/core/telemetry.js" in src, f"{page} ne charge pas telemetry.js"


@pytest.mark.parametrize("page", PAGES)
def test_page_charge_le_consentement(page: str):
    """Mesurer sans offrir le choix serait non conforme : consent.js partout
    où telemetry.js est chargé."""
    src = (REPO_ROOT / page).read_text(encoding="utf-8")
    assert "ui/core/consent.js" in src, f"{page} ne charge pas consent.js"


@pytest.mark.parametrize("page", PAGES)
def test_ordre_consentement_avant_emetteur(page: str):
    """consent.js pose la clé lue par telemetry.js : il doit venir avant."""
    src = (REPO_ROOT / page).read_text(encoding="utf-8")
    assert src.index("ui/core/consent.js") < src.index("ui/core/telemetry.js"), (
        f"{page} : consent.js doit être chargé avant telemetry.js"
    )
