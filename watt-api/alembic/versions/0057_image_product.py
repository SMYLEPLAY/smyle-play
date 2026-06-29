"""0057 — type de produit 'image' + champs image sur prompts (C4 Monde Visuel V1)

Revision ID: 0057_image_product
Revises: 0056_voice_supply
Create Date: 2026-06-14

C4 Monde Visuel V1 — axe Images IA (Chemin A, comme les Beats 0052 : on
généralise l'entité vendable `prompts` au lieu de creer une table separee →
reutilise toute la plomberie achat/possession/revente/royalties).

Une image IA = une ligne `prompts` avec product_type='image'. Difference
cle vs beat : une image n'a PAS de Track. Le fichier (original + apercu)
vit directement sur la ligne `prompts` (image_r2_key / preview_r2_key).
La recette d'image (prompt_text) est gatee derriere l'achat.

Sur `prompts` :
  - CHECK ck_prompts_product_type etendu → ('recipe', 'beat', 'image').
  - CHECK ck_prompts_prompt_text_length etendu → une image exige
    prompt_text NOT NULL, SANS borne de longueur (un prompt d'image peut
    faire 3 mots comme 500 ; la borne 100..1000 reste reservee aux recipe).
  - Nouvelles colonnes (toutes nullable, remplies seulement pour les images) :
      image_platform        (String)  — plateforme de generation
      image_model_version   (String)  — version du modele
      image_settings        (JSONB)   — reglages libres (steps, cfg, seed...)
      negative_prompt       (Text)    — prompt negatif eventuel
      image_r2_key          (String)  — cle R2 de l'ORIGINAL (jamais public)
      preview_r2_key        (String)  — cle R2 de l'APERCU reduit (public)

Provenance obligatoire pour les images : on ajoute un CHECK conditionnel
ck_prompts_image_provenance qui n'impose image_platform/image_model_version
NOT NULL QUE si product_type='image' (recipe/beat non touches).

Donnees existantes : toutes les lignes restent product_type IN ('recipe',
'beat') → les nouveaux CHECK sont satisfaits (les colonnes image_* sont NULL,
le CHECK provenance ne s'applique qu'aux images). Sur, pas de data migration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0057_image_product"
down_revision = "0056_voice_supply"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Nouvelles colonnes image_* (toutes nullable) ────────────────────────
    op.add_column("prompts", sa.Column("image_platform", sa.String(50), nullable=True))
    op.add_column("prompts", sa.Column("image_model_version", sa.String(100), nullable=True))
    op.add_column("prompts", sa.Column("image_settings", JSONB(), nullable=True))
    op.add_column("prompts", sa.Column("negative_prompt", sa.Text(), nullable=True))
    op.add_column("prompts", sa.Column("image_r2_key", sa.String(500), nullable=True))
    op.add_column("prompts", sa.Column("preview_r2_key", sa.String(500), nullable=True))

    # ── product_type : autoriser 'image' (drop + recreate, cf. 0052) ────────
    op.drop_constraint("ck_prompts_product_type", "prompts", type_="check")
    op.create_check_constraint(
        "ck_prompts_product_type",
        "prompts",
        "product_type IN ('recipe', 'beat', 'image')",
    )

    # ── prompt_text : ajouter la branche image (NOT NULL, sans borne) ───────
    # recipe ⇒ 100..1000 (compat Suno) ; beat ⇒ NULL ; image ⇒ NOT NULL libre.
    op.drop_constraint("ck_prompts_prompt_text_length", "prompts", type_="check")
    op.create_check_constraint(
        "ck_prompts_prompt_text_length",
        "prompts",
        "(product_type = 'recipe' AND char_length(prompt_text) BETWEEN 100 AND 1000) "
        "OR (product_type = 'beat' AND prompt_text IS NULL) "
        "OR (product_type = 'image' AND prompt_text IS NOT NULL)",
    )

    # ── Provenance obligatoire UNIQUEMENT pour les images ───────────────────
    op.create_check_constraint(
        "ck_prompts_image_provenance",
        "prompts",
        "product_type <> 'image' "
        "OR (image_platform IS NOT NULL AND image_model_version IS NOT NULL)",
    )


def downgrade() -> None:
    # Provenance image
    op.drop_constraint("ck_prompts_image_provenance", "prompts", type_="check")

    # prompt_text : retour a la version 0052 (recipe | beat)
    op.drop_constraint("ck_prompts_prompt_text_length", "prompts", type_="check")
    op.create_check_constraint(
        "ck_prompts_prompt_text_length",
        "prompts",
        "(product_type = 'recipe' AND char_length(prompt_text) BETWEEN 100 AND 1000) "
        "OR (product_type = 'beat' AND prompt_text IS NULL)",
    )

    # product_type : retour a ('recipe', 'beat')
    op.drop_constraint("ck_prompts_product_type", "prompts", type_="check")
    op.create_check_constraint(
        "ck_prompts_product_type",
        "prompts",
        "product_type IN ('recipe', 'beat')",
    )

    # Colonnes image_*
    op.drop_column("prompts", "preview_r2_key")
    op.drop_column("prompts", "image_r2_key")
    op.drop_column("prompts", "negative_prompt")
    op.drop_column("prompts", "image_settings")
    op.drop_column("prompts", "image_model_version")
    op.drop_column("prompts", "image_platform")
