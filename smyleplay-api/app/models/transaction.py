import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class TransactionType(str, enum.Enum):
    UNLOCK = "unlock"
    CREDIT_PURCHASE = "credit_purchase"
    EARNING = "earning"
    REFUND = "refund"
    BONUS = "bonus"
    GRANT = "grant"  # V1 seulement, pour tests internes
    # Phase 10 (P2P resale) — la valeur est ajoutée dans la migration 0010
    # pour que le CHECK conditionnel (= pour unlock/resale, <= sinon) puisse
    # référencer 'resale' sans cast error. Aucun code actuel ne crée de
    # transaction RESALE — la valeur reste dormante jusqu'à la Phase 10.
    RESALE = "resale"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class Transaction(Base):
    __tablename__ = "transactions"

    __table_args__ = (
        # Phase 9: tightened from >=0 to >0 (toute transaction est >= 1 crédit)
        CheckConstraint(
            "credits_amount > 0",
            name="ck_transactions_credits_amount_positive",
        ),
        CheckConstraint(
            "platform_fee >= 0",
            name="ck_transactions_platform_fee_nonneg",
        ),
        CheckConstraint(
            "artist_revenue >= 0",
            name="ck_transactions_artist_revenue_nonneg",
        ),
        # Phase 9.5 : CHECK conditionnel par type.
        #   - UNLOCK / RESALE : split STRICTEMENT égal à credits_amount
        #     (zéro crédit perdu, conservation garantie au niveau DB)
        #   - autres types (GRANT/BONUS/CREDIT_PURCHASE/EARNING/REFUND) :
        #     split <= credits_amount (split = 0 OK, pas de seller)
        # cf. migration 0010_strict_unlock_check.
        CheckConstraint(
            "(type IN ('unlock', 'resale') "
            " AND artist_revenue + platform_fee = credits_amount) "
            "OR "
            "(type NOT IN ('unlock', 'resale') "
            " AND artist_revenue + platform_fee <= credits_amount)",
            name="ck_transactions_split_within_amount",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    type: Mapped[TransactionType] = mapped_column(
        # values_callable : force SQLAlchemy à envoyer la VALUE de l'enum
        # ("unlock") au lieu du NAME ("UNLOCK"). Sans ça, asyncpg crash avec
        # InvalidTextRepresentationError car l'enum DB est en lowercase.
        SQLEnum(
            TransactionType,
            name="transaction_type",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        SQLEnum(
            TransactionStatus,
            name="transaction_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=TransactionStatus.PENDING,
        server_default=TransactionStatus.PENDING.value,
    )
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    credits_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_fee: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    artist_revenue: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    external_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    euro_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
