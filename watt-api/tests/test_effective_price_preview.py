"""
FIX 1 — L'aperçu de prix (get_effective_price_for_prompt) doit renvoyer le
MÊME `paid` que le débit réel (unlock_prompt_atomic), c'est-à-dire appliquer
la PYRAMIDE ADN complète : perk profil -30% ET perk playlist -20% en cascade.

Avant le fix, l'aperçu n'appliquait que le perk profil → prix affiché faux
(supérieur au prix réellement débité) quand l'acheteur possédait aussi l'ADN
d'une playlist contenant le son.

Test sans DB : on monkeypatche les trois services importés dans le namespace
du router (get_public_prompt + les deux vérifs de possession) et on vérifie
que le `paid` de l'aperçu == compute_effective_price(base, True, True).
"""
import uuid

import pytest

import app.routers.catalog as catalog
from app.services.credits import compute_effective_price


class _FakeUser:
    def __init__(self, uid):
        self.id = uid


@pytest.mark.asyncio
async def test_preview_applique_les_deux_perks(monkeypatch):
    prompt_id = uuid.uuid4()
    buyer_id = uuid.uuid4()
    artist_id = uuid.uuid4()
    base_price = 80

    async def _fake_get_public_prompt(db, pid):
        return {
            "price_credits": base_price,
            "artist": {"id": artist_id},
        }

    async def _fake_owns_artist_adn(db, *, user_id, artist_id):
        return True

    async def _fake_owns_playlist_adn(db, *, user_id, prompt_id):
        return True

    monkeypatch.setattr(catalog, "get_public_prompt", _fake_get_public_prompt)
    monkeypatch.setattr(catalog, "user_owns_artist_adn", _fake_owns_artist_adn)
    monkeypatch.setattr(
        catalog, "user_owns_playlist_adn_for_prompt", _fake_owns_playlist_adn
    )

    res = await catalog.get_effective_price_for_prompt(
        prompt_id=prompt_id, current_user=_FakeUser(buyer_id), db=None
    )

    # Cascade -30% puis -20% : 80 → 56 → 44 (cf. compute_effective_price docstring).
    expected = compute_effective_price(base_price, True, True)
    assert expected == 44
    assert res.paid == expected
    assert res.base_price == base_price
    assert res.perk_applied is True


@pytest.mark.asyncio
async def test_preview_perk_playlist_seul(monkeypatch):
    prompt_id = uuid.uuid4()
    buyer_id = uuid.uuid4()
    artist_id = uuid.uuid4()
    base_price = 50

    async def _fake_get_public_prompt(db, pid):
        return {"price_credits": base_price, "artist": {"id": artist_id}}

    async def _fake_owns_artist_adn(db, *, user_id, artist_id):
        return False

    async def _fake_owns_playlist_adn(db, *, user_id, prompt_id):
        return True

    monkeypatch.setattr(catalog, "get_public_prompt", _fake_get_public_prompt)
    monkeypatch.setattr(catalog, "user_owns_artist_adn", _fake_owns_artist_adn)
    monkeypatch.setattr(
        catalog, "user_owns_playlist_adn_for_prompt", _fake_owns_playlist_adn
    )

    res = await catalog.get_effective_price_for_prompt(
        prompt_id=prompt_id, current_user=_FakeUser(buyer_id), db=None
    )

    # -20% seul : 50 → 40.
    assert res.paid == compute_effective_price(base_price, False, True) == 40
