"""A2 — escrow des gains : maturation (depuis le ledger) + gel.

withdrawable = min(gagnés détenus non gelés − gains encore en maturation,
                   gains maturés > EARNINGS_MATURITY_DAYS).
"""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.escrow import (
    gagnes_status,
    matured_gagnes,
    set_gagnes_bloque,
    withdrawable_gagnes,
)
from app.services.users import create_user


async def _new_user() -> uuid.UUID:
    email = f"pytest-escrow-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        return u.id


async def _set_gagnes(uid, n):
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET smyles_gagnes = :n, smyles_promo = 0, "
                "smyles_achetes = 0, smyles_gagnes_bloque = 0, credits_balance = :n "
                "WHERE id = :uid"
            ),
            {"n": n, "uid": uid},
        )
        await db.commit()


async def _insert_earning(uid, amount, days_ago):
    async with SessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO transactions "
                "(id, type, status, seller_id, credits_amount, artist_revenue, "
                " platform_fee, created_at) "
                "VALUES (:tid, 'earning', 'completed', :uid, :amt, :amt, 0, "
                "        now() - (:d * interval '1 day'))"
            ),
            {"tid": uuid.uuid4(), "uid": uid, "amt": amount, "d": days_ago},
        )
        await db.commit()


async def _cleanup(uid):
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def test_maturation_filtre_les_gains_recents():
    uid = await _new_user()
    try:
        await _set_gagnes(uid, 100)
        await _insert_earning(uid, 100, days_ago=30)  # maturé
        await _insert_earning(uid, 50, days_ago=0)    # trop récent
        async with SessionLocal() as db:
            assert await matured_gagnes(db, uid) == 100  # le récent (50) exclu
    finally:
        await _cleanup(uid)


async def test_withdrawable_est_le_min_detenu_mature():
    uid = await _new_user()
    try:
        await _set_gagnes(uid, 100)
        await _insert_earning(uid, 100, days_ago=30)
        async with SessionLocal() as db:
            assert await withdrawable_gagnes(db, uid) == 100
    finally:
        await _cleanup(uid)


async def test_gel_reduit_le_retirable():
    uid = await _new_user()
    try:
        await _set_gagnes(uid, 100)
        await _insert_earning(uid, 100, days_ago=30)
        async with SessionLocal() as db:
            await set_gagnes_bloque(db, uid, 40)
            await db.commit()
        async with SessionLocal() as db:
            st = await gagnes_status(db, uid)
        assert st["total"] == 100
        assert st["bloque"] == 40
        assert st["retirable"] == 60
        assert st["en_attente"] == 0
    finally:
        await _cleanup(uid)


async def test_non_mature_pas_retirable():
    uid = await _new_user()
    try:
        await _set_gagnes(uid, 100)
        await _insert_earning(uid, 100, days_ago=0)  # pas encore maturé
        async with SessionLocal() as db:
            assert await withdrawable_gagnes(db, uid) == 0
    finally:
        await _cleanup(uid)


async def test_fenetre_de_maturation_est_de_30_jours():
    """Pricing v2 (30/09) : 7 → 30 jours. Un gain de 10 jours n'est plus mûr."""
    from app.services.escrow import EARNINGS_MATURITY_DAYS

    assert EARNINGS_MATURITY_DAYS == 30
    uid = await _new_user()
    try:
        await _set_gagnes(uid, 100)
        await _insert_earning(uid, 100, days_ago=10)
        async with SessionLocal() as db:
            assert await matured_gagnes(db, uid) == 0
            assert await withdrawable_gagnes(db, uid) == 0
    finally:
        await _cleanup(uid)


async def test_gain_recent_pas_couvert_par_anciens_gains_reclasses():
    """Après le reclassement de la bêta (migration 0099 : gagnés → promo), les
    anciennes ventes restent au ledger comme « maturées ». Un gain d'aujourd'hui
    ne doit PAS devenir retirable grâce à elles (fenêtre de 30 j respectée)."""
    uid = await _new_user()
    try:
        await _insert_earning(uid, 100, days_ago=60)  # vieux gain, reclassé en promo
        await _set_gagnes(uid, 8)                     # seul le nouveau gain est en gagnés
        await _insert_earning(uid, 8, days_ago=0)     # la nouvelle vente
        async with SessionLocal() as db:
            assert await matured_gagnes(db, uid) == 100
            assert await withdrawable_gagnes(db, uid) == 0
            st = await gagnes_status(db, uid)
        assert st["en_attente"] == 8
    finally:
        await _cleanup(uid)
