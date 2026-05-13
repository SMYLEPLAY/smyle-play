"""voice : ajoute voice_origin + linked_track_id (Phase B metadata)

Revision ID: 0027_voice_origin_and_linked_track
Revises: 0026_create_dna_table
Create Date: 2026-05-13

Fix 2026-05-13 : séparer op.add_column et op.create_foreign_key
(la syntaxe inline FK dans add_column ne créait pas la contrainte
côté PostgreSQL via Alembic → pre-deploy failed).
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
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_voices_linked_track_id_tracks",
        "voices",
        "tracks",
        ["linked_track_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_voices_linked_track_id",
        "voices",
        ["linked_track_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_voices_linked_track_id", table_name="voices")
    op.drop_constraint(
        "fk_voices_linked_track_id_tracks", "voices", type_="foreignkey"
    )
    op.drop_column("voices", "linked_track_id")
    op.drop_constraint("ck_voices_voice_origin_enum", "voices", type_="check")
    op.drop_column("voices", "voice_origin")
