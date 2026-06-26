"""
Journal de téléchargements (H0.5+) — trace requêtable des téléchargements gatés.
Qui (user) a téléchargé quoi (product_id) et quand. Sert à l'anti-abus
(repérer un compte qui aspire le catalogue) et à l'audit. Best-effort : la
journalisation ne bloque jamais un téléchargement légitime.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class DownloadEvent(Base):
    __tablename__ = "download_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # 'audio' | 'image'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
