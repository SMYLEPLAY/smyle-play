"""Invariants comptables du ledger (A0) — append-only, immutabilité, idempotence.

Vérifie les garanties posées au niveau DB par la migration 0070 :
  - DELETE d'une transaction → interdit (append-only) ;
  - UPDATE d'un champ financier → interdit (immutabilité) ;
  - UPDATE de status/completed_at → autorisé (cycle de vie) ;
  - idempotency_key → unique (un rejeu ne peut pas dupliquer une écriture).
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.transaction import Transaction, TransactionStatus, TransactionType


async def _new_tx(db, **kw):
    """Crée une transaction minimale valide (GRANT, 1 crédit, split 0)."""
    tx = Transaction(
        type=TransactionType.GRANT,
        status=TransactionStatus.PENDING,
        credits_amount=1,
        platform_fee=0,
        artist_revenue=0,
        **kw,
    )
    db.add(tx)
    await db.flush()
    return tx


async def test_delete_transaction_interdit():
    async with SessionLocal() as db:
        tx = await _new_tx(db)
        await db.commit()
        tid = tx.id
    # Le trigger append-only doit faire échouer le DELETE.
    with pytest.raises(DBAPIError):
        async with SessionLocal() as db:
            await db.execute(
                text("DELETE FROM transactions WHERE id = :id"), {"id": tid}
            )
            await db.commit()


async def test_update_champ_financier_interdit():
    async with SessionLocal() as db:
        tx = await _new_tx(db)
        await db.commit()
        tid = tx.id
    # Modifier un montant doit échouer (immutabilité).
    with pytest.raises(DBAPIError):
        async with SessionLocal() as db:
            await db.execute(
                text("UPDATE transactions SET credits_amount = 999 WHERE id = :id"),
                {"id": tid},
            )
            await db.commit()


async def test_update_status_autorise():
    async with SessionLocal() as db:
        tx = await _new_tx(db)
        await db.commit()
        tid = tx.id
    # status + completed_at peuvent changer (cycle de vie PENDING→COMPLETED).
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE transactions SET status = 'completed', "
                "completed_at = now() WHERE id = :id"
            ),
            {"id": tid},
        )
        await db.commit()
    async with SessionLocal() as db:
        row = (await db.execute(
            text("SELECT status FROM transactions WHERE id = :id"), {"id": tid}
        )).first()
        assert row.status == "completed"


async def test_idempotency_key_unique():
    key = f"idem-{uuid.uuid4().hex}"
    async with SessionLocal() as db:
        await _new_tx(db, idempotency_key=key)
        await db.commit()
    # Un rejeu portant la même clé est rejeté par l'index unique.
    with pytest.raises(IntegrityError):
        async with SessionLocal() as db:
            await _new_tx(db, idempotency_key=key)
            await db.commit()


async def test_idempotency_key_null_autorise_doublons():
    # Plusieurs transactions sans clé (NULL) restent permises (index partiel).
    async with SessionLocal() as db:
        await _new_tx(db)
        await _new_tx(db)
        await db.commit()
