"""
Service parrainage (mécanique 1).

Boucle d'expérience client : un parrain partage son `referral_code`. Un
nouvel inscrit le saisit → on crée un lien `Referral` en statut PENDING.
La récompense (10 Smyles PAR CÔTÉ) n'est versée qu'à la PREMIÈRE vraie
action du filleul (1er son posté OU 1er achat), via `maybe_reward_referral`.
Cet ancrage sur une action réelle est l'anti-faux-compte : créer 1000
comptes vides ne rapporte rien.

Barème ancré sur l'économie réelle (1 Smyle ≈ 0,70 €, bonus de bienvenue
= 10 Smyles). Voir [[2026-06-07]] et [[project_mechanics_before_stripe]].
"""
import secrets
import string
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.referral import Referral, ReferralStatus
from app.models.transaction import TransactionType
from app.models.user import User
from app.services.credits import grant_credits_atomic

# Montant crédité à CHAQUE côté (parrain + filleul) au déblocage.
REFERRAL_REWARD_CREDITS = 10

# Alphabet sans caractères ambigus (pas de O/0, I/1) → codes lisibles à l'oral.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8


async def generate_referral_code(db: AsyncSession) -> str:
    """Génère un code de parrainage unique (retry sur collision improbable)."""
    for _ in range(10):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        exists = await db.scalar(
            select(User.id).where(User.referral_code == code)
        )
        if exists is None:
            return code
    # Fallback ultra-improbable : on élargit la longueur.
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH + 4))


async def attach_referral_at_signup(
    db: AsyncSession,
    new_user: User,
    referral_code: str | None,
) -> Referral | None:
    """
    Lie le nouvel inscrit à un parrain si le code fourni est valide.

    Best-effort et silencieux : un code inconnu, vide, ou auto-parrainage
    ne casse JAMAIS l'inscription (return None). Aucun crédit versé ici —
    seulement le lien PENDING. Le caller commit.
    """
    if not referral_code:
        return None
    code = referral_code.strip().upper()
    if not code:
        return None

    referrer = await db.scalar(
        select(User).where(User.referral_code == code)
    )
    if referrer is None:
        return None
    if referrer.id == new_user.id:
        return None  # anti auto-parrainage

    # Un filleul ne peut être parrainé qu'une fois (unique en base, mais on
    # vérifie en amont pour éviter une IntegrityError).
    already = await db.scalar(
        select(Referral.id).where(Referral.referred_id == new_user.id)
    )
    if already is not None:
        return None

    referral = Referral(
        referrer_id=referrer.id,
        referred_id=new_user.id,
        status=ReferralStatus.PENDING,
        reward_credits=REFERRAL_REWARD_CREDITS,
    )
    db.add(referral)
    return referral


async def maybe_reward_referral(db: AsyncSession, referred_user_id: UUID) -> bool:
    """
    Débloque la récompense de parrainage à la 1ère action du filleul.

    IDEMPOTENT : si pas de parrainage en attente (ou déjà récompensé), ne fait
    rien et retourne False. Sûr à appeler depuis plusieurs points (création de
    son, achat) sans double crédit.

    Verse `reward_credits` au parrain ET au filleul via BONUS, puis passe le
    lien en REWARDED. Le caller commit.
    """
    referral = await db.scalar(
        select(Referral).where(
            Referral.referred_id == referred_user_id,
            Referral.status == ReferralStatus.PENDING,
        )
    )
    if referral is None:
        return False

    amount = referral.reward_credits

    # Crédite les deux côtés. grant_credits_atomic pose ses propres savepoints.
    await grant_credits_atomic(
        db,
        referral.referrer_id,
        amount,
        reason="referral_reward_referrer",
        tx_type=TransactionType.BONUS,
        metadata={"referral_id": str(referral.id), "side": "referrer"},
    )
    await grant_credits_atomic(
        db,
        referral.referred_id,
        amount,
        reason="referral_reward_referred",
        tx_type=TransactionType.BONUS,
        metadata={"referral_id": str(referral.id), "side": "referred"},
    )

    referral.status = ReferralStatus.REWARDED
    from sqlalchemy import func as _func
    referral.rewarded_at = _func.now()
    await db.flush()
    return True


async def get_referral_stats(db: AsyncSession, user_id: UUID) -> dict:
    """Stats de parrainage du user : code + filleuls + Smyles gagnés."""
    user = await db.get(User, user_id)
    code = user.referral_code if user else None

    rows = (
        await db.execute(
            select(Referral.status, Referral.reward_credits).where(
                Referral.referrer_id == user_id
            )
        )
    ).all()

    total = len(rows)
    rewarded = sum(1 for status, _ in rows if status == ReferralStatus.REWARDED)
    pending = total - rewarded
    credits_earned = sum(
        credits for status, credits in rows if status == ReferralStatus.REWARDED
    )

    return {
        "referral_code": code,
        "total_referred": total,
        "rewarded": rewarded,
        "pending": pending,
        "credits_earned": credits_earned,
        "reward_per_side": REFERRAL_REWARD_CREDITS,
    }
