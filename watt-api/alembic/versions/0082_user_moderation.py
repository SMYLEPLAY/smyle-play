"""user_moderation — bannissement de compte (DSA : capacité d'action)

Revision ID: 0082_user_moderation
Revises: 0081_content_reports
Create Date: 2026-07-24

Phase 3 lancement — modération actionnable. Le signalement DSA (0081)
permettait de RECEVOIR un signalement mais pas d'AGIR. On ajoute le
bannissement de compte : `is_banned` (bloque login + tout accès authentifié),
`banned_at` et `ban_reason` (traçabilité de la décision, exigée par le DSA).
Colonnes simples (bool/timestamp/text) — aucun type enum, aucun piège de
CREATE TYPE. server_default false → les comptes existants restent actifs.
"""
import sqlalchemy as sa
from alembic import op

revision = "0082_user_moderation"
down_revision = "0081_content_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_banned",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_index("ix_users_is_banned", "users", ["is_banned"])
    op.add_column(
        "users",
        sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("ban_reason", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "ban_reason")
    op.drop_column("users", "banned_at")
    op.drop_index("ix_users_is_banned", table_name="users")
    op.drop_column("users", "is_banned")
