"""Idempotence de grant_credits_atomic (A0 — anti double-crédit).

La table `transactions` porte déjà, depuis la migration 0070, une colonne
`idempotency_key` et un index UNIQUE partiel. Ces tests vérifient que le SERVICE
de crédit s'appuie dessus : un rejeu portant la même clé est un NO-OP (aucun
second crédit, aucune seconde ligne de ledger), tandis que les appels SANS clé
gardent leur comportement historique (répétables).

Chemin le plus à risque câblé : le bonus de bienvenue (app/services/users.py)
passe `welcome_bonus:{user_id}` → exactement un bonus par compte, même si la
création est rejouée.
"""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.transaction import TransactionType
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import grant_credits_atomic
from app.services.users import create_user


async def _new_user() -> uuid.UUID:
    email = f"pytest-idem-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        return u.id


async def _balance(uid: uuid.UUID) -> int:
    async with SessionLocal() as db:
        r = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": uid},
        )).first()
    return int(r.credits_balance)


async def _count_tx_with_key(key: str) -> int:
    async with SessionLocal() as db:
        r = (await db.execute(
            text("SELECT count(*) AS n FROM transactions WHERE idempotency_key = :k"),
            {"k": key},
        )).first()
    return int(r.n)


async def _cleanup(uid: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def test_rejeu_meme_cle_est_noop():
    """Deux grants portant la MÊME clé → une seule ligne de ledger, un seul
    crédit, et la même transaction renvoyée."""
    uid = await _new_user()
    key = f"test-idem:{uuid.uuid4().hex}"
    try:
        before = await _balance(uid)
        async with SessionLocal() as db:
            tx1 = await grant_credits_atomic(
                db, uid, 10, reason="idem-test",
                tx_type=TransactionType.CREDIT_PURCHASE,
                idempotency_key=key,
            )
            await db.commit()
            tx1_id = tx1.id

        async with SessionLocal() as db:
            tx2 = await grant_credits_atomic(
                db, uid, 10, reason="idem-test",
                tx_type=TransactionType.CREDIT_PURCHASE,
                idempotency_key=key,
            )
            await db.commit()
            tx2_id = tx2.id

        # Même transaction renvoyée, créditée UNE seule fois.
        assert tx1_id == tx2_id
        assert await _balance(uid) == before + 10
        assert await _count_tx_with_key(key) == 1
    finally:
        await _cleanup(uid)


async def test_sans_cle_les_grants_se_repetent():
    """Sans idempotency_key, le comportement historique est préservé : deux
    grants créditent deux fois (répétables)."""
    uid = await _new_user()
    try:
        before = await _balance(uid)
        async with SessionLocal() as db:
            await grant_credits_atomic(
                db, uid, 5, tx_type=TransactionType.CREDIT_PURCHASE,
            )
            await grant_credits_atomic(
                db, uid, 5, tx_type=TransactionType.CREDIT_PURCHASE,
            )
            await db.commit()
        assert await _balance(uid) == before + 10
    finally:
        await _cleanup(uid)


async def test_cles_differentes_creditent_chacune():
    """Deux clés distinctes = deux opérations logiques distinctes → deux
    crédits."""
    uid = await _new_user()
    k1 = f"test-idem:{uuid.uuid4().hex}"
    k2 = f"test-idem:{uuid.uuid4().hex}"
    try:
        before = await _balance(uid)
        async with SessionLocal() as db:
            await grant_credits_atomic(
                db, uid, 7, tx_type=TransactionType.CREDIT_PURCHASE,
                idempotency_key=k1,
            )
            await grant_credits_atomic(
                db, uid, 4, tx_type=TransactionType.CREDIT_PURCHASE,
                idempotency_key=k2,
            )
            await db.commit()
        assert await _balance(uid) == before + 11
        assert await _count_tx_with_key(k1) == 1
        assert await _count_tx_with_key(k2) == 1
    finally:
        await _cleanup(uid)


async def test_bonus_bienvenue_est_exactement_une_fois():
    """Le bonus de bienvenue porte une clé dérivée de l'id du compte : rejouer
    le grant de bienvenue pour le MÊME compte ne recrédite pas."""
    uid = await _new_user()  # create_user a déjà émis le welcome bonus (clé posée)
    try:
        balance_apres_inscription = await _balance(uid)
        # Rejeu explicite du même grant de bienvenue (même clé que create_user).
        async with SessionLocal() as db:
            await grant_credits_atomic(
                db, uid, 10, reason="welcome_bonus",
                tx_type=TransactionType.BONUS,
                idempotency_key=f"welcome_bonus:{uid}",
            )
            await db.commit()
        # Aucun second crédit : le solde n'a pas bougé.
        assert await _balance(uid) == balance_apres_inscription
        assert await _count_tx_with_key(f"welcome_bonus:{uid}") == 1
    finally:
        await _cleanup(uid)
