"""Lot G — la page /legal annonce ce que le code fait (remises acheteur,
Pionnier « quand le programme est ouvert », outil et version obligatoires,
journaux techniques, purge des signalements à 3 ans)."""
import re
from pathlib import Path

from app.core.legal import SIGNALEMENTS_RETENTION_ANS
from app.services.credits import compute_effective_price, compute_split
from app.services.oeuvre_c4_purchase import OEUVRE_DISCOUNT_PCT, oeuvre_bundle_price

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL = (REPO_ROOT / "legal.html").read_text(encoding="utf-8")
TEXTE = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", LEGAL))


def test_remises_acheteur_annoncees_et_justes():
    # −30 % (ADN de l'artiste), −20 % (ADN de playlist), cumul ; remise de
    # l'Œuvre choisie par le créateur (0, 10 ou 20 %, 10 par défaut).
    assert compute_effective_price(100, True) == 70
    assert compute_effective_price(100, False, True) == 80
    assert compute_effective_price(100, True, True) == 56
    assert OEUVRE_DISCOUNT_PCT == 10 and oeuvre_bundle_price(50, 50)[0] == 90
    for t in ("−30 %", "−20 %", "−44 %", "0, 10 ou 20 %"):
        assert t in TEXTE, t
    from app.services.oeuvre_c4_purchase import REMISES_OEUVRE
    assert REMISES_OEUVRE == (0, 10, 20)
    assert "Ta part et la commission sont calculées sur le prix réellement payé" in TEXTE
    # L'exemple chiffré correspond au code.
    paye = compute_effective_price(30, True)
    part, commission = compute_split(paye)
    assert (paye, part, commission) == (21, 16, 5)
    assert "lui coûte 21 Smyles ; tu reçois 16 Smyles (au lieu de 24) et WATT 5" in TEXTE


def test_resume_pionnier_quand_le_programme_est_ouvert():
    resume = LEGAL[LEGAL.index('id="resume"'):LEGAL.index('class="lg-toc"')]
    assert "quand le programme est ouvert" in resume


def test_outil_et_version_obligatoires():
    assert "obligatoirement l'outil d'IA utilisé et sa version" in TEXTE
    assert "les indiquer est obligatoire pour publier un son" in TEXTE


def test_journaux_techniques_et_ip():
    assert "Journaux techniques" in TEXTE and "l'adresse IP" in TEXTE
    assert "Journaux techniques et d'erreurs (dont l'adresse IP) : 90 jours au plus" in TEXTE


def test_purge_des_signalements_annoncee():
    assert SIGNALEMENTS_RETENTION_ANS == 3
    assert f"{SIGNALEMENTS_RETENTION_ANS} ans après la décision" in TEXTE
    assert "supprimés automatiquement" in TEXTE


def test_contenu_retire_coupe_pour_tous():
    assert "n'est plus accessible à personne, acheteurs compris" in TEXTE
    assert "gardent leur accès" in TEXTE  # hors retrait, l'accès reste acquis


def test_marqueurs_editeur_intacts():
    assert LEGAL.count("{{EDITEUR_ADRESSE}}") == 3
    assert LEGAL.count("{{EDITEUR_TELEPHONE}}") == 2
