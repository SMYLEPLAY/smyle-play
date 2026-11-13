"""Refonte de l'interface — lot 6 (pages de texte, formulaires, sous-écrans
du Board). Habillage par ui/pwa/refonte.css uniquement : aucun texte ni
aucun élément n'est modifié dans les pages. Ces tests vérifient que les
repères visés existent toujours."""
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CSS = (RACINE / "ui" / "pwa" / "refonte.css").read_text(encoding="utf-8")
LOT6 = CSS.split("LOT 6", 1)[1]


def _page(nom):
    return (RACINE / nom).read_text(encoding="utf-8")


def test_pages_de_texte_reperes_presents():
    attendus = {
        "comment-ca-marche.html": ('class="wrap"', 'class="back"', 'class="step"'),
        "legal.html": ('class="lg-top"', 'class="lg-wrap"', "lg-note"),
        "offres.html": ('class="off-wrap"', "off-card", "off-cta"),
        "tarifs.html": ('class="tarifs-wrap"', "tarifs-card", "tarifs-btn"),
        "retractation.html": ('class="rt-top"', 'class="rt-card"'),
        "reset.html": ('class="rs-top"', 'class="rs-card"'),
        "verifier-email.html": ('class="ve-top"', 'class="ve-card"'),
    }
    for page, motifs in attendus.items():
        html = _page(page)
        for motif in motifs:
            assert motif in html, (page, motif)
    for classe in (".lg-wrap", ".off-wrap", ".tarifs-wrap", ".rt-card", ".rs-card", ".ve-card"):
        assert classe in LOT6


def test_pages_d_administration_non_concernees():
    # Elles partagent « .wrap » avec « Comment ça marche » mais n'ont pas de
    # lien « .back » : le sélecteur ne doit pas les attraper.
    assert "body > .wrap:has(> .back)" in LOT6
    for page in ("gestion.html", "pret-a-sortir.html", "analytics.html"):
        assert 'class="back"' not in _page(page)


def test_sous_ecrans_du_board_par_variables():
    assert ".dash-page .dash-main" in LOT6
    board_css = (RACINE / "dashboard.css").read_text(encoding="utf-8")
    for variable in ("--d-gold", "--d-gold-dim", "--d-border", "--d-bg"):
        assert f"{variable}:" in LOT6
        assert f"{variable}:" in board_css
    assert 'class="dash-page"' in _page("dashboard.html")


def test_accolades_equilibrees():
    sans = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    assert sans.count("{") == sans.count("}")
