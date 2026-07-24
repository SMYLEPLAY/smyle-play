"""token_version — révocation des JWT après reset de mot de passe

Revision ID: 0084_token_version
Revises: 0083_user_terms
Create Date: 2026-07-24

Durcissement : le JWT porte un numéro de version (claim `tv`) recopié depuis
users.token_version. get_current_user rejette un jeton dont le `tv` ne
correspond plus. Un reset de mot de passe incrémente token_version → tous les
jetons émis avant deviennent invalides (fin de la fenêtre 60 min post-reset).
Colonne simple, server_default 0 : les jetons existants (sans claim `tv`) sont
traités comme tv=0 et restent valides jusqu'à leur expiration naturelle.
"""
import sqlalchemy as sa
from alembic import op

revision = "0084_token_version"
down_revision = "0083_user_terms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
