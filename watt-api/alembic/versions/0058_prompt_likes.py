"""0058 — table prompt_likes (likes durables, V1 = images)

Revision ID: 0058_prompt_likes
Revises: 0057_image_product
Create Date: 2026-06-15

C4 livraison 5 — likes images durables (remplace le hack localStorage de la
livraison 4, clé sp_img_likes_v1).

Le coeur audio passe par la wishlist = playlist privée (playlist_tracks.track_id
FK dure vers tracks.id). Une image (product_type='image') n'a PAS de Track →
elle ne peut pas entrer dans la wishlist audio. On crée donc un store dédié,
générique (clé prompt), mais utilisé pour les images en V1. Ce store séparé
respecte la séparation son/image : les likes image ne polluent jamais la
wishlist audio.

Table `prompt_likes` :
  - user_id    (UUID FK users, CASCADE)
  - prompt_id  (UUID FK prompts, CASCADE)
  - created_at (DateTime tz, default now())
  - PK composite (user_id, prompt_id) — un like unique par (user, prompt),
    rend le like idempotent au niveau DB.
  - Index sur user_id — "mes prompts likés" est la requête chaude.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0058_prompt_likes"
down_revision = "0057_image_product"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "prompt_likes",
        sa.Column("user_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"],   ["users.id"],   ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "prompt_id", name="pk_prompt_likes"),
    )
    op.create_index("ix_prompt_likes_user_id", "prompt_likes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_prompt_likes_user_id", table_name="prompt_likes")
    op.drop_table("prompt_likes")
