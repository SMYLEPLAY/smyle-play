"""add legacy_id column to tracks for tracks.json ID compatibility

Revision ID: 0012_add_track_legacy_id
Revises: 0011_extend_tracks
Create Date: 2026-04-18

Étape 4 de la migration Flask → FastAPI.

Les IDs historiques du catalogue WATT (ex: 'sl-sw001amberdrivedriftwav')
sont référencés par le JS existant pour :
  - les compteurs de plays en localStorage (smyle_plays_<id>)
  - les panneaux playlist (data-id attribute sur les cartes)
  - les URL publiques (/artiste/<slug>?track=<id>)

Remplacer ces IDs par des UUID casserait le site en production (links
existants, compteurs de plays localStorage, etc.). On ajoute donc une
colonne `legacy_id` unique qui conserve l'ID d'origine de tracks.json,
en parallèle de l'UUID Postgres.

Pour les tracks uploadées via le dashboard (futures), legacy_id reste
NULL et on utilise l'UUID comme identifiant public.
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0012_add_track_legacy_id"
down_revision = "0011_extend_tracks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracks",
        sa.Column("legacy_id", sa.String(length=100), nullable=True),
    )
    op.create_unique_constraint(
        "uq_tracks_legacy_id",
        "tracks",
        ["legacy_id"],
    )
    op.create_index(
        "ix_tracks_legacy_id",
        "tracks",
        ["legacy_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tracks_legacy_id", table_name="tracks")
    op.drop_constraint("uq_tracks_legacy_id", "tracks", type_="unique")
    op.drop_column("tracks", "legacy_id")
