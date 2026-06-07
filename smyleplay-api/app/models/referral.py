import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReferralStatus(str, enum.Enum):
    PENDING  = "pending"   # filleul inscrit, récompense pas encore débloquée
    REWARDED = "rewarded"  # filleul a fait sa 1ère action → les 2 crédités


class Referral(Base):
    """
    Lien de parrainage parrain → filleul.

    Règles métier (cf. [[project_mechanics_before_stripe]]) :
      - Un filleul ne peut être parrainé qu'UNE fois (unique sur referred_id).
      - Pas d'auto-parrainage (CHECK referrer_id != referred_id).
      - La récompense (10 Smyles par côté) n'est versée qu'à la PREMIÈRE
        vraie action du filleul (1er son posté OU 1er achat) — anti-faux-compte.
        Tant que status=PENDING, aucun crédit n'a été versé.

    reward_credits : montant crédité À CHAQUE côté lors du passage REWARDED.
    Snapshoté à la création pour rester stable même si le barème change.
    """

    __tablename__ = "referrals"
    __table_args__ = (
        CheckConstraint(
            "referrer_id != referred_id",
            name="ck_referrals_no_self",
        ),
        CheckConstraint(
            "reward_credits > 0",
            name="ck_referrals_reward_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referrer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Unique : un compte ne peut être parrainé qu'une seule fois.
    referred_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[ReferralStatus] = mapped_column(
        SQLEnum(ReferralStatus, name="referral_status", native_enum=False),
        nullable=False,
        default=ReferralStatus.PENDING,
        server_default=ReferralStatus.PENDING.value,
        index=True,
    )
    reward_credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    rewarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
