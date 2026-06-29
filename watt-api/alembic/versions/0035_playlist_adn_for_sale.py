"""0035 — playlist ADN for sale (adn_for_sale + adn_price)

Revision ID: 0035_playlist_adn_for_sale
Revises: 0034_soft_delete_adns_voices
Create Date: 2026-05-14

Ajoute deux colonnes à la table `playlists` :
  • adn_for_sale BOOLEAN NOT NULL DEFAULT FALSE
      → l'artiste a activé la vente de l'ADN de cette playlist
  • adn_price    INTEGER NULL
      → prix en Smyles (null = pas en vente / gratuit selon adn_for_sale)

Le seed_prompt existant (déjà en DB) sert de contenu de l'ADN.
Le flow d'achat (OwnedPlaylistAdn) est prévu Sprint 2.
"""

from alembic import op
import sqlalchemy as sa

revision      = "0035_playlist_adn_for_sale"
down_revision = "0034_soft_delete_adns_voices"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "playlists",
        sa.Column(
            "adn_for_sale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "playlists",
        sa.Column("adn_price", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("playlists", "adn_price")
    op.drop_column("playlists", "adn_for_sale")
