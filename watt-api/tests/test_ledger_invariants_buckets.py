"""Invariants des sous-soldes (A1) — non-négativité, ordre de dépense, anti
double-dépense concurrente.

Complète test_ledger_invariants.py (garanties append-only du ledger `transactions`)
et test_smyle_buckets.py (helpers en isolation) par les invariants de SÛRETÉ qui
manquaient explicitement :

  - aucun bucket ne peut devenir négatif (CHECK DB) ;
  - l'ordre de dépense préserve le RETIRABLE : promo → achetés → gagnés, donc
    les gagnés (encaissables = dette plateforme, doctrine de juin conservée)
    sont consommés EN DERNIER ;
  - deux débits concurrents sur le même user ne peuvent pas double-dépenser :
    le verrou FOR UPDATE sérialise, le second échoue proprement si le solde
    n'y est plus, et aucun solde ne passe négatif.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import debit_with_priority
from app.services.users import create_user


async def _new_user() -> uuid.UUID:
    email = f"pytest-inv-{uuid.uuid4().hex[:10]}@smyleplay.example"
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
            {"p": promo, "a": achetes, "g": gagnes,
             "t": promo + achetes + gagnes, "uid": uid},
        )
        await db.commit()


async def _read(uid):
    async with SessionLocal() as db:
        return (await db.execute(
            text(
                "SELECT smyles_promo, smyles_achetes, smyles_gagnes, "
                "credits_balance FROM users WHERE id=:uid"
            ),
            {"uid": uid},
        )).first()


async def _cleanup(uid):
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


# ---------------------------------------------------------------------------
# 1. Non-négativité : la DB refuse un bucket négatif (CHECK de la migration 0071).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "col",
    ["smyles_achetes", "smyles_gagnes", "smyles_promo", "smyles_gagnes_bloque"],
)
async def test_bucket_negatif_refuse_par_la_db(col):
    uid = await _new_user()
    try:
        with pytest.raises(IntegrityError):
            async with SessionLocal() as db:
                await db.execute(
                    text(f"UPDATE users SET {col} = -1 WHERE id = :uid"),
                    {"uid": uid},
                )
                await db.commit()
    finally:
        await _cleanup(uid)


async def test_debit_ne_laisse_jamais_un_bucket_negatif():
    """Un débit supérieur au solde est refusé AVANT toute mutation : les buckets
    restent intacts, aucun ne passe négatif."""
    uid = await _new_user()
    try:
        await _set_buckets(uid, promo=1, achetes=1, gagnes=1)  # total 3
        async with SessionLocal() as db:
            with pytest.raises(ValueError):
                await debit_with_priority(db, uid, 4)
            await db.rollback()
        r = await _read(uid)
        assert (r.smyles_promo, r.smyles_achetes, r.smyles_gagnes) == (1, 1, 1)
        assert r.credits_balance == 3
    finally:
        await _cleanup(uid)


# ---------------------------------------------------------------------------
# 2. Ordre de dépense : le RETIRABLE (gagnés) est préservé au maximum.
# ---------------------------------------------------------------------------

async def test_ordre_preserve_les_gagnes_retirables():
    """promo puis achetés sont consommés d'abord ; les gagnés (retirables)
    ne sont entamés que si promo+achetés ne suffisent pas."""
    uid = await _new_user()
    try:
        await _set_buckets(uid, promo=2, achetes=5, gagnes=10)  # total 17
        # Débit de 6 : 2 promo + 4 achetés ; gagnés INTACTS.
        async with SessionLocal() as db:
            taken = await debit_with_priority(db, uid, 6)
            await db.commit()
        assert taken == {"promo": 2, "achetes": 4, "gagnes": 0}
        r = await _read(uid)
        assert r.smyles_gagnes == 10          # retirable préservé
        assert (r.smyles_promo, r.smyles_achetes) == (0, 1)
        assert r.credits_balance == 11
    finally:
        await _cleanup(uid)


async def test_les_gagnes_ne_sont_entames_qu_en_dernier_recours():
    """Quand promo+achetés ne couvrent pas le débit, on puise le reste — et
    UNIQUEMENT le reste — dans les gagnés."""
    uid = await _new_user()
    try:
        await _set_buckets(uid, promo=1, achetes=2, gagnes=10)  # total 13
        async with SessionLocal() as db:
            taken = await debit_with_priority(db, uid, 5)  # 1+2 puis 2 gagnés
            await db.commit()
        assert taken == {"promo": 1, "achetes": 2, "gagnes": 2}
        r = await _read(uid)
        assert r.smyles_gagnes == 8
        assert (r.smyles_promo, r.smyles_achetes) == (0, 0)
        assert r.credits_balance == 8
    finally:
        await _cleanup(uid)


# ---------------------------------------------------------------------------
# 3. Débit concurrent : pas de double-dépense (verrou FOR UPDATE).
# ---------------------------------------------------------------------------

async def test_debit_concurrent_ne_double_depense_pas():
    """Deux débits simultanés du solde ENTIER sur le même user : exactement UN
    réussit, l'autre échoue proprement (solde insuffisant), et le solde final
    est 0 — jamais négatif. Sans le verrou FOR UPDATE, les deux liraient un
    solde suffisant et débiteraient → solde négatif (double-dépense)."""
    uid = await _new_user()
    try:
        await _set_buckets(uid, promo=0, achetes=0, gagnes=5)  # total 5

        async def worker() -> str:
            async with SessionLocal() as db:
                try:
                    await debit_with_priority(db, uid, 5)
                    await db.commit()
                    return "ok"
                except ValueError:
                    await db.rollback()
                    return "insufficient"

        results = await asyncio.gather(worker(), worker())

        # Exactement un succès, un refus.
        assert sorted(results) == ["insufficient", "ok"], results

        r = await _read(uid)
        # Solde entièrement consommé une seule fois, jamais négatif.
        assert r.credits_balance == 0
        assert r.smyles_gagnes == 0
        assert min(r.smyles_promo, r.smyles_achetes, r.smyles_gagnes) >= 0
    finally:
        await _cleanup(uid)
