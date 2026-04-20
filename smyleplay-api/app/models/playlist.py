"""
Playlist & PlaylistTrack — modèle unifié étape 3 (chantier profil public).

Deux entités :

  • Playlist     — regroupement de tracks appartenant à un utilisateur. Une
                   seule table, discriminée par `visibility` ("public" ou
                   "private"), permet de lister "toutes mes playlists" du
                   dashboard sans UNION. Les playlists publiques ne doivent
                   contenir QUE des tracks de l'owner (contrainte appliquée
                   côté service, pas en DB, pour garder la latitude de
                   corriger par data-migration si besoin). Les privées
                   servent de wishlist / favoris et peuvent agréger les sons
                   d'autres artistes.

  • PlaylistTrack — table de jonction N-N playlist↔track avec `position`
                    pour préserver l'ordre au rendu. PK composite sur
                    (playlist_id, track_id) — empêche structurellement les
                    doublons sans qu'on ait à gérer un `UniqueConstraint`
                    séparé.

Champs forward-compat (présents mais non exposés à l'API V1) :
  - `cover_video_url` : vignette animée prévue pour /u/<slug> (étape 5).
  - `seed_prompt`     : prompt SUNO d'origine pour reproduire la génération.
  - `dna_description` : description ADN de la playlist pour la V2 monétisée
                        (feature flag côté routeur — la colonne est créée
                        mais aucun endpoint n'y touche en V1).
  - `color`           : même convention que tracks.color — NULL signifie
                        "hérite de la brandColor de l'owner" au rendu front.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Playlist(Base):
    __tablename__ = "playlists"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public', 'private')",
            name="ck_playlists_visibility_enum",
        ),
        Index("ix_playlists_owner_visibility", "owner_id", "visibility"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # "public" | "private" — discriminateur. Migration 0021 pose aussi un
    # CHECK constraint SQL ; le même CHECK est répété ici pour que les
    # create_all() (tests legacy) appliquent la règle.
    visibility: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="private",
    )

    cover_video_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    seed_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Forward-compat V2 — non exposé à l'API V1 (feature flag côté routeur).
    dna_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (
        PrimaryKeyConstraint(
            "playlist_id", "track_id", name="pk_playlist_tracks"
        ),
        Index("ix_playlist_tracks_position", "playlist_id", "position"),
    )

    playlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playlists.id", ondelete="CASCADE"),
        nullable=False,
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracks.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
