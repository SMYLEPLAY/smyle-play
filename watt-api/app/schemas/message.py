from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# S-03 (2026-09-02) — hygiène : un message ne contient pas de caractère de
# contrôle hors saut de ligne / tabulation (NUL, ESC, retour chariot isolé,
# séquences ANSI…). Le retour chariot `\r` est toléré uniquement dans `\r\n`
# (collé par certains navigateurs) et normalisé en `\n`.
_ALLOWED_CONTROL = {"\n", "\t"}


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def reject_control_chars(cls, v: str) -> str:
        v = v.replace("\r\n", "\n")
        for ch in v:
            code = ord(ch)
            if (code < 32 or code == 127) and ch not in _ALLOWED_CONTROL:
                raise ValueError("Le message contient des caractères de contrôle interdits")
        if v.strip() == "":
            raise ValueError("Le message ne peut pas être vide")
        return v


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
