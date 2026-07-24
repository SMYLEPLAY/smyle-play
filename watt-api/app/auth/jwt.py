from datetime import datetime, timedelta, timezone

import jwt  # PyJWT (remplace python-jose, CVE-2024-33663/33664, non maintenue)
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.users import get_user_by_email

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(subject: str, token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_EXPIRE_MINUTES
    )
    # `tv` = version de jeton (durcissement) : recopiée depuis user.token_version,
    # vérifiée à chaque requête. Un reset de mot de passe l'incrémente → révoque
    # les jetons antérieurs.
    payload = {"sub": subject, "exp": expire, "tv": token_version}
    return jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def _decode_claims(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None


def decode_access_token(token: str) -> str | None:
    claims = _decode_claims(token)
    return claims.get("sub") if claims else None


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    claims = _decode_claims(token)
    email = claims.get("sub") if claims else None
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = await get_user_by_email(db, email)
    if user is None:
        raise credentials_exception
    # Révocation (durcissement) : le `tv` du jeton doit correspondre à la
    # version courante du compte. Un jeton sans `tv` vaut 0 (comptes/jetons
    # antérieurs à la fonctionnalité → restent valides jusqu'à expiration).
    if int(claims.get("tv", 0) or 0) != int(user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée, reconnecte-toi.",
        )
    # Modération DSA (Phase 3) : un compte banni ne peut plus rien faire
    # d'authentifié, même avec un jeton encore valide.
    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte suspendu.",
        )
    return user
