"""adns + voices_for_sale : ajout colonne is_deleted (soft-delete)

Revision ID: 0033_soft_delete_adns_voices
Revises: 0032_merge_heads
Create Date: 2026-05-14

Permet la suppression logique des ADN et des voix côté artiste vendeur,
sans casser les références OwnedAdn / OwnedVoice des acheteurs.

Règle métier :
  - is_deleted=True → disparaît du marketplace et du dashboard artiste
  - Les acheteurs (OwnedAdn, OwnedVoice) conservent leur accès en library
  - Cohérent avec le pattern prompts/tracks (migration 0028)
"""
from alembic import op
import sqlalchemy as sa


revision = "0034_soft_delete_adns_voices"
down_revision = "0033_final_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "adns",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "voices_for_sale",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("adns", "is_deleted")
    op.drop_column("voices_for_sale", "is_deleted")
