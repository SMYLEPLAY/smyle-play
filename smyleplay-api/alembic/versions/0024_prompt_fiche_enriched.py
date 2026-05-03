"""ajout 5 champs réglages génération sur prompts (P1-F4)

Revision ID: 0024_prompt_fiche_enriched
Revises: 0023_add_voices_for_sale
Create Date: 2026-05-04

Contexte produit (P1-F4 — fiche vente prompt enrichie) :

  Sans réglages de génération, l'acheteur d'un prompt n'arrive pas à
  reproduire le morceau original — il tape le texte dans Suno mais
  obtient une variante divergente. Pour augmenter la valeur perçue
  et la conversion, on ajoute 5 champs sur la fiche prompt :

  OBLIGATOIRES à la création (côté Pydantic — DB en nullable pour
  rétro-compat des prompts existants) :
    1. prompt_platform        — IA d'origine (Suno / Udio / etc)
    2. prompt_weirdness       — réglage Suno-spécifique
    3. prompt_style_influence — référence artistes/genres
    4. prompt_vocal_gender    — masculin / féminin / instrumental

  OPTIONNEL :
    5. prompt_model_version   — version exacte (Suno v4, Udio 1.5, ...)

Choix de design :
  - **Toutes les colonnes sont NULLable en DB** pour ne pas casser les
    prompts existants (migration sans data fix). La validation strict
    (4 obligatoires) est portée côté Pydantic `PromptCreate`. Les
    anciens prompts restent valides ; les nouveaux doivent renseigner.
  - **CHECK constraints conditionnelles** sur platform et vocal_gender
    (`IS NULL OR IN (...)`) — laisse les NULL legacy passer mais
    valide les valeurs explicites. Pas d'ENUM Postgres (DROP/CREATE
    coûte un downtime ; un VARCHAR + CHECK reste flexible pour
    ajouter une plateforme plus tard).
  - **prompt_model_version** sans CHECK : texte libre, on accepte
    n'importe quoi (les versions évoluent vite).
  - **prompt_style_influence** plafonné à 500 chars : assez pour 2-3
    refs détaillées, pas un essai narratif.
  - **prompt_weirdness** plafonné à 50 chars : un nombre 0-100 ou un
    label court ("très varié"), pas un paragraphe.

Rollback : downgrade() drop les 5 colonnes + leurs CHECK constraints.
"""
import sqlalchemy as sa
from alembic import op


revision = "0024_prompt_fiche_enriched"
down_revision = "0023_add_voices_for_sale"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 5 nouvelles colonnes — toutes nullable pour rétro-compat ──────────
    op.add_column(
        "prompts",
        sa.Column("prompt_platform", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "prompts",
        sa.Column(
            "prompt_model_version", sa.String(length=50), nullable=True
        ),
    )
    op.add_column(
        "prompts",
        sa.Column("prompt_weirdness", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "prompts",
        sa.Column(
            "prompt_style_influence", sa.String(length=500), nullable=True
        ),
    )
    op.add_column(
        "prompts",
        sa.Column(
            "prompt_vocal_gender", sa.String(length=20), nullable=True
        ),
    )

    # ── CHECK constraints sur enums (conditionnelles : laisse NULL passer) ──
    op.create_check_constraint(
        "ck_prompts_platform_enum",
        "prompts",
        "prompt_platform IS NULL OR prompt_platform IN "
        "('suno', 'udio', 'riffusion', 'stable_audio', 'autre')",
    )
    op.create_check_constraint(
        "ck_prompts_vocal_gender_enum",
        "prompts",
        "prompt_vocal_gender IS NULL OR prompt_vocal_gender IN "
        "('masculin', 'feminin', 'instrumental')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_prompts_vocal_gender_enum", "prompts", type_="check"
    )
    op.drop_constraint(
        "ck_prompts_platform_enum", "prompts", type_="check"
    )
    op.drop_column("prompts", "prompt_vocal_gender")
    op.drop_column("prompts", "prompt_style_influence")
    op.drop_column("prompts", "prompt_weirdness")
    op.drop_column("prompts", "prompt_model_version")
    op.drop_column("prompts", "prompt_platform")
