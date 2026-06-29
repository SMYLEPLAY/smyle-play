"""ADN Album — génome de style vendable (analogue ADN Playlist)

Revision ID: 0062_album_adn
Revises: 0061_image_style_tags
Create Date: 2026-06-16

Calque STRICT de l'ADN Playlist (migration 0035), porté sur `albums` :

  • 6 colonnes ADN sur `albums` (colonnes, PAS une table dédiée) :
      - seed_prompt      TEXT          — prompt/réglages représentatifs (gaté)
      - dna_description  TEXT          — description du génome (teaser exposé)
      - adn_style        VARCHAR(40)   — style dominant (codes STYLES images.py)
      - adn_palette      VARCHAR(255)  — palette (CSV hex / mots-clés, gaté)
      - adn_for_sale     BOOLEAN NOT NULL DEFAULT false
      - adn_price        INTEGER       — prix Smyles (NULL = pas de prix)

  • table `owned_album_adns` (possession) : analogue VISUEL de
    owned_playlist_adns. PK composite (user_id, album_id), FKs ON DELETE
    CASCADE, owned_at horodaté.

Pas de data migration : les colonnes naissent NULL/false sur les albums
existants — neutre, l'album reste une curation non vendable tant que l'owner
n'a pas activé adn_for_sale + posé un prix.

Rollback : drop de la table puis des 6 colonnes.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0062_album_adn"
down_revision = "0061_image_style_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("albums", sa.Column("seed_prompt", sa.Text(), nullable=True))
    op.add_column("albums", sa.Column("dna_description", sa.Text(), nullable=True))
    op.add_column("albums", sa.Column("adn_style", sa.String(40), nullable=True))
    op.add_column("albums", sa.Column("adn_palette", sa.String(255), nullable=True))
    op.add_column(
        "albums",
        sa.Column(
            "adn_for_sale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("albums", sa.Column("adn_price", sa.Integer(), nullable=True))

    op.create_table(
        "owned_album_adns",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("album_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["album_id"], ["albums.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "album_id", name="pk_owned_album_adns"
        ),
    )
    op.create_index(
        "ix_owned_album_adns_user_id", "owned_album_adns", ["user_id"]
    )
    op.create_index(
        "ix_owned_album_adns_album_id", "owned_album_adns", ["album_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_owned_album_adns_album_id", table_name="owned_album_adns")
    op.drop_index("ix_owned_album_adns_user_id", table_name="owned_album_adns")
    op.drop_table("owned_album_adns")

    op.drop_column("albums", "adn_price")
    op.drop_column("albums", "adn_for_sale")
    op.drop_column("albums", "adn_palette")
    op.drop_column("albums", "adn_style")
    op.drop_column("albums", "dna_description")
    op.drop_column("albums", "seed_prompt")
