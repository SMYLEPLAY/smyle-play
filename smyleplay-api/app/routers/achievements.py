"""
Phase 9.6 — Endpoints achievements.

Routes :
  GET /achievements        (public)  — catalog complet des badges
  GET /me/achievements     (auth)    — progression du user courant
                                       + items (débloqués/pas) + counts par axe

Le catalog est public car les badges sont des objectifs visibles
(pas de gating de contenu). Les hooks dans unlock_*_atomic créent les
UserAchievement automatiquement — le user n'a pas à appeler un endpoint
pour "claim" un badge.

Pas de POST/PUT/DELETE en V1 : le catalog est statique (seedé via
migration 0009), les déblocages sont automatiques.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.achievement import (
    AchievementProgressByAxis,
    AchievementRead,
    AchievementsListResponse,
    MyAchievementsResponse,
    UserAchievementProgress,
)
from app.services.achievements import (
    list_all_achievements,
    list_user_achievements_with_progress,
)


# Deux routers car deux préfixes différents (cf. main.py library/catalog
# qui font pareil) — séparer permet à FastAPI de bien grouper dans Swagger.
public_router = APIRouter(prefix="/achievements", tags=["achievements"])
me_router = APIRouter(prefix="/me/achievements", tags=["achievements"])


# -----------------------------------------------------------------------------
# GET /achievements — catalog public
# -----------------------------------------------------------------------------

@public_router.get("", response_model=AchievementsListResponse)
async def list_achievements_catalog(
    db: AsyncSession = Depends(get_db),
):
    """
    Catalog complet des badges, ordonné par axe puis threshold puis display_order.

    Pas d'auth — c'est de la donnée publique (les utilisateurs doivent
    pouvoir voir les objectifs disponibles avant de s'inscrire).
    """
    items = await list_all_achievements(db)
    return AchievementsListResponse(
        items=[AchievementRead.model_validate(a) for a in items],
        total=len(items),
    )


# -----------------------------------------------------------------------------
# GET /me/achievements — progression personnelle
# -----------------------------------------------------------------------------

@me_router.get("", response_model=MyAchievementsResponse)
async def list_my_achievements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Progression du user courant sur les 3 axes + statut de chaque achievement.

    Réponse :
      - progress.{buyer,fan,artist} : compteurs courants (ex: 12 prompts
        unlockés, 3 ADN, 250 crédits gagnés)
      - items[i].unlocked : True si débloqué, False sinon
      - items[i].unlocked_at : timestamp si débloqué
      - items[i].bonus_transaction_id : audit trail vers la transaction BONUS
        (null si reward=0 ou pas encore débloqué)

    L'UI peut afficher des barres "12/50 pour Collectionneur" en utilisant
    progress.buyer comparé à items[].achievement.threshold côté front.
    """
    data = await list_user_achievements_with_progress(
        db, user_id=current_user.id
    )
    return MyAchievementsResponse(
        progress=AchievementProgressByAxis(**data["progress"]),
        items=[
            UserAchievementProgress(
                achievement=AchievementRead.model_validate(item["achievement"]),
                unlocked=item["unlocked"],
                unlocked_at=item["unlocked_at"],
                bonus_transaction_id=item["bonus_transaction_id"],
            )
            for item in data["items"]
        ],
    )
