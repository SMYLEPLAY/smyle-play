"""
Événement d'écoute (chantier « vraies stats », 2026-06-10).

Avant : Track.plays = un compteur total — le graphique Analytique du
dashboard affichait une courbe SIMULÉE (getPlaysHistory côté front).
Maintenant : chaque play insère AUSSI une ligne play_events horodatée →
la courbe 7j/30j devient réelle (agrégation par jour côté SQL).

Volontairement minimal : pas de user_id (un play est anonyme par design,
cf. POST /watt/plays), pas d'IP (RGPD : aucune donnée personnelle).
Le compteur Track.plays reste la source du TOTAL (rétrocompatible).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlayEvent(Base):
    __tablename__ = "play_events"
    __table_args__ = (
        # L'agrégation type "courbe 30j d'un artiste" filtre par track + date.
        Index("ix_play_events_track_created", "track_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
