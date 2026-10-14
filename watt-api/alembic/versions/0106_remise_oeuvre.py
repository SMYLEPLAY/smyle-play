"""remise_oeuvre — remise de l'offre groupée choisie par le créateur

Revision ID: 0106_remise_oeuvre
Revises: 0105_apercus_audio
Create Date: 2026-10-14

L'offre « Acheter l'Œuvre » (son + image en un seul achat) avait une remise
fixe de 10 %. Le créateur la choisit désormais : 0, 10 ou 20 %. Elle est
portée par l'image de l'Œuvre (`prompts.remise_oeuvre_pct`).

Défaut 10 : les Œuvres existantes ne changent pas de prix.
Rollback : suppression de la colonne (retour à 10 % pour tous).
"""
import sqlalchemy as sa
from alembic import op

revision = "0106_remise_oeuvre"
down_revision = "0105_apercus_audio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column(
        "remise_oeuvre_pct", sa.SmallInteger(), nullable=False, server_default="10"))
    op.create_check_constraint(
        "ck_prompts_remise_oeuvre_pct", "prompts", "remise_oeuvre_pct IN (0, 10, 20)")


def downgrade() -> None:
    op.drop_constraint("ck_prompts_remise_oeuvre_pct", "prompts", type_="check")
    op.drop_column("prompts", "remise_oeuvre_pct")
