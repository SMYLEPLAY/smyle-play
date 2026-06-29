"""0052 — type de produit vendable (recette | beat) + champs beat sur tracks

Revision ID: 0052_beat_product
Revises: 0051_unlocked_edition_number
Create Date: 2026-06-09

Phase 2 Marketplace VF — axe Beats (Chemin A : on généralise l'entité
vendable `prompts` au lieu de créer une table séparée → réutilise toute la
plomberie achat/possession/revente).

Sur `prompts` :
  - `product_type` : 'recipe' (défaut, = l'existant) | 'beat'.
  - `license_type` : NULL | 'lease' | 'exclusive' (rempli pour les beats).
  - `prompt_text` devient NULLable (un beat n'a pas de prompt). La contrainte
    de longueur 100..1000 ne s'applique plus QU'aux recettes.

Sur `tracks` :
  - `beat_id` (FK prompts, SET NULL) — miroir de `prompt_id` : un morceau peut
    vendre une recette ET un beat.
  - `pack_price_credits` — prix du bundle (recette + beat), NULL = pas de pack.

Données existantes : toutes les lignes deviennent product_type='recipe' (leur
prompt_text 100..1000 satisfait la nouvelle contrainte conditionnelle). Sûr.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0052_beat_product"
down_revision = "0051_unlocked_edition_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── prompts.product_type ────────────────────────────────────────────────
    op.add_column(
        "prompts",
        sa.Column(
            "product_type",
            sa.String(20),
            nullable=False,
            server_default="recipe",
        ),
    )
    op.create_check_constraint(
        "ck_prompts_product_type",
        "prompts",
        "product_type IN ('recipe', 'beat')",
    )

    # ── prompts.license_type (rempli pour les beats) ────────────────────────
    op.add_column(
        "prompts",
        sa.Column("license_type", sa.String(20), nullable=True),
    )
    op.create_check_constraint(
        "ck_prompts_license_type",
        "prompts",
        "license_type IS NULL OR license_type IN ('lease', 'exclusive')",
    )

    # ── prompts.prompt_text NULLable + contrainte de longueur conditionnelle ─
    op.alter_column(
        "prompts", "prompt_text",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.drop_constraint(
        "ck_prompts_prompt_text_length", "prompts", type_="check"
    )
    op.create_check_constraint(
        "ck_prompts_prompt_text_length",
        "prompts",
        "(product_type = 'recipe' AND char_length(prompt_text) BETWEEN 100 AND 1000) "
        "OR (product_type = 'beat' AND prompt_text IS NULL)",
    )

    # ── tracks.beat_id + tracks.pack_price_credits ──────────────────────────
    op.add_column(
        "tracks",
        sa.Column("beat_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tracks_beat_id",
        "tracks", "prompts",
        ["beat_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tracks_beat_id", "tracks", ["beat_id"])
    op.add_column(
        "tracks",
        sa.Column("pack_price_credits", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tracks", "pack_price_credits")
    op.drop_index("ix_tracks_beat_id", table_name="tracks")
    op.drop_constraint("fk_tracks_beat_id", "tracks", type_="foreignkey")
    op.drop_column("tracks", "beat_id")

    op.drop_constraint("ck_prompts_prompt_text_length", "prompts", type_="check")
    op.create_check_constraint(
        "ck_prompts_prompt_text_length",
        "prompts",
        "char_length(prompt_text) BETWEEN 100 AND 1000",
    )
    op.alter_column(
        "prompts", "prompt_text",
        existing_type=sa.Text(),
        nullable=False,
    )

    op.drop_constraint("ck_prompts_license_type", "prompts", type_="check")
    op.drop_column("prompts", "license_type")
    op.drop_constraint("ck_prompts_product_type", "prompts", type_="check")
    op.drop_column("prompts", "product_type")
