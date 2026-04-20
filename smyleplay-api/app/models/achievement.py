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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AchievementAxis(str, enum.Enum):
    """Trois axes d'achievements indépendants pour ne pas tout mélanger."""

    BUYER = "buyer"   # Collection : nb de prompts unlockés
    FAN = "fan"       # Engagement profond : nb d'ADN possédées
    ARTIST = "artist" # Création : nb de ventes ou crédits gagnés


class Achievement(Base):
    """
    Catalogue statique des badges débloquables.

    - Seedé via la migration 0009 avec ON CONFLICT (code) DO NOTHING
      pour idempotence
    - Le `code` est l'identifiant stable cross-version (slug)
    - threshold est interprété selon l'axis :
        * BUYER : nb de UnlockedPrompt où current_owner = user
        * FAN   : nb de OwnedAdn où user = user
        * ARTIST: credits_earned_total du user
    - credit_reward : si > 0, déclenche un grant_credits_atomic en BONUS
      au moment du déblocage
    """

    __tablename__ = "achievements"
    __table_args__ = (
        UniqueConstraint("code", name="uq_achievements_code"),
        CheckConstraint(
            "threshold > 0",
            name="ck_achievements_threshold_positive",
        ),
        CheckConstraint(
            "credit_reward >= 0",
            name="ck_achievements_credit_reward_nonneg",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    axis: Mapped[AchievementAxis] = mapped_column(
        # values_callable : force SQLAlchemy à envoyer la VALUE de l'enum
        # ("buyer") au lieu du NAME ("BUYER"). Sans ça, asyncpg crash avec
        # InvalidTextRepresentationError car l'enum DB est en lowercase.
        # Même pattern que TransactionType / TransactionStatus.
        SQLEnum(
            AchievementAxis,
            name="achievement_axis",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    credit_reward: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class UserAchievement(Base):
    """
    Trace les achievements débloqués par chaque user.

    - UNIQUE (user_id, achievement_id) : un badge ne se débloque qu'une
      seule fois (idempotence du hook check_and_grant_achievements)
    - bonus_transaction_id : audit trail vers la Transaction BONUS
      créée pour la récompense (null si credit_reward=0)
    """

    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "achievement_id",
            name="uq_user_achievements_user_ach",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    achievement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("achievements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    bonus_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
