"""voice : ajoute voice_origin + linked_track_id (Phase B metadata)

Revision ID: 0027_voice_origin_and_linked_track
Revises: 0026_create_dna_table
Create Date: 2026-05-13

Fix 2026-05-13 (hotfix #2) : la table cible s'appelle `voices_for_sale`,
pas `voices`. Migration 0023 a explicitement choisi le nom long pour
distinguer "voix en vente" de "voix générique". Le model SQLAlchemy
référence bien `voices_for_sale` (app/models/voice.py:63) — c'est la
migration qui s'était trompée. Railway pre-deploy plantait avec
"relation 'voices' does not exist".

Pour les voix vendables, l'acheteur a le droit de voir avant achat :
  - Le sample audio (pré-écoute streaming)
  - L'origine de la voix : personnelle / IA / artiste connu
  - Si la voix est associée à un morceau du vendeur (FK Track)
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
        "voices_for_sale",
        sa.Column("voice_origin", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_voices_voice_origin_enum",
        "voices_for_sale",
        "voice_origin IS NULL OR voice_origin IN "
        "('personal', 'ai', 'known_artist')",
    )

    op.add_column(
        "voices_for_sale",
        sa.Column(
            "linked_track_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_voices_linked_track_id_tracks",
        "voices_for_sale",
        "tracks",
        ["linked_track_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_voices_linked_track_id",
        "voices_for_sale",
        ["linked_track_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_voices_linked_track_id", table_name="voices_for_sale")
    op.drop_constraint(
        "fk_voices_linked_track_id_tracks",
        "voices_for_sale",
        type_="foreignkey",
    )
    op.drop_column("voices_for_sale", "linked_track_id")
    op.drop_constraint(
        "ck_voices_voice_origin_enum", "voices_for_sale", type_="check"
    )
    op.drop_column("voices_for_sale", "voice_origin")
