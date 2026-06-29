"""0051 — numéro d'édition #X/N sur les exemplaires (unlocked_prompts)

Revision ID: 0051_unlocked_edition_number
Revises: 0050_recipes_final
Create Date: 2026-06-09

Rareté tangible (Phase 1 Marketplace VF). Ajoute `edition_number` sur
`unlocked_prompts` : le numéro d'exemplaire dans l'édition limitée
(« tu possèdes le #3/10 »).

- Assigné séquentiellement au mint (1..max_supply) UNIQUEMENT pour les
  éditions limitées (prompts.max_supply non NULL). NULL = tirage illimité.
- Backfill des exemplaires DÉJÀ vendus : numérotation par ordre d'achat
  (unlocked_at croissant, id en départage), le plus ancien = #1, par prompt.
- Contrainte UNIQUE(prompt_id, edition_number) : pas deux fois le même
  numéro pour un prompt. Les NULL (illimités) restent autorisés en multiple.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0051_unlocked_edition_number"
down_revision = "0050_recipes_final"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Colonne nullable (pattern éprouvé, zéro risque).
    op.add_column(
        "unlocked_prompts",
        sa.Column("edition_number", sa.Integer(), nullable=True),
    )

    # 2. Backfill — uniquement les exemplaires d'éditions LIMITÉES
    #    (prompts.max_supply non NULL). Ordre = date d'achat puis id (départage
    #    déterministe). ROW_NUMBER garantit l'unicité par prompt.
    op.execute(
        """
        WITH numbered AS (
            SELECT
                up.id AS up_id,
                ROW_NUMBER() OVER (
                    PARTITION BY up.prompt_id
                    ORDER BY up.unlocked_at ASC, up.id ASC
                ) AS rn
            FROM unlocked_prompts up
            JOIN prompts p ON p.id = up.prompt_id
            WHERE p.max_supply IS NOT NULL
        )
        UPDATE unlocked_prompts u
        SET edition_number = numbered.rn
        FROM numbered
        WHERE u.id = numbered.up_id
        """
    )

    # 3. Contrainte d'unicité (après backfill, donc valide les données
    #    existantes). NULL distincts en Postgres → illimités non bloqués.
    op.create_unique_constraint(
        "uq_unlocked_prompts_prompt_edition",
        "unlocked_prompts",
        ["prompt_id", "edition_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_unlocked_prompts_prompt_edition",
        "unlocked_prompts",
        type_="unique",
    )
    op.drop_column("unlocked_prompts", "edition_number")
