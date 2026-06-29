"""0038 — colonne tags sur tracks

Revision ID: 0038_track_tags
Revises: 0037_notifs_msgs_trades
Create Date: 2026-05-25

Ajoute un champ texte libre `tags` sur la table tracks.
Permet la recherche par mots-clés / mood à la création d'un son.

Exemples de valeurs : "chill, dark, 90bpm, guitare, nuit"
Format : texte libre séparé par des virgules, max 500 chars.
NULL = aucun tag défini (ancien contenu et créations sans tag).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0038_track_tags"
down_revision = "0037_notifs_msgs_trades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracks",
        sa.Column("tags", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tracks", "tags")
