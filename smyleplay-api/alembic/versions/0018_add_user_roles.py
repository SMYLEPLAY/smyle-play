"""profil membre — casquettes / rôles déclarés (multi-select)

Revision ID: 0018_add_user_roles
Revises: 0017_profile_colors
Create Date: 2026-04-20

Chantier "Positionnement fan/artiste" :

Le profil /u/<slug> devient la carte d'identité déclarative du compte.
L'utilisateur y choisit 1 ou plusieurs casquettes parmi une liste fermée :
artiste, producteur, beatmaker, topliner, ghostwriter, compositeur,
parolier, arrangeur, editeur, dj, ingenieur_son, auditeur.

Le WATT BOARD reste le cockpit qui pilote la partie artiste (upload sons,
analytics, recettes). Les rôles sont donc purement déclaratifs côté
profil — ils n'ouvrent/ferment pas de fonctionnalités, ils indiquent au
réseau "qui on est" (ex. un topliner qui cherche un producteur).

Stockage : JSON array de strings (slugs/codes). NULL = pas encore choisi.
Array vide [] = explicitement "aucune casquette" (rare, mais valide).
Portable Postgres (JSONB) + SQLite (TEXT) via sa.JSON.
"""
import sqlalchemy as sa
from alembic import op


revision = "0018_add_user_roles"
down_revision = "0017_profile_colors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("roles", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "roles")
