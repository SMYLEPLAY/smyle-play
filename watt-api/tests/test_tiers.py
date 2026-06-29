"""Paliers créateur (C6) — config commission/emplacements + split tier-aware."""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import artist_pct_for_user, compute_split
from app.services.tiers import (
    UserTier,
    artist_pct_for_tier,
    commission_pct_for_tier,
    is_featured_tier,
    listing_slots_for_tier,
    normalize_tier,
    tier_public_info,
)
from app.services.users import create_user


# --- Config pure (sans DB) -------------------------------------------------

def test_commission_bareme():
    assert commission_pct_for_tier(UserTier.STANDARD) == 20
    assert commission_pct_for_tier(UserTier.PREMIUM) == 12
    assert commission_pct_for_tier(UserTier.MYTHIQUE) == 5


def test_artist_pct_complement():
    assert artist_pct_for_tier("standard") == 80
    assert artist_pct_for_tier("premium") == 88
    assert artist_pct_for_tier("mythique") == 95


def test_listing_slots():
    assert listing_slots_for_tier("standard") == 10
    assert listing_slots_for_tier("premium") == 50
    assert listing_slots_for_tier("mythique") is None  # illimité


def test_featured_flag():
    assert is_featured_tier("standard") is False
    assert is_featured_tier("premium") is True
    assert is_featured_tier("mythique") is True


def test_normalize_tier_robuste():
    # NULL / vide / casse / inconnu → Standard (jamais de crash)
    assert normalize_tier(None) is UserTier.STANDARD
    assert normalize_tier("") is UserTier.STANDARD
    assert normalize_tier("PREMIUM") is UserTier.PREMIUM
    assert normalize_tier("  Mythique ") is UserTier.MYTHIQUE
    assert normalize_tier("inconnu") is UserTier.STANDARD


def test_tier_public_info_shape():
    info = tier_public_info("premium")
    assert info == {
        "tier": "premium",
        "label": "Premium",
        "commission_pct": 12,
        "artist_pct": 88,
        "listing_slots": 50,
        "featured": True,
    }


def test_split_par_palier():
    # 100 crédits : Standard 80/20, Premium 88/12, Mythique 95/5.
    assert compute_split(100, artist_pct_for_tier("standard")) == (80, 20)
    assert compute_split(100, artist_pct_for_tier("premium")) == (88, 12)
    assert compute_split(100, artist_pct_for_tier("mythique")) == (95, 5)


# --- Helper DB : palier du vendeur --------------------------------------

async def test_artist_pct_for_user_lit_le_palier():
    email = f"pytest-tier-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    try:
        # Défaut = standard → 80%
        async with SessionLocal() as db:
            assert await artist_pct_for_user(db, uid) == 80
        # Promotion premium → 88%
        async with SessionLocal() as db:
            await db.execute(
                text("UPDATE users SET tier = 'premium' WHERE id = :id"),
                {"id": uid},
            )
            await db.commit()
        async with SessionLocal() as db:
            assert await artist_pct_for_user(db, uid) == 88
        # Mythique → 95%
        async with SessionLocal() as db:
            await db.execute(
                text("UPDATE users SET tier = 'mythique' WHERE id = :id"),
                {"id": uid},
            )
            await db.commit()
        async with SessionLocal() as db:
            assert await artist_pct_for_user(db, uid) == 95
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
