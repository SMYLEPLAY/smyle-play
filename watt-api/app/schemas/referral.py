from pydantic import BaseModel


class ReferralStats(BaseModel):
    """Stats de parrainage exposées au user connecté (GET /referrals/me)."""

    referral_code: str | None
    total_referred: int      # nb de filleuls inscrits avec mon code
    rewarded: int            # filleuls ayant déclenché la récompense
    pending: int             # filleuls inscrits, action pas encore faite
    credits_earned: int      # Smyles gagnés via parrainage (côté parrain)
    reward_per_side: int     # barème courant (Smyles par côté)
