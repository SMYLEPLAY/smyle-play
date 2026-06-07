"""
Service streak de connexion (mécanique 2).

Boucle d'expérience client : revenir chaque jour = Smyles. Crée l'habitude,
deuxième source de Smyles (avec le parrainage) qui alimente le sink (packs).

Barème ancré sur l'économie réelle (1 Smyle ≈ 0,70 €, bonus de bienvenue
= 10 Smyles) — volontairement conservateur pour ne pas inonder l'économie :
  - +1 Smyle par jour réclamé.
  - +3 (au lieu de +1) tous les 7 jours consécutifs (J7, J14, …).
  => une semaine pleine = 6×1 + 3 = 9 Smyles.

Règles :
  - 1 réclamation par jour (date UTC). Re-checkin le même jour = no-op.
  - Gap d'un jour ou plus → le streak repart à 1.
Voir [[2026-06-07]] et [[project_engagement_loop_economy]].
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import TransactionType
from app.models.user import User
from app.services.credits import grant_credits_atomic

# Tous les 7 jours consécutifs, la récompense passe de DAILY à MILESTONE.
DAILY_REWARD = 1
MILESTONE_REWARD = 3
MILESTONE_EVERY = 7


def _today_utc():
    return datetime.now(timezone.utc).date()


def reward_for_streak(streak_count: int) -> int:
    """Récompense du jour selon le rang dans le cycle (7e jour = palier)."""
    if streak_count > 0 and streak_count % MILESTONE_EVERY == 0:
        return MILESTONE_REWARD
    return DAILY_REWARD


async def get_streak_status(db: AsyncSession, user_id: UUID) -> dict:
    """État du streak SANS réclamer (pour affichage)."""
    user = await db.get(User, user_id)
    today = _today_utc()
    last = user.last_checkin_date if user else None
    current = user.streak_count if user else 0

    # Si le dernier check-in est plus vieux qu'hier, le streak est "cassé"
    # (l'affichage doit montrer 0 à venir, pas l'ancien compteur).
    if last is not None and last < today - timedelta(days=1):
        current_effective = 0
    else:
        current_effective = current

    can_checkin = last != today
    # Aperçu de ce que rapportera le prochain check-in.
    next_count = 1 if (last is None or last < today - timedelta(days=1)) else current + 1
    next_reward = reward_for_streak(next_count) if can_checkin else 0

    return {
        "streak_count": current_effective,
        "can_checkin_today": can_checkin,
        "next_reward": next_reward,
        "days_until_milestone": (MILESTONE_EVERY - (next_count % MILESTONE_EVERY)) % MILESTONE_EVERY
        if can_checkin else None,
    }


async def claim_daily_checkin(db: AsyncSession, user_id: UUID) -> dict:
    """
    Réclame la récompense quotidienne. Idempotent par jour.

    Retourne un dict avec `claimed` (False si déjà fait aujourd'hui),
    le nouveau streak_count et la récompense versée. Le caller commit.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found")

    today = _today_utc()
    last = user.last_checkin_date

    # Déjà réclamé aujourd'hui → no-op idempotent.
    if last == today:
        return {
            "claimed": False,
            "streak_count": user.streak_count,
            "reward_granted": 0,
            "already_claimed": True,
        }

    # Consécutif si le dernier check-in était hier ; sinon on repart à 1.
    if last == today - timedelta(days=1):
        new_count = user.streak_count + 1
    else:
        new_count = 1

    reward = reward_for_streak(new_count)

    user.last_checkin_date = today
    user.streak_count = new_count
    await db.flush()

    await grant_credits_atomic(
        db,
        user_id,
        reward,
        reason="streak_checkin",
        tx_type=TransactionType.BONUS,
        metadata={"streak_count": new_count},
    )

    is_milestone = new_count % MILESTONE_EVERY == 0
    return {
        "claimed": True,
        "streak_count": new_count,
        "reward_granted": reward,
        "is_milestone": is_milestone,
        "already_claimed": False,
    }
