"""
Suppression d'un SON depuis le profil (02/07) — symétrie stricte avec le
delete image (routers/images.py) :

  DELETE /tracks/{uuid} (soft) doit :
    1. masquer le track (is_deleted=True) ;
    2. retirer sa recette liée de la vente (is_deleted + is_published=False) —
       les acheteurs gardent leur UnlockedPrompt ;
    3. détacher l'œuvre complète : le partenaire VISUEL survivant perd
       bundle_exclusive et redevient visible/vendable individuellement
       (jamais de produit fantôme).

L'ancien chemin front (/watt/tracks/<id>, hard delete DB+R2 porté du Flask)
est abandonné par artiste.js au profit de cet endpoint.
"""

import uuid as _uuid
from typing import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.track import Track


@pytest_asyncio.fixture(loop_scope="session")
async def oeuvre_son(test_user: dict) -> AsyncIterator[dict]:
    """Track + recette liée + image partenaire (œuvre née-ensemble)."""
    recipe_id, image_id, track_id = _uuid.uuid4(), _uuid.uuid4(), _uuid.uuid4()
    async with SessionLocal() as db:
        db.add(Prompt(
            id=recipe_id,
            artist_id=test_user["id"],
            title="Recette du son test",
            prompt_text="x" * 120,
            product_type="recipe",
            price_credits=10,
            is_published=True,
            linked_prompt_id=image_id,
            bundle_exclusive=True,
        ))
        db.add(Prompt(
            id=image_id,
            artist_id=test_user["id"],
            title="Cover du son test",
            prompt_text="a neon jungle at dusk",
            product_type="image",
            price_credits=40,
            is_published=True,
            image_platform="chatgpt",
            image_model_version="gpt-image-1",
            linked_prompt_id=recipe_id,
            bundle_exclusive=True,
        ))
        db.add(Track(
            id=track_id,
            title="Son à supprimer",
            artist_id=test_user["id"],
            prompt_id=recipe_id,
        ))
        await db.commit()
    yield {"track_id": track_id, "recipe_id": recipe_id, "image_id": image_id}
    async with SessionLocal() as db:
        await db.execute(delete(Track).where(Track.id == track_id))
        await db.execute(
            delete(Prompt).where(Prompt.id.in_([recipe_id, image_id]))
        )
        await db.commit()


async def test_delete_son_is_symmetric_with_image_delete(
    client: AsyncClient, auth_headers: dict, oeuvre_son: dict
):
    resp = await client.delete(
        f"/tracks/{oeuvre_son['track_id']}", headers=auth_headers
    )
    assert resp.status_code == 204, resp.text

    async with SessionLocal() as db:
        track = (await db.execute(
            select(Track).where(Track.id == oeuvre_son["track_id"])
        )).scalar_one()
        recipe = (await db.execute(
            select(Prompt).where(Prompt.id == oeuvre_son["recipe_id"])
        )).scalar_one()
        image = (await db.execute(
            select(Prompt).where(Prompt.id == oeuvre_son["image_id"])
        )).scalar_one()

    # 1. le son est masqué
    assert track.is_deleted is True
    # 2. la recette est retirée de la vente
    assert recipe.is_deleted is True
    assert recipe.is_published is False
    # 3. l'œuvre est détachée des DEUX côtés, le visuel survivant est libéré
    assert recipe.linked_prompt_id is None
    assert image.linked_prompt_id is None
    assert image.bundle_exclusive is False
    assert image.is_deleted is False
    assert image.is_published is True


async def test_delete_son_requires_owner(
    client: AsyncClient, oeuvre_son: dict
):
    """Sans auth → pas de suppression (401/403)."""
    resp = await client.delete(f"/tracks/{oeuvre_son['track_id']}")
    assert resp.status_code in (401, 403)
