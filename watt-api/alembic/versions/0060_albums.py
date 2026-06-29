"""albums + album_images — équivalent visuel des playlists (C4 My Mix)

Revision ID: 0060_albums
Revises: 0059_linked_prompt
Create Date: 2026-06-16

Album d'images = curation perso d'images (product_type='image'), strictement
calqué sur la machinerie Playlist / PlaylistTrack (migration 0021). NON
vendable : aucune colonne prix/rareté/ADN. Pure collection type Pinterest.

  Design choices (miroir de 0021) :
    • une seule table `albums` avec `visibility` texte (public|private) plutôt
      que deux tables : permet de lister "tous mes albums" du dashboard d'une
      requête, et de faire évoluer la visibilité sans DDL.
    • junction table `album_images` explicite pour supporter l'ordre via
      `position` INT et permettre d'ajouter des méta par ligne plus tard.
    • `cover_prompt_id` (UUID NULLABLE) : image de couverture optionnelle.
      FK prompts.id ON DELETE SET NULL — si l'image de couverture est
      supprimée physiquement, l'album survit sans couverture (pas de pointeur
      fantôme).

  Indices :
    • `(owner_id, visibility)` couvre "liste mes albums" (dashboard) et
      "liste mes albums publics" (profil).
    • PK composite `(album_id, prompt_id)` dans `album_images` empêche les
      doublons (ajouter deux fois la même image au même album).
    • `(album_id, position)` pour ordonner au rendu.

  Rollback :
    • `downgrade()` drop les deux tables dans le bon ordre (junction → parent).

Pas de data migration : nouvelles tables vides.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0060_albums"
down_revision = "0059_linked_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Table principale ──────────────────────────────────────────────────
    op.create_table(
        "albums",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "visibility",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'private'"),
        ),
        sa.Column(
            "cover_prompt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "visibility IN ('public', 'private')",
            name="ck_albums_visibility_enum",
        ),
    )
    op.create_index(
        "ix_albums_owner_visibility",
        "albums",
        ["owner_id", "visibility"],
    )

    # ── Junction album ↔ image (prompt product_type='image') ───────────────
    op.create_table(
        "album_images",
        sa.Column(
            "album_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "prompt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "album_id", "prompt_id", name="pk_album_images"
        ),
    )
    op.create_index(
        "ix_album_images_position",
        "album_images",
        ["album_id", "position"],
    )


def downgrade() -> None:
    op.drop_index("ix_album_images_position", table_name="album_images")
    op.drop_table("album_images")
    op.drop_index("ix_albums_owner_visibility", table_name="albums")
    op.drop_table("albums")
