"""
S-08 sécurité (2026-09-02) — gates API du MODE LANCEMENT (audit A §M8).

Avant : `MODE_LANCEMENT` ne masquait que le front. Les routeurs `resale`,
`packs`, `trades` et `voices` étaient montés inconditionnellement — leurs
mutations d'argent (ouvrir un pack, lister/acheter une revente, créer ou
accepter une offre de troc, acheter une voix) restaient appelables en direct
avec un jeton valide. Seul `the_plan` était conditionné, mais par un montage
évalué au boot (rallumage = redéploiement).

Désormais : `require_launch_item(item)` relit `settings.launch_flags_dict()`
à chaque requête → 404 quand l'item est masqué, y compris authentifié.

DB-free pour l'essentiel : le 404 de la dépendance est levé AVANT le corps de
la route (et avant `get_current_user` pour les dépendances de routeur), donc
un appel non authentifié suffit à prouver la fermeture.
"""
import pytest

from app.config import settings

# (méthode, chemin, item de drapeau)
_GATED = [
    ("GET", "/resale/market", "resale"),
    ("POST", "/resale/prompts/00000000-0000-0000-0000-000000000001/list", "resale"),
    ("POST", "/resale/00000000-0000-0000-0000-000000000001/buy", "resale"),
    ("POST", "/packs/mystery/open", "packs"),
    ("GET", "/trades/offers/me", "troc"),
    ("POST", "/trades/offers", "troc"),
    ("GET", "/api/voices", "voix"),
    ("POST", "/unlocks/voices/00000000-0000-0000-0000-000000000001", "voix"),
    ("GET", "/products/the-plan/v1", "thePlan"),
    ("POST", "/products/the-plan/v1/buy", "thePlan"),
]

_SHOW_ATTR = {
    "resale": "SHOW_RESALE",
    "packs": "SHOW_PACKS",
    "troc": "SHOW_TROC",
    "voix": "SHOW_VOIX",
    "thePlan": "SHOW_THE_PLAN",
}


async def _call(client, method: str, path: str, headers: dict | None = None):
    return await client.request(method, path, headers=headers or {}, json={})


@pytest.mark.parametrize("method,path,item", _GATED)
async def test_route_masquee_repond_404(client, method, path, item, monkeypatch):
    """Défauts de production (MODE_LANCEMENT=True, SHOW_*=False) → 404."""
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    for attr in _SHOW_ATTR.values():
        monkeypatch.setattr(settings, attr, False)

    r = await _call(client, method, path)
    assert r.status_code == 404, (path, r.status_code, r.text[:200])
    assert "lancement" in r.json().get("detail", "").lower(), r.text[:200]


@pytest.mark.parametrize("method,path,item", _GATED)
async def test_route_masquee_repond_404_meme_authentifiee(
    client, auth_headers, method, path, item, monkeypatch
):
    """Un jeton valide ne contourne pas la gate (c'était le trou : curl + token)."""
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    for attr in _SHOW_ATTR.values():
        monkeypatch.setattr(settings, attr, False)

    r = await _call(client, method, path, auth_headers)
    assert r.status_code == 404, (path, r.status_code, r.text[:200])


@pytest.mark.parametrize("method,path,item", _GATED)
async def test_route_rallumee_nest_plus_404(client, method, path, item, monkeypatch):
    """SHOW_<ITEM>=True rallume la route sans redéploiement (≠ 404)."""
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    monkeypatch.setattr(settings, _SHOW_ATTR[item], True)

    r = await _call(client, method, path)
    # 401/403 (auth), 422 (corps vide), 200… : tout sauf le 404 de la gate.
    assert r.status_code != 404, (path, r.text[:200])


async def test_mode_lancement_off_rallume_tout(client, monkeypatch):
    """MODE_LANCEMENT=False (fin du lancement) rallume tous les items."""
    monkeypatch.setattr(settings, "MODE_LANCEMENT", False)
    for attr in _SHOW_ATTR.values():
        monkeypatch.setattr(settings, attr, False)

    for method, path, _item in _GATED:
        r = await _call(client, method, path)
        assert r.status_code != 404, (path, r.text[:200])


async def test_routes_non_gatees_restent_ouvertes(client, monkeypatch):
    """Régression : les offres ADN et le reste d'unlocks NE sont PAS gatés."""
    monkeypatch.setattr(settings, "MODE_LANCEMENT", True)
    for attr in _SHOW_ATTR.values():
        monkeypatch.setattr(settings, attr, False)

    # /adn-offers est un routeur distinct (main.py) — jamais gaté par le troc.
    r = await client.get("/adn-offers/me")
    assert r.status_code in (401, 403), r.text[:200]
    # Le catalogue public reste servi.
    r = await client.get("/catalog/adns")
    assert r.status_code == 200, r.text[:200]
