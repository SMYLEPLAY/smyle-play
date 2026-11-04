"""retractation_vendeur_pro — fonction de rétractation en ligne + statut vendeur

Revision ID: 0111_retractation_vendeur_pro
Revises: 0110_preuve_achat_carte
Create Date: 2026-11-04

1. Fonction de rétractation en ligne (art. L221-21 et D221-5 du Code de la
   consommation, en vigueur depuis le 19/06/2026) : table `retractations`
   qui garde chaque déclaration (nom et prénom, achat visé, email de
   l'accusé de réception), horodatée.
2. Statut du vendeur (art. L111-7 II du Code de la consommation) :
   `users.vendeur_pro`, faux par défaut (particulier). Le créateur qui vend
   à titre professionnel coche la case dans son WATT BOARD ; le statut est
   affiché avant chaque achat.

Rollback : suppression de la table et de la colonne.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0111_retractation_vendeur_pro"
down_revision = "0110_preuve_achat_carte"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("vendeur_pro", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "retractations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("nom_prenom", sa.String(120), nullable=False),
        sa.Column("contrat", sa.String(500), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="recue"),
        sa.Column("ar_envoye", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_retractations_created_at", "retractations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_retractations_created_at", table_name="retractations")
    op.drop_table("retractations")
    op.drop_column("users", "vendeur_pro")
