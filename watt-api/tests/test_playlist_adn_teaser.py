"""
Chantier C (02/07) — teaser public de l'ADN Playlist + fuite du génome.

Deux règles verrouillées ici :

1. FUITE (P0, corrigée) : GET /watt/users/{slug}/playlists (page artiste
   publique) sérialisait PlaylistRead avec seed_prompt intact — le génome
   d'un ADN EN VENTE était lisible sans achat, en violation de la règle
   « prompts jamais visibles sans achat ». Désormais : seed_prompt=None sur
   cette route dès que adn_for_sale=True (même règle que la fiche publique
   /watt/playlists/{id}).

2. TEASER : dna_description (parité ADN Album) circule de bout en bout —
   POST/PATCH owner → exposé publiquement comme teaser (lui, il est fait
   pour être vu avant achat).
"""

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select, update

from app.database import SessionLocal
from app.models.playlist import Playlist
from app.models.user import User
from app.routers.watt_compat import _derive_artist_slug


@pytest_asyncio.fixture(loop_scope="session")
async def published_user(test_user: dict) -> AsyncIterator[dict]:
    """User publié (gate profile_public) avec un artist_name sluggable."""
    async with SessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.id == test_user["id"])
            .values(profile_public=True, artist_name="Teaser Adn Artist")
        )
        await db.commit()
        user = (await db.execute(
            select(User).where(User.id == test_user["id"])
        )).scalar_one()
        slug = _derive_artist_slug(user)
    yield {**test_user, "slug": slug}
    async with SessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.id == test_user["id"])
            .values(profile_public=False, artist_name=None)
        )
        await db.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def adn_playlist(
    client: AsyncClient, auth_headers: dict, published_user: dict
) -> AsyncIterator[dict]:
    """Playlist publique avec ADN en vente (génome + teaser), via l'API."""
    resp = await client.post(
        "/playlists",
        json={
            "title": "Univers Teaser",
            "visibility": "public",
            "seed_prompt": "GENOME-SECRET-NE-JAMAIS-LEAKER",
            "adn_for_sale": True,
            "adn_price": 300,
            "dna_description": "Un monde néon, chaud et nocturne.",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    yield data
    async with SessionLocal() as db:
        await db.execute(delete(Playlist).where(Playlist.id == data["id"]))
        await db.commit()


async def test_public_slug_listing_never_leaks_genome(
    client: AsyncClient, published_user: dict, adn_playlist: dict
):
    """ADN en vente → seed_prompt ABSENT du listing public, teaser présent."""
    resp = await client.get(f"/watt/users/{published_user['slug']}/playlists")
    assert resp.status_code == 200, resp.text
    items = [p for p in resp.json() if p["id"] == adn_playlist["id"]]
    assert items, "la playlist publique doit apparaître sur le profil"
    pl = items[0]
    assert pl["seed_prompt"] is None
    assert "GENOME-SECRET" not in resp.text
    assert pl["dna_description"] == "Un monde néon, chaud et nocturne."
    assert pl["adn_price"] == 300


async def test_seed_still_free_when_adn_not_for_sale(
    client: AsyncClient, auth_headers: dict, published_user: dict, adn_playlist: dict
):
    """Règle existante conservée : ADN pas en vente → seed libre (public)."""
    resp = await client.patch(
        f"/playlists/{adn_playlist['id']}",
        json={"adn_for_sale": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(f"/watt/users/{published_user['slug']}/playlists")
    pl = [p for p in resp.json() if p["id"] == adn_playlist["id"]][0]
    assert pl["seed_prompt"] == "GENOME-SECRET-NE-JAMAIS-LEAKER"
    # remet en vente pour ne pas polluer les autres tests
    await client.patch(
        f"/playlists/{adn_playlist['id']}",
        json={"adn_for_sale": True, "adn_price": 300},
        headers=auth_headers,
    )


async def test_owner_patch_and_read_dna_description(
    client: AsyncClient, auth_headers: dict, adn_playlist: dict
):
    """PATCH owner met à jour le teaser ; l'owner garde la vue génome."""
    resp = await client.patch(
        f"/playlists/{adn_playlist['id']}",
        json={"dna_description": "Teaser v2 — plus sombre."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["dna_description"] == "Teaser v2 — plus sombre."
    resp = await client.get(
        f"/playlists/{adn_playlist['id']}", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dna_description"] == "Teaser v2 — plus sombre."
    assert body["seed_prompt"] == "GENOME-SECRET-NE-JAMAIS-LEAKER"


async def test_teaser_length_bounded(
    client: AsyncClient, auth_headers: dict, adn_playlist: dict
):
    """dna_description > 2000 chars → 422 (borne miroir de l'ADN Album)."""
    resp = await client.patch(
        f"/playlists/{adn_playlist['id']}",
        json={"dna_description": "x" * 2001},
        headers=auth_headers,
    )
    assert resp.status_code == 422
