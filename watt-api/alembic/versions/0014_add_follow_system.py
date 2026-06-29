"""add follow system + profile_public flag

Revision ID: 0014_add_follow_system
Revises: 0013_add_prompt_lyrics
Create Date: 2026-04-19

Chantier 1 — Profils artistes publics + Réseau Créatif WATT.

Deux changements structurants :

1. Table `user_follows` (many-to-many auto-référentielle sur users)
   - un follower suit un followee
   - paire (follower_id, followee_id) unique
   - CHECK SQL interdit l'auto-follow (follower != followee)
   - ON DELETE CASCADE sur les deux FK : si un compte est supprimé,
     toutes ses arêtes sortantes ET entrantes disparaissent

2. Colonne `users.profile_public` (bool, default FALSE)
   - gatekeeping de la visibilité publique
   - passera à TRUE via endpoint `POST /me/profile/publish` (wattboard)
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0014_add_follow_system"
down_revision = "0013_add_prompt_lyrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Colonne profile_public sur users ─────────────────────────────
    op.add_column(
        "users",
        sa.Column(
            "profile_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # ── 2. Table user_follows ───────────────────────────────────────────
    op.create_table(
        "user_follows",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "follower_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "followee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "follower_id", "followee_id", name="uq_user_follow_pair"
        ),
        sa.CheckConstraint(
            "follower_id <> followee_id", name="ck_user_follow_no_self"
        ),
    )


def downgrade() -> None:
    op.drop_table("user_follows")
    op.drop_column("users", "profile_public")
