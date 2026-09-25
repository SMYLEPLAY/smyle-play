"""stripe_payments — achat de Smyles par carte (Brique 5, Lot 3)

Revision ID: 0097_stripe_payments
Revises: 0096_trophees_sans_recompense
Create Date: 2026-09-24

Deux tables, sans aucune donnée de carte (Stripe Checkout les garde) :

  - `stripe_payments` : une ligne par session Checkout créée. Porte le pack,
    le montant, la PREUVE de la renonciation au droit de rétractation
    (`consent_immediate_at`, obligatoire), le lien vers l'écriture de crédit
    au ledger, et le suivi des remboursements / litiges : Smyles repris
    (`smyles_recovered`), manque non récupérable (`shortfall`) et signalement
    à l'admin (`flagged_at`).
  - `stripe_events` : identifiants d'événements Stripe déjà traités
    (idempotence du webhook, en plus de la clé d'idempotence du ledger).

`user_id` en ON DELETE SET NULL : un paiement est une pièce comptable, il
survit à la suppression du compte.
Rollback : drop des deux tables.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0097_stripe_payments"
down_revision = "0096_trophees_sans_recompense"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stripe_payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("session_id", sa.String(255), nullable=False, unique=True),
        sa.Column("payment_intent", sa.String(255), nullable=True, index=True),
        sa.Column("pack_id", sa.String(32), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="eur"),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("consent_immediate_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("credited_tx_id", UUID(as_uuid=True),
                  sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("smyles_recovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shortfall", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("credits > 0 AND amount_cents > 0", name="ck_stripe_payments_positive"),
        sa.CheckConstraint(
            "smyles_recovered >= 0 AND shortfall >= 0 AND smyles_recovered + shortfall <= credits",
            name="ck_stripe_payments_recovery",
        ),
    )
    op.create_table(
        "stripe_events",
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("stripe_events")
    op.drop_table("stripe_payments")
