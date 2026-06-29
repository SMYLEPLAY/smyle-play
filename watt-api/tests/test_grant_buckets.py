"""A1.3 (sous-étape 1) — grant_credits_atomic route les crédits vers le bon bucket.

credit_purchase → achetés ; bonus/grant → promo ; earning → gagnés. Et somme des
buckets == credits_balance (invariant maintenu sur le chemin de crédit central).
"""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.transaction import TransactionType
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import grant_credits_atomic, user_bucket_consistent
from app.services.users import create_user


async def _read(uid):
    async with SessionLocal() as db:
        return (await db.execute(
            text(
                "SELECT smyles_promo, smyles_achetes, smyles_gagnes, credits_balance "
                "FROM users WHERE id = :uid"
            ),
            {"uid": uid},
        )).first()


async def test_bonus_bienvenue_route_en_promo_et_coherent():
    # create_user crédite le bonus de bienvenue (BONUS) → doit aller en promo.
    email = f"pytest-grant-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    try:
        r = await _read(uid)
        assert r.smyles_achetes == 0 and r.smyles_gagnes == 0
        assert r.smyles_promo == r.credits_balance  # tout le bonus en promo
        async with SessionLocal() as db:
            assert await user_bucket_consistent(db, uid) is True
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def test_credit_purchase_va_en_achetes():
    email = f"pytest-grant-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    try:
        before = await _read(uid)
        async with SessionLocal() as db:
            await grant_credits_atomic(
                db, uid, 5, reason="pack", tx_type=TransactionType.CREDIT_PURCHASE
            )
            await db.commit()
        after = await _read(uid)
        assert after.smyles_achetes == before.smyles_achetes + 5
        assert after.smyles_promo == before.smyles_promo  # promo inchangé
        async with SessionLocal() as db:
            assert await user_bucket_consistent(db, uid) is True
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def test_bonus_supplementaire_va_en_promo():
    email = f"pytest-grant-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    try:
        before = await _read(uid)
        async with SessionLocal() as db:
            await grant_credits_atomic(
                db, uid, 3, reason="streak", tx_type=TransactionType.BONUS
            )
            await db.commit()
        after = await _read(uid)
        assert after.smyles_promo == before.smyles_promo + 3
        assert after.smyles_achetes == before.smyles_achetes
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
