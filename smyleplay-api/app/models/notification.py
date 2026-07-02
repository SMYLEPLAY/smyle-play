import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationType(str, enum.Enum):
    PURCHASE = "purchase"   # 💸 quelqu'un a acheté ta création
    LIKE     = "like"       # ❤️ quelqu'un a liké ta track
    FOLLOW   = "follow"     # 👤 quelqu'un te suit
    MESSAGE  = "message"    # ✉️ nouveau message reçu
    TRADE    = "trade"      # 🔄 offre de trade reçue / acceptée / rejetée
    SYSTEM   = "system"     # ⚙️ trophée débloqué, bonus crédits, etc.


class Notification(Base):
    """
    Centre de notifications catégorisées.

    - user_id     : destinataire de la notif
    - actor_id    : qui a déclenché l'action (null pour system)
    - target_type : type de l'entité concernée ('track','prompt','adn','trade',etc.)
    - target_id   : UUID de l'entité (pour navigation directe côté front)
    - metadata_json : data lisible par le front (nom de la track, prix payé, etc.)
    - read_at     : null = non lu. Index filtré sur (user_id, read_at IS NULL).
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[NotificationType] = mapped_column(
        SQLEnum(
            NotificationType,
            name="notification_type",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
