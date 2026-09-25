"""Stats créateur (Section 3 — confiance/motivation).

GET /me/creator-stats — lecture seule : écoutes, ventes, revenus (Smyles gagnés)
du créateur connecté. Complète l'ancien /me/stats (qui ne donnait qu'écoutes +
rang) avec les VENTES et les REVENUS, les signaux qui motivent un créateur à
revenir. Aucune écriture, aucun impact sur l'existant.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.track import Track
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User

router = APIRouter(tags=["creator-stats"])


@router.get("/me/creator-stats")
async def creator_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    uid = current_user.id

    tracks = int((await db.execute(
        select(func.count(Track.id)).where(
            Track.artist_id == uid, Track.is_deleted.is_(False)
        )
    )).scalar() or 0)

    plays = int((await db.execute(
        select(func.coalesce(func.sum(Track.plays), 0)).where(
            Track.artist_id == uid, Track.is_deleted.is_(False)
        )
    )).scalar() or 0)

    # Ventes = transactions COMPLETED où l'utilisateur est le vendeur et a
    # touché des Smyles (artist_revenue > 0). Revenus = somme de ces gains.
    sales_row = (await db.execute(
        select(
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.artist_revenue), 0),
        ).where(
            Transaction.seller_id == uid,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.artist_revenue > 0,
        )
    )).first()
    sales = int((sales_row[0] if sales_row else 0) or 0)
    revenue = int((sales_row[1] if sales_row else 0) or 0)

    # Lot 3 — part des gains payée par les acheteurs avec des Smyles OFFERTS :
    # gagnée, dépensable, mais NON retirable (fuite « offert → argent réel »
    # corrigée). Ventes directes (ligne UNLOCK : promo_non_retirable) + part
    # vendeur et royaltie des reventes (détail dans metadata « promo »).
    non_retirable = int((await db.execute(text(
        "SELECT COALESCE(SUM(CASE "
        "  WHEN type = 'unlock' AND seller_id = :u THEN promo_non_retirable "
        "  WHEN type = 'resale' AND seller_id = :u THEN COALESCE((metadata_json->'promo'->>'vendeur')::int, 0) "
        "  ELSE 0 END), 0) "
        "+ COALESCE((SELECT SUM(COALESCE((metadata_json->'promo'->>'artiste')::int, 0)) "
        "  FROM transactions WHERE type = 'resale' AND status = 'completed' "
        "  AND metadata_json->>'original_artist_id' = CAST(:u AS text)), 0) "
        "FROM transactions WHERE status = 'completed' AND seller_id = :u"
    ), {"u": uid})).scalar_one() or 0)

    return {
        "tracks": tracks,
        "plays": plays,
        "sales": sales,
        "revenue_smyles": revenue,
        # Cumul des gains « gagnés — non retirables » (payés en Smyles offerts).
        "revenue_non_retirable_smyles": non_retirable,
        # Ceux encore sur le compte (le promo se dépense en premier).
        "gagnes_non_retirables_detenus": int(current_user.smyles_promo_gagnes or 0),
    }
