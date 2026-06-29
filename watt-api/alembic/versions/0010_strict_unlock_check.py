"""tighten transactions check: strict equality for unlock/resale

Revision ID: 0010_strict_unlock_check
Revises: 0009_add_marketplace
Create Date: 2026-04-18

Phase 9.5 — Filet DB pour le système financier critique.

Avant cette migration :
  CHECK (artist_revenue + platform_fee <= credits_amount)

  Trop large : pour les UNLOCK (et bientôt les RESALE Phase 10), on veut
  garantir l'égalité STRICTE — sinon on peut créer une transaction qui
  "perd" des crédits sans trace, et l'invariant de conservation casse.

Après cette migration :
  CHECK conditionnel par type :
    - type IN ('unlock', 'resale')  →  artist_revenue + platform_fee = credits_amount
    - sinon                          →  artist_revenue + platform_fee <= credits_amount

  GRANT/BONUS/CREDIT_PURCHASE/EARNING/REFUND : split = 0 / 0 → l'inégalité
  large reste vraie (0 + 0 <= amount) et c'est ce qu'on veut, parce qu'il
  n'y a pas de notion de "seller" sur ces types.

Pourquoi ajouter 'resale' à l'enum DÈS Phase 9.5 alors que la feature
arrive en Phase 10 ?
  PostgreSQL refuse `type IN ('unlock', 'resale')` au moment du CREATE
  CONSTRAINT si 'resale' n'est pas une valeur valide du PG ENUM (cast
  literal → enum impossible). On l'ajoute donc maintenant, dormant. Aucun
  code Python ne crée de transactions 'resale' avant Phase 10.

Note PostgreSQL : ALTER TYPE ... ADD VALUE ne peut PAS être utilisé dans
la même transaction que les commandes qui réfèrent à la nouvelle valeur
(restriction documentée). On wrap donc le ALTER TYPE dans un
autocommit_block(), puis on sort pour faire le DROP/CREATE des CHECK.

Downgrade : on ne peut PAS retirer une valeur d'un enum PostgreSQL
(limitation connue, sans `DROP VALUE`). Le downgrade restaure seulement
l'ancienne contrainte permissive et laisse 'resale' dans l'enum. C'est un
no-op de sécurité tant qu'aucune row ne l'utilise.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0010_strict_unlock_check"
down_revision = "0009_add_marketplace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Ajout de 'resale' à l'enum transaction_type
    #    Doit être committé AVANT que la nouvelle CHECK l'utilise
    #    → autocommit_block obligatoire (PostgreSQL).
    # ------------------------------------------------------------------
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'resale'"
        )

    # ------------------------------------------------------------------
    # 2. DROP l'ancienne contrainte permissive (<=)
    # ------------------------------------------------------------------
    op.drop_constraint(
        "ck_transactions_split_within_amount",
        "transactions",
        type_="check",
    )

    # ------------------------------------------------------------------
    # 3. CREATE la contrainte conditionnelle :
    #    - UNLOCK / RESALE : split STRICTEMENT égal à credits_amount
    #    - autres types    : split <= credits_amount (split = 0 OK)
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_transactions_split_within_amount",
        "transactions",
        "(type IN ('unlock', 'resale') "
        " AND artist_revenue + platform_fee = credits_amount) "
        "OR "
        "(type NOT IN ('unlock', 'resale') "
        " AND artist_revenue + platform_fee <= credits_amount)",
    )


def downgrade() -> None:
    # Restore le CHECK <= permissif. NOTE : on ne peut PAS retirer la
    # valeur 'resale' d'un PG ENUM (limitation PostgreSQL, pas de
    # DROP VALUE). Elle reste dormante dans l'enum, sans impact tant
    # qu'aucune row ne l'utilise.
    op.drop_constraint(
        "ck_transactions_split_within_amount",
        "transactions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_transactions_split_within_amount",
        "transactions",
        "artist_revenue + platform_fee <= credits_amount",
    )
