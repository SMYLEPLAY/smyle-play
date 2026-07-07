"""
Binarité cartes (07/07) — /watt/tracks-recent expose la face visuelle.

Vérifie que le payload des cards son porte :
  - linkedImage {id, previewKey, priceCredits, imagePlatform, bundleExclusive}
    quand le prompt du son est lié à une image PUBLIÉE (œuvre),
  - linkedImage = None sinon (et jamais de fuite d'image dépubliée),
  - isOeuvreComplete cohérent.

REQUIRES : Postgres réel via DATABASE_URL (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user


async def _mk_artist() -> uuid.UUID:
    email = f"pytest-binar-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE users SET profile_public = TRUE, artist_name = 'BinarTest' "
            "WHERE id = :u"), {"u": uid})
        await db.commit()
    return uid


async def _mk_son_image_track(artist_id, *, image_published=True):
    async with SessionLocal() as db:
        img = Prompt(
            artist_id=artist_id,
            title=f"Image {uuid.uuid4().hex[:6]}",
            description="Tagline",
            prompt_text="X" * 100,
            price_credits=40,
            is_published=image_published,
            product_type="image",
            image_platform="chatgpt",
            image_model_version="gpt-4o",
        )
        son = Prompt(
            artist_id=artist_id,
            title=f"Son {uuid.uuid4().hex[:6]}",
            description="Tagline",
            prompt_text="X" * 100,
            price_credits=30,
            is_published=True,
        )
        db.add_all([img, son])
        await db.flush()
        son.linked_prompt_id = img.id
        img.linked_prompt_id = son.id
        tr = Track(
            artist_id=artist_id,
            title=f"Track {uuid.uuid4().hex[:6]}",
            prompt_id=son.id,
        )
        db.add(tr)
        await db.commit()
        return son.id, img.id, tr.id


async def _cleanup(artist_id, track_ids):
    async with SessionLocal() as db:
        from app.models.dna import DNA
        await db.execute(delete(Track).where(Track.id.in_(track_ids)))
        await db.execute(delete(DNA).where(DNA.artist_id == artist_id))
        await db.execute(delete(Prompt).where(Prompt.artist_id == artist_id))
        await db.execute(delete(User).where(User.id == artist_id))
        await db.commit()


async def test_tracks_recent_linked_image(client):
    artist = await _mk_artist()
    son_id, img_id, tr_id = await _mk_son_image_track(artist)
    try:
        r = await client.get("/watt/tracks-recent?limit=100")
        assert r.status_code == 200, r.text
        tracks = r.json()["tracks"]
        mine = [t for t in tracks if t.get("promptId") == str(son_id)]
        assert mine, "Track de test absent du payload"
        li = mine[0].get("linkedImage")
        assert li is not None, "linkedImage manquant sur un son lié"
        assert li["id"] == str(img_id)
        assert li["priceCredits"] == 40
        assert li["imagePlatform"] == "chatgpt"
        assert mine[0]["isOeuvreComplete"] is True
    finally:
        await _cleanup(artist, [tr_id])


async def test_tracks_recent_no_leak_unpublished_image(client):
    artist = await _mk_artist()
    son_id, _img_id, tr_id = await _mk_son_image_track(
        artist, image_published=False
    )
    try:
        r = await client.get("/watt/tracks-recent?limit=100")
        assert r.status_code == 200, r.text
        tracks = r.json()["tracks"]
        mine = [t for t in tracks if t.get("promptId") == str(son_id)]
        assert mine, "Track de test absent du payload"
        assert mine[0].get("linkedImage") is None, (
            "Une image dépubliée ne doit pas fuiter dans linkedImage"
        )
        assert mine[0]["isOeuvreComplete"] is False
    finally:
        await _cleanup(artist, [tr_id])
