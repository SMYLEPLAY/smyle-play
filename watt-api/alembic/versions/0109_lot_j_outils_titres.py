"""lot_j_outils_titres — ElevenLabs Music accepté ; titres de recette courts

Revision ID: 0109_lot_j_outils_titres
Revises: 0108_reclasse_achetes_promo
Create Date: 2026-10-21

Lot J (équilibre de la plateforme) :
1. WATT accepte les sons générés avec ElevenLabs Music : la contrainte
   `ck_prompts_platform_enum` est élargie. `tracks.platform` n'a pas de
   contrainte en base (validation côté schéma).
2. Un titre de recette peut faire 2 caractères (« Nuit » passait pour le son
   mais faisait échouer sa recette, minimum 5) : `ck_prompts_title_min_length`.

Rollback : contraintes d'origine rétablies ; les recettes « elevenlabs »
passent en « autre » et les titres de moins de 5 caractères sont complétés
(« Nuit » → « Nuit… ») pour que la contrainte s'applique.
"""
from alembic import op

revision = "0109_lot_j_outils_titres"
down_revision = "0108_reclasse_achetes_promo"
branch_labels = None
depends_on = None

_AVANT = "('suno', 'udio', 'riffusion', 'stable_audio', 'autre')"
_APRES = "('suno', 'udio', 'riffusion', 'stable_audio', 'elevenlabs', 'autre')"


def upgrade() -> None:
    op.drop_constraint("ck_prompts_platform_enum", "prompts", type_="check")
    op.create_check_constraint(
        "ck_prompts_platform_enum", "prompts",
        f"prompt_platform IS NULL OR prompt_platform IN {_APRES}",
    )
    op.drop_constraint("ck_prompts_title_min_length", "prompts", type_="check")
    op.create_check_constraint(
        "ck_prompts_title_min_length", "prompts", "char_length(title) >= 2",
    )


def downgrade() -> None:
    op.execute("UPDATE prompts SET title = rpad(title, 5, '…') WHERE char_length(title) < 5")
    op.drop_constraint("ck_prompts_title_min_length", "prompts", type_="check")
    op.create_check_constraint(
        "ck_prompts_title_min_length", "prompts", "char_length(title) >= 5",
    )
    op.execute("UPDATE prompts SET prompt_platform = 'autre' WHERE prompt_platform = 'elevenlabs'")
    op.execute("UPDATE tracks SET platform = 'autre' WHERE platform = 'elevenlabs'")
    op.drop_constraint("ck_prompts_platform_enum", "prompts", type_="check")
    op.create_check_constraint(
        "ck_prompts_platform_enum", "prompts",
        f"prompt_platform IS NULL OR prompt_platform IN {_AVANT}",
    )
