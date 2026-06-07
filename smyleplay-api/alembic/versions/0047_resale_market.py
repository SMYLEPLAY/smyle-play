"""0047 — marché secondaire (revente de prompts avec royalties)

Revision ID: 0047_resale_market
Revises: 0046_prompt_supply
Create Date: 2026-06-08

1. unlocked_prompts.resale_price (nullable) : NULL = pas en vente ; sinon prix
   de revente fixé par le propriétaire actuel.
2. Assouplit la contrainte de split des transactions pour les RESALE : une
   revente a 3 bénéficiaires (artiste 30% royaltie + plateforme 20% + vendeur
   50%), la part vendeur n'est pas stockée dans artist_revenue/platform_fee →
   on passe de "= credits_amount" à "<= credits_amount" pour resale.
   UNLOCK reste strict (=). Relâchement only → aucune donnée existante violée
   (resale était dormant).
"""
import sqlalchemy as sa
from alembic import op

revision = "0047_resale_market"
down_revision = "0046_prompt_supply"
branch_labels = None
depends_on = None

_OLD_CHECK = (
    "(type IN ('unlock', 'resale') "
    " AND artist_revenue + platform_fee = credits_amount) "
    "OR "
    "(type NOT IN ('unlock', 'resale') "
    " AND artist_revenue + platform_fee <= credits_amount)"
)
_NEW_CHECK = (
    "(type = 'unlock' "
    " AND artist_revenue + platform_fee = credits_amount) "
    "OR "
    "(type <> 'unlock' "
    " AND artist_revenue + platform_fee <= credits_amount)"
)


def upgrade() -> None:
    op.add_column(
        "unlocked_prompts",
        sa.Column("resale_price", sa.Integer(), nullable=True),
    )
    op.drop_constraint(
        "ck_transactions_split_within_amount", "transactions", type_="check"
    )
    op.create_check_constraint(
        "ck_transactions_split_within_amount", "transactions", _NEW_CHECK
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_transactions_split_within_amount", "transactions", type_="check"
    )
    op.create_check_constraint(
        "ck_transactions_split_within_amount", "transactions", _OLD_CHECK
    )
    op.drop_column("unlocked_prompts", "resale_price")
