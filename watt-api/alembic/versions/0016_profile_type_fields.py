"""profil artiste type — cover photo + influences + socials étendus

Revision ID: 0016_profile_type_fields
Revises: 0015_add_profile_fields
Create Date: 2026-04-19

Chantier "Profil artiste type" : refonte complète du profil public.

Ajouts :
  - cover_photo_url : bannière en tête de page artiste (style Spotify/IG)
  - influences      : texte long "inspirations / DNA créatif" sous la bio
  - tiktok          : lien profil TikTok
  - spotify         : lien profil Spotify
  - twitter_x       : lien profil Twitter / X

Tous nullable, purement additif.
"""
import sqlalchemy as sa
from alembic import op


revision = "0016_profile_type_fields"
down_revision = "0015_add_profile_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("cover_photo_url", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("influences",      sa.Text(),              nullable=True))
    op.add_column("users", sa.Column("tiktok",          sa.String(length=255),  nullable=True))
    op.add_column("users", sa.Column("spotify",         sa.String(length=500),  nullable=True))
    op.add_column("users", sa.Column("twitter_x",       sa.String(length=255),  nullable=True))


def downgrade() -> None:
    op.drop_column("users", "twitter_x")
    op.drop_column("users", "spotify")
    op.drop_column("users", "tiktok")
    op.drop_column("users", "influences")
    op.drop_column("users", "cover_photo_url")
