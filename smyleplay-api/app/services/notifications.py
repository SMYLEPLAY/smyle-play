"""
Service notifications — helper fire-and-forget.

Utilisé par tous les routers qui doivent créer des notifs :
  unlocks.py  → purchase (au seller)
  follows.py  → follow (au followed)
  messages.py → message (au receiver)
  trades.py   → trade (au receiver / résolution)

Design :
  - Toujours fire-and-forget (swallow exceptions) : une erreur de notif
    ne doit jamais casser l'opération métier principale.
  - create_notification() est la seule fonction publique.
  - Le caller passe la session DB déjà ouverte — pas de nouvelle session.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    *,
    user_id: UUID,
    type: NotificationType,
    actor_id: UUID | None = None,
    target_type: str | None = None,
    target_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Crée une notification. Swallow toutes les exceptions.

    Params :
      user_id     : destinataire
      type        : NotificationType (purchase, like, follow, message, trade, system)
      actor_id    : qui a déclenché l'action (None pour system)
      target_type : 'track' | 'prompt' | 'adn' | 'voice' | 'trade' | 'thread'
      target_id   : UUID de l'entité (pour navigation front)
      metadata    : dict lisible par le front (ex: {"track_title": "...", "amount": 50})
    """
    try:
        notif = Notification(
            user_id=user_id,
            type=type,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            metadata_json=metadata,
        )
        db.add(notif)
        await db.flush()   # flush dans la transaction courante du caller
    except Exception as exc:  # noqa: BLE001
        logger.warning("[notifications] create failed user=%s type=%s err=%s",
                       user_id, type, exc)
