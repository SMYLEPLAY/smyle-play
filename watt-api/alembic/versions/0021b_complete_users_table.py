"""complete users table — add all missing fundamental columns (pre-0022)

Revision ID: 0021b_complete_users_table
Revises: 0021_add_playlists
Create Date: 2026-04-20

Migration corrective : les migrations Alembic existantes n'ont jamais créé
les colonnes fondamentales de la table `users` (password_hash, artist_name,
bio, brand_color, profile_public, language, credits_balance, etc.). Le
modèle SQLAlchemy `app.models.user.User` les définit, mais côté DB rien
ne les a jamais ajoutées — probablement parce que le dev local tournait
sur `db.create_all()` qui synchronise tout depuis le modèle.

Sur un Postgres vierge (Railway prod), seules les colonnes créées par
l'init (id, email, created_at) + celles ajoutées par 0015/0016/0017/0018
existent. La migration 0022 tente un INSERT avec `password_hash`,
`artist_name`, `bio`, `brand_color`, `profile_public` → UndefinedColumnError.

Cette migration comble le trou en ajoutant **toutes** les colonnes du
modèle User qui ne sont pas encore en DB, avant que 0022 fasse son seed.

Idempotente : on vérifie colonne par colonne via l'inspecteur SQLAlchemy
pour permettre de rejouer la migration sur une DB partiellement migrée
(ex. dev local qui a tourné `db.create_all()` avant).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0021b_complete_users_table"
down_revision: Union[str, None] = "0021_add_playlists"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Colonnes à garantir sur `users`. Tuples : (nom, définition SQLAlchemy).
# Toutes nullable ou avec server_default pour être backward-compatible
# avec des lignes existantes éventuelles.
_MISSING_COLUMNS = [
    (
        "password_hash",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    ),
    (
        "artist_name",
        sa.Column("artist_name", sa.String(length=100), nullable=True),
    ),
    (
        "bio",
        sa.Column("bio", sa.Text(), nullable=True),
    ),
    (
        "avatar_url",
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
    ),
    (
        "universe_description",
        sa.Column("universe_description", sa.Text(), nullable=True),
    ),
    (
        "brand_color",
        sa.Column("brand_color", sa.String(length=7), nullable=True),
    ),
    (
        "profile_public",
        sa.Column(
            "profile_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    ),
    (
        "language",
        sa.Column(
            "language",
            sa.String(length=2),
            nullable=False,
            server_default=sa.text("'en'"),
        ),
    ),
    (
        "credits_balance",
        sa.Column(
            "credits_balance",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("10"),
        ),
    ),
    (
        "credits_earned_total",
        sa.Column(
            "credits_earned_total",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    ),
    (
        "updated_at",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ),
]


def _existing_user_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns("users")}


def upgrade() -> None:
    existing = _existing_user_columns()

    for col_name, col_def in _MISSING_COLUMNS:
        if col_name in existing:
            continue
        op.add_column("users", col_def)


def downgrade() -> None:
    # Ordre inverse pour les drops. On ne drop que si la colonne existe.
    existing = _existing_user_columns()
    for col_name, _ in reversed(_MISSING_COLUMNS):
        if col_name in existing:
            op.drop_column("users", col_name)
