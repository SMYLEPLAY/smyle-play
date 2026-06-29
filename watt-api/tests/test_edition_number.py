"""
#X/N — numérotation des exemplaires d'édition limitée (Phase 1, 2026-06-09).

Vérifie que `unlocked_prompts.edition_number` est attribué correctement au
mint (achat direct) :

  - Édition LIMITÉE (max_supply défini) : numéros séquentiels 1, 2, 3…
    dans l'ordre des achats, et la contrainte UNIQUE(prompt_id, edition_number)
    empêche tout doublon.
  - Tirage ILLIMITÉ (max_supply NULL) : edition_number reste NULL (pas de
    numéro — décision produit : on ne numérote que la rareté limitée).

Niveau service (SessionLocal direct), modelé sur test_loop_mechanics.py.
Postgres requis (cf. conftest). En local : pytest -q.
"""
import uuid

import pytest
from sqlalchemy import delete, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.unlocks import unlock_prompt_atomic
from app.services.users import create_user


async def _make_user(initial_balance: int = 1000) -> uuid.UUID:
    email = f"pytest-edition-{uuid.uuid4().hex[:12]}@smyleplay.example"
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


async def _make_prompt(artist_id: uuid.UUID, max_supply: int | None) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artist_id,
            title=f"Edition {uuid.uuid4().hex[:8]}",
            description="Tagline",
            prompt_text="X" * 100,
            price_credits=10,
            is_published=True,
            max_supply=max_supply,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _unlock(buyer_id: uuid.UUID, prompt_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await unlock_prompt_atomic(db, buyer_id=buyer_id, prompt_id=prompt_id)
        await db.commit()


async def _edition(owner_id: uuid.UUID, prompt_id: uuid.UUID) -> int | None:
    async with SessionLocal() as db:
        return (await db.execute(
            select(UnlockedPrompt.edition_number).where(
                UnlockedPrompt.current_owner_id == owner_id,
                UnlockedPrompt.prompt_id == prompt_id,
            )
        )).scalar_one()


async def _cleanup(prompt_id: uuid.UUID, *uids: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(Prompt).where(Prompt.id == prompt_id))
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def test_limited_edition_assigns_sequential_numbers():
    artist = await _make_user()
    b1 = await _make_user()
    b2 = await _make_user()
    b3 = await _make_user()
    prompt = await _make_prompt(artist, max_supply=3)
    try:
        await _unlock(b1, prompt)
        await _unlock(b2, prompt)
        await _unlock(b3, prompt)

        # Numéros séquentiels dans l'ordre d'achat.
        assert await _edition(b1, prompt) == 1
        assert await _edition(b2, prompt) == 2
        assert await _edition(b3, prompt) == 3

        # Pas de doublon : 3 numéros distincts pour ce prompt.
        async with SessionLocal() as db:
            nums = (await db.execute(
                select(UnlockedPrompt.edition_number).where(
                    UnlockedPrompt.prompt_id == prompt
                )
            )).scalars().all()
        assert sorted(nums) == [1, 2, 3]
    finally:
        await _cleanup(prompt, artist, b1, b2, b3)


async def test_unlimited_edition_has_no_number():
    artist = await _make_user()
    buyer = await _make_user()
    prompt = await _make_prompt(artist, max_supply=None)
    try:
        await _unlock(buyer, prompt)
        assert await _edition(buyer, prompt) is None
    finally:
        await _cleanup(prompt, artist, buyer)
