"""0054 — table password_reset_tokens (reset mot de passe)

Revision ID: 0054_password_reset
Revises: 0053_play_events
Create Date: 2026-06-10

Mission reset MDP (Tier 1 audit gaps). Jetons à usage unique, expiration
60 min, stockés HACHÉS (SHA-256) — une fuite de table ne permet aucune
réinitialisation. Flux : POST /auth/forgot-password (toujours 200,
anti-énumération) → email Resend avec lien /reset?token=… →
POST /auth/reset-password.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0054_password_reset"
down_revision = "0053_play_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_prt_token_hash", "password_reset_tokens", ["token_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_prt_token_hash", table_name="password_reset_tokens")
    op.drop_index(
        "ix_password_reset_tokens_user_id",
        table_name="password_reset_tokens",
    )
    op.drop_table("password_reset_tokens")
