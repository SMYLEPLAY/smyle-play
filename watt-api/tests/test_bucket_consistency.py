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


_SUM_CONSTRAINT = "ck_users_buckets_sum_eq_balance"


async def test_user_incoherent_detecte():
    """Le canari (A1.2) doit DÉTECTER un écart somme(buckets) != solde.

    Depuis A1.4 (CHECK de somme posé par la migration 0088), écrire une ligne
    incohérente est refusé au niveau DB. Le canari reste utile pendant la
    fenêtre NOT VALID en prod (lignes legacy) : pour vérifier qu'il sait
    détecter, on SUSPEND le CHECK le temps d'injecter l'incohérence, puis on le
    restaure (NOT VALID → pas de rescan des autres lignes)."""
    uid = await _new_user()
    async with SessionLocal() as db:
        had_constraint = bool((await db.execute(
            text(
                "SELECT 1 FROM pg_constraint WHERE conname = :n "
                "AND conrelid = 'users'::regclass"
            ),
            {"n": _SUM_CONSTRAINT},
        )).first())
    try:
        async with SessionLocal() as db:
            if had_constraint:
                await db.execute(
                    text(f"ALTER TABLE users DROP CONSTRAINT IF EXISTS {_SUM_CONSTRAINT}")
                )
            # État volontairement incohérent : buckets à 0, solde forcé à 10.
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
            # On supprime la ligne incohérente AVANT de restaurer la contrainte,
            # sinon le ré-ADD échouerait (et on ne restaure que si elle existait).
            await db.execute(delete(User).where(User.id == uid))
            if had_constraint:
                await db.execute(
                    text(
                        f"ALTER TABLE users ADD CONSTRAINT {_SUM_CONSTRAINT} "
                        "CHECK (smyles_achetes + smyles_gagnes + smyles_promo "
                        "= credits_balance) NOT VALID"
                    )
                )
            await db.commit()


async def test_count_inconsistencies_renvoie_un_entier():
    async with SessionLocal() as db:
        n = await count_bucket_inconsistencies(db)
    assert isinstance(n, int)
    assert n >= 0
