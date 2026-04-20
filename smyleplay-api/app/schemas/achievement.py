"""
Phase 9.6 — Schémas Pydantic pour les achievements.

Deux familles :
  - AchievementRead       : vue catalog publique (un badge avec ses paliers)
  - UserAchievementProgress : statut user pour 1 badge (débloqué ou pas)
  - MyAchievementsResponse  : agrégat /me/achievements (progress par axe + items)

Le catalog est entièrement public (pas de gating) car les badges sont
des objectifs visibles dans l'UI. Le contenu gated reste les prompt_text /
example_outputs (Phase 9.4).
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.achievement import AchievementAxis


# -----------------------------------------------------------------------------
# Catalog public d'un achievement
# -----------------------------------------------------------------------------

class AchievementRead(BaseModel):
    """Vue catalog d'un badge — affichable publiquement sur la page Trophées."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str
    axis: AchievementAxis
    threshold: int
    credit_reward: int
    display_order: int


class AchievementsListResponse(BaseModel):
    """Réponse de GET /achievements — catalog complet groupé par axe côté UI."""

    items: list[AchievementRead]
    total: int


# -----------------------------------------------------------------------------
# Progression user
# -----------------------------------------------------------------------------

class UserAchievementProgress(BaseModel):
    """
    Statut d'UN achievement pour le user courant.

    `unlocked=False` + `unlocked_at=None` : badge pas encore obtenu, mais
    on peut afficher la progression (current_value vs threshold) côté UI.
    `unlocked=True` + `unlocked_at` : badge débloqué, optionnellement avec
    `bonus_transaction_id` pour audit (lien vers la transaction BONUS).
    """

    achievement: AchievementRead
    unlocked: bool
    unlocked_at: datetime | None = None
    bonus_transaction_id: UUID | None = None


class AchievementProgressByAxis(BaseModel):
    """
    Compteurs courants du user sur les 3 axes.

      - buyer  : nb d'UnlockedPrompt possédés (current_owner)
      - fan    : nb d'OwnedAdn
      - artist : credits_earned_total cumulé
    """

    buyer: int
    fan: int
    artist: int


class MyAchievementsResponse(BaseModel):
    """
    Réponse de GET /me/achievements.

    `progress` permet à l'UI d'afficher des barres de progression
    ("12/50 prompts pour Collectionneur") sans recalcul côté front.
    """

    progress: AchievementProgressByAxis
    items: list[UserAchievementProgress]
