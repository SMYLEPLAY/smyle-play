"""analytics_events — télémétrie produit privacy-first (D0)

Revision ID: 0075_analytics_events
Revises: 0074_platform_reserve
Create Date: 2026-06-29

Phase D0 du plan « Finir les détails ». Table `analytics_events` : journal
d'événements produit pour mesurer le funnel (visiteur → inscrit → 1er achat →
revient) SANS donnée personnelle.

Privacy-first : pas d'IP, pas de user-agent, pas de PII. `session_id` est un
jeton anonyme généré côté client ; `user_id` (nullable) n'est posé que si
l'utilisateur est connecté.

Rollback : drop de la table.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0075_analytics_events"
down_revision = "0074_platform_reserve"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("path", sa.String(256), nullable=True),
        sa.Column("referrer", sa.String(256), nullable=True),
        sa.Column("props", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_analytics_events_session_id", "analytics_events", ["session_id"])
    op.create_index("ix_analytics_events_user_id", "analytics_events", ["user_id"])
    op.create_index("ix_analytics_events_name", "analytics_events", ["name"])
    op.create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_analytics_events_created_at", table_name="analytics_events")
    op.drop_index("ix_analytics_events_name", table_name="analytics_events")
    op.drop_index("ix_analytics_events_user_id", table_name="analytics_events")
    op.drop_index("ix_analytics_events_session_id", table_name="analytics_events")
    op.drop_table("analytics_events")
