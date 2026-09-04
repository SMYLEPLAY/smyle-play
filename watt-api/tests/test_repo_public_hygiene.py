"""Hygiène du dépôt PUBLIC — aucun artefact personnel ne doit y revenir.

Le dépôt `SMYLEPLAY/smyle-play` est public, et le reste (décision du 02/08 :
sur GitHub Free, la protection de branche n'existe QUE sur les dépôts publics —
le passer en privé désactiverait la protection de `main`). La contrepartie est
que l'hygiène doit être vérifiée par un test, pas par la vigilance.

Ce test garde trois choses hors du dépôt : les chemins personnels, les
fichiers de configuration de la machine de Tom, et les documents internes.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Ce fichier CONTIENT le motif qu'il traque (la chaine cherchee plus bas est
# ecrite en clair dans le code du test). Sans cette exclusion, le garde-fou se
# denonce lui-meme et la CI est rouge en permanence. On s'exclut donc du scan :
# c'est le seul fichier du depot ou le motif est legitime.
_CE_FICHIER = Path(__file__).resolve()

_SKIP_DIRS = {
    ".git", "venv", ".venv", "node_modules", "__pycache__", "OBSIDIAN",
    ".pytest_cache", "_masters_backup", "_d2wt", ".relay", ".watcher-logs",
}
_TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".html", ".css", ".md", ".txt", ".json", ".yml",
    ".yaml", ".toml", ".sh", ".cfg", ".ini",
}


def _fichiers_texte():
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in p.relative_to(REPO_ROOT).parts):
            continue
        if p.resolve() == _CE_FICHIER:
            continue
        yield p


def test_aucun_chemin_personnel():
    """Un chemin /Users/<qqun>/ dans un dépôt public dit à tout le monde
    comment est rangée la machine du mainteneur."""
    fautifs = []
    for p in _fichiers_texte():
        try:
            if "/Users/" in p.read_text(encoding="utf-8", errors="ignore"):
                fautifs.append(str(p.relative_to(REPO_ROOT)))
        except OSError:
            continue
    assert not fautifs, f"chemins personnels exposés : {fautifs}"


@pytest.mark.parametrize(
    "motif",
    ["*.plist", "LIGNE_TERMINAL_*.txt", "AUDIT_*.md"],
)
def test_aucun_artefact_machine(motif: str):
    """Agents launchd, transcrits de terminal, audits internes : hors dépôt."""
    trouves = [
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.glob(motif)
        if p.is_file()
    ]
    assert not trouves, f"artefacts à sortir du dépôt public : {trouves}"


# F-03 (2026-09-02) : python-jose (CVE-2024-33663/33664) a été remplacé par
# PyJWT le 2026-07 (app/auth/jwt.py) mais restait déclaré dans
# watt-api/pyproject.toml — un `pip install ./watt-api` aurait réinstallé une
# bibliothèque vulnérable. Les trois fichiers de dépendances ne doivent plus
# jamais la mentionner.
_FICHIERS_DEPENDANCES = (
    "watt-api/pyproject.toml",
    "requirements.in",
    "requirements.txt",
)


@pytest.mark.parametrize("fichier", _FICHIERS_DEPENDANCES)
def test_aucune_dependance_python_jose(fichier: str):
    chemin = REPO_ROOT / fichier
    assert chemin.is_file(), f"{fichier} introuvable"
    contenu = chemin.read_text(encoding="utf-8").lower()
    assert "jose" not in contenu, f"python-jose encore référencé dans {fichier}"


def test_pyproject_declare_pyjwt_et_les_dependances_reellement_importees():
    """pyproject.toml aligné sur requirements.in : le code importe jwt (PyJWT),
    boto3 (R2), slowapi (rate-limit), pydub (audio) et bcrypt (mots de passe)."""
    contenu = (REPO_ROOT / "watt-api/pyproject.toml").read_text(encoding="utf-8").lower()
    for dep in ("pyjwt", "boto3", "slowapi", "pydub", "bcrypt"):
        assert dep in contenu, f"{dep} absent de watt-api/pyproject.toml"
