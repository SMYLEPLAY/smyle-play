"""phase 7 and 8 sync

Revision ID: b2fe0db4906d
Revises: 4856b7981481
Create Date: 2026-04-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2fe0db4906d'
down_revision: Union[str, None] = '4856b7981481'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create transactions table
    op.create_table(
        'transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'type',
            sa.Enum(
                'unlock', 'credit_purchase', 'earning', 'refund', 'bonus', 'grant',
                name='transaction_type'
            ),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'pending', 'completed', 'failed', 'rolled_back',
                name='transaction_status'
            ),
            nullable=False,
        ),
        sa.Column('buyer_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('seller_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('credits_amount', sa.Integer(), nullable=False),
        sa.Column('platform_fee', sa.Integer(), nullable=False),
        sa.Column('artist_revenue', sa.Integer(), nullable=False),
        sa.Column('external_reference', sa.String(length=255), nullable=True),
        sa.Column('euro_amount_cents', sa.Integer(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('credits_amount >= 0', name='ck_transactions_credits_amount_nonneg'),
        sa.CheckConstraint('platform_fee >= 0', name='ck_transactions_platform_fee_nonneg'),
        sa.CheckConstraint('artist_revenue >= 0', name='ck_transactions_artist_revenue_nonneg'),
        sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['seller_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_transactions_buyer_id', 'transactions', ['buyer_id'])
    op.create_index('ix_transactions_seller_id', 'transactions', ['seller_id'])

    # Trigger: prevent mutation of finalized transactions
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_transaction_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
          IF OLD.status = 'pending' AND NEW.status IN ('completed', 'failed', 'rolled_back') THEN
            IF (NEW.id != OLD.id OR
                NEW.type != OLD.type OR
                NEW.credits_amount != OLD.credits_amount OR
                NEW.platform_fee != OLD.platform_fee OR
                NEW.artist_revenue != OLD.artist_revenue) THEN
              RAISE EXCEPTION 'Transactions are immutable: only status transitions from pending are allowed';
            END IF;
            RETURN NEW;
          END IF;
          IF (NEW.id = OLD.id AND
              NEW.type = OLD.type AND
              NEW.status = OLD.status AND
              NEW.credits_amount = OLD.credits_amount AND
              NEW.platform_fee = OLD.platform_fee AND
              NEW.artist_revenue = OLD.artist_revenue AND
              NEW.external_reference IS NOT DISTINCT FROM OLD.external_reference AND
              NEW.euro_amount_cents IS NOT DISTINCT FROM OLD.euro_amount_cents AND
              NEW.metadata_json IS NOT DISTINCT FROM OLD.metadata_json AND
              NEW.created_at = OLD.created_at AND
              NEW.completed_at IS NOT DISTINCT FROM OLD.completed_at) THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'Transactions are immutable once finalized';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER enforce_transaction_immutability
          BEFORE UPDATE ON transactions
          FOR EACH ROW EXECUTE FUNCTION prevent_transaction_mutation();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_transaction_delete()
        RETURNS TRIGGER AS $$
        BEGIN
          RAISE EXCEPTION 'Transactions cannot be deleted';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER enforce_transaction_no_delete
          BEFORE DELETE ON transactions
          FOR EACH ROW EXECUTE FUNCTION prevent_transaction_delete();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS enforce_transaction_no_delete ON transactions")
    op.execute("DROP TRIGGER IF EXISTS enforce_transaction_immutability ON transactions")
    op.execute("DROP FUNCTION IF EXISTS prevent_transaction_delete()")
    op.execute("DROP FUNCTION IF EXISTS prevent_transaction_mutation()")
    op.drop_index('ix_transactions_seller_id', table_name='transactions')
    op.drop_index('ix_transactions_buyer_id', table_name='transactions')
    op.drop_table('transactions')
    op.execute("DROP TYPE IF EXISTS transaction_status")
    op.execute("DROP TYPE IF EXISTS transaction_type")
