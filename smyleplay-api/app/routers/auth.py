from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token
from app.core.ratelimit import (
    LIMIT_FORGOT_PASSWORD,
    LIMIT_LOGIN,
    LIMIT_REGISTER,
    LIMIT_RESET_PASSWORD,
    limiter,
)
from app.database import get_db
from app.schemas.user import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserLogin,
    UserRead,
)
from app.services.playlists import ensure_default_wishlist
from app.services.referrals import attach_referral_at_signup
from app.services.users import authenticate_user, create_user, get_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(LIMIT_REGISTER)
async def register(
    user: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    existing = await get_user_by_email(db, user.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    new_user = await create_user(db, user)
    # Lien de parrainage — best-effort, silencieux. Un code invalide / absent
    # ne casse jamais l'inscription. Aucun crédit versé ici : seulement le lien
    # PENDING, débloqué plus tard à la 1ère action du filleul.
    try:
        referral = await attach_referral_at_signup(db, new_user, user.referral_code)
        if referral is not None:
            await db.commit()
    except Exception:
        await db.rollback()
    # Seed wishlist par défaut — best-effort, idempotent. Une erreur ici
    # ne doit pas casser l'inscription : la wishlist pourra être recréée
    # paresseusement au premier GET /playlists/wishlist.
    try:
        await ensure_default_wishlist(db, new_user)
    except Exception:
        await db.rollback()
    # Email de bienvenue — best-effort (chantier hygiène revenu 2026-06-10).
    # Mode test Resend tant que le domaine WATT n'est pas déposé.
    try:
        from app.services.emails import send_welcome_email
        await send_welcome_email(
            new_user.email, name=new_user.artist_name or None
        )
    except Exception:
        pass
    return new_user


@router.post("/login", response_model=Token)
@limiter.limit(LIMIT_LOGIN)
async def login(
    credentials: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, credentials.email, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(subject=user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
    }


# ─────────────────────────────────────────────────────────────────────────
# Reset mot de passe (mission Tier 1, 2026-06-10)
#
# Sécurité : jeton 32 bytes urlsafe, stocké HACHÉ (SHA-256), expiration
# 60 min, usage unique, réponse toujours 200 sur forgot-password
# (anti-énumération d'emails). Demander un nouveau lien invalide les
# jetons actifs précédents du même compte.
# ─────────────────────────────────────────────────────────────────────────

@router.post("/forgot-password")
@limiter.limit(LIMIT_FORGOT_PASSWORD)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Toujours {"ok": true} — qu'un compte existe ou non pour cet email."""
    import hashlib
    import secrets
    from datetime import datetime, timedelta, timezone

    user = await get_user_by_email(db, payload.email)
    if user is not None and not str(user.email).endswith("@deleted.watt"):
        # Invalide les jetons actifs précédents (un seul lien valable).
        from sqlalchemy import update as _update

        from app.models.password_reset_token import PasswordResetToken
        now = datetime.now(timezone.utc)
        await db.execute(
            _update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

        token = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=now + timedelta(minutes=60),
        ))
        await db.commit()

        # Lien absolu : même origine que la requête (front + API servis
        # ensemble). https forcé hors localhost (proxy Railway).
        base = str(request.base_url).rstrip("/")
        if "localhost" not in base and "127.0.0.1" not in base:
            base = base.replace("http://", "https://", 1)
        try:
            from app.services.emails import send_password_reset_email
            await send_password_reset_email(
                user.email, link=f"{base}/reset?token={token}"
            )
        except Exception:
            pass
    return {"ok": True}


@router.post("/reset-password")
@limiter.limit(LIMIT_RESET_PASSWORD)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Échange jeton valide → nouveau mot de passe. 400 si lien mort."""
    import hashlib
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.password_reset_token import PasswordResetToken
    from app.models.user import User
    from app.services.users import hash_password

    th = hashlib.sha256(payload.token.encode()).hexdigest()
    prt = (await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == th)
    )).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if prt is None or prt.used_at is not None or prt.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lien invalide ou expiré. Redemande un email de réinitialisation.",
        )

    user = (await db.execute(
        select(User).where(User.id == prt.user_id)
    )).scalar_one_or_none()
    if user is None or str(user.email).endswith("@deleted.watt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compte introuvable.",
        )

    user.password_hash = hash_password(payload.new_password)
    prt.used_at = now
    await db.commit()
    return {"ok": True}
