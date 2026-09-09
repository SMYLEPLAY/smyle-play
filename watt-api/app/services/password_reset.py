"""
Émission des jetons de réinitialisation de mot de passe (B2, 2026-09-08).

Ce module NE CHANGE RIEN au mécanisme : il extrait, tel quel, le code qui
vivait dans `app/routers/auth.py::forgot_password` (jeton 32 bytes urlsafe,
empreinte SHA-256 en base, 60 minutes, usage unique, invalidation des jetons
actifs précédents). Un seul endroit produit désormais un jeton :

  - `POST /auth/forgot-password` (chemin normal, envoi par email) ;
  - `tools/reset_link.py` (secours bêta interne, lien affiché en local).

Les deux appellent `issue_reset_token()`. Un jeton produit par l'outil est
donc rigoureusement le même objet qu'un jeton produit par l'endpoint, et il
est accepté par `POST /auth/reset-password` sans traitement particulier.

Le jeton en clair n'est renvoyé qu'une fois, par la valeur de retour. Il
n'est JAMAIS journalisé (un log Railway lisible = 60 minutes de prise de
contrôle offerte à quiconque lit les logs).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy import update as _update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_token import PasswordResetToken
from app.models.user import User

logger = logging.getLogger(__name__)

# Durée de validité — valeur historique, ne pas changer sans revoir le texte
# de l'email et de reset.html qui annoncent 60 minutes.
RESET_TOKEN_TTL_MINUTES = 60

# Suffixe des comptes anonymisés par la suppression de compte
# (app/services/account_deletion.py).
DELETED_EMAIL_SUFFIX = "@deleted.watt"


class ResetLinkRefused(Exception):
    """Le compte visé n'a pas droit à un lien (inconnu, supprimé, banni)."""


def account_is_resettable(user: User | None) -> bool:
    """Le compte peut-il recevoir un lien ? (règle du endpoint, inchangée)"""
    return user is not None and not str(user.email).endswith(DELETED_EMAIL_SUFFIX)


async def issue_reset_token(db: AsyncSession, user: User) -> str:
    """
    Invalide les jetons actifs du compte, en crée un neuf, commit, et renvoie
    le jeton EN CLAIR (unique occasion de le lire — seule l'empreinte reste).
    """
    now = datetime.now(timezone.utc)
    # Un seul lien vivant à la fois.
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
        expires_at=now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
    ))
    await db.commit()
    return token


def build_reset_link(base_url: str, token: str) -> str:
    """
    Lien absolu vers la page de réinitialisation.

    S-10 : le jeton passe en FRAGMENT (`#token=`), jamais en query — un
    fragment n'est pas transmis au serveur, donc ni access-logs uvicorn ni
    en-tête Referer.
    """
    base = (base_url or "").rstrip("/")
    if "localhost" not in base and "127.0.0.1" not in base:
        base = base.replace("http://", "https://", 1)
    return f"{base}/reset#token={token}"


async def issue_reset_link_for_email(
    db: AsyncSession,
    email: str,
    *,
    base_url: str,
) -> tuple[User, str]:
    """
    Chemin de SECOURS (outil local `tools/reset_link.py`, jamais HTTP).

    Contrairement au endpoint — qui répond 200 quoi qu'il arrive pour ne rien
    révéler — cet appel est bavard : il est destiné à un opérateur humain,
    pas au réseau. Il refuse explicitement le compte inconnu, supprimé ou
    banni.

    Renvoie (user, lien). Le lien contient le jeton en clair : à afficher une
    fois, jamais à journaliser.
    """
    target = (email or "").strip().lower()
    if not target:
        raise ResetLinkRefused("email vide.")

    user = (
        await db.execute(select(User).where(User.email == target))
    ).scalars().first()

    if user is None:
        raise ResetLinkRefused(f"aucun compte avec l'email {target!r}.")
    if str(user.email).endswith(DELETED_EMAIL_SUFFIX):
        raise ResetLinkRefused(f"{target} : compte supprimé — aucun lien émis.")
    if bool(getattr(user, "is_banned", False)):
        raise ResetLinkRefused(f"{target} : compte banni — aucun lien émis.")

    token = await issue_reset_token(db, user)
    # Trace applicative : QUI a été visé et QUAND. Jamais le jeton ni le lien.
    logger.warning(
        "[reset-secours] lien de réinitialisation émis hors email pour "
        "user_id=%s email=%s (expire dans %s min)",
        user.id, user.email, RESET_TOKEN_TTL_MINUTES,
    )
    return user, build_reset_link(base_url, token)
