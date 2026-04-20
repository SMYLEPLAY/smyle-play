"""
UserFollow — lien d'abonnement entre deux utilisateurs artistes.

Modèle many-to-many minimaliste : chaque ligne représente une arête
"follower_id → followee_id" horodatée. La combinaison (follower_id,
followee_id) est unique (pas de doublons), et on rejette l'auto-follow
via CHECK constraint SQL.

Ce lien sert à :
  - construire le Réseau Créatif WATT côté dashboard (mes abonnements +
    mes abonnés forment les nœuds satellites de mon graphe),
  - afficher le bouton Follow/Unfollow sur la page /artiste/<slug>,
  - filtrer le fil d'actualités futur (posts des artistes suivis).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserFollow(Base):
    __tablename__ = "user_follows"
    __table_args__ = (
        UniqueConstraint(
            "follower_id", "followee_id", name="uq_user_follow_pair"
        ),
        CheckConstraint(
            "follower_id <> followee_id", name="ck_user_follow_no_self"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    follower_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    followee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
