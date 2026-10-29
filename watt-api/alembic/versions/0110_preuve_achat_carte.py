"""preuve_achat_carte — preuve complète de renonciation et déclaration de majorité

Revision ID: 0110_preuve_achat_carte
Revises: 0109_lot_j_outils_titres
Create Date: 2026-10-29

Lot L (paiement sûr) : pour chaque session de paiement Stripe, on garde en
plus de l'horodatage (consent_immediate_at) :
  - l'empreinte SHA-256 du texte de renonciation affiché sur la page Stripe ;
  - la version des CGU/CGV en vigueur au moment de l'achat ;
  - la déclaration « J'ai 18 ans ou plus ».
Colonnes ajoutées vides (NULL) pour les paiements existants : aucun impact.

Rollback : suppression des trois colonnes.
"""
import sqlalchemy as sa
from alembic import op

revision = "0110_preuve_achat_carte"
down_revision = "0109_lot_j_outils_titres"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stripe_payments", sa.Column("consent_text_sha256", sa.String(64), nullable=True))
    op.add_column("stripe_payments", sa.Column("cgu_version", sa.String(32), nullable=True))
    op.add_column("stripe_payments", sa.Column("majeur_declare", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("stripe_payments", "majeur_declare")
    op.drop_column("stripe_payments", "cgu_version")
    op.drop_column("stripe_payments", "consent_text_sha256")
