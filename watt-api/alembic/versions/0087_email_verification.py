"""email_verification — colonne users.email_verified + table des jetons

Revision ID: 0087_email_verification
Revises: 0086_transaction_type_burn
Create Date: 2026-09-11

Phase A (ouverture gratuite) — vérification d'email NON bloquante par défaut.

Deux objets, une seule migration de feature (même modèle que 0082 qui ajoutait
`is_banned` + colonnes de traçabilité en une fois) :

  1. `users.email_verified` : booléen NOT NULL, server_default 'false'. Les
     comptes existants (bêta interne) restent donc à `false` sans être
     enfermés dehors — le login ne bloque QUE si REQUIRE_EMAIL_VERIFIED=true
     (défaut False, cf. app/config.py + app/routers/auth.py).

  2. `email_verification_tokens` : même robustesse que le reset MDP
     (`password_reset_tokens`, 0-init) — on stocke le SHA-256 du jeton, jamais
     le jeton en clair ; expiration + usage unique (`used_at`). Un nouvel
     envoi invalide le précédent (fait côté service).

Colonnes/table simples (bool / uuid / timestamp / varchar) — aucun type enum,
aucun piège CREATE TYPE, aucune donnée existante touchée.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0087_email_verification"
down_revision = "0086_transaction_type_burn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # SHA-256 hex du jeton (64 chars) — jamais le jeton lui-même.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_evt_token_hash", "email_verification_tokens", ["token_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_evt_token_hash", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "email_verified")
