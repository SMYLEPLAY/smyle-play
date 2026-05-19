"""0037 — tables notifications, message_threads, messages, trade_offers

Revision ID: 0037_notifications_messages_trades
Revises: 0036_owned_playlist_adns
Create Date: 2026-05-19

Phase C — Messagerie + Notifications + Trading.

3 nouvelles tables :
  - notifications   : centre de notifs catégorisées (6 types visuels)
  - message_threads : conversations 1:1 entre users (1 thread par paire)
  - messages        : messages texte dans un thread
  - trade_offers    : offres d'échange de prompts/ADN entre créateurs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0037_notifications_messages_trades"
down_revision = "0036_owned_playlist_adns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. NOTIFICATIONS ─────────────────────────────────────────────────────
    # Types : purchase (💸), like (❤️), follow (👤), message (✉️),
    #         trade (🔄), system (⚙️)
    # Utilise DO $$ BEGIN ... EXCEPTION pour être idempotent (migration partielle possible)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE notification_type AS ENUM (
                'purchase', 'like', 'follow', 'message', 'trade', 'system'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type notification_type NOT NULL,
            actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
            target_type VARCHAR(30),
            target_id UUID,
            metadata_json JSONB,
            read_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
        ON notifications (user_id, created_at)
        WHERE read_at IS NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_user_created
        ON notifications (user_id, created_at)
    """)

    # ── 2. MESSAGE THREADS ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS message_threads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            participant_a UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            participant_b UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            last_message_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_message_threads_pair UNIQUE (participant_a, participant_b),
            CONSTRAINT ck_message_threads_no_self CHECK (participant_a != participant_b)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_message_threads_a ON message_threads (participant_a)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_message_threads_b ON message_threads (participant_b)")

    # ── 3. MESSAGES ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL REFERENCES message_threads(id) ON DELETE CASCADE,
            sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            read_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_messages_content_nonempty CHECK (length(trim(content)) > 0)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_thread_created ON messages (thread_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages (sender_id)")

    # ── 4. TRADE OFFERS ──────────────────────────────────────────────────────
    # Trade entre créateurs uniquement — chacun cède l'accès à sa propre création.
    # Pas de resale (pas de current_owner_id swap) — on crée simplement
    # un UnlockedPrompt pour chaque side lors de l'acceptation.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE trade_status AS ENUM (
                'pending', 'accepted', 'rejected', 'cancelled', 'expired'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS trade_offers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            receiver_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            offered_prompt_id UUID REFERENCES prompts(id) ON DELETE SET NULL,
            requested_prompt_id UUID REFERENCES prompts(id) ON DELETE SET NULL,
            credit_supplement INTEGER NOT NULL DEFAULT 0,
            status trade_status NOT NULL DEFAULT 'pending',
            message TEXT,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ,
            offered_price_at_trade INTEGER,
            requested_price_at_trade INTEGER,
            CONSTRAINT ck_trade_offers_no_self CHECK (sender_id != receiver_id),
            CONSTRAINT ck_trade_offers_supplement_nonneg CHECK (credit_supplement >= 0)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_trade_offers_sender ON trade_offers (sender_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trade_offers_receiver ON trade_offers (receiver_id, status)")


def downgrade() -> None:
    op.drop_table("trade_offers")
    op.execute("DROP TYPE IF EXISTS trade_status")
    op.drop_table("messages")
    op.drop_table("message_threads")
    op.drop_table("notifications")
    op.execute("DROP TYPE IF EXISTS notification_type")
