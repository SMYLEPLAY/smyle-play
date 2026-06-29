"""smyle_buckets — 3 sous-soldes par catégorie de Smyle (A1.1)

Revision ID: 0071_smyle_buckets
Revises: 0070_ledger_append_only
Create Date: 2026-06-29

A1.1 du moteur économique (doctrine éco). Ajoute 3 sous-soldes sur `users` selon
l'ORIGINE du Smyle (= sa cashabilité) :
  - smyles_achetes : achetés en € (packs)        → non encaissables
  - smyles_gagnes  : reçus via une vente          → ENCAISSABLES (= dette)
  - smyles_promo   : offerts par la plateforme    → non encaissables, expirables

`credits_balance` reste la source de vérité du solde ; les buckets sont
maintenus EN PARALLÈLE (étape additive — aucun call-site n'est encore branché ;
ça vient en A1.3). L'invariant `achetes + gagnes + promo == credits_balance`
sera posé en contrainte DB en A1.4, quand tous les chemins crédit/débit
passeront par les helpers.

BACKFILL CONSERVATEUR : on initialise `smyles_achetes = credits_balance` (et
gagnes = promo = 0). Ainsi la somme == balance dès la migration, et on ne
SURESTIME JAMAIS la dette encaissable (gagnés = 0). La re-catégorisation fine
(rejeu du ledger pour ventiler en gagnés/promo) se fera en A1.2.

CHECK >= 0 par colonne (jamais de bucket négatif). PAS encore de CHECK
d'invariant somme==balance (A1.4).

Rollback : drop des 3 colonnes (et de leurs CHECK).
"""
import sqlalchemy as sa
from alembic import op


revision = "0071_smyle_buckets"
down_revision = "0070_ledger_append_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("smyles_achetes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("smyles_gagnes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("smyles_promo", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill conservateur : tout le solde courant → achetés (non encaissable).
    op.execute("UPDATE users SET smyles_achetes = credits_balance")

    op.create_check_constraint(
        "ck_users_smyles_achetes_nonneg", "users", "smyles_achetes >= 0"
    )
    op.create_check_constraint(
        "ck_users_smyles_gagnes_nonneg", "users", "smyles_gagnes >= 0"
    )
    op.create_check_constraint(
        "ck_users_smyles_promo_nonneg", "users", "smyles_promo >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_smyles_promo_nonneg", "users", type_="check")
    op.drop_constraint("ck_users_smyles_gagnes_nonneg", "users", type_="check")
    op.drop_constraint("ck_users_smyles_achetes_nonneg", "users", type_="check")
    op.drop_column("users", "smyles_promo")
    op.drop_column("users", "smyles_gagnes")
    op.drop_column("users", "smyles_achetes")
