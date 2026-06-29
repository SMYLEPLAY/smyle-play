"""0041 — genre vocal : ajoute 'neutre' et 'mixte'

Revision ID: 0041_vocal_genders
Revises: 0040_trader_achievements
Create Date: 2026-06-06

Étend la contrainte CHECK ck_prompts_vocal_gender_enum pour accepter
'neutre' et 'mixte' en plus de masculin / feminin / instrumental.
Opération transactionnelle standard (drop + recreate CHECK).
"""
from alembic import op

revision = "0041_vocal_genders"
down_revision = "0040_trader_achievements"
branch_labels = None
depends_on = None

_OLD = (
    "prompt_vocal_gender IS NULL OR prompt_vocal_gender IN "
    "('masculin', 'feminin', 'instrumental')"
)
_NEW = (
    "prompt_vocal_gender IS NULL OR prompt_vocal_gender IN "
    "('masculin', 'feminin', 'instrumental', 'neutre', 'mixte')"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_prompts_vocal_gender_enum", "prompts", type_="check"
    )
    op.create_check_constraint(
        "ck_prompts_vocal_gender_enum", "prompts", _NEW
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_prompts_vocal_gender_enum", "prompts", type_="check"
    )
    op.create_check_constraint(
        "ck_prompts_vocal_gender_enum", "prompts", _OLD
    )
