import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OwnedAdn(Base):
    """
    Jointure user ↔ ADN. Représente la possession permanente d'une ADN.

    - PK composite (user_id, adn_id) : un user ne peut posséder une ADN
      qu'une seule fois
    - ondelete=CASCADE des deux côtés : si user ou ADN est supprimé, la
      possession disparaît (l'historique reste dans Transaction)
    - Lookup ultra-fréquent dans le calcul du perk -30% sur les prompts
    """

    __tablename__ = "owned_adns"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "adn_id", name="pk_owned_adns"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    adn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("adns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
