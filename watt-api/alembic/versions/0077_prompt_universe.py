"""prompt_universe — univers WATT par image (parité tracks.universe)

Revision ID: 0077_prompt_universe
Revises: 0076_oeuvre_binding
Create Date: 2026-06-30

Trou de binarité fine (cf. AUDIT) : une track porte son `universe` (4 mondes
WATT) mais une IMAGE (ligne `prompts` product_type='image') non. On ajoute
`prompts.universe` (nullable) + CHECK enum miroir STRICT de
`ck_tracks_universe_enum` (migration 0011) pour pouvoir tagger/filtrer une cover
officielle par monde comme un son.

ADDITIF et NON destructif : colonne nullable, sans défaut → aucune ligne
existante touchée. NULL = prompt hors-univers (cas par défaut : recettes audio,
images utilisateur lambda). Indexé pour le filtre /watt/search/images?universe=.

Rollback : drop de l'index, du CHECK et de la colonne.
"""
import sqlalchemy as sa
from alembic import op


revision = "0077_prompt_universe"
down_revision = "0076_oeuvre_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("universe", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_prompts_universe", "prompts", ["universe"])
    op.create_check_constraint(
        "ck_prompts_universe_enum",
        "prompts",
        "universe IS NULL OR universe IN "
        "('sunset-lover', 'jungle-osmose', 'night-city', 'hit-mix')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_prompts_universe_enum", "prompts", type_="check")
    op.drop_index("ix_prompts_universe", table_name="prompts")
    op.drop_column("prompts", "universe")
