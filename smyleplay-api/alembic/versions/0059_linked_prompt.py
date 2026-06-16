"""0059 — liaison 1:1 son <-> image (Oeuvre complete, C4)

Revision ID: 0059_linked_prompt
Revises: 0058_prompt_likes
Create Date: 2026-06-16

C4 « Oeuvre complete » — lier un son et une image en DEUX produits
INDEPENDANTS (prix/rarete/recette propres, achat separe) mais relies pour
l'affichage. Lien 1:1, nature croisee obligatoire (image <-> son), jamais
image <-> image. La regle 1:1 et la nature croisee sont enforce en service
(link_products) ; la DB ne porte que la colonne + l'index.

Sur `prompts` :
  - linked_prompt_id (UUID, NULLABLE) : pointe vers l'AUTRE produit de la
    paire. Self-FK prompts.id ON DELETE SET NULL — si l'un des deux produits
    est supprime physiquement, l'autre voit son lien remis a NULL (pas de
    pointeur fantome). Le soft-delete (is_deleted) ne touche PAS le lien :
    c'est gere au niveau service/affichage.
  - index ix_prompts_linked_prompt_id : sert a retrouver le partenaire et a
    verifier l'unicite cote service.

Donnees existantes : toutes les lignes restent linked_prompt_id NULL → aucune
data migration, aucune contrainte violee.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0059_linked_prompt"
down_revision = "0058_prompt_likes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("linked_prompt_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_prompts_linked_prompt_id",
        "prompts",
        "prompts",
        ["linked_prompt_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_prompts_linked_prompt_id", "prompts", ["linked_prompt_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_prompts_linked_prompt_id", table_name="prompts")
    op.drop_constraint(
        "fk_prompts_linked_prompt_id", "prompts", type_="foreignkey"
    )
    op.drop_column("prompts", "linked_prompt_id")
