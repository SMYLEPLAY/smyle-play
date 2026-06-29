"""create tracks table (missing migration — pre-0011)

Revision ID: 0010b_create_tracks_table
Revises: 0010_strict_unlock_check
Create Date: 2026-04-20

Migration corrective : la table `tracks` était supposée exister avant la
migration 0011_extend_tracks_for_flask_migration, qui fait `ALTER TABLE
tracks ADD COLUMN ...`. Mais aucune migration précédente ne créait la
table — elle existait uniquement dans `app.models.track.Track` côté
SQLAlchemy.

Cette migration crée la version **initiale** de la table (id, title,
audio_url, artist_id, created_at). Les colonnes étendues (universe,
duration_seconds, r2_key, plays, legacy_id, color) sont ajoutées par
les migrations 0011, 0012, 0020.

Idempotent : utilise `IF NOT EXISTS` pour être rejouable sans crash si
la table a été créée autrement (Flask db.create_all côté legacy, etc.).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0010b_create_tracks_table"
down_revision: Union[str, None] = "0010_strict_unlock_check"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check si la table existe déjà (cas idempotent sur DB déjà partiellement init)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tracks" in inspector.get_table_names():
        return

    op.create_table(
        "tracks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("audio_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "artist_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["artist_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tracks_artist_id", "tracks", ["artist_id"])


def downgrade() -> None:
    op.drop_index("ix_tracks_artist_id", table_name="tracks")
    op.drop_table("tracks")
