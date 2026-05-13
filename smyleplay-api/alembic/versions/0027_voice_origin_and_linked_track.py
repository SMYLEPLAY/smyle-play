"""voice : ajoute voice_origin + linked_track_id (Phase B metadata)

Revision ID: 0027_voice_origin_and_linked_track
Revises: 0026_create_dna_table
Create Date: 2026-05-13

Validé Tom 2026-05-13 (project_visibility_rule_revised).

Pour les voix vendables, l'acheteur a le droit de voir avant achat :
  - Le sample audio (pré-écoute streaming)
  - L'origine de la voix : personnelle / IA / artiste connu
  - Si la voix est associée à un morceau du vendeur (FK Track)
  - Prix + métadonnées (nom, style, genres, license)

Cette migration ajoute :
  • voice_origin : enum string (personal/ai/known_artist), nullable car
    legacy voices peuvent ne pas avoir cette info (à compléter par l'owner)
  • linked_track_id : FK Track NULL, set si la voix démontre un track
    spécifique de l'artiste
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0027_voice_origin_and_linked_track"
down_revision = "0026_create_dna_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "voices",
        sa.Column("voice_origin", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_voices_voice_origin_enum",
        "voices",
        "voice_origin IS NULL OR voice_origin IN ('personal', 'ai', 'known_artist')",
    )

    op.add_column(
        "voices",
        sa.Column(
            "linked_track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_voices_linked_track_id",
        "voices",
        ["linked_track_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_voices_linked_track_id", table_name="voices")
    op.drop_column("voices", "linked_track_id")
    op.drop_constraint("ck_voices_voice_origin_enum", "voices", type_="check")
    op.drop_column("voices", "voice_origin")
