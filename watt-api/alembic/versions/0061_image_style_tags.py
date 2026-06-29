"""image_style + image_tags — taxonomie visuelle (C4 DNA image)

Revision ID: 0061_image_style_tags
Revises: 0060_albums
Create Date: 2026-06-16

Deux colonnes nullable sur `prompts`, remplies SEULEMENT pour les images
(product_type='image') et facultatives même alors — fondations data pour la
recherche/découverte du Monde Image (filtres ?style= et ?tag= sur GET /images).

  • image_style  VARCHAR(40)  — style de rendu (réaliste, cartoon, anime, 3d…).
                                 Valeur unique parmi STYLES (cf. images.py).
  • image_tags   VARCHAR(255) — tags d'usage séparés par virgule (cover,
                                 portrait, paysage, logo, banniere, avatar,
                                 wallpaper, mockup, illustration, texture, fx).

Pas de contrainte DB enum : la validation (valeur hors-liste ignorée) est
portée côté router (validation légère, portable). Pas de data migration :
les colonnes naissent NULL sur tous les prompts existants — neutre.

Rollback : drop des deux colonnes (aucune dépendance, pas d'index).
"""
import sqlalchemy as sa
from alembic import op


revision = "0061_image_style_tags"
down_revision = "0060_albums"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column("image_style", sa.String(40), nullable=True))
    op.add_column("prompts", sa.Column("image_tags", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("prompts", "image_tags")
    op.drop_column("prompts", "image_style")
