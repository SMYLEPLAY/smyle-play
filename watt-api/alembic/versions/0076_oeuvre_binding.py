"""oeuvre_binding — binding playlist↔album d'une même Œuvre (chantier C3)

Revision ID: 0076_oeuvre_binding
Revises: 0075_analytics_events
Create Date: 2026-06-30

Chantier C3 du plan « Binarité musique / visuel ». L'œuvre 1:1 (son↔image,
linked_prompt_id) existe déjà ; il manquait de relier la PLAYLIST entière à
l'ALBUM entier d'une même œuvre. On ajoute une clé logique douce partagée :

  • playlists.oeuvre_slug (nullable, indexé)
  • albums.oeuvre_slug    (nullable, indexé)
  • albums.universe        (nullable, indexé) — miroir de tracks.universe pour
    teinter la face VISUELLE des 4 œuvres officielles WATT, avec le MÊME CHECK
    enum que ck_tracks_universe_enum.

Une Œuvre = (playlist + album) MÊME oeuvre_slug ET MÊME owner_id.

Migration ADDITIVE et NON destructive : toutes les colonnes sont nullable, sans
valeur par défaut imposée → aucune ligne existante n'est touchée, aucun
backfill requis. Pas de FK sur oeuvre_slug (clé logique douce : le slug peut
exister d'un côté avant que l'autre face soit créée).

Rollback : drop des index, du CHECK et des colonnes.
"""
import sqlalchemy as sa
from alembic import op


revision = "0076_oeuvre_binding"
down_revision = "0075_analytics_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── playlists.oeuvre_slug ────────────────────────────────────────────
    op.add_column(
        "playlists",
        sa.Column("oeuvre_slug", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "ix_playlists_oeuvre_slug", "playlists", ["oeuvre_slug"]
    )

    # ── albums.oeuvre_slug + albums.universe ─────────────────────────────
    op.add_column(
        "albums",
        sa.Column("oeuvre_slug", sa.String(length=80), nullable=True),
    )
    op.create_index("ix_albums_oeuvre_slug", "albums", ["oeuvre_slug"])

    op.add_column(
        "albums",
        sa.Column("universe", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_albums_universe", "albums", ["universe"])
    # Miroir STRICT de ck_tracks_universe_enum (migration 0011).
    op.create_check_constraint(
        "ck_albums_universe_enum",
        "albums",
        "universe IS NULL OR universe IN "
        "('sunset-lover', 'jungle-osmose', 'night-city', 'hit-mix')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_albums_universe_enum", "albums", type_="check")
    op.drop_index("ix_albums_universe", table_name="albums")
    op.drop_column("albums", "universe")

    op.drop_index("ix_albums_oeuvre_slug", table_name="albums")
    op.drop_column("albums", "oeuvre_slug")

    op.drop_index("ix_playlists_oeuvre_slug", table_name="playlists")
    op.drop_column("playlists", "oeuvre_slug")
