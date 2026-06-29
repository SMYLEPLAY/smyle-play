"""profil artiste type — 2 couleurs personnalisables (fond + accent)

Revision ID: 0017_profile_colors
Revises: 0016_profile_type_fields
Create Date: 2026-04-20

Chantier "Profil artiste type" : chaque artiste peut personnaliser sa page
publique via 2 couleurs hex (#RRGGBB) stockées sur la ligne user.

Ajouts :
  - profile_bg_color    : couleur de fond (--bg côté front)
  - profile_brand_color : couleur d'accent / écritaux (--brand côté front)

Les deux sont nullable. Null = fallback au violet WATT (#070608 / #8800FF)
appliqué côté front. Format attendu : "#RRGGBB" (7 chars) validé côté API
par Pydantic, pas de contrainte CHECK en DB pour rester additif-only.
"""
import sqlalchemy as sa
from alembic import op


revision = "0017_profile_colors"
down_revision = "0016_profile_type_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("profile_bg_color", sa.String(length=7), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("profile_brand_color", sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "profile_brand_color")
    op.drop_column("users", "profile_bg_color")
