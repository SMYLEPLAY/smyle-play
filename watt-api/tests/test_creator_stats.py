"""Stats créateur (Section 3) — écoutes / ventes / revenus."""
import uuid

from httpx import AsyncClient
from sqlalchemy import delete

from app.database import SessionLocal
from app.models.track import Track
from app.models.transaction import Transaction, TransactionStatus, TransactionType


async def test_creator_stats_counts_plays_sales_revenue(
    client: AsyncClient, test_user: dict, auth_headers: dict
):
    uid = test_user["id"]
    track_id = uuid.uuid4()
    tx_id = uuid.uuid4()
    try:
        async with SessionLocal() as db:
            db.add(Track(id=track_id, artist_id=uid, title="Hit", plays=5,
                         is_deleted=False))
            # Une vente : l'utilisateur est vendeur, touche 8 Smyles (10 = 8 + 2).
            db.add(Transaction(
                id=tx_id, type=TransactionType.UNLOCK,
                status=TransactionStatus.COMPLETED,
                seller_id=uid,
                credits_amount=10, platform_fee=2, artist_revenue=8,
            ))
            await db.commit()

        r = await client.get("/me/creator-stats", headers=auth_headers)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["tracks"] == 1, s
        assert s["plays"] == 5, s
        assert s["sales"] == 1, s
        assert s["revenue_smyles"] == 8, s

        # sans auth → 401
        r0 = await client.get("/me/creator-stats")
        assert r0.status_code == 401, r0.text
    finally:
        # Le ledger est append-only : on ne supprime PAS la transaction
        # (seller_id passe à NULL quand le user fixture est supprimé). On
        # nettoie seulement le track.
        async with SessionLocal() as db:
            await db.execute(delete(Track).where(Track.id == track_id))
            await db.commit()
