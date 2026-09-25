"""promo_non_retirable — fuite « Smyles offerts → argent réel » (Lot 3)

Revision ID: 0095_promo_non_retirable
Revises: 0094_user_activity_days
Create Date: 2026-09-24

Décision Tom (23/09) : la part d'une vente payée par l'acheteur en Smyles
PROMO (offerts) ne doit jamais devenir retirable chez le vendeur (ni chez
l'artiste d'origine en revente). Elle est créditée dans le bucket `promo` du
bénéficiaire (dépensable, non retirable) — le CHECK de somme A1.4
(achetes + gagnes + promo = credits_balance) n'est PAS touché.

Ajouts :
  1. `transactions.promo_paid` (INT, défaut 0) : part du montant payée par
     l'acheteur en Smyles promo — c'est l'AUDIT de la fuite, vente par vente.
     `transactions.promo_non_retirable` (INT, défaut 0) : part créditée en
     non retirable aux bénéficiaires (vendeur, et artiste d'origine en revente).
     CHECK 0 <= promo_non_retirable <= promo_paid <= credits_amount.
     Les deux colonnes rejoignent la liste des champs IMMUABLES du trigger
     append-only (0070).
  2. `users.smyles_promo_gagnes` (INT, défaut 0) : SOUS-ENSEMBLE de
     `smyles_promo` = Smyles gagnés en vente mais non retirables (affichage
     créateur « gagnés — non retirables »). Un trigger le borne à
     `smyles_promo` à chaque écriture (le promo se dépense en premier ; on
     considère que les Smyles OFFERTS partent avant les gains non retirables),
     + CHECK 0 <= smyles_promo_gagnes <= smyles_promo.

Sûreté : colonnes neuves à 0, contraintes trivialement vraies à la pose.
Rollback : restaure la fonction append-only de 0070, drop des ajouts.
"""
import sqlalchemy as sa
from alembic import op

revision = "0095_promo_non_retirable"
down_revision = "0094_user_activity_days"
branch_labels = None
depends_on = None

_FN_NEW = """
CREATE OR REPLACE FUNCTION transactions_append_only() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'transactions are append-only: DELETE forbidden (id=%)', OLD.id;
  END IF;
  -- UPDATE : status et completed_at peuvent changer librement.
  -- buyer_id / seller_id peuvent UNIQUEMENT passer à NULL (anonymisation RGPD :
  -- la FK users.id est en ON DELETE SET NULL → la suppression d'un compte nulle
  -- ces colonnes ; il faut l'autoriser). En revanche, les RÉASSIGNER à un autre
  -- utilisateur reste interdit, et tous les champs FINANCIERS sont immuables.
  IF NEW.id IS DISTINCT FROM OLD.id
     OR NEW.type IS DISTINCT FROM OLD.type
     OR (NEW.buyer_id IS DISTINCT FROM OLD.buyer_id AND NEW.buyer_id IS NOT NULL)
     OR (NEW.seller_id IS DISTINCT FROM OLD.seller_id AND NEW.seller_id IS NOT NULL)
     OR NEW.credits_amount IS DISTINCT FROM OLD.credits_amount
     OR NEW.platform_fee IS DISTINCT FROM OLD.platform_fee
     OR NEW.artist_revenue IS DISTINCT FROM OLD.artist_revenue
     OR NEW.external_reference IS DISTINCT FROM OLD.external_reference
     OR NEW.euro_amount_cents IS DISTINCT FROM OLD.euro_amount_cents
     OR NEW.metadata_json IS DISTINCT FROM OLD.metadata_json
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
     OR NEW.promo_paid IS DISTINCT FROM OLD.promo_paid
     OR NEW.promo_non_retirable IS DISTINCT FROM OLD.promo_non_retirable
  THEN
    RAISE EXCEPTION
      'transactions are immutable: only status/completed_at may change (id=%)', OLD.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_FN_OLD = """
CREATE OR REPLACE FUNCTION transactions_append_only() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'transactions are append-only: DELETE forbidden (id=%)', OLD.id;
  END IF;
  -- UPDATE : status et completed_at peuvent changer librement.
  -- buyer_id / seller_id peuvent UNIQUEMENT passer à NULL (anonymisation RGPD :
  -- la FK users.id est en ON DELETE SET NULL → la suppression d'un compte nulle
  -- ces colonnes ; il faut l'autoriser). En revanche, les RÉASSIGNER à un autre
  -- utilisateur reste interdit, et tous les champs FINANCIERS sont immuables.
  IF NEW.id IS DISTINCT FROM OLD.id
     OR NEW.type IS DISTINCT FROM OLD.type
     OR (NEW.buyer_id IS DISTINCT FROM OLD.buyer_id AND NEW.buyer_id IS NOT NULL)
     OR (NEW.seller_id IS DISTINCT FROM OLD.seller_id AND NEW.seller_id IS NOT NULL)
     OR NEW.credits_amount IS DISTINCT FROM OLD.credits_amount
     OR NEW.platform_fee IS DISTINCT FROM OLD.platform_fee
     OR NEW.artist_revenue IS DISTINCT FROM OLD.artist_revenue
     OR NEW.external_reference IS DISTINCT FROM OLD.external_reference
     OR NEW.euro_amount_cents IS DISTINCT FROM OLD.euro_amount_cents
     OR NEW.metadata_json IS DISTINCT FROM OLD.metadata_json
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
  THEN
    RAISE EXCEPTION
      'transactions are immutable: only status/completed_at may change (id=%)', OLD.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_FN_CLAMP = """
CREATE OR REPLACE FUNCTION clamp_smyles_promo_gagnes() RETURNS trigger AS $$
BEGIN
  IF NEW.smyles_promo_gagnes > NEW.smyles_promo THEN
    NEW.smyles_promo_gagnes := NEW.smyles_promo;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.add_column("transactions", sa.Column(
        "promo_paid", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("transactions", sa.Column(
        "promo_non_retirable", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint(
        "ck_transactions_promo_parts",
        "transactions",
        "promo_non_retirable >= 0 AND promo_non_retirable <= promo_paid "
        "AND promo_paid <= credits_amount",
    )
    op.execute(_FN_NEW)

    op.add_column("users", sa.Column(
        "smyles_promo_gagnes", sa.Integer(), nullable=False, server_default="0"))
    op.execute(_FN_CLAMP)
    op.execute(
        "CREATE TRIGGER trg_users_clamp_promo_gagnes BEFORE INSERT OR UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION clamp_smyles_promo_gagnes()"
    )
    op.create_check_constraint(
        "ck_users_smyles_promo_gagnes_subset",
        "users",
        "smyles_promo_gagnes >= 0 AND smyles_promo_gagnes <= smyles_promo",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_smyles_promo_gagnes_subset", "users", type_="check")
    op.execute("DROP TRIGGER IF EXISTS trg_users_clamp_promo_gagnes ON users")
    op.execute("DROP FUNCTION IF EXISTS clamp_smyles_promo_gagnes()")
    op.drop_column("users", "smyles_promo_gagnes")
    op.execute(_FN_OLD)
    op.drop_constraint("ck_transactions_promo_parts", "transactions", type_="check")
    op.drop_column("transactions", "promo_non_retirable")
    op.drop_column("transactions", "promo_paid")
