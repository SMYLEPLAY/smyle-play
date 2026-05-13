"""voice_meta : voice_origin + linked_track_id (Phase B)

Revision ID: 0027_voice_meta
Revises: 0026_create_dna_table
Create Date: 2026-05-13

Fix 2026-05-13 (hotfix #3) : raccourcir le revision ID. L'ancien
ID `0027_voice_origin_and_linked_track` faisait 34 chars, mais la
colonne `alembic_version.version_num` est en VARCHAR(32). Quand
alembic a tenté d'écrire la version après l'ALTER TABLE réussi, ça
a planté avec `value too long for type character varying(32)`.

Les ALTER TABLE de cette migration sont déjà commit en prod (DDL
transactionnel mais ROLLBACK seulement sur le INSERT alembic_version
qui suit). Cette nouvelle migration est donc IDEMPOTENTE : on utilise
IF NOT EXISTS / IF EXISTS pour ne pas re-tenter d'ajouter des
colonnes déjà présentes.

Note future : tout revision ID alembic doit faire ≤ 32 chars.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0027_voice_meta"
down_revision = "0026_create_dna_table"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """True si la colonne existe déjà (idempotence prod)."""
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return res is not None


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = :n"
        ),
        {"n": name},
    ).first()
    return res is not None


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes WHERE indexname = :n"
        ),
        {"n": name},
    ).first()
    return res is not None


def upgrade() -> None:
    # voice_origin
    if not _column_exists("voices_for_sale", "voice_origin"):
        op.add_column(
            "voices_for_sale",
            sa.Column("voice_origin", sa.String(length=20), nullable=True),
        )
    if not _constraint_exists("ck_voices_voice_origin_enum"):
        op.create_check_constraint(
            "ck_voices_voice_origin_enum",
            "voices_for_sale",
            "voice_origin IS NULL OR voice_origin IN "
            "('personal', 'ai', 'known_artist')",
        )

    # linked_track_id + FK + index
    if not _column_exists("voices_for_sale", "linked_track_id"):
        op.add_column(
            "voices_for_sale",
            sa.Column(
                "linked_track_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
    if not _constraint_exists("fk_voices_linked_track_id_tracks"):
        op.create_foreign_key(
            "fk_voices_linked_track_id_tracks",
            "voices_for_sale",
            "tracks",
            ["linked_track_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _index_exists("ix_voices_linked_track_id"):
        op.create_index(
            "ix_voices_linked_track_id",
            "voices_for_sale",
            ["linked_track_id"],
        )


def downgrade() -> None:
    if _index_exists("ix_voices_linked_track_id"):
        op.drop_index(
            "ix_voices_linked_track_id", table_name="voices_for_sale"
        )
    if _constraint_exists("fk_voices_linked_track_id_tracks"):
        op.drop_constraint(
            "fk_voices_linked_track_id_tracks",
            "voices_for_sale",
            type_="foreignkey",
        )
    if _column_exists("voices_for_sale", "linked_track_id"):
        op.drop_column("voices_for_sale", "linked_track_id")
    if _constraint_exists("ck_voices_voice_origin_enum"):
        op.drop_constraint(
            "ck_voices_voice_origin_enum",
            "voices_for_sale",
            type_="check",
        )
    if _column_exists("voices_for_sale", "voice_origin"):
        op.drop_column("voices_for_sale", "voice_origin")
