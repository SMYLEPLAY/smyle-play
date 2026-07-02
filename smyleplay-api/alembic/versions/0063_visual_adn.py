"""ADN Visuel artiste — signature visuelle vendable (calque ADN musical)

Revision ID: 0063_visual_adn
Revises: 0062_album_adn
Create Date: 2026-06-17

Sommet de la pyramide visuelle (profil > album > image). Calque STRICT de
l'ADN musical artiste (table `adns`, migration ADN d'origine) :

  • table `visual_adns` (1 par artiste, UNIQUE artist_id) :
      - description       TEXT NOT NULL  (CHECK char_length >= 200)
      - usage_guide       TEXT
      - example_outputs   TEXT
      - price_credits     INTEGER NOT NULL (CHECK 30..500)
      - ai_reference      VARCHAR(30)
      - max_supply        INTEGER
      - style             VARCHAR(40)    — code STYLES (images.py), public
      - palette           VARCHAR(255)   — génome gaté
      - is_published / is_deleted BOOLEAN NOT NULL DEFAULT false
      - created_at / updated_at / last_updated_by_artist_at

  • table `owned_visual_adns` (possession) : calque owned_adns.
      PK composite (user_id, visual_adn_id), FKs ON DELETE CASCADE, owned_at.

Pas de data migration. Rollback : drop des deux tables (ordre inverse).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0063_visual_adn"
down_revision = "0062_album_adn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visual_adns",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("artist_id", UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("usage_guide", sa.Text(), nullable=True),
        sa.Column("example_outputs", sa.Text(), nullable=True),
        sa.Column("price_credits", sa.Integer(), nullable=False),
        sa.Column("ai_reference", sa.String(30), nullable=True),
        sa.Column("max_supply", sa.Integer(), nullable=True),
        sa.Column("style", sa.String(40), nullable=True),
        sa.Column("palette", sa.String(255), nullable=True),
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_updated_by_artist_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["artist_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artist_id", name="uq_visual_adns_artist_id"),
        sa.CheckConstraint(
            "price_credits >= 30 AND price_credits <= 500",
            name="ck_visual_adns_price_credits_range",
        ),
        sa.CheckConstraint(
            "char_length(description) >= 200",
            name="ck_visual_adns_description_min_length",
        ),
    )
    op.create_index(
        "ix_visual_adns_artist_id", "visual_adns", ["artist_id"]
    )

    op.create_table(
        "owned_visual_adns",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("visual_adn_id", UUID(as_uuid=True), nullable=False),
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
            ["visual_adn_id"], ["visual_adns.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "visual_adn_id", name="pk_owned_visual_adns"
        ),
    )
    op.create_index(
        "ix_owned_visual_adns_user_id", "owned_visual_adns", ["user_id"]
    )
    op.create_index(
        "ix_owned_visual_adns_visual_adn_id",
        "owned_visual_adns",
        ["visual_adn_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_owned_visual_adns_visual_adn_id", table_name="owned_visual_adns"
    )
    op.drop_index(
        "ix_owned_visual_adns_user_id", table_name="owned_visual_adns"
    )
    op.drop_table("owned_visual_adns")

    op.drop_index("ix_visual_adns_artist_id", table_name="visual_adns")
    op.drop_table("visual_adns")
