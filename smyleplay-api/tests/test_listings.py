"""Emplacements de vente par palier (C6.3) — comptage, jauge, garde différée."""
import uuid

import pytest
from sqlalchemy import delete

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
import app.services.listings as listings_mod
from app.services.listings import (
    ListingSlotLimitReached,
    count_active_listings,
    ensure_listing_slot_available,
    listing_slots_status,
)
from app.services.users import create_user


async def _fresh_user_id() -> uuid.UUID:
    email = f"pytest-slots-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        return u.id


async def test_compte_zero_pour_compte_neuf():
    uid = await _fresh_user_id()
    try:
        async with SessionLocal() as db:
            assert await count_active_listings(db, uid) == 0
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def test_jauge_standard_par_defaut():
    uid = await _fresh_user_id()
    try:
        async with SessionLocal() as db:
            st = await listing_slots_status(db, uid, "standard")
        assert st["tier"] == "standard"
        assert st["used"] == 0
        assert st["limit"] == 10
        assert st["remaining"] == 10
        assert st["over"] is False
        assert st["enforced"] is False  # paiements pas ouverts
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def test_jauge_mythique_illimitee():
    uid = await _fresh_user_id()
    try:
        async with SessionLocal() as db:
            st = await listing_slots_status(db, uid, "mythique")
        assert st["limit"] is None
        assert st["remaining"] is None
        assert st["over"] is False
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def test_garde_no_op_si_non_appliquee(monkeypatch):
    # Flag OFF : même au-delà de la limite, aucune levée (jauge ≠ blocage).
    monkeypatch.setattr(listings_mod, "LISTING_SLOTS_ENFORCED", False)

    async def _fake_count(db, artist_id):
        return 999

    monkeypatch.setattr(listings_mod, "count_active_listings", _fake_count)
    async with SessionLocal() as db:
        await ensure_listing_slot_available(db, uuid.uuid4(), "standard")  # ne lève pas


async def test_garde_bloque_si_appliquee_et_au_plafond(monkeypatch):
    monkeypatch.setattr(listings_mod, "LISTING_SLOTS_ENFORCED", True)

    async def _fake_count(db, artist_id):
        return 10  # = limite standard

    monkeypatch.setattr(listings_mod, "count_active_listings", _fake_count)
    async with SessionLocal() as db:
        with pytest.raises(ListingSlotLimitReached):
            await ensure_listing_slot_available(db, uuid.uuid4(), "standard")


async def test_garde_mythique_jamais_bloquee(monkeypatch):
    monkeypatch.setattr(listings_mod, "LISTING_SLOTS_ENFORCED", True)

    async def _fake_count(db, artist_id):
        return 100000

    monkeypatch.setattr(listings_mod, "count_active_listings", _fake_count)
    async with SessionLocal() as db:
        await ensure_listing_slot_available(db, uuid.uuid4(), "mythique")  # illimité
