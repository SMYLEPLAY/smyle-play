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
