from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: UUID
    sender_id: UUID
    content: str
    read_at: datetime | None = None
    created_at: datetime


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    other_user_id: UUID          # enrichi : l'interlocuteur (pas soi)
    other_user_name: str | None  # enrichi
    other_user_avatar: str | None
    last_message_at: datetime | None = None
    last_message_preview: str | None = None  # enrichi : 60 premiers chars
    unread_count: int = 0        # nb de messages non lus pour le current user
    created_at: datetime


class ThreadMessagesResponse(BaseModel):
    thread_id: UUID
    other_user_id: UUID
    other_user_name: str | None
    messages: list[MessageRead]
