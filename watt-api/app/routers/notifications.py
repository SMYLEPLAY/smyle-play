"""
Endpoints notifications.

Routes (toutes auth requise) :
  GET  /me/notifications              → liste paginée (50 max, tri recent first)
  GET  /me/notifications/unread-count → juste le compteur (pour la cloche)
  POST /me/notifications/read-all     → marque tout comme lu
  PATCH /me/notifications/{id}/read   → marque une notif comme lue
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationRead, NotificationsResponse

router = APIRouter(prefix="/me/notifications", tags=["notifications"])


async def _enrich(notif: Notification, db: AsyncSession) -> NotificationRead:
    """Enrichit une notif avec le nom + avatar de l'actor."""
    actor_name = None
    actor_avatar = None
    if notif.actor_id:
        actor = (await db.execute(
            select(User.artist_name, User.avatar_url)
            .where(User.id == notif.actor_id)
        )).first()
        if actor:
            actor_name = actor.artist_name
            actor_avatar = actor.avatar_url

    return NotificationRead(
        id=notif.id,
        type=notif.type,
        actor_id=notif.actor_id,
        actor_name=actor_name,
        actor_avatar=actor_avatar,
        target_type=notif.target_type,
        target_id=notif.target_id,
        metadata_json=notif.metadata_json,
        read_at=notif.read_at,
        created_at=notif.created_at,
    )


@router.get("", response_model=NotificationsResponse)
async def get_my_notifications(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationsResponse:
    """Retourne les notifs du user, les plus récentes en premier."""
    limit = min(limit, 100)

    rows = (await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )).scalars().all()

    unread_count = (await db.execute(
        select(func.count())
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
    )).scalar_one()

    items = [await _enrich(n, db) for n in rows]
    return NotificationsResponse(items=items, unread_count=unread_count)


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Endpoint léger pour le badge de la cloche (polling toutes les 30s)."""
    count = (await db.execute(
        select(func.count())
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
    )).scalar_one()
    return {"unread_count": count}


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Marque toutes les notifs non lues comme lues."""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    await db.commit()


@router.patch("/{notif_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_one_read(
    notif_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Marque une notif spécifique comme lue."""
    notif = (await db.execute(
        select(Notification).where(
            Notification.id == notif_id,
            Notification.user_id == current_user.id,
        )
    )).scalar_one_or_none()

    if not notif:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notification introuvable")

    if notif.read_at is None:
        notif.read_at = datetime.now(timezone.utc)
        await db.commit()
