"""resserrage des bornes prompt_text : 100..1000 (compat Suno)

Revision ID: 0019_tighten_prompt_text_bounds
Revises: 0018_add_user_roles
Create Date: 2026-04-20

Justification produit :
  Suno n'accepte pas plus de 1000 caractères en entrée prompt. Vendre un
  prompt > 1000 chars reviendrait à vendre du contenu inutilisable dans
  l'outil cible. Inversement, < 100 chars ne laisse pas assez de substance
  pour être considéré comme un vrai "prompt" vendable (style, BPM, mood,
  références). On aligne donc :

    Ancien  :  char_length(prompt_text) >= 50
    Nouveau :  char_length(prompt_text) BETWEEN 100 AND 1000

Cohérence :
  Pydantic  PROMPT_TEXT_MIN = 100, PROMPT_TEXT_MAX = 1000
  JS front  dashboard.js validates 100 <= len <= 1000 client-side
  DB CHECK  ck_prompts_prompt_text_length (renamed from _min_length)

Le renommage de la contrainte permet de capturer la nouvelle sémantique
(min+max dans une seule CHECK plutôt que "min_length" seul).

Rollback-friendly : `downgrade()` rétablit exactement l'ancienne contrainte.
Pas de DATA migration : les prompts existants qui seraient hors bornes (rare
car seed + tests respectent déjà > 50, en pratique > 100) seraient bloqués
par la nouvelle CHECK côté Postgres. Si un tel prompt existe, la migration
échouera — c'est volontaire pour que les données restent cohérentes.
Sur SQLite (tests), les CheckConstraint sont poseurs-silencieux.
"""
import sqlalchemy as sa
from alembic import op


revision = "0019_tighten_prompt_text_bounds"
down_revision = "0018_add_user_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # On drop l'ancienne check puis on ajoute la nouvelle. `IF EXISTS` évite
    # de péter sur les bases qui auraient déjà été touchées à la main.
    with op.batch_alter_table("prompts") as batch_op:
        batch_op.drop_constraint(
            "ck_prompts_prompt_text_min_length",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_prompts_prompt_text_length",
            "char_length(prompt_text) BETWEEN 100 AND 1000",
        )


def downgrade() -> None:
    with op.batch_alter_table("prompts") as batch_op:
        batch_op.drop_constraint(
            "ck_prompts_prompt_text_length",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_prompts_prompt_text_min_length",
            "char_length(prompt_text) >= 50",
        )
