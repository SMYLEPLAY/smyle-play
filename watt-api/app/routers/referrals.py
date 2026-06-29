"""
Router parrainage (mécanique 1).

Endpoints :
  GET /referrals/me  → mon code de parrainage + mes stats (auth)

L'intake du code se fait à l'inscription (POST /auth/register, champ
referral_code). Le déblocage de la récompense est automatique à la 1ère
action du filleul (cf. app/services/referrals.maybe_reward_referral),
branché sur la création de son et l'achat — pas d'endpoint dédié.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.referral import ReferralStats
from app.services.referrals import get_referral_stats

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/me", response_model=ReferralStats)
async def my_referrals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stats = await get_referral_stats(db, current_user.id)
    return ReferralStats(**stats)
