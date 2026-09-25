"""admin_restauration_paiements — outils admin + sécurité du paiement (Étape 2)

Revision ID: 0098_admin_restauration
Revises: 0097_stripe_payments
Create Date: 2026-09-25

1. `admin_journal` : journal des actions d'administration (retrait d'un
   contenu, restauration, déblocage d'un compte…) — qui, quoi, motif, quand,
   état avant. Append-only par usage (aucune route de modification).

2. Restauration d'un contenu retiré : SEUL un chemin admin explicite peut
   lever la marque `taken_down_at`. Les triggers de 0092 sont renforcés :
   effacer `taken_down_at` lève une erreur, sauf si la transaction a posé
   `SET LOCAL watt.restauration = 'on'` — ce que fait uniquement le service
   de restauration (qui journalise dans la même transaction). Ainsi aucun
   code (PATCH créateur, script, erreur) ne peut « dé-retirer » un contenu
   par accident, et toute restauration laisse une trace.

3. Achat par carte : `users.achat_carte_bloque_at` / `achat_carte_bloque_motif`
   — compte bloqué pour les achats par carte (remboursement ou litige alors
   que les Smyles étaient déjà dépensés). Débloquable par l'admin.

4. `stripe_payments.mode_test` : paiement fait avec une clé Stripe de TEST.
   Les Smyles crédités ainsi sont marqués (registre) et exclus des chiffres.

Rollback : triggers de 0092 restaurés, ajouts supprimés.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0098_admin_restauration"
down_revision = "0097_stripe_payments"
branch_labels = None
depends_on = None

_GARDE = """
    IF TG_OP = 'UPDATE' AND OLD.taken_down_at IS NOT NULL AND NEW.taken_down_at IS NULL
       AND current_setting('watt.restauration', true) IS DISTINCT FROM 'on' THEN
        RAISE EXCEPTION 'restauration d''un contenu retiré : passer par la restauration admin';
    END IF;
"""

_FN_PUBLISHED_NEW = """
CREATE OR REPLACE FUNCTION keep_taken_down_unpublished() RETURNS trigger AS $$
BEGIN
""" + _GARDE + """
    IF NEW.taken_down_at IS NOT NULL THEN
        NEW.is_published := FALSE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_FN_DELETED_NEW = """
CREATE OR REPLACE FUNCTION keep_taken_down_deleted() RETURNS trigger AS $$
BEGIN
""" + _GARDE + """
    IF NEW.taken_down_at IS NOT NULL THEN
        NEW.is_deleted := TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_FN_PUBLISHED_OLD = """
CREATE OR REPLACE FUNCTION keep_taken_down_unpublished() RETURNS trigger AS $$
BEGIN
    IF NEW.taken_down_at IS NOT NULL THEN
        NEW.is_published := FALSE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_FN_DELETED_OLD = """
CREATE OR REPLACE FUNCTION keep_taken_down_deleted() RETURNS trigger AS $$
BEGIN
    IF NEW.taken_down_at IS NOT NULL THEN
        NEW.is_deleted := TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "admin_journal",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("admin_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(40), nullable=False, index=True),
        sa.Column("cible_type", sa.String(20), nullable=False),
        sa.Column("cible_id", sa.String(64), nullable=False, index=True),
        sa.Column("motif", sa.Text(), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.execute(_FN_PUBLISHED_NEW)
    op.execute(_FN_DELETED_NEW)
    op.add_column("users", sa.Column("achat_carte_bloque_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("achat_carte_bloque_motif", sa.Text(), nullable=True))
    op.add_column("stripe_payments", sa.Column(
        "mode_test", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("stripe_payments", "mode_test")
    op.drop_column("users", "achat_carte_bloque_motif")
    op.drop_column("users", "achat_carte_bloque_at")
    op.execute(_FN_DELETED_OLD)
    op.execute(_FN_PUBLISHED_OLD)
    op.drop_table("admin_journal")
