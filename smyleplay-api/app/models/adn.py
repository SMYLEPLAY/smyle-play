import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Adn(Base):
    """
    ADN (signature créative) d'un artiste.

    - 1 ADN max par artiste (UNIQUE artist_id)
    - Non-transférable : primary market uniquement, jamais P2P
    - Prix encadré : 30 <= price_credits <= 500
    - Contenu enrichi : description + usage_guide + example_outputs
    - Validation min length sur description (200 chars) au niveau DB
    """

    __tablename__ = "adns"
    __table_args__ = (
        UniqueConstraint("artist_id", name="uq_adns_artist_id"),
        CheckConstraint(
            "price_credits >= 30 AND price_credits <= 500",
            name="ck_adns_price_credits_range",
        ),
        CheckConstraint(
            "char_length(description) >= 200",
            name="ck_adns_description_min_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    artist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    usage_guide: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_outputs: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # Distinct de updated_at: ne se met à jour QUE quand l'artiste modifie
    # le contenu (description, usage_guide, example_outputs), pas lors de
    # changements internes (price uniquement, etc.).
    last_updated_by_artist_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
