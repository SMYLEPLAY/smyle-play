"""
Jeton de réinitialisation de mot de passe (mission reset MDP, 2026-06-10).

Sécurité :
  - On ne stocke JAMAIS le jeton en clair — uniquement son SHA-256.
    Une fuite de la table ne permet pas de réinitialiser des comptes.
  - Usage unique (used_at) + expiration courte (60 min).
  - Pas de lien navigable depuis le jeton vers l'email en clair dans les
    réponses API (anti-énumération : /auth/forgot-password répond toujours
    200, que l'email existe ou non).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("ix_prt_token_hash", "token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 hex du jeton (64 chars) — jamais le jeton lui-même.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
