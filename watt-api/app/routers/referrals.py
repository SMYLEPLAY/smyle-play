"""
Router parrainage (mécanique 1).

Endpoints :
  GET  /referrals/me      → mon code de parrainage + mes stats (auth)
  POST /referrals/quetes  → Étape 3 : verse les paliers de quêtes atteints
                            (filleuls ACTIFS, bucket promo, idempotent) et
                            renvoie la progression. 404 si
                            FEATURE_QUETES_PARRAINAGE est OFF.

L'intake du code se fait à l'inscription (POST /auth/register, champ
referral_code). Le déblocage de la récompense est automatique à la 1ère
action du filleul (cf. app/services/referrals.maybe_reward_referral),
branché sur la création de son et l'achat — pas d'endpoint dédié.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.core.ratelimit import LIMIT_PURCHASE, limiter
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


@router.post("/quetes")
@limiter.limit(LIMIT_PURCHASE)  # écrit au registre : même plafond qu'un achat
async def mes_quetes(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not settings.FEATURE_QUETES_PARRAINAGE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    from app.services.quetes_parrainage import verifier_et_verser_quetes

    try:
        res = await verifier_et_verser_quetes(db, current_user.id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return res
