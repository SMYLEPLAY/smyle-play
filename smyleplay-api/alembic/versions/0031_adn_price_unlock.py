"""adn : retire le plafond max sur price_credits (Tom 2026-05-13)

Revision ID: 0031_adn_price_unlock
Revises: 0030_adn_rarity
Create Date: 2026-05-13

Tom 2026-05-13 — Les éditions Mythic/Legendary doivent pouvoir se vendre
au-dessus de 500 crédits (avant : plafond hardcodé). On garde un min à 30
pour préserver la valeur du marketplace (anti-spam), mais plus de borne max.

Migration idempotente : drop constraint si existe, recreate avec min only.
"""
from alembic import op
import sqlalchemy as sa


revision = "0031_adn_price_unlock"
down_revision = "0030_adn_rarity"
branch_labels = None
depends_on = None


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    res = bind.execute(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"),
        {"n": name},
    ).first()
    return res is not None


def upgrade() -> None:
    # Drop ancien CHECK 30..500
    if _constraint_exists("ck_adns_price_credits_range"):
        op.drop_constraint(
            "ck_adns_price_credits_range", "adns", type_="check"
        )
    # Recreate avec min only
    if not _constraint_exists("ck_adns_price_credits_min"):
        op.create_check_constraint(
            "ck_adns_price_credits_min",
            "adns",
            "price_credits >= 30",
        )


def downgrade() -> None:
    if _constraint_exists("ck_adns_price_credits_min"):
        op.drop_constraint(
            "ck_adns_price_credits_min", "adns", type_="check"
        )
    if not _constraint_exists("ck_adns_price_credits_range"):
        op.create_check_constraint(
            "ck_adns_price_credits_range",
            "adns",
            "price_credits >= 30 AND price_credits <= 500",
        )
