"""treasury_account — compte trésorerie société (Brique 1)

Revision ID: 0089_treasury_account
Revises: 0088_buckets_invariant_check
Create Date: 2026-09-20

Brique 1 : la commission plateforme doit atterrir sur un compte société au lieu
de disparaître de la circulation. Ce compte est VOLONTAIREMENT distinct du profil
vitrine « Smyle » (`is_official`, migration 0022) : on ne mélange pas une identité
artiste publique et la trésorerie de la société (décision Tom 20/09).

Ce que pose cette migration :
  - `users.is_treasury` : booléen NOT NULL DEFAULT false ;
  - un index UNIQUE PARTIEL sur `is_treasury = TRUE` → au plus UN compte
    trésorerie, et sa résolution est indexée (même patron que
    `ix_users_is_official_true`) ;
  - le compte lui-même, seedé de façon idempotente (`ON CONFLICT (email)`).

Résolution du compte (IMPORTANT) : son `id` est un UUID généré à la migration,
donc DIFFÉRENT dans chaque environnement (prod ≠ staging ≠ test). Aucun UUID en
dur nulle part : le code le résout par `WHERE is_treasury = TRUE`
(cf. `app/services/treasury.py::treasury_user_id`). Même piège que le compte
`is_official`, tranché de la même manière.

Profil du compte :
  - `profile_public = FALSE` → jamais listé, jamais affiché ;
  - `password_hash = NULL` → aucune connexion possible (aucun mot de passe ne
    peut correspondre) ; le compte n'est pas un utilisateur, c'est un registre ;
  - soldes et buckets à 0 → l'invariant A1.4
    (`achetes + gagnes + promo = credits_balance`) est satisfait dès le seed.

Invariant respecté : cette migration N'AJOUTE AUCUN bucket et ne touche PAS au
CHECK de somme déployé en 0088 (option (b) retenue : la commission ira dans le
bucket `achetes`, non retirable, du compte trésorerie).

Rollback : suppression du compte, de l'index et de la colonne.
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0089_treasury_account"
down_revision = "0088_buckets_invariant_check"
branch_labels = None
depends_on = None


TREASURY_EMAIL = "tresorerie@smyleplay.com"
TREASURY_ARTIST_NAME = "Tresorerie WATT"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_treasury",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Au plus UN compte trésorerie ; résolution indexée.
    op.create_index(
        "ix_users_is_treasury_true",
        "users",
        ["is_treasury"],
        unique=True,
        postgresql_where=sa.text("is_treasury = TRUE"),
    )

    # Seed idempotent. Soldes/buckets laissés aux server_default (0) → somme
    # des buckets == credits_balance == 0, CHECK A1.4 satisfait.
    op.execute(
        sa.text(
            """
            INSERT INTO users (id, email, artist_name, profile_public, is_treasury)
            VALUES (:id, :email, :artist_name, FALSE, TRUE)
            ON CONFLICT (email) DO NOTHING
            """
        ).bindparams(
            id=uuid.uuid4(),
            email=TREASURY_EMAIL,
            artist_name=TREASURY_ARTIST_NAME,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM users WHERE email = :email").bindparams(
            email=TREASURY_EMAIL
        )
    )
    op.drop_index("ix_users_is_treasury_true", table_name="users")
    op.drop_column("users", "is_treasury")
