"""Modération DSA — actions concrètes sur un contenu ou un compte signalé.

Phase 3 lancement (2026-07-24). Le signalement DSA (0081) ne faisait que
RECEVOIR. Ici on AGIT, réservé au compte officiel (contrôle is_official fait
au niveau des endpoints) :

- `takedown_content` : retire un contenu de la vue publique en réutilisant le
  drapeau « caché » propre à chaque type (is_published / is_deleted / visibility).
  On NE supprime jamais la ligne → la preuve est conservée (exigence DSA) et un
  éventuel acheteur garde son accès en bibliothèque.
- `ban_user` / `unban_user` : suspend / rétablit un compte (login + tout accès
  authentifié bloqués via get_current_user).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.album import Album
from app.models.playlist import Playlist
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def ban_user(
    db: AsyncSession, user_id: uuid.UUID, reason: str | None = None
) -> User | None:
    """Suspend un compte. Retourne le User modifié, ou None s'il n'existe pas."""
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None:
        return None
    user.is_banned = True
    user.banned_at = datetime.now(timezone.utc)
    user.ban_reason = (reason or "").strip()[:500] or None
    return user


async def unban_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Rétablit un compte suspendu."""
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None:
        return None
    user.is_banned = False
    user.banned_at = None
    user.ban_reason = None
    return user


async def takedown_content(
    db: AsyncSession,
    target_type: str,
    target_id: str,
    reason: str | None = None,
) -> dict:
    """
    Retire de la vue publique le contenu signalé, selon son type.
    Retourne {"ok": bool, "detail": str}. Ne commit PAS (l'appelant commit).
    """
    ttype = (target_type or "").strip().lower()
    tid = _as_uuid(target_id)
    if tid is None and ttype != "profil":
        return {"ok": False, "detail": "Identifiant de cible invalide."}

    if ttype in ("prompt", "image"):
        obj = (await db.execute(
            select(Prompt).where(Prompt.id == tid)
        )).scalar_one_or_none()
        if obj is None:
            return {"ok": False, "detail": "Contenu introuvable."}
        obj.is_published = False
        return {"ok": True, "detail": "Contenu retiré de la vitrine."}

    if ttype == "track":
        obj = (await db.execute(
            select(Track).where(Track.id == tid)
        )).scalar_one_or_none()
        if obj is None:
            return {"ok": False, "detail": "Morceau introuvable."}
        obj.is_deleted = True
        return {"ok": True, "detail": "Morceau retiré."}

    if ttype == "playlist":
        obj = (await db.execute(
            select(Playlist).where(Playlist.id == tid)
        )).scalar_one_or_none()
        if obj is None:
            return {"ok": False, "detail": "Playlist introuvable."}
        obj.visibility = "private"
        return {"ok": True, "detail": "Playlist passée en privé."}

    if ttype == "album":
        obj = (await db.execute(
            select(Album).where(Album.id == tid)
        )).scalar_one_or_none()
        if obj is None:
            return {"ok": False, "detail": "Album introuvable."}
        obj.visibility = "private"
        return {"ok": True, "detail": "Album passé en privé."}

    if ttype == "profil":
        # Signalement d'un profil → on suspend le compte visé.
        pid = tid or _as_uuid(target_id)
        if pid is None:
            return {"ok": False, "detail": "Identifiant de profil invalide."}
        user = await ban_user(db, pid, reason)
        if user is None:
            return {"ok": False, "detail": "Compte introuvable."}
        return {"ok": True, "detail": "Compte suspendu."}

    return {"ok": False, "detail": f"Type de cible non géré : {ttype}."}
