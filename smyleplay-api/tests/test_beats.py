"""
Beats (Phase 2 Marketplace VF, 2026-06-09).

Couvre :
  - création d'un beat SANS ADN (différence clé avec les recettes) ;
  - exclusif → max_supply forcé à 1, retiré de la vente (is_published=False)
    à l'achat, et 2e acheteur refusé (stock-out) ;
  - lease → reste publié, plusieurs acheteurs possibles ;
  - téléchargement gaté : 403 pour un non-acheteur, 404 pour un beat inexistant.

Niveau service (SessionLocal) + un test HTTP pour le gate de download.
Postgres requis (cf. conftest).
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.beats import create_beat
from app.services.pack_purchase import buy_pack_atomic
from app.services.unlocks import PromptNotPurchasable, unlock_prompt_atomic
from app.services.users import create_user


async def _make_user(initial_balance: int = 1000) -> uuid.UUID:
    email = f"pytest-beat-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = user.id
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET credits_balance = :b WHERE id = :u"),
            {"b": initial_balance, "u": uid},
        )
        await db.commit()
    return uid


async def _make_beat(artist_id, license_type, max_supply=None, is_published=True) -> uuid.UUID:
    async with SessionLocal() as db:
        beat = await create_beat(
            db,
            artist_id=artist_id,
            title=f"Beat {uuid.uuid4().hex[:8]}",
            description="prod by test",
            price_credits=10,
            license_type=license_type,
            max_supply=max_supply,
            is_published=is_published,
        )
        bid = beat.id
        await db.commit()
        return bid


async def _beat(beat_id):
    async with SessionLocal() as db:
        return await db.get(Prompt, beat_id)


async def _cleanup(beat_id, *uids):
    async with SessionLocal() as db:
        await db.execute(delete(Prompt).where(Prompt.id == beat_id))
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def test_create_beat_requires_no_adn():
    """Un beat se crée sans ADN (contrairement aux recettes)."""
    artist = await _make_user()
    beat_id = await _make_beat(artist, license_type="lease")
    try:
        b = await _beat(beat_id)
        assert b is not None
        assert b.product_type == "beat"
        assert b.prompt_text is None       # un beat n'a pas de prompt
        assert b.license_type == "lease"
    finally:
        await _cleanup(beat_id, artist)


async def test_exclusive_beat_forces_supply_one_and_unpublishes_on_purchase():
    artist = await _make_user()
    buyer1 = await _make_user()
    buyer2 = await _make_user()
    beat_id = await _make_beat(artist, license_type="exclusive", is_published=True)
    try:
        # Exclusif → max_supply forcé à 1.
        b = await _beat(beat_id)
        assert b.max_supply == 1

        # 1er acheteur OK → le beat est retiré de la vente.
        async with SessionLocal() as db:
            await unlock_prompt_atomic(db, buyer_id=buyer1, prompt_id=beat_id)
            await db.commit()
        b = await _beat(beat_id)
        assert b.is_published is False, "un beat exclusif doit être retiré après l'achat"

        # 2e acheteur refusé (stock-out 1/1).
        with pytest.raises(PromptNotPurchasable):
            async with SessionLocal() as db:
                await unlock_prompt_atomic(db, buyer_id=buyer2, prompt_id=beat_id)
                await db.commit()
    finally:
        await _cleanup(beat_id, artist, buyer1, buyer2)


async def test_lease_beat_stays_published_and_allows_multiple_buyers():
    artist = await _make_user()
    buyer1 = await _make_user()
    buyer2 = await _make_user()
    beat_id = await _make_beat(artist, license_type="lease", max_supply=None, is_published=True)
    try:
        async with SessionLocal() as db:
            await unlock_prompt_atomic(db, buyer_id=buyer1, prompt_id=beat_id)
            await db.commit()
        # Toujours en vente après une vente lease.
        b = await _beat(beat_id)
        assert b.is_published is True
        # Un 2e acheteur peut aussi l'acheter.
        async with SessionLocal() as db:
            await unlock_prompt_atomic(db, buyer_id=buyer2, prompt_id=beat_id)
            await db.commit()
    finally:
        await _cleanup(beat_id, artist, buyer1, buyer2)


async def test_download_forbidden_for_non_owner(client: AsyncClient, auth_headers: dict):
    """Le téléchargement est réservé aux acheteurs : 403 pour un non-acheteur."""
    artist = await _make_user()
    beat_id = await _make_beat(artist, license_type="lease")
    try:
        # test_user (auth_headers) n'est ni l'artiste ni un acheteur → 403,
        # AVANT tout accès R2.
        r = await client.get(f"/beats/{beat_id}/download", headers=auth_headers)
        assert r.status_code == 403, r.text
    finally:
        await _cleanup(beat_id, artist)


async def test_download_unknown_beat_is_404(client: AsyncClient, auth_headers: dict):
    fake = "00000000-0000-0000-0000-000000000000"
    r = await client.get(f"/beats/{fake}/download", headers=auth_headers)
    assert r.status_code == 404, r.text


# --- Achat pack (recette + beat) ------------------------------------------

async def _make_recipe(artist_id) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artist_id,
            title=f"Recipe {uuid.uuid4().hex[:8]}",
            description="x",
            prompt_text="Y" * 120,  # recette : 100..1000 chars
            price_credits=10,
            is_published=True,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _make_track_with_pack(artist_id, recipe_id, beat_id, pack_price) -> uuid.UUID:
    async with SessionLocal() as db:
        t = Track(
            title=f"Track {uuid.uuid4().hex[:8]}",
            artist_id=artist_id,
            prompt_id=recipe_id,
            beat_id=beat_id,
            pack_price_credits=pack_price,
        )
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return t.id


async def test_buy_pack_unlocks_both_products():
    artist = await _make_user()
    buyer = await _make_user(initial_balance=2000)
    recipe_id = await _make_recipe(artist)
    beat_id = await _make_beat(artist, license_type="lease", is_published=True)
    track_id = await _make_track_with_pack(artist, recipe_id, beat_id, 15)
    try:
        async with SessionLocal() as db:
            result = await buy_pack_atomic(db, buyer_id=buyer, track_id=track_id)
            await db.commit()
        assert result["price_paid"] == 15

        # L'acheteur possède LES DEUX produits après un seul achat pack.
        async with SessionLocal() as db:
            owned = (await db.execute(
                select(UnlockedPrompt.prompt_id).where(
                    UnlockedPrompt.current_owner_id == buyer
                )
            )).scalars().all()
        assert recipe_id in owned, "la recette doit être débloquée par le pack"
        assert beat_id in owned, "le beat doit être débloqué par le pack"
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Track).where(Track.id == track_id))
            await db.execute(delete(Prompt).where(Prompt.id.in_([recipe_id, beat_id])))
            for uid in (artist, buyer):
                await db.execute(delete(User).where(User.id == uid))
            await db.commit()
