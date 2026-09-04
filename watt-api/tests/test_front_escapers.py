"""Garde-fou XSS front — S-01 (2026-09-04), plan de finition sécurité.

Le front vanilla construit son HTML en `innerHTML` avec des gabarits, et
chaque module porte son propre échappeur local. L'audit du 02/09 (annexe A
§B1, §B2, « Autres injections ») a trouvé quatre XSS stockés qui reposaient
tous sur le même défaut : un échappeur qui ne traite pas les guillemets.

    - `div.textContent = s; return div.innerHTML` n'échappe que & < > : une
      valeur posée dans un attribut (`src="…"`, `onclick="…('…')"`) en sort
      avec un simple `"` ou `'`.
    - `String(s).replace(/</g, '&lt;')` seul : même chose, en pire.
    - certaines interpolations n'appelaient aucun échappeur (`src="${p.audio_url}"`,
      `${track.name}`).

Ce test parcourt `ui/**/*.js` et les JS racine (comme
`test_repo_public_hygiene.py`) et refuse ces trois formes. La référence à
copier est `ui/albums.js` : `& < > " ' \\`` → entités.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_SKIP_DIRS = {
    ".git", "venv", ".venv", "node_modules", "__pycache__", "OBSIDIAN",
    ".pytest_cache", "_masters_backup", "_d2wt", ".relay", ".watcher-logs",
    "e2e", "graphify-out", "watt-api", "scripts", "data",
}

# Échappeur « textContent → innerHTML » : n'échappe pas les guillemets.
_RE_TEXTCONTENT_ESCAPER = re.compile(
    r"createElement\(\s*['\"]div['\"]\s*\)[^;]*;\s*"
    r"\w+\.textContent\s*=[^;]*;\s*"
    r"return\s+\w+\.innerHTML",
    re.DOTALL,
)

# Échappeur dont le corps est UNIQUEMENT `.replace(/</g, '&lt;')`
# (ex. `const esc = (s) => String(s == null ? '' : s).replace(/</g, '&lt;');`).
_RE_LT_ONLY_ESCAPER = re.compile(
    r"(?:const|let|var)\s+_?esc\w*\s*=\s*\(?\s*\w+\s*\)?\s*=>\s*"
    r"String\([^;]*?\)\.replace\(/</g,\s*['\"]&lt;['\"]\)\s*;"
)

# Interpolations brutes qui ont servi de vecteur (annexe A §B2, injection #7),
# en contexte HTML : attribut (`src="${…}"`) ou nœud texte (`>${track.name}<`).
# Un `${track.name}` passé à showToast (textContent) n'est pas concerné.
_RAW_INTERPOLATIONS = (
    r'src="\$\{p\.audio_url\}"',
    r'src="\$\{p\.preview_url\}"',
    r"[>\"']\$\{track\.name\}",
)


def _fichiers_js():
    """`ui/**/*.js` + JS à la racine du dépôt (artiste.js, dashboard.js…)."""
    seen = set()
    for p in list(REPO_ROOT.glob("*.js")) + list((REPO_ROOT / "ui").rglob("*.js")):
        if not p.is_file():
            continue
        rel = p.relative_to(REPO_ROOT)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if p.name.endswith(".min.js") or p in seen:
            continue
        seen.add(p)
        yield p


def _lire(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def test_scan_couvre_le_front():
    """Le parcours doit voir les fichiers de portée de S-01 (sinon le garde-fou
    ne garde rien)."""
    noms = {str(p.relative_to(REPO_ROOT)) for p in _fichiers_js()}
    for attendu in (
        "artiste.js", "library.js", "ui/hub/marketplace.js",
        "ui/topbar/topbar.js", "ui/messaging/messaging.js", "ui/core/trade-view.js",
    ):
        assert attendu in noms, f"{attendu} absent du scan : {sorted(noms)[:10]}…"


def test_aucun_echappeur_textcontent_innerhtml():
    """`div.textContent → innerHTML` laisse passer `"` et `'` : interdit."""
    fautifs = []
    for p in _fichiers_js():
        src = _lire(p)
        for m in _RE_TEXTCONTENT_ESCAPER.finditer(src):
            ligne = src.count("\n", 0, m.start()) + 1
            fautifs.append(f"{p.relative_to(REPO_ROOT)}:{ligne}")
    assert not fautifs, (
        "échappeur textContent→innerHTML (n'échappe pas les guillemets) : "
        f"{fautifs} — copier ui/albums.js:_esc"
    )


def test_aucun_echappeur_lt_seul():
    """Un échappeur réduit à `.replace(/</g, '&lt;')` n'en est pas un."""
    fautifs = []
    for p in _fichiers_js():
        src = _lire(p)
        for m in _RE_LT_ONLY_ESCAPER.finditer(src):
            ligne = src.count("\n", 0, m.start()) + 1
            fautifs.append(f"{p.relative_to(REPO_ROOT)}:{ligne}")
    assert not fautifs, (
        f"échappeur `replace(/</g,'&lt;')` seul : {fautifs} — copier ui/albums.js:_esc"
    )


@pytest.mark.parametrize("motif", _RAW_INTERPOLATIONS)
def test_aucune_interpolation_brute(motif: str):
    """Les vecteurs identifiés par l'audit ne doivent pas réapparaître bruts."""
    rx = re.compile(motif)
    fautifs = []
    for p in _fichiers_js():
        src = _lire(p)
        for m in rx.finditer(src):
            ligne = src.count("\n", 0, m.start()) + 1
            fautifs.append(f"{p.relative_to(REPO_ROOT)}:{ligne}")
    assert not fautifs, f"interpolation brute `{motif}` : {fautifs}"


def test_echappeurs_de_reference_complets():
    """Les échappeurs des fichiers de portée S-01 traitent bien `"` et `'`
    (la forme exacte importe peu : entités présentes dans le corps)."""
    attendus = {
        "ui/hub/marketplace.js": r"function _esc\(s\)",
        "library.js": r"function esc\(s\)",
        "ui/core/page-services.js": r"function _esc\(s\)",
        "ui/messaging/messaging.js": r"function _esc\(s\)",
        "ui/topbar/topbar.js": r"function _esc\(s\)",
        "ui/core/dom.js": r"function _esc\(s\)",
        "ui/core/trade-view.js": r"const _esc = ",
    }
    for rel, tete in attendus.items():
        src = _lire(REPO_ROOT / rel)
        m = re.search(tete, src)
        assert m, f"{rel} : échappeur `{tete}` introuvable"
        corps = src[m.start(): m.start() + 600]
        assert "&quot;" in corps and "&#39;" in corps, (
            f"{rel} : l'échappeur n'échappe pas `\"` et `'` — copier ui/albums.js:_esc"
        )
