"""modèle Playlist unifié : table + junction + seed wishlist

Revision ID: 0021_add_playlists
Revises: 0020_add_track_color
Create Date: 2026-04-20

Contexte produit — Étape 3 du chantier architecture profil public :

  Un artiste (ou un membre) peut regrouper des tracks dans des "playlists".
  Chaque playlist est :
    - soit publique (visible sur /u/<slug>, contient UNIQUEMENT les tracks
      de l'owner — pas de repartage des sons des autres en public),
    - soit privée (wishlist, favoris, collections de consommation — peut
      contenir des tracks d'autres artistes).

  Design choices :
    • une seule table `playlists` avec `visibility` texte (public|private)
      plutôt que deux tables séparées : permet de lister "toutes mes
      playlists" côté dashboard d'une requête, et de faire évoluer la
      visibilité sans DDL.
    • junction table `playlist_tracks` explicite pour (a) supporter l'ordre
      via `position` INT, (b) permettre d'ajouter rapidement des méta par
      ligne plus tard (unlocked_at, added_by, etc.) sans re-migrer.
    • `cover_video_url` et `seed_prompt` sont prévus ici pour que la future
      UI d'étape 5 ne demande pas de nouvelle migration.
    • `dna_description` TEXT nullable : v1 reste PAS monétisée (feature flag
      côté API — le champ existe mais l'endpoint d'achat n'est pas exposé).
      On garde la colonne pour que V2 (ADN de playlist) n'ait qu'à activer
      le flag, sans re-migrer.
    • `color` VARCHAR(7) nullable : idem convention que tracks.color — null
      signifie "hérite de la brandColor de l'owner" côté front.

  Indices :
    • `(owner_id, visibility)` couvre "liste mes playlists publiques" et
      "liste toutes mes playlists" (dashboard).
    • PK composite `(playlist_id, track_id)` dans `playlist_tracks` empêche
      les doublons (ajouter deux fois le même son à la même playlist).
    • `(playlist_id, position)` pour ordonner au rendu.

  Rollback :
    • `downgrade()` drop les deux tables dans le bon ordre (junction → parent).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0021_add_playlists"
down_revision = "0020_add_track_color"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Table principale ──────────────────────────────────────────────────
    op.create_table(
        "playlists",
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
        sa.Column("cover_video_url", sa.String(length=2048), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("seed_prompt", sa.Text(), nullable=True),
        # Forward-compat V2 — pas exposé à l'API en V1 (feature flag).
        sa.Column("dna_description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "visibility IN ('public', 'private')",
            name="ck_playlists_visibility_enum",
        ),
    )
    op.create_index(
        "ix_playlists_owner_visibility",
        "playlists",
        ["owner_id", "visibility"],
    )

    # ── Junction playlist ↔ track ─────────────────────────────────────────
    op.create_table(
        "playlist_tracks",
        sa.Column(
            "playlist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("playlists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
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
            "playlist_id", "track_id", name="pk_playlist_tracks"
        ),
    )
    op.create_index(
        "ix_playlist_tracks_position",
        "playlist_tracks",
        ["playlist_id", "position"],
    )


def downgrade() -> None:
    op.drop_index("ix_playlist_tracks_position", table_name="playlist_tracks")
    op.drop_table("playlist_tracks")
    op.drop_index("ix_playlists_owner_visibility", table_name="playlists")
    op.drop_table("playlists")
