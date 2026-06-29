"""Sous-soldes par catégorie de Smyle (A1.1) — helpers credit_bucket / debit_with_priority.

Teste les helpers en ISOLATION (les call-sites ne sont pas encore branchés — A1.3) :
on fixe l'état des buckets via SQL, puis on vérifie crédit ciblé et débit par
priorité (promo → achetés → gagnés), avec maintien de somme == credits_balance.
"""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import credit_bucket, debit_with_priority
from app.services.users import create_user


async def _new_user() -> uuid.UUID:
    email = f"pytest-bucket-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        return u.id


async def _set_buckets(uid, *, promo, achetes, gagnes):
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET smyles_promo=:p, smyles_achetes=:a, "
                "smyles_gagnes=:g, credits_balance=:t WHERE id=:uid"
            ),
            {"p": promo, "a": achetes, "g": gagnes, "t": promo + achetes + gagnes, "uid": uid},
        )
        await db.commit()


async def _read(uid):
    async with SessionLocal() as db:
        r = (await db.execute(
            text(
                "SELECT smyles_promo, smyles_achetes, smyles_gagnes, credits_balance "
                "FROM users WHERE id=:uid"
            ),
            {"uid": uid},
        )).first()
    return r


async def _cleanup(uid):
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def test_credit_bucket_cible_le_bon_bucket():
    uid = await _new_user()
    try:
        await _set_buckets(uid, promo=0, achetes=0, gagnes=0)
        async with SessionLocal() as db:
            await credit_bucket(db, uid, 5, bucket="gagnes")
            await credit_bucket(db, uid, 3, bucket="promo")
            await db.commit()
        r = await _read(uid)
        assert r.smyles_gagnes == 5
        assert r.smyles_promo == 3
        assert r.smyles_achetes == 0
        assert r.credits_balance == 8  # somme == balance
    finally:
        await _cleanup(uid)


async def test_credit_bucket_inconnu_leve():
    uid = await _new_user()
    try:
        async with SessionLocal() as db:
            with pytest.raises(ValueError):
                await credit_bucket(db, uid, 5, bucket="inexistant")
    finally:
        await _cleanup(uid)


async def test_debit_consomme_promo_puis_achetes_puis_gagnes():
    uid = await _new_user()
    try:
        await _set_buckets(uid, promo=3, achetes=4, gagnes=10)  # total 17
        async with SessionLocal() as db:
            taken = await debit_with_priority(db, uid, 5)
            await db.commit()
        assert taken == {"promo": 3, "achetes": 2, "gagnes": 0}
        r = await _read(uid)
        assert (r.smyles_promo, r.smyles_achetes, r.smyles_gagnes) == (0, 2, 10)
        assert r.credits_balance == 12
    finally:
        await _cleanup(uid)


async def test_debit_solde_insuffisant_leve():
    uid = await _new_user()
    try:
        await _set_buckets(uid, promo=1, achetes=1, gagnes=1)  # total 3
        async with SessionLocal() as db:
            with pytest.raises(ValueError):
                await debit_with_priority(db, uid, 10)
    finally:
        await _cleanup(uid)
