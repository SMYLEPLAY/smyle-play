"""
Émission des jetons de vérification d'email (Phase A — ouverture gratuite,
2026-09-11).

Décalque du reset MDP (`app/services/password_reset.py`) : jeton 32 bytes
urlsafe, empreinte SHA-256 en base (jamais le jeton en clair), expiration,
usage unique (`used_at`), et invalidation des jetons actifs précédents au
nouvel envoi. Le jeton en clair n'est renvoyé qu'une fois, par la valeur de
retour, et n'est JAMAIS journalisé.

Le jeton voyage en FRAGMENT (`#token=`) dans le lien, comme le reset : un
fragment n'est pas transmis au serveur, donc il ne finit ni dans les
access-logs uvicorn ni dans un en-tête Referer.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import update as _update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_verification_token import EmailVerificationToken
from app.models.user import User

logger = logging.getLogger(__name__)

# La vérification n'est pas urgente (contrairement au reset MDP, 60 min) :
# 48 h laissent le temps d'ouvrir l'email. Un nouvel envoi reste possible à
# tout moment (endpoint de renvoi) et invalide le précédent.
VERIFICATION_TOKEN_TTL_HOURS = 48

# Suffixe des comptes anonymisés par la suppression de compte
# (app/services/account_deletion.py) — jamais de lien pour ceux-là.
DELETED_EMAIL_SUFFIX = "@deleted.watt"


def account_can_verify(user: User | None) -> bool:
    """Le compte peut-il recevoir un lien de vérification ? On n'émet pas de
    lien pour un compte inconnu, supprimé, ou déjà vérifié."""
    return (
        user is not None
        and not str(user.email).endswith(DELETED_EMAIL_SUFFIX)
        and not bool(getattr(user, "email_verified", False))
    )


async def issue_verification_token(db: AsyncSession, user: User) -> str:
    """
    Invalide les jetons actifs du compte, en crée un neuf, commit, et renvoie
    le jeton EN CLAIR (unique occasion de le lire — seule l'empreinte reste).
    """
    now = datetime.now(timezone.utc)
    # Un seul lien vivant à la fois.
    await db.execute(
        _update(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    token = secrets.token_urlsafe(32)
    db.add(EmailVerificationToken(
        user_id=user.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now + timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS),
    ))
    await db.commit()
    return token


def build_verification_link(base_url: str, token: str) -> str:
    """
    Lien absolu vers la page de vérification d'email.

    Comme le reset MDP : le jeton passe en FRAGMENT (`#token=`), jamais en
    query — un fragment n'est pas transmis au serveur (ni access-logs ni
    Referer). Le front lit `location.hash` et POSTe sur /auth/verify-email.
    """
    base = (base_url or "").rstrip("/")
    if "localhost" not in base and "127.0.0.1" not in base:
        base = base.replace("http://", "https://", 1)
    return f"{base}/verifier-email#token={token}"
