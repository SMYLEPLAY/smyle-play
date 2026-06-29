"""0056 — #X/N sur les voix (max_supply + edition_number)

Revision ID: 0056_voice_supply
Revises: 0055_track_is_beat_bpm
Create Date: 2026-06-12

Chantier Voix (marathon) : la rareté #X/N remplace le vocabulaire
« licence » comme mécanique de valeur, alignée sur les prompts
(migration 0051). max_supply NULL = tirage illimité, non numéroté.
1 = vente unique (retrait à l'achat). La colonne voices_for_sale.license
RESTE en base (historique figé dans transactions.metadata_json) mais
n'est plus exposée dans les UI.
"""
from alembic import op
import sqlalchemy as sa


revision = "0056_voice_supply"
down_revision = "0055_track_is_beat_bpm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "voices_for_sale",
        sa.Column("max_supply", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_voices_max_supply_pos",
        "voices_for_sale",
        "max_supply IS NULL OR max_supply >= 1",
    )
    op.add_column(
        "owned_voices",
        sa.Column("edition_number", sa.Integer(), nullable=True),
    )
    # Filet anti-doublon de numéro (le lock artiste sérialise déjà les achats).
    op.create_unique_constraint(
        "uq_owned_voices_edition",
        "owned_voices",
        ["voice_id", "edition_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_owned_voices_edition", "owned_voices", type_="unique")
    op.drop_column("owned_voices", "edition_number")
    op.drop_constraint("ck_voices_max_supply_pos", "voices_for_sale", type_="check")
    op.drop_column("voices_for_sale", "max_supply")
