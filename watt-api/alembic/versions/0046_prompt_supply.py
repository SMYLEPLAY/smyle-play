"""0046 — rareté/supply sur les prompts (édition limitée, comme les ADN)

Revision ID: 0046_prompt_supply
Revises: 0045_hide_duplicate_smyle
Create Date: 2026-06-08

Ajoute prompts.max_supply (nullable) : NULL = illimité, 1 = pièce unique,
N = édition limitée. Le tier de rareté est dérivé via compute_rarity_tier().
Prix libre inchangé (price_credits, min 3). Stock-out enforcé à l'achat.
"""
import sqlalchemy as sa
from alembic import op

revision = "0046_prompt_supply"
down_revision = "0045_hide_duplicate_smyle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("max_supply", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prompts", "max_supply")
