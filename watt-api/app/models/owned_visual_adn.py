import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OwnedVisualAdn(Base):
    """
    Jointure user ↔ ADN visuel. Possession permanente d'un ADN visuel.

    Calque STRICT de OwnedAdn :
    - PK composite (user_id, visual_adn_id) : un user ne possède un ADN
      visuel qu'une seule fois
    - ondelete=CASCADE des deux côtés : si user ou ADN visuel supprimé, la
      possession disparaît (l'historique reste dans Transaction)
    - Lookup chaud dans le calcul du perk -30% sur les IMAGES de l'artiste
    """

    __tablename__ = "owned_visual_adns"
    __table_args__ = (
        PrimaryKeyConstraint(
            "user_id", "visual_adn_id", name="pk_owned_visual_adns"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    visual_adn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("visual_adns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
