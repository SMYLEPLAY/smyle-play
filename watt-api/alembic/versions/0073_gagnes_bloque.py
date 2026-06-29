"""gagnes_bloque — portion gelée des gagnés (A2, escrow)

Revision ID: 0073_gagnes_bloque
Revises: 0072_reconcile_buckets
Create Date: 2026-06-29

A2 du moteur économique — escrow des gains. Ajoute `smyles_gagnes_bloque` sur
users : portion des gagnés GELÉE (litige / fraude / séquestre concours-enchères-
précommandes), non retirable. Le reste des gagnés devient retirable après
maturation (calcul à la lecture depuis le ledger, cf. app/services/escrow.py —
pas de colonne de date, pas de job : la maturité se dérive de created_at des
transactions de gain).

Additif, défaut 0 → aucun gain n'est gelé tant qu'un admin ne le décide pas.
CHECK >= 0.

Rollback : drop de la colonne (+ contrainte).
"""
import sqlalchemy as sa
from alembic import op


revision = "0073_gagnes_bloque"
down_revision = "0072_reconcile_buckets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "smyles_gagnes_bloque", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_check_constraint(
        "ck_users_smyles_gagnes_bloque_nonneg", "users", "smyles_gagnes_bloque >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_users_smyles_gagnes_bloque_nonneg", "users", type_="check"
    )
    op.drop_column("users", "smyles_gagnes_bloque")
