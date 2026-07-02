from pydantic import BaseModel


class StreakStatus(BaseModel):
    """État du streak sans réclamer (GET /streak/me)."""

    streak_count: int                 # jours consécutifs en cours
    can_checkin_today: bool           # False si déjà réclamé aujourd'hui
    next_reward: int                  # Smyles que rapportera le prochain check-in
    days_until_milestone: int | None  # jours avant le palier +3 (None si déjà fait)


class StreakClaim(BaseModel):
    """Résultat d'un check-in (POST /streak/checkin)."""

    claimed: bool          # False si déjà réclamé aujourd'hui (no-op)
    streak_count: int
    reward_granted: int    # Smyles versés (0 si déjà réclamé)
    is_milestone: bool = False
    already_claimed: bool = False
