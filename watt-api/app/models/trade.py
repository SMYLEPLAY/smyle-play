import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TradeStatus(str, enum.Enum):
    PENDING   = "pending"    # offre envoyée, attente réponse
    ACCEPTED  = "accepted"   # échange effectué, crédits transférés
    REJECTED  = "rejected"   # receiver a refusé
    CANCELLED = "cancelled"  # sender a annulé
    EXPIRED   = "expired"    # délai 7j dépassé


class TradeOffer(Base):
    """
    Offre d'échange de prompts entre créateurs.

    Règle : chaque partie ne peut offrir que ses propres créations.
    Pas de resale (pas de transfert de current_owner_id) —
    l'acceptation crée deux UnlockedPrompt (un pour chaque side).

    credit_supplement : crédits extra offerts par le sender pour
    compenser un écart de valeur entre les deux prompts. Min 0.

    Les prix sont snapshotés à la création (offered_price_at_trade,
    requested_price_at_trade) pour audit et calcul de royalties.
    """

    __tablename__ = "trade_offers"
    __table_args__ = (
        CheckConstraint("sender_id != receiver_id",
                        name="ck_trade_offers_no_self"),
        CheckConstraint("credit_supplement >= 0",
                        name="ck_trade_offers_supplement_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Prompt que le SENDER offre (doit être le créateur)
    offered_prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Prompt que le SENDER demande au receiver (le receiver doit être créateur)
    requested_prompt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Crédits supplémentaires offerts par le sender (asymétrie de valeur)
    credit_supplement: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[TradeStatus] = mapped_column(
        SQLEnum(
            TradeStatus,
            name="trade_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=TradeStatus.PENDING,
        server_default=TradeStatus.PENDING.value,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Snapshot des prix au moment du trade (audit + royalties)
    offered_price_at_trade: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    requested_price_at_trade: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
