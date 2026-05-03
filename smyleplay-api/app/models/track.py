import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        CheckConstraint(
            "universe IS NULL OR universe IN "
            "('sunset-lover', 'jungle-osmose', 'night-city', 'hit-mix')",
            name="ck_tracks_universe_enum",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    artist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # --- Champs ajoutés migration 0011 (import catalogue WATT v1) ---
    universe: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        index=True,
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    r2_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    plays: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # --- Champ ajouté migration 0012 (compat tracks.json) ---
    # ID historique issu de tracks.json (ex: 'sl-sw001amberdrivedriftwav').
    # Utilisé par le JS existant pour les URLs et compteurs de plays.
    # NULL pour les tracks uploadées après cette migration (UUID suffit).
    legacy_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        index=True,
    )

    # --- Champ ajouté migration 0020 (Étape 2 : couleur par morceau) ---
    # Couleur hex "#RRGGBB" affichée sur les cellules orphelines de /u/<slug>.
    # NULL = fallback brandColor de l'artiste (puis or WATT en dernier ressort).
    # Pas de CHECK en DB pour rester ouvert à des palettes étendues plus tard ;
    # le format est validé côté Pydantic (regex) à la création/édition.
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # --- Champs ajoutés migration 0025 (Sprint 1 pivot écoute, 2026-05-04) ---
    # cover_url : URL R2 de la pochette du morceau. NULL = fallback couleur.
    cover_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # prompt_id : lien track → prompt vendable. NULL = track sans prompt.
    # ON DELETE SET NULL pour préserver l'audio si le prompt est supprimé.
    prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
