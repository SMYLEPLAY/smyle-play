"""0036 — table owned_playlist_adns

Revision ID: 0036_owned_playlist_adns
Revises: 0035_playlist_adn_for_sale
Create Date: 2026-05-14

Crée la table `owned_playlist_adns` (possession d'ADN Playlist).
PK composite (user_id, playlist_id) — un user achète une fois par playlist.
Donne droit à réduction sur ADN Track de la playlist (calculé dans unlock_adn_atomic).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0036_owned_playlist_adns"
down_revision = "0035_playlist_adn_for_sale"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "owned_playlist_adns",
        sa.Column("user_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("playlist_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"],     ["users.id"],     ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "playlist_id", name="pk_owned_playlist_adns"),
    )
    op.create_index("ix_owned_playlist_adns_user_id",     "owned_playlist_adns", ["user_id"])
    op.create_index("ix_owned_playlist_adns_playlist_id", "owned_playlist_adns", ["playlist_id"])


def downgrade() -> None:
    op.drop_index("ix_owned_playlist_adns_playlist_id", table_name="owned_playlist_adns")
    op.drop_index("ix_owned_playlist_adns_user_id",     table_name="owned_playlist_adns")
    op.drop_table("owned_playlist_adns")
