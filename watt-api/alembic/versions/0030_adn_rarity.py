"""adn : ai_reference + max_supply (rareté + provenance IA)

Revision ID: 0030_adn_rarity
Revises: 0029_voice_preview
Create Date: 2026-05-13

Validé Tom 2026-05-13.

ai_reference : enum string indiquant l'IA utilisée pour générer le contenu
de l'ADN (chatgpt / claude / grok / gemini / mistral / perplexity / autre).
Nullable car ADN legacy ne savent pas (à compléter par l'owner).

max_supply :
  - NULL  → édition illimitée (default historique)
  - 1     → exclusive (1 seul acheteur possible)
  - 2..N  → édition limitée (N acheteurs max)
Stock-out enforcé côté service unlock_adn_atomic.
"""
from alembic import op
import sqlalchemy as sa


revision = "0030_adn_rarity"
down_revision = "0029_voice_preview"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "adns",
        sa.Column("ai_reference", sa.String(length=30), nullable=True),
    )
    op.create_check_constraint(
        "ck_adns_ai_reference_enum",
        "adns",
        "ai_reference IS NULL OR ai_reference IN "
        "('chatgpt', 'claude', 'grok', 'gemini', 'mistral', 'perplexity', 'autre')",
    )

    op.add_column(
        "adns",
        sa.Column("max_supply", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_adns_max_supply_positive",
        "adns",
        "max_supply IS NULL OR max_supply >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_adns_max_supply_positive", "adns", type_="check")
    op.drop_column("adns", "max_supply")
    op.drop_constraint("ck_adns_ai_reference_enum", "adns", type_="check")
    op.drop_column("adns", "ai_reference")
