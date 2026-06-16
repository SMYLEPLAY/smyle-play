"""
Album & AlbumImage — équivalent VISUEL des playlists (chantier C4 My Mix).

Deux entités, calquées STRICTEMENT sur le modèle Playlist / PlaylistTrack :

  • Album      — curation perso d'images (product_type='image' de la table
                 `prompts`) appartenant à un utilisateur. NON vendable : pure
                 collection type Pinterest. Une seule table discriminée par
                 `visibility` ("public" | "private") — permet de lister "tous
                 mes albums" du dashboard sans UNION et de basculer la
                 visibilité sans DDL. Les albums privés servent de moodboards
                 perso ; les publics sont exposés sur /u/<slug>.
                 `cover_prompt_id` (optionnel) pointe vers une image de
                 couverture — FK prompts.id ON DELETE SET NULL : si l'image de
                 couverture est supprimée, l'album n'a plus de couverture mais
                 survit (pas de pointeur fantôme).

  • AlbumImage — table de jonction N-N album↔image avec `position` pour
                 préserver l'ordre au rendu. PK composite sur
                 (album_id, prompt_id) — empêche structurellement les doublons
                 (ajouter deux fois la même image au même album) sans
                 UniqueConstraint séparé. ON DELETE CASCADE des deux côtés :
                 supprimer l'album OU l'image retire la ligne de jonction.

Anti-fuite : aucune logique de prix/achat/rareté ici (album = curation pure).
Les images d'un album ne sont exposées qu'en aperçu PUBLIC côté router (jamais
prompt_text / image_r2_key / image_settings / negative_prompt).
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
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public', 'private')",
            name="ck_albums_visibility_enum",
        ),
        Index("ix_albums_owner_visibility", "owner_id", "visibility"),
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

    # "public" | "private" — discriminateur. Migration 0060 pose aussi un
    # CHECK constraint SQL ; le même CHECK est répété ici pour que les
    # create_all() (tests legacy) appliquent la règle.
    visibility: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="private",
    )

    # Image de couverture optionnelle (une ligne prompts product_type='image').
    # ON DELETE SET NULL : la suppression de l'image de couverture remet le
    # pointeur à NULL plutôt que d'empêcher la suppression de l'image.
    cover_prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AlbumImage(Base):
    __tablename__ = "album_images"
    __table_args__ = (
        PrimaryKeyConstraint(
            "album_id", "prompt_id", name="pk_album_images"
        ),
        Index("ix_album_images_position", "album_id", "position"),
    )

    album_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("albums.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="CASCADE"),
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
