"""A3 — réserve € & solvabilité : dette encaissable, poches, feu tricolore."""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.reserve import (
    PAYOUT_RATE_CENTS,
    _zone,
    cashable_debt_cents,
    move_reserve,
    reserve_poche_cents,
    reserve_status,
)
from app.services.users import create_user


def test_zone_tricolore():
    assert _zone(140, 100) == "🟢"   # > 130 %
    assert _zone(120, 100) == "🟠"   # 110–130 %
    assert _zone(105, 100) == "🔴"   # 100–110 %
    assert _zone(90, 100) == "⚫"    # < 100 %
    assert _zone(0, 0) == "🟢"       # pas de dette → vert


async def test_dette_reflete_les_gagnes():
    async with SessionLocal() as db:
        debt_before = await cashable_debt_cents(db)
    email = f"pytest-res-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    try:
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE users SET smyles_gagnes = 100, credits_balance = 100, "
                    "smyles_achetes = 0, smyles_promo = 0 WHERE id = :uid"
                ),
                {"uid": uid},
            )
            await db.commit()
        async with SessionLocal() as db:
            debt_after = await cashable_debt_cents(db)
        assert debt_after - debt_before == 100 * PAYOUT_RATE_CENTS
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def test_move_reserve_credite_et_debite():
    async with SessionLocal() as db:
        before = await reserve_poche_cents(db, "payout")
    try:
        async with SessionLocal() as db:
            await move_reserve(db, "payout", 5000)
            await db.commit()
        async with SessionLocal() as db:
            assert await reserve_poche_cents(db, "payout") == before + 5000
    finally:
        async with SessionLocal() as db:
            await move_reserve(db, "payout", -5000)  # restaure l'état
            await db.commit()


async def test_status_shape():
    async with SessionLocal() as db:
        st = await reserve_status(db)
    assert set(st["reserve_cents"].keys()) == {"payout", "tax", "refund", "cash"}
    assert "cashable_debt_cents" in st
    assert "zone" in st and st["zone"] in {"🟢", "🟠", "🔴", "⚫"}
    assert isinstance(st["solvable"], bool)
