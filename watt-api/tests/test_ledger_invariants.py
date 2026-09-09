"""Invariants comptables du ledger (A0) — append-only, immutabilité, idempotence.

Vérifie les garanties posées au niveau DB par la migration 0070 :
  - DELETE d'une transaction → interdit (append-only) ;
  - UPDATE d'un champ financier → interdit (immutabilité) ;
  - UPDATE de status/completed_at → autorisé (cycle de vie) ;
  - idempotency_key → unique (un rejeu ne peut pas dupliquer une écriture).

D6 (2026-09-08) — s'ajoute l'invariant de MASSE MONÉTAIRE sur le troc :
l'acceptation d'un échange brûle des frais des deux côtés ; chaque Smyle
détruit doit avoir sa ligne de ledger (type BURN), sinon
`somme des écritures != variation des soldes`.
"""
import uuid

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.trade import TradeOffer
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import grant_credits_atomic
from app.services.users import create_user


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


async def test_suppression_user_anonymise_la_tx():
    """Régression : supprimer un user dont des transactions référencent l'id
    déclenche la FK ON DELETE SET NULL (buyer_id → NULL). Le trigger doit
    l'AUTORISER (anonymisation), sinon la suppression de compte est cassée."""
    email = f"pytest-ledger-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        tx = await _new_tx(db, buyer_id=uid)
        await db.commit()
        tid = tx.id
    # DELETE user → SET NULL sur transactions.buyer_id → ne doit PAS lever.
    async with SessionLocal() as db:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
        await db.commit()
    async with SessionLocal() as db:
        row = (await db.execute(
            text("SELECT buyer_id FROM transactions WHERE id = :id"), {"id": tid}
        )).first()
        assert row.buyer_id is None  # anonymisé, pas bloqué


# ---------------------------------------------------------------------------
# D6 — masse monétaire : les frais de troc brûlés doivent laisser une trace.
# ---------------------------------------------------------------------------

_TRADE_FEE_FLOOR = 2


def _expected_fee(price: int) -> int:
    """Réplique la règle de frais du routeur (20 %, plancher 2) — la règle
    économique n'est PAS testée ici, on vérifie que la trace correspond au
    montant réellement détruit."""
    return max(_TRADE_FEE_FLOOR, round(price * 0.20))


async def _seed_prompt(artist_id: uuid.UUID, price: int) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artist_id,
            title=f"Prompt {uuid.uuid4().hex[:8]}",
            description="Tagline",
            prompt_text="X" * 100,
            price_credits=price,
            is_published=True,
        )
        db.add(p)
        await db.commit()
        return p.id


async def _total_balance() -> int:
    """Masse monétaire en circulation (somme des soldes utilisateurs)."""
    async with SessionLocal() as db:
        row = (await db.execute(
            text("SELECT COALESCE(SUM(credits_balance), 0) AS s FROM users")
        )).first()
        return int(row.s)


async def _tx_ids() -> set:
    async with SessionLocal() as db:
        return {
            r[0] for r in (await db.execute(text("SELECT id FROM transactions")))
        }


