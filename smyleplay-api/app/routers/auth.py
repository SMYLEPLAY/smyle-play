from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token
from app.database import get_db
from app.schemas.user import Token, UserCreate, UserLogin, UserRead
from app.services.playlists import ensure_default_wishlist
from app.services.referrals import attach_referral_at_signup
from app.services.users import authenticate_user, create_user, get_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
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
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
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
