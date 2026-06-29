"""0042 — parrainage (mécanique 1)

Revision ID: 0042_referrals
Revises: 0041_vocal_genders
Create Date: 2026-06-07

Ajoute :
  1. users.referral_code (code de parrainage unique, partageable).
     Backfillé pour les comptes existants puis indexé unique.
  2. table referrals (lien parrain → filleul, statut + récompense snapshotée).

Barème figé (ancré sur l'économie réelle : 1 Smyle ≈ 0,70 €, bonus de
bienvenue = 10 Smyles) : 10 Smyles par côté, versés à la 1ère vraie action
du filleul (1er son posté OU 1er achat). Voir [[2026-06-07]].
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042_referrals"
down_revision = "0041_vocal_genders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Colonne referral_code — nullable d'abord (le temps du backfill).
    op.add_column(
        "users",
        sa.Column("referral_code", sa.String(length=12), nullable=True),
    )

    # 2. Backfill : un code unique par compte existant.
    #    8 caractères hex majuscules dérivés de l'id + aléa → collision
    #    négligeable, et l'index unique ci-dessous garantit l'unicité.
    op.execute(
        """
        UPDATE users
        SET referral_code = upper(
            substr(md5(random()::text || id::text || clock_timestamp()::text), 1, 8)
        )
        WHERE referral_code IS NULL
        """
    )

    # 3. Index unique (après backfill pour éviter tout conflit transitoire).
    op.create_index(
        "ix_users_referral_code",
        "users",
        ["referral_code"],
        unique=True,
    )

    # 4. Table referrals.
    op.create_table(
        "referrals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "referrer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "referred_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "status",
            sa.String(length=8),
            nullable=False,
            server_default="pending",
            index=True,
        ),
        sa.Column(
            "reward_credits",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "rewarded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "referrer_id != referred_id", name="ck_referrals_no_self"
        ),
        sa.CheckConstraint(
            "reward_credits > 0", name="ck_referrals_reward_positive"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'rewarded')", name="ck_referrals_status_enum"
        ),
    )


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_column("users", "referral_code")
