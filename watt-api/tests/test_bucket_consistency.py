"""A1.2 — vérification de cohérence des buckets (mode shadow), lecture seule.

Invariant cible : smyles_achetes + smyles_gagnes + smyles_promo == credits_balance.
Le checker mesure l'écart SANS qu'on s'appuie encore sur les buckets (le câblage
des crédits/débits = A1.3 ; le CHECK DB = A1.4).
"""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import (
    count_bucket_inconsistencies,
    user_bucket_consistent,
)
from app.services.users import create_user


async def _new_user() -> uuid.UUID:
    email = f"pytest-cons-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        return u.id


async def test_user_coherent_quand_buckets_egalent_le_solde():
    uid = await _new_user()
    try:
        # On force un état cohérent (buckets = solde).
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE users SET smyles_achetes = credits_balance, "
                    "smyles_gagnes = 0, smyles_promo = 0 WHERE id = :uid"
                ),
                {"uid": uid},
            )
            await db.commit()
        async with SessionLocal() as db:
            assert await user_bucket_consistent(db, uid) is True
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def test_user_incoherent_detecte():
    uid = await _new_user()
    try:
        # État volontairement incohérent : buckets à 0, solde forcé à 10.
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE users SET smyles_achetes = 0, smyles_gagnes = 0, "
                    "smyles_promo = 0, credits_balance = 10 WHERE id = :uid"
                ),
                {"uid": uid},
            )
            await db.commit()
        async with SessionLocal() as db:
            assert await user_bucket_consistent(db, uid) is False
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def test_count_inconsistencies_renvoie_un_entier():
    async with SessionLocal() as db:
        n = await count_bucket_inconsistencies(db)
    assert isinstance(n, int)
    assert n >= 0
