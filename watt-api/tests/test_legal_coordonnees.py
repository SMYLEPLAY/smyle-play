"""Les coordonnées de l'éditeur viennent de la configuration, jamais du dépôt."""
from pathlib import Path

import pytest

from app.config import settings

REPO = Path(__file__).resolve().parents[2]


def test_legal_html_ne_contient_que_des_marqueurs():
    texte = (REPO / "legal.html").read_text(encoding="utf-8")
    assert "{{EDITEUR_ADRESSE}}" in texte
    assert "{{EDITEUR_TELEPHONE}}" in texte


@pytest.mark.asyncio
async def test_legal_affiche_les_coordonnees_configurees(client, monkeypatch):
    monkeypatch.setattr(settings, "EDITEUR_ADRESSE", "1 rue <Test>, 75000 Paris")
    monkeypatch.setattr(settings, "EDITEUR_TELEPHONE", "01 23 45 67 89")
    for chemin in ("/legal", "/legal.html"):
        r = await client.get(chemin)
        assert r.status_code == 200, chemin
        assert "{{EDITEUR_" not in r.text, chemin
    assert "1 rue &lt;Test&gt;, 75000 Paris" in r.text
    assert "01 23 45 67 89" in r.text
    assert "{{EDITEUR_" not in r.text


@pytest.mark.asyncio
async def test_legal_repli_sans_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "EDITEUR_ADRESSE", "")
    monkeypatch.setattr(settings, "EDITEUR_TELEPHONE", "")
    r = await client.get("/legal")
    assert r.status_code == 200
    assert "{{EDITEUR_" not in r.text
    assert "communiqué sur simple demande" in r.text
