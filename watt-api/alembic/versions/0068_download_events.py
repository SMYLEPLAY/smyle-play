"""download_events — journal des téléchargements gatés (H0.5+)

Revision ID: 0068_download_events
Revises: 0067_user_signup_ip
Create Date: 2026-06-26

Trace requêtable : qui a téléchargé quel produit, quand. Anti-abus + audit.
Table additive, aucune donnée existante touchée.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0068_download_events"
down_revision = "0067_user_signup_ip"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_download_events_user_id", "download_events", ["user_id"])
    op.create_index("ix_download_events_product_id", "download_events", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_download_events_product_id", table_name="download_events")
    op.drop_index("ix_download_events_user_id", table_name="download_events")
    op.drop_table("download_events")
