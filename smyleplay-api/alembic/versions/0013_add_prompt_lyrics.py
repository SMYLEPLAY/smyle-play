"""add lyrics column to prompts (gated content for vocal tracks)

Revision ID: 0013_add_prompt_lyrics
Revises: 0012_add_track_legacy_id
Create Date: 2026-04-19

Phase 3 — extension du modèle Prompt.

Pour les morceaux vocaux (notamment l'univers HIT MIX), le prompt Suno
seul ne suffit pas : l'acheteur veut aussi pouvoir reproduire les paroles
exactes utilisées par l'artiste. On ajoute donc un champ `lyrics`
nullable au modèle Prompt.

⚠️ Sensibilité : ce champ contient du contenu PAYANT. Il ne doit JAMAIS
être renvoyé par les endpoints de listing (/watt/prompts) ni par
/watt/prompts/{id} sans preuve d'unlock. Il sera servi uniquement après
vérification de UnlockedPrompt côté API.

Pour les morceaux instrumentaux (SUNSET LOVER, JUNGLE OSMOSE, NIGHT
CITY) : lyrics reste NULL.
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0013_add_prompt_lyrics"
down_revision = "0012_add_track_legacy_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("lyrics", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prompts", "lyrics")
