"""final merge — réunir 0028_soft_delete avec la chaîne principale

Revision ID: 0033_final_merge
Revises: 0028_soft_delete_prompts_tracks, 0032_merge_heads
Create Date: 2026-05-14

Diagnostic Tom 2026-05-14 :
La PR #94 (soft-delete) a créé 0028_soft_delete_prompts_tracks avec
down_revision = "0027_voice_meta", c-à-d le même parent que
0029_voice_preview. Ces deux migrations forment un fork qui n'a jamais
été reconnecté.

La précédente migration 0032_merge_heads avait fusionné la chaîne
principale (0031_adn_price_unlock) avec la chaîne legacy (b2fe0db),
mais a oublié 0028_soft_delete → 2 heads persistants → alembic refuse
de démarrer ("Multiple head revisions are present").

Cette migration est un MERGE PUR (aucun SQL) qui unit :
  - 0028_soft_delete_prompts_tracks
  - 0032_merge_heads

Après ce merge il ne reste qu'1 head : 0033_final_merge.
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision = "0033_final_merge"
down_revision = ("0028_soft_delete_prompts_tracks", "0032_merge_heads")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
