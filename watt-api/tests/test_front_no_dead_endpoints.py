"""Garde-fou « aucune route morte appelée par le front » — K-04 (2026-09-04).

Deux familles de chemins morts avaient survécu dans le JS (annexe B §M5, §M17,
bugs B1 et B13) :

  - `POST /unlocks/oeuvre/{id}` : cette route n'a jamais existé. Le routeur
    `app/routers/unlocks.py` n'expose que `/prompts`, `/adns`, `/voices`,
    `/playlist-adn`, `/visual-adns` et `/album-adn`. L'utilisateur confirmait
    un prix remisé « −10 % » calculé côté client, puis recevait « Achat de
    l'œuvre impossible ». L'achat groupé réel est
    `POST /watt/oeuvre/{slug}/buy-complete` (prix calculé serveur).
  - les unlocks directs d'ADN (`/unlocks/adns/`, `/unlocks/visual-adns/`,
    `/unlocks/playlist-adn/`) répondent **410 Gone** depuis la doctrine « ADN
    uniquement sur offre » : ils ne subsistaient qu'en repli, atteints si
    `AdnOfferModal` n'était pas chargé — un repli mort qui affichait un
    message technique.

Le test est statique (aucune DB) : il refuse toute réapparition de ces
chemins dans un littéral de chaîne du front. Les commentaires ne sont pas
concernés — c'est l'APPEL qui est interdit, pas la mémoire de l'incident —
mais aucun d'eux ne cite le chemin entre guillemets, donc la règle est
simplement « la sous-chaîne ne doit plus apparaître du tout ».
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_SKIP_DIRS = {
    ".git", "venv", ".venv", "node_modules", "__pycache__", "OBSIDIAN",
    ".pytest_cache", "_masters_backup", "_d2wt", ".relay", ".watcher-logs",
    "e2e", "graphify-out", "watt-api", "scripts", "data",
}

# Routes que le front ne doit plus appeler : inexistante (oeuvre) ou 410 Gone.
_ROUTES_MORTES = (
    "/unlocks/oeuvre/",
    "/unlocks/adns/",
    "/unlocks/visual-adns/",
    "/unlocks/playlist-adn/",
)


def _fichiers_js():
    """`ui/**/*.js` + JS à la racine (artiste.js, dashboard.js, library.js…)."""
    for p in list(REPO_ROOT.glob("*.js")) + list((REPO_ROOT / "ui").rglob("*.js")):
        if not p.is_file() or p.name.endswith(".min.js"):
            continue
        rel = p.relative_to(REPO_ROOT)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        yield p


def test_scan_couvre_le_front():
    """Sans les fichiers de portée, le garde-fou ne garderait rien."""
    noms = {str(p.relative_to(REPO_ROOT)) for p in _fichiers_js()}
    for attendu in ("artiste.js", "ui/hub/marketplace.js", "ui/modals/purchase-drawer.js"):
        assert attendu in noms, f"{attendu} absent du scan"


@pytest.mark.parametrize("route", _ROUTES_MORTES)
def test_aucune_route_morte_dans_le_front(route: str):
    fautifs = []
    for p in _fichiers_js():
        src = p.read_text(encoding="utf-8", errors="ignore")
        for n, ligne in enumerate(src.splitlines(), 1):
            if route in ligne:
                fautifs.append(f"{p.relative_to(REPO_ROOT)}:{n}")
    assert not fautifs, (
        f"route morte `{route}` encore référencée par le front : {fautifs} — "
        "l'achat groupé passe par POST /watt/oeuvre/{slug}/buy-complete, "
        "les ADN par POST /adn-offers"
    )


def test_types_adn_routes_vers_la_modale_d_offre():
    """Le drawer ne doit pas retomber sur 'son' pour un type « offre seule ».

    Les trois types ADN ne sont plus dans `ENDPOINTS` : sans le test
    `_knownType`, `open({type:'adn-artist'})` serait requalifié en 'son' et
    déclencherait un achat direct sur un identifiant d'ADN.
    """
    src = (REPO_ROOT / "ui/modals/purchase-drawer.js").read_text(encoding="utf-8")
    assert "function _knownType(t)" in src, "purchase-drawer.js : _knownType absent"
    assert "var type  = _knownType(opts.type) ? opts.type : 'son';" in src, (
        "purchase-drawer.js : le repli de type ne consulte plus OFFER_ONLY_TYPES"
    )
    for t in ("'playlist'", "'visual-adn'", "'adn-artist'"):
        assert t in src.split("var OFFER_ONLY_TYPES = {", 1)[1][:400], (
            f"purchase-drawer.js : {t} n'est plus routé vers AdnOfferModal"
        )
