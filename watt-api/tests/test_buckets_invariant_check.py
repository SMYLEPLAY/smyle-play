"""CHECK d'invariants des sous-soldes (A1.4) — migration 0088.

Vérifie que les DEUX contraintes posées en base tiennent :
  - `credits_balance >= 0` (dérive comblée : absente avant 0088) ;
  - `smyles_achetes + smyles_gagnes + smyles_promo = credits_balance`.

Ces tests supposent la migration 0088 appliquée (alembic upgrade head).
"""
import uuid

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user


async def _new_user() -> uuid.UUID:
    email = f"pytest-a14-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        return u.id


async def _cleanup(uid):
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def test_solde_total_negatif_refuse():
    """Le CHECK credits_balance >= 0 (posé par 0088) rejette un solde négatif."""
    uid = await _new_user()
    try:
        with pytest.raises(IntegrityError):
            async with SessionLocal() as db:
                # Cohérent en somme mais négatif → refusé par le CHECK de
                # non-négativité (pas par celui de somme).
                await db.execute(
                    text(
                        "UPDATE users SET credits_balance = -1, "
                        "smyles_achetes = -1, smyles_gagnes = 0, smyles_promo = 0 "
                        "WHERE id = :uid"
                    ),
                    {"uid": uid},
                )
                await db.commit()
    finally:
        await _cleanup(uid)


async def test_somme_buckets_differente_du_solde_refuse():
    """smyles_achetes + smyles_gagnes + smyles_promo doit égaler credits_balance."""
    uid = await _new_user()
    try:
        with pytest.raises(IntegrityError):
            async with SessionLocal() as db:
                # On gonfle un bucket sans toucher le solde total → somme > solde.
                await db.execute(
                    text(
                        "UPDATE users SET smyles_achetes = smyles_achetes + 5 "
                        "WHERE id = :uid"
                    ),
                    {"uid": uid},
                )
                await db.commit()
    finally:
        await _cleanup(uid)


async def test_solde_sans_bucket_correspondant_refuse():
    """Poser credits_balance sans aligner les buckets est désormais refusé
    (c'est exactement le bug de seeding que la PR corrige côté tests)."""
    uid = await _new_user()
    try:
        with pytest.raises(IntegrityError):
            async with SessionLocal() as db:
                await db.execute(
                    text("UPDATE users SET credits_balance = 500 WHERE id = :uid"),
                    {"uid": uid},
                )
                await db.commit()
    finally:
        await _cleanup(uid)


async def test_operation_coherente_passe():
    """Une mutation qui conserve somme == solde et reste >= 0 est acceptée."""
    uid = await _new_user()
    try:
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE users SET smyles_achetes = 7, smyles_gagnes = 3, "
                    "smyles_promo = 0, credits_balance = 10 WHERE id = :uid"
                ),
                {"uid": uid},
            )
            await db.commit()
        async with SessionLocal() as db:
            r = (await db.execute(
                text(
                    "SELECT smyles_achetes + smyles_gagnes + smyles_promo AS s, "
                    "credits_balance AS b FROM users WHERE id = :uid"
                ),
                {"uid": uid},
            )).first()
        assert r.s == r.b == 10
    finally:
        await _cleanup(uid)
