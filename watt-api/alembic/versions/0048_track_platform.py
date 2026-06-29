"""0048 — colonne platform sur tracks

Revision ID: 0048_track_platform
Revises: 0047_resale_market
Create Date: 2026-06-08

Ajoute `platform` sur tracks : l'IA / l'outil avec lequel le son a été
généré (suno, udio, riffusion, stable_audio, autre). Sélectionné à la
création (dashTrackPlatform), affiché sur la carte ID avant achat.

Le sélecteur existait déjà côté UI mais la valeur n'était jamais stockée
(aucune colonne) — même enum que prompts.prompt_platform pour cohérence.
NULL = non renseigné (anciens sons).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0048_track_platform"
down_revision = "0047_resale_market"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Simple ajout de colonne nullable — calqué sur 0038_track_tags (pattern
    # éprouvé, zéro risque migration). L'enum (suno/udio/riffusion/
    # stable_audio/autre) est garanti par le <select> frontend ; pas de CHECK
    # DB ici pour rester sur le chemin de migration le plus sûr.
    op.add_column(
        "tracks",
        sa.Column("platform", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tracks", "platform")
