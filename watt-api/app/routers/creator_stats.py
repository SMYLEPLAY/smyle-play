"""Stats créateur (Section 3 — confiance/motivation).

GET /me/creator-stats — lecture seule : écoutes, ventes, revenus (Smyles gagnés)
du créateur connecté. Complète l'ancien /me/stats (qui ne donnait qu'écoutes +
rang) avec les VENTES et les REVENUS, les signaux qui motivent un créateur à
revenir. Aucune écriture, aucun impact sur l'existant.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
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

    return {
        "tracks": tracks,
        "plays": plays,
        "sales": sales,
        "revenue_smyles": revenue,
    }
