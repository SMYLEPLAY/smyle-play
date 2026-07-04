"""adn_offers_reserve — offres cash sur ADN + reserve caché (chantier OFFRES-ADN)

Revision ID: 0080_adn_offers_reserve
Revises: 0079_seed_prix_watt
Create Date: 2026-07-03

Doctrine (2026-07-03_doctrine-vente-ADN-2-rails) : tout ADN (musique + visuel)
se vend UNIQUEMENT sur proposition — plus d'achat direct. Un acheteur fait une
offre en Smyles → le vendeur accepte/refuse → transfert + livraison.

Structure :
  1. trade_offers : on ÉTEND le système de trade existant (décision Tom 03/07,
     extension > table dédiée) —
       - target_type   VARCHAR(20) NULL  ∈ {playlist_adn, album_adn, visual_adn}
                       (String volontaire, pas d'enum DB → ajout d'un type
                       futur sans migration)
       - target_id     UUID NULL         (id de l'ADN ciblé)
       - amount_credits INTEGER NULL     (montant proposé ; NULL = trade
                       prompt classique) + CHECK >= 1
  2. Reserve caché (plancher artiste, jamais exposé publiquement) :
       - playlists.adn_reserve_credits    INTEGER NULL
       - albums.adn_reserve_credits       INTEGER NULL
       - visual_adns.adn_reserve_credits  INTEGER NULL
       - adns.adn_reserve_credits         INTEGER NULL  (profil musical —
         décision Tom 03/07 : même règle pour TOUT ADN, sommet inclus)

Une offre < reserve est rejetée automatiquement (create ET accept).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0080_adn_offers_reserve"
down_revision = "0079_seed_prix_watt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extension trade_offers → offres cash sur ADN
    op.add_column(
        "trade_offers",
        sa.Column("target_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "trade_offers",
        sa.Column("target_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "trade_offers",
        sa.Column("amount_credits", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_trade_offers_amount_min",
        "trade_offers",
        "amount_credits IS NULL OR amount_credits >= 1",
    )
    op.create_index(
        "ix_trade_offers_target_type", "trade_offers", ["target_type"]
    )
    op.create_index(
        "ix_trade_offers_target_id", "trade_offers", ["target_id"]
    )

    # 2. Reserve caché par ADN (plancher artiste)
    op.add_column(
        "playlists",
        sa.Column("adn_reserve_credits", sa.Integer(), nullable=True),
    )
    op.add_column(
        "albums",
        sa.Column("adn_reserve_credits", sa.Integer(), nullable=True),
    )
    op.add_column(
        "visual_adns",
        sa.Column("adn_reserve_credits", sa.Integer(), nullable=True),
    )
    op.add_column(
        "adns",
        sa.Column("adn_reserve_credits", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("adns", "adn_reserve_credits")
    op.drop_column("visual_adns", "adn_reserve_credits")
    op.drop_column("albums", "adn_reserve_credits")
    op.drop_column("playlists", "adn_reserve_credits")
    op.drop_index("ix_trade_offers_target_id", table_name="trade_offers")
    op.drop_index("ix_trade_offers_target_type", table_name="trade_offers")
    op.drop_constraint(
        "ck_trade_offers_amount_min", "trade_offers", type_="check"
    )
    op.drop_column("trade_offers", "amount_credits")
    op.drop_column("trade_offers", "target_id")
    op.drop_column("trade_offers", "target_type")
