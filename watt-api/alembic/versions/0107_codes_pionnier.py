"""codes_pionnier — accès Pionnier sur invitation + anti-comptes multiples

Revision ID: 0107_codes_pionnier
Revises: 0106_remise_oeuvre
Create Date: 2026-10-15

1. `pioneer_codes` : codes d'invitation à usage unique, générés par l'admin et
   envoyés en message privé. En direct, le rang Pionnier n'est attribué qu'à
   un compte qui a utilisé un code (réglage PIONEER_CODE_REQUIRED).
2. `users.email_canonical` : forme « canonique » de l'email (sans +alias, et
   sans points pour Gmail), pour refuser `tom+1@gmail.com` quand
   `tom@gmail.com` existe déjà. Index NON unique : les comptes déjà en double
   ne bloquent pas la migration ; seule l'inscription refuse les doublons.
3. `users.ia_rights_confirmed_at` : date à laquelle le créateur a confirmé
   détenir les droits commerciaux de ses contenus générés par IA.

Rollback : suppression de la table et des colonnes.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0107_codes_pionnier"
down_revision = "0106_remise_oeuvre"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pioneer_codes",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("note", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("used_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Un compte n'utilise qu'un seul code.
    op.create_index("uq_pioneer_codes_used_by", "pioneer_codes", ["used_by"],
                    unique=True, postgresql_where=sa.text("used_by IS NOT NULL"))

    op.add_column("users", sa.Column("email_canonical", sa.String(320), nullable=True))
    op.add_column("users", sa.Column("ia_rights_confirmed_at",
                                     sa.DateTime(timezone=True), nullable=True))
    # Remplissage : même règle que app/core/emails_canoniques.py.
    op.execute(
        """
        UPDATE users SET email_canonical = CASE
          WHEN split_part(email, '@', 2) IN ('gmail.com', 'googlemail.com') THEN
            replace(split_part(split_part(email, '@', 1), '+', 1), '.', '') || '@gmail.com'
          ELSE
            split_part(split_part(email, '@', 1), '+', 1) || '@' || split_part(email, '@', 2)
        END
        WHERE email LIKE '%@%' AND email NOT LIKE '%@deleted.watt'
        """
    )
    op.create_index("ix_users_email_canonical", "users", ["email_canonical"])


def downgrade() -> None:
    op.drop_index("ix_users_email_canonical", table_name="users")
    op.drop_column("users", "ia_rights_confirmed_at")
    op.drop_column("users", "email_canonical")
    op.drop_index("uq_pioneer_codes_used_by", table_name="pioneer_codes")
    op.drop_table("pioneer_codes")
