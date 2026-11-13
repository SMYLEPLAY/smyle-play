"""Refonte — premiers retours après ouverture de l'interrupteur.

· Deux mondes, deux couleurs : musique en violet, visuel en bleu (Board,
  Bibliothèque, accueil).
· Le bloc de l'accueil affiche la photo de couverture de SMYLE si elle existe.
· Couverture par défaut du profil plus visible."""
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CSS = (RACINE / "ui" / "pwa" / "refonte.css").read_text(encoding="utf-8")
JS = (RACINE / "ui" / "refonte" / "accueil.js").read_text(encoding="utf-8")


def test_deux_mondes_deux_couleurs():
    assert "--rf-bleu: #0055ff" in CSS and "--rf-violet: #8800ff" in CSS
    assert '#wb3-board[data-monde="visuel"] { --rf-monde: var(--rf-bleu)' in CSS
    assert '.wb3-monde-btn.is-active[data-monde="audio"]' in CSS
    assert '.wb3-monde-btn.is-active[data-monde="visuel"]' in CSS
    assert '.lib-mode-btn.is-active[data-mode="image"]' in CSS
    assert '.mp-mode-btn.is-active[data-mode="image"]' in CSS


def test_les_reperes_de_monde_existent_dans_le_site():
    assert 'data-monde="visuel"' in (RACINE / "wattboard-v3.css").read_text(encoding="utf-8")
    assert 'class="lib-mode-btn" data-mode="image"' in (RACINE / "library.html").read_text(encoding="utf-8")
    assert 'class="mp-mode-btn" data-mode="image"' in (RACINE / "index.html").read_text(encoding="utf-8")


def test_couverture_de_smyle_sur_l_accueil():
    assert "fetch('/watt/artists/smyle')" in JS
    assert "couverture(couvSmyle)" in JS


def test_couverture_par_defaut_du_profil():
    assert ".ap-page .ap-hero-banner:not(.has-image)::before" in CSS
