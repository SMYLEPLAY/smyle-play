"""ledger_append_only — invariants comptables du ledger (A0)

Revision ID: 0070_ledger_append_only
Revises: 0069_user_tier
Create Date: 2026-06-26

A0 de la doctrine économique : le ledger `transactions` devient APPEND-ONLY et
les écritures financières IMMUABLES, appliqué AU NIVEAU DB (pas seulement dans
le code applicatif, qui peut être contourné).

Garanties posées ici :
  - DELETE sur `transactions` → INTERDIT (append-only). Toute correction se fait
    par une écriture inverse (contre-passation), jamais par suppression.
  - UPDATE → `status` et `completed_at` changent librement (cycle de vie
    PENDING→COMPLETED/FAILED/ROLLED_BACK). `buyer_id`/`seller_id` peuvent
    UNIQUEMENT passer à NULL (anonymisation RGPD via FK ON DELETE SET NULL).
    Tout changement d'un champ FINANCIER (type, montants, split, euro,
    métadonnées, clé d'idempotence, created_at, id) → INTERDIT, et réassigner
    buyer/seller à un AUTRE utilisateur → INTERDIT.
  - Idempotence : colonne `idempotency_key` (nullable) avec index UNIQUE partiel
    → un rejeu portant la même clé ne peut pas créer une seconde écriture.

Audit 2026-06-26 : aucun code ne DELETE de transaction ; la seule mutation
existante est `status`/`completed_at` → le trigger ne casse aucun flux.

(L'invariant « somme des buckets = credits_balance » viendra avec A1, quand les
sous-soldes existeront. Le « aucun solde négatif » est déjà garanti par
ck_users_credits_balance_nonneg.)

Rollback : drop des triggers + fonction + index + colonne.
"""
import sqlalchemy as sa
from alembic import op


revision = "0070_ledger_append_only"
down_revision = "0069_user_tier"
branch_labels = None
depends_on = None


_TRIGGER_FN = """
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


def upgrade() -> None:
    # 1. Clé d'idempotence (nullable, unique là où renseignée).
    op.add_column(
        "transactions",
        sa.Column("idempotency_key", sa.String(255), nullable=True),
    )
    op.create_index(
        "uq_transactions_idempotency_key",
        "transactions",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # 2. Fonction + triggers append-only / immutabilité.
    op.execute(_TRIGGER_FN)
    op.execute(
        "CREATE TRIGGER trg_transactions_no_delete "
        "BEFORE DELETE ON transactions "
        "FOR EACH ROW EXECUTE FUNCTION transactions_append_only();"
    )
    op.execute(
        "CREATE TRIGGER trg_transactions_immutable "
        "BEFORE UPDATE ON transactions "
        "FOR EACH ROW EXECUTE FUNCTION transactions_append_only();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_transactions_immutable ON transactions;")
    op.execute("DROP TRIGGER IF EXISTS trg_transactions_no_delete ON transactions;")
    op.execute("DROP FUNCTION IF EXISTS transactions_append_only();")
    op.drop_index("uq_transactions_idempotency_key", table_name="transactions")
    op.drop_column("transactions", "idempotency_key")
