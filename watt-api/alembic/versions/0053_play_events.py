"""0053 — table play_events (vraies stats d'écoute)

Revision ID: 0053_play_events
Revises: 0052_beat_product
Create Date: 2026-06-10

Chantier « vraies stats » (Tier 1 audit gaps) : le graphique Analytique du
dashboard affichait une courbe simulée. Chaque play (POST /watt/plays)
insère désormais un événement horodaté → courbe 7j/30j réelle, agrégée par
jour côté SQL. Track.plays reste le compteur TOTAL (rétrocompatible) ; les
données antérieures à cette migration n'ont pas d'événements (la courbe
démarre à la date du déploiement — assumé et affiché côté front).

Anonyme par design : pas de user_id ni d'IP (RGPD).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0053_play_events"
down_revision = "0052_beat_product"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "play_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "track_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_play_events_track_id", "play_events", ["track_id"])
    op.create_index(
        "ix_play_events_track_created",
        "play_events",
        ["track_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_play_events_track_created", table_name="play_events")
    op.drop_index("ix_play_events_track_id", table_name="play_events")
    op.drop_table("play_events")
