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
    op.execute("""
        CREATE TYPE notification_type AS ENUM (
            'purchase', 'like', 'follow', 'message', 'trade', 'system'
        )
    """)

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("type", sa.Enum(
            "purchase", "like", "follow", "message", "trade", "system",
            name="notification_type", create_type=False,
        ), nullable=False),
        # actor = qui a déclenché la notif (peut être null si système)
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        # target = entité concernée (track_id, prompt_id, trade_id, etc.)
        sa.Column("target_type", sa.String(30), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Extra data lisible par le front (ex: nom de la track, prix payé)
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    # Index filtré sur unread — hyper-rapide pour GET /me/notifications?unread=true
    op.create_index(
        "idx_notifications_user_unread",
        "notifications",
        ["user_id", "created_at"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index("idx_notifications_user_created",
                    "notifications", ["user_id", "created_at"])

    # ── 2. MESSAGE THREADS ───────────────────────────────────────────────────
    # 1 thread par paire (participant_a < participant_b pour garantir unicité)
    op.create_table(
        "message_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("participant_a", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("participant_b", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        # Contrainte : unicité de la paire (ordre canonique imposé par le service)
        sa.UniqueConstraint("participant_a", "participant_b",
                            name="uq_message_threads_pair"),
        # Auto-message interdit
        sa.CheckConstraint("participant_a != participant_b",
                           name="ck_message_threads_no_self"),
    )
    op.create_index("idx_message_threads_a", "message_threads", ["participant_a"])
    op.create_index("idx_message_threads_b", "message_threads", ["participant_b"])

    # ── 3. MESSAGES ──────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("message_threads.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint("length(trim(content)) > 0",
                           name="ck_messages_content_nonempty"),
    )
    op.create_index("idx_messages_thread_created",
                    "messages", ["thread_id", "created_at"])
    op.create_index("idx_messages_sender", "messages", ["sender_id"])

    # ── 4. TRADE OFFERS ──────────────────────────────────────────────────────
    # Trade entre créateurs uniquement — chacun cède l'accès à sa propre création.
    # Pas de resale (pas de current_owner_id swap) — on crée simplement
    # un UnlockedPrompt pour chaque side lors de l'acceptation.
    op.execute("""
        CREATE TYPE trade_status AS ENUM (
            'pending', 'accepted', 'rejected', 'cancelled', 'expired'
        )
    """)

    op.create_table(
        "trade_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("receiver_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        # Ce que le sender offre (son prompt, dont il est le créateur)
        sa.Column("offered_prompt_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("prompts.id", ondelete="SET NULL"),
                  nullable=True),
        # Ce que le sender demande (prompt du receiver, dont le receiver est créateur)
        sa.Column("requested_prompt_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("prompts.id", ondelete="SET NULL"),
                  nullable=True),
        # Supplément crédits offert par le sender si échange asymétrique
        # (ex: mon prompt vaut 50, le tien vaut 80 → j'ajoute 30 crédits)
        sa.Column("credit_supplement", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("status", sa.Enum(
            "pending", "accepted", "rejected", "cancelled", "expired",
            name="trade_status", create_type=False,
        ), nullable=False, server_default="pending"),
        # Message optionnel du sender pour contextualiser l'offre
        sa.Column("message", sa.Text, nullable=True),
        # Expire automatiquement après 7 jours (nettoyé par cron ou au fetch)
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        # Garde un snap du prix des deux prompts au moment du trade
        sa.Column("offered_price_at_trade", sa.Integer, nullable=True),
        sa.Column("requested_price_at_trade", sa.Integer, nullable=True),
        sa.CheckConstraint("sender_id != receiver_id",
                           name="ck_trade_offers_no_self"),
        sa.CheckConstraint("credit_supplement >= 0",
                           name="ck_trade_offers_supplement_nonneg"),
    )
    op.create_index("idx_trade_offers_sender",
                    "trade_offers", ["sender_id", "status"])
    op.create_index("idx_trade_offers_receiver",
                    "trade_offers", ["receiver_id", "status"])


def downgrade() -> None:
    op.drop_table("trade_offers")
    op.execute("DROP TYPE IF EXISTS trade_status")
    op.drop_table("messages")
    op.drop_table("message_threads")
    op.drop_table("notifications")
    op.execute("DROP TYPE IF EXISTS notification_type")
