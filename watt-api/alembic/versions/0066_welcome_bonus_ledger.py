"""welcome_bonus_ledger — défaut credits_balance 10→0 (bonus tracé via ledger)

Revision ID: 0066_welcome_bonus_ledger
Revises: 0065_avatar_gallery
Create Date: 2026-06-25

H0.6 durcissement (décision Tom 2026-06-25) : le bonus de bienvenue (10 crédits)
était posé silencieusement par le server_default de la colonne, sans trace dans
le grand livre des transactions. On veut que CHAQUE crédit ait une transaction
d'origine avant de brancher l'argent réel.

Cette migration met le défaut à 0 ; le grant de 10 est désormais émis
explicitement par create_user via grant_credits_atomic (transaction BONUS).
Net inchangé pour un nouvel inscrit (0 défaut + 10 grant = 10), mais traçable.

⚠️ Les lignes users EXISTANTES ne sont pas touchées (ALTER DEFAULT n'affecte que
les futurs INSERT sans valeur explicite). Aucun rétro-grant : on ne réécrit pas
l'historique des comptes déjà créés.

Rollback : rétablit le défaut 10 (comportement pré-traçage).
"""
from alembic import op


revision = "0066_welcome_bonus_ledger"
down_revision = "0065_avatar_gallery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "credits_balance", server_default="0")


def downgrade() -> None:
    op.alter_column("users", "credits_balance", server_default="10")
