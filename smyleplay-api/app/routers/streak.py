"""
Router streak de connexion (mécanique 2).

Endpoints :
  GET  /streak/me       → état du streak sans réclamer (auth)
  POST /streak/checkin  → réclame la récompense du jour (auth, idempotent/jour)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.streak import StreakClaim, StreakStatus
from app.services.streak import claim_daily_checkin, get_streak_status

router = APIRouter(prefix="/streak", tags=["streak"])


@router.get("/me", response_model=StreakStatus)
async def my_streak(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    status = await get_streak_status(db, current_user.id)
    return StreakStatus(**status)


@router.post("/checkin", response_model=StreakClaim)
async def checkin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await claim_daily_checkin(db, current_user.id)
    await db.commit()
    return StreakClaim(**result)
