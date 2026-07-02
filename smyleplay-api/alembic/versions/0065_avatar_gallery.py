"""0065 — galerie d'images d'un produit IMAGE (C4 galerie avatar)

Revision ID: 0065_avatar_gallery
Revises: 0064_visual_achiev
Create Date: 2026-06-18

Permet qu'un produit IMAGE (ligne `prompts`, product_type='image') porte une
GALERIE de plusieurs images. Cas d'usage : un avatar = un personnage avec 10+
visuels. À l'achat, l'acheteur récupère TOUTES les images originales de la
galerie + la recette. Aperçus de galerie publics, originaux gatés (download).

Table `prompt_gallery_images` :
  - prompt_id   → FK prompts.id ON DELETE CASCADE (index)
  - image_r2_key   = ORIGINAL gaté (String 500)
  - preview_r2_key = APERÇU public (String 500)
  - position    = ordre d'affichage (Integer, default 0)
  - created_at

Index : prompt_id seul (jointures) + (prompt_id, position) (listing ordonné).
Pas de data migration : la galerie est optionnelle et vide par défaut, la
création d'image existante n'est pas touchée.

NB chaîne : down_revision = '0064_visual_achiev' (la VALEUR `revision` déclarée
dans 0064_visual_achievements.py, ≤ 32 chars), pas le nom de fichier.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0065_avatar_gallery"
down_revision = "0064_visual_achiev"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_gallery_images",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "prompt_id",
            UUID(as_uuid=True),
            sa.ForeignKey("prompts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("image_r2_key", sa.String(length=500), nullable=False),
        sa.Column("preview_r2_key", sa.String(length=500), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_prompt_gallery_images_prompt_id",
        "prompt_gallery_images",
        ["prompt_id"],
    )
    op.create_index(
        "ix_prompt_gallery_images_prompt_position",
        "prompt_gallery_images",
        ["prompt_id", "position"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prompt_gallery_images_prompt_position",
        table_name="prompt_gallery_images",
    )
    op.drop_index(
        "ix_prompt_gallery_images_prompt_id",
        table_name="prompt_gallery_images",
    )
    op.drop_table("prompt_gallery_images")
