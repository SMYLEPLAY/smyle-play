"""platform_reserve — registre de la réserve € segmentée (A3)

Revision ID: 0074_platform_reserve
Revises: 0073_gagnes_bloque
Create Date: 2026-06-29

A3 du moteur économique. Table `platform_reserve` : la réserve en euros (cents)
segmentée en 4 poches étiquetées (doctrine éco) — on sait toujours où est
chaque euro :
  - payout : adosse la dette encaissable (gagnés × taux)
  - tax    : provision TVA / impôts
  - refund : provision remboursements / chargebacks
  - cash   : trésorerie opérationnelle (jamais mêlée aux 3 autres)

Une ligne par poche, montant en cents (BigInteger, CHECK >= 0). Seedée à 0.
Le crédit réel (achat de pack → payout) viendra avec Stripe (Phase B). Ici =
structure + calcul de l'invariant réserve ≥ dette + provisions.

Rollback : drop de la table.
"""
import sqlalchemy as sa
from alembic import op


revision = "0074_platform_reserve"
down_revision = "0073_gagnes_bloque"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_reserve",
        sa.Column("poche", sa.String(16), primary_key=True),
        sa.Column(
            "amount_cents", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.CheckConstraint("amount_cents >= 0", name="ck_platform_reserve_nonneg"),
    )
    op.execute(
        "INSERT INTO platform_reserve (poche, amount_cents) VALUES "
        "('payout', 0), ('tax', 0), ('refund', 0), ('cash', 0)"
    )


def downgrade() -> None:
    op.drop_table("platform_reserve")
