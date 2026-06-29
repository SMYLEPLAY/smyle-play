"""add profile fields (genre + socials + city) on users

Revision ID: 0015_add_profile_fields
Revises: 0014_add_follow_system
Create Date: 2026-04-19

Chantier 1 — Étape 2 : refonte page artiste.

Les champs genre / city / soundcloud / instagram / youtube vivaient jusqu'ici
uniquement dans le store legacy Flask (/api/watt/profile JSON). Ce qui empêche
la page artiste FastAPI (/watt/artists/<slug>) de les renvoyer — elle les
laisse vides. La refonte visuelle a besoin de ces champs pour peupler le hero
+ les liens sociaux.

On remonte donc ces 5 colonnes dans la table `users`. Toutes nullable pour ne
pas casser les comptes existants. La migration est purement additive.
"""
import sqlalchemy as sa
from alembic import op


revision = "0015_add_profile_fields"
down_revision = "0014_add_follow_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("genre",      sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("city",       sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("soundcloud", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("instagram",  sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("youtube",    sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "youtube")
    op.drop_column("users", "instagram")
    op.drop_column("users", "soundcloud")
    op.drop_column("users", "city")
    op.drop_column("users", "genre")
