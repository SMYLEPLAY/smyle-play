"""is_admin — rôle d'administration distinct du compte vitrine « Smyle »

Revision ID: 0085_users_is_admin
Revises: 0084_token_version
Create Date: 2026-09-04

Annexe B §2 (tâche B-M2). Jusqu'ici la seule garde d'administration était
`users.is_official`, or ce flag n'est PAS un rôle : il désigne le compte
vitrine « Smyle » et porte des effets d'interface (checkmark, tri en tête des
listes, exclusion des listes communauté, rattachement des playlists modèles).
Cocher `is_official` sur le compte perso de Tom pour lui donner l'accès admin
polluerait donc la vitrine. On sépare : `is_admin` = droit d'administration,
`is_official` = identité vitrine, la garde acceptant l'un OU l'autre.

Migration purement ADDITIVE : colonne booléenne NOT NULL avec server_default
FALSE — aucune ligne existante n'est modifiée, aucun droit n'est accordé.
Le downgrade retire la colonne (aucune donnée métier perdue : les droits sont
reposés par tools/make_admin.py).
"""
import sqlalchemy as sa
from alembic import op

revision = "0085_users_is_admin"
down_revision = "0084_token_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