async def test_frais_de_troc_brules_tracés_au_ledger(
    client, test_user, auth_headers, monkeypatch
):
    """Un échange accepté avec frais écrit, pour CHAQUE partie débitée, une
    ligne BURN du montant exact détruit — et la masse monétaire réconcilie :

        soldes_avant - soldes_après == somme(BURN) - somme(crédits émis)

    Sans l'écriture de ledger, somme(BURN) == 0 alors que les soldes ont
    baissé → le test échoue (c'était l'état avant D6)."""
    monkeypatch.setattr(settings, "SHOW_TROC", True)

    sender_id = test_user["id"]
    receiver_email = f"pytest-burn-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        receiver = await create_user(
            db, UserCreate(email=receiver_email, password="12345678")
        )
        receiver_id = receiver.id

    offered_price, requested_price = 50, 30  # frais attendus : 10 et 6
    offer_id = None
    try:
        # Les deux parties doivent pouvoir payer leur frais.
        async with SessionLocal() as db:
            await grant_credits_atomic(
                db, sender_id, 100, "test D6",
                tx_type=TransactionType.CREDIT_PURCHASE,
            )
            await grant_credits_atomic(
                db, receiver_id, 100, "test D6",
                tx_type=TransactionType.CREDIT_PURCHASE,
            )
            await db.commit()

        offered_prompt = await _seed_prompt(sender_id, offered_price)
        requested_prompt = await _seed_prompt(receiver_id, requested_price)

        # Connexion du receiver (seul lui peut accepter).
        r = await client.post(
            "/auth/login",
            json={"email": receiver_email, "password": "12345678"},
        )
        assert r.status_code == 200, r.text
        receiver_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await client.post(
            "/trades/offers",
            json={
                "receiver_id": str(receiver_id),
                "offered_prompt_id": str(offered_prompt),
                "requested_prompt_id": str(requested_prompt),
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        offer_id = uuid.UUID(r.json()["id"])

        balance_before = await _total_balance()
        tx_before = await _tx_ids()

        r = await client.patch(
            f"/trades/offers/{offer_id}/accept", headers=receiver_headers
        )
        assert r.status_code == 200, r.text

        balance_after = await _total_balance()

        # 1. Une ligne BURN par partie, du montant EXACT débité.
        async with SessionLocal() as db:
            rows = (await db.execute(
                text(
                    "SELECT buyer_id, credits_amount, platform_fee, "
                    "artist_revenue, status, metadata_json "
                    "FROM transactions WHERE type = 'burn' "
                    "AND metadata_json->>'trade_offer_id' = :oid"
                ),
                {"oid": str(offer_id)},
            )).all()
        burns = {r.buyer_id: r for r in rows}
        assert set(burns) == {sender_id, receiver_id}, rows
        # Le sender reçoit le prompt DEMANDÉ, le receiver le prompt OFFERT.
        assert burns[sender_id].credits_amount == _expected_fee(requested_price)
        assert burns[receiver_id].credits_amount == _expected_fee(offered_price)
        for row in rows:
            assert row.status == "completed"
            # Une destruction n'a pas de bénéficiaire : split à 0.
            assert row.platform_fee == 0 and row.artist_revenue == 0

        burned = sum(r.credits_amount for r in rows)

        # 2. Invariant de masse : la baisse des soldes = ce qui a été brûlé,
        #    moins les Smyles émis pendant l'opération (trophées, etc. —
        #    eux aussi tracés).
        async with SessionLocal() as db:
            emitted = (await db.execute(
                text(
                    "SELECT COALESCE(SUM(credits_amount), 0) AS s "
                    "FROM transactions WHERE type IN "
                    "('bonus', 'grant', 'earning', 'credit_purchase', 'refund') "
                    "AND NOT (id = ANY(:seen))"
                ),
                {"seen": list(tx_before)},
            )).first()
        assert balance_before - balance_after == burned - int(emitted.s)
        assert burned > 0  # sinon l'invariant serait trivialement vrai

        # 3. Les sous-soldes restent cohérents (somme(buckets) == solde).
        async with SessionLocal() as db:
            bad = (await db.execute(
                text(
                    "SELECT count(*) AS n FROM users WHERE id = ANY(:ids) AND "
                    "smyles_achetes + smyles_gagnes + smyles_promo "
                    "<> credits_balance"
                ),
                {"ids": [sender_id, receiver_id]},
            )).first()
        assert int(bad.n) == 0
    finally:
        async with SessionLocal() as db:
            if offer_id is not None:
                await db.execute(
                    delete(TradeOffer).where(TradeOffer.id == offer_id)
                )
            await db.execute(
                delete(UnlockedPrompt).where(
                    UnlockedPrompt.current_owner_id.in_([sender_id, receiver_id])
                )
            )
            await db.execute(
                delete(Prompt).where(Prompt.artist_id.in_([sender_id, receiver_id]))
            )
            await db.execute(delete(User).where(User.id == receiver_id))
            await db.commit()
