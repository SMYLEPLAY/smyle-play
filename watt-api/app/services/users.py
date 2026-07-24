from datetime import datetime, timezone

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate
from app.services.referrals import generate_referral_code

# Bonus de bienvenue offert à l'inscription. Désormais GRANTé explicitement
# (transaction BONUS tracée dans le ledger) au lieu du server_default de la
# colonne credits_balance. Cf. migration 0066 + décision Tom 2026-06-25.
WELCOME_BONUS_CREDITS = 10


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession, user: UserCreate, signup_ip: str | None = None
) -> User:
    db_user = User(
        email=user.email,
        password_hash=hash_password(user.password),
        referral_code=await generate_referral_code(db),
        signup_ip=signup_ip,  # anti-abus H0.4 (None si indéterminé)
        # Inscription encadrée (Phase 3) : register() a déjà exigé l'acceptation
        # CGU + âge avant d'appeler create_user → on trace l'instant (preuve).
        accepted_terms_at=datetime.now(timezone.utc),
    )
    db.add(db_user)
    # flush → refresh DANS la transaction (asyncpg : un refresh APRÈS commit
    # s'exécute dans une nouvelle transaction qui ne voit pas toujours la ligne
    # → "Could not refresh instance"). On charge les valeurs server-default
    # (created_at, soldes, etc.) avant de committer.
    await db.flush()
    await db.refresh(db_user)

    # Bonus de bienvenue : grant EXPLICITE et tracé (transaction BONUS) plutôt
    # qu'un solde initial silencieux. grant_credits_atomic pose son propre
    # savepoint + lock la row user ; on est encore avant le commit final, donc
    # tout part dans la même transaction (atomique). Import local pour éviter
    # tout cycle d'import au chargement du module.
    from app.models.transaction import TransactionType
    from app.services.credits import grant_credits_atomic

    await grant_credits_atomic(
        db,
        db_user.id,
        WELCOME_BONUS_CREDITS,
        reason="welcome_bonus",
        tx_type=TransactionType.BONUS,
    )
    await db.refresh(db_user)  # recharge credits_balance = 10 (post-grant)
    await db.commit()
    return db_user


async def get_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User))
    return list(result.scalars().all())


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User | None:
    user = await get_user_by_email(db, email)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
