from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationType


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: NotificationType
    actor_id: UUID | None = None
    actor_name: str | None = None   # enrichi par le router (JOIN users)
    actor_avatar: str | None = None  # enrichi par le router
    target_type: str | None = None
    target_id: UUID | None = None
    metadata_json: dict[str, Any] | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationsResponse(BaseModel):
    items: list[NotificationRead]
    unread_count: int
