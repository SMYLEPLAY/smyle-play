"""user_terms — acceptation CGU + âge à l'inscription (preuve horodatée)

Revision ID: 0083_user_terms
Revises: 0082_user_moderation
Create Date: 2026-07-24

Phase 3 lancement — inscription encadrée. On trace l'instant où l'utilisateur
a accepté les CGU et confirmé avoir l'âge minimum (15 ans). `accepted_terms_at`
NULL = comptes créés avant cette exigence (legacy). Colonne simple, nullable,
aucun impact sur l'existant.
"""
import sqlalchemy as sa
from alembic import op

revision = "0083_user_terms"
down_revision = "0082_user_moderation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("accepted_terms_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "accepted_terms_at")
