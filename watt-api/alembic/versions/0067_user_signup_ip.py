"""user_signup_ip — capture IP d'inscription (anti-abus H0.4)

Revision ID: 0067_user_signup_ip
Revises: 0066_welcome_bonus_ledger
Create Date: 2026-06-25

H0.4 anti-abus (décision Tom 2026-06-25 : on stocke l'IP). Colonne nullable
`signup_ip` sur users, renseignée à l'inscription. Sert au plafond parrainage
PAR IP et à la détection multi-comptes (comptes partageant une IP de signup).

Nullable : les comptes existants restent NULL (pas de rétro-capture possible),
et une IP indéterminée ne bloque jamais une inscription. VARCHAR(64) couvre
IPv6 + un éventuel préfixe.

Rollback : drop de la colonne (aucune dépendance, pas d'index).
"""
import sqlalchemy as sa
from alembic import op


revision = "0067_user_signup_ip"
down_revision = "0066_welcome_bonus_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("signup_ip", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "signup_ip")
