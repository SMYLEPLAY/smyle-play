"""0043 — streak de connexion (mécanique 2)

Revision ID: 0043_streak
Revises: 0042_referrals
Create Date: 2026-06-07

Ajoute à users :
  - last_checkin_date (Date, nullable) : dernier jour réclamé.
  - streak_count (Integer, default 0)  : jours consécutifs en cours.

Barème : +1 Smyle/jour, +3 au lieu de +1 tous les 7 jours consécutifs
(≈9 Smyles/semaine pleine). Voir [[2026-06-07]].
"""
import sqlalchemy as sa
from alembic import op

revision = "0043_streak"
down_revision = "0042_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_checkin_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "streak_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "streak_count")
    op.drop_column("users", "last_checkin_date")
