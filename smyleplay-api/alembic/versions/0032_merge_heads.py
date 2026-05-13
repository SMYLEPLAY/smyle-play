"""merge: réunir les deux têtes Alembic (chaîne numérotée + chaîne hash legacy)

Revision ID: 0032_merge_heads
Revises: 0031_adn_price_unlock, b2fe0db4906d
Create Date: 2026-05-13

Migration de merge pure — aucune modification de schéma.
Résout l'erreur 'Multiple head revisions' sur Railway.
"""
from alembic import op


revision = "0032_merge_heads"
down_revision = ("0031_adn_price_unlock", "b2fe0db4906d")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
