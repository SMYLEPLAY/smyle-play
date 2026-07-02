"""0055 — tracks.is_beat + tracks.bpm (C2 : le beat devient un drapeau)

Revision ID: 0055_track_is_beat_bpm
Revises: 0054_password_reset
Create Date: 2026-06-12

Marathon C2 (décision gelée 2026-06-11) : UN produit audio — la recette
est LE produit. « Beat » n'est plus une ligne prompts distincte mais un
DRAPEAU de placement sur le track (étagère /beats) + BPM optionnel.

Backfill : les tracks déjà liés à un beat legacy (beat_id non NULL)
sont flagués is_beat=TRUE pour apparaître sur /beats sans re-saisie.
"""
from alembic import op
import sqlalchemy as sa


revision = "0055_track_is_beat_bpm"
down_revision = "0054_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracks",
        sa.Column(
            "is_beat", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column("tracks", sa.Column("bpm", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_tracks_bpm_range",
        "tracks",
        "bpm IS NULL OR (bpm BETWEEN 40 AND 300)",
    )
    # Backfill legacy : tout track lié à un produit beat = placement /beats.
    op.execute("UPDATE tracks SET is_beat = TRUE WHERE beat_id IS NOT NULL")


def downgrade() -> None:
    op.drop_constraint("ck_tracks_bpm_range", "tracks", type_="check")
    op.drop_column("tracks", "bpm")
    op.drop_column("tracks", "is_beat")
