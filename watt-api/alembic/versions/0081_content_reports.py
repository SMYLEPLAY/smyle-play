"""content_reports — signalement DSA (D3 Confiance, 07/07)

Revision ID: 0081_content_reports
Revises: 0080_adn_offers_reserve
Create Date: 2026-07-07

Table des signalements de contenu (DSA art. 16) : anonyme autorisé
(reporter_id nullable + reporter_email facultatif pour l'accusé),
cycle new → reviewed → actioned | rejected, cible en String extensible.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0081_content_reports"
down_revision = "0080_adn_offers_reserve"
branch_labels = None
depends_on = None

_REASONS = (
    "contenu_illegal", "contrefacon", "haine_violence",
    "nudite", "spam_arnaque", "autre",
)
_STATUSES = ("new", "reviewed", "actioned", "rejected")


def upgrade() -> None:
    # FIX déploiement 07/07 : on crée les types UNE seule fois (checkfirst),
    # puis create_type=False dans les colonnes — sinon create_table ré-émet
    # CREATE TYPE sans checkfirst → DuplicateObjectError (deploy KO en boucle).
    from sqlalchemy.dialects import postgresql as pg

    pg.ENUM(*_REASONS, name="report_reason").create(
        op.get_bind(), checkfirst=True
    )
    pg.ENUM(*_STATUSES, name="report_status").create(
        op.get_bind(), checkfirst=True
    )
    report_reason = pg.ENUM(*_REASONS, name="report_reason", create_type=False)
    report_status = pg.ENUM(*_STATUSES, name="report_status", create_type=False)

    op.create_table(
        "content_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reporter_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("reporter_email", sa.String(320), nullable=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("reason", report_reason, nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "status", report_status, nullable=False, server_default="new"
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "reporter_id IS NOT NULL OR reporter_email IS NOT NULL "
            "OR detail IS NOT NULL",
            name="ck_content_reports_not_empty",
        ),
    )
    op.create_index("ix_content_reports_reporter_id", "content_reports", ["reporter_id"])
    op.create_index("ix_content_reports_target_type", "content_reports", ["target_type"])
    op.create_index("ix_content_reports_target_id", "content_reports", ["target_id"])
    op.create_index("ix_content_reports_status", "content_reports", ["status"])


def downgrade() -> None:
    op.drop_table("content_reports")
    sa.Enum(name="report_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="report_reason").drop(op.get_bind(), checkfirst=True)
