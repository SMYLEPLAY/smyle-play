import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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


class VisualAdn(Base):
    """
    ADN VISUEL (signature visuelle) d'un artiste — sommet de la pyramide
    visuelle (profil > album > image).

    Calque STRICT de l'ADN musical (Adn) :
    - 1 ADN visuel max par artiste (UNIQUE artist_id)
    - Non-transférable : primary market uniquement, jamais P2P
    - Prix encadré : 30 <= price_credits <= 500
    - Contenu enrichi : description + usage_guide + example_outputs
    - Validation min length sur description (200 chars) au niveau DB

    Spécifique visuel :
    - style   : un des codes STYLES (images.py) — style dominant
    - palette : palette de couleurs (CSV hex / mots-clés) — GATÉE (génome)
    """

    __tablename__ = "visual_adns"
    __table_args__ = (
        UniqueConstraint("artist_id", name="uq_visual_adns_artist_id"),
        CheckConstraint(
            "price_credits >= 30 AND price_credits <= 500",
            name="ck_visual_adns_price_credits_range",
        ),
        CheckConstraint(
            "char_length(description) >= 200",
            name="ck_visual_adns_description_min_length",
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
    # IA utilisée pour générer le contenu (badge card publique). Nullable.
    ai_reference: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    # Rareté : NULL = illimité, 1 = exclusif, N = édition limitée.
    # Stock-out enforcé côté unlock_visual_adn_atomic (sold_count vs
    # max_supply via OwnedVisualAdn).
    max_supply: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # ── Spécifique VISUEL ────────────────────────────────────────────────
    # style : style dominant, un des codes STYLES (cf. images.py). Public
    #         (sert au badge de la card publique).
    style: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # palette : palette de couleurs (CSV hex / mots-clés). GATÉE — fait
    #           partie du génome, jamais exposée publiquement.
    palette: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    # Soft-delete : masque l'ADN visuel du marketplace et du dashboard
    # artiste. Les OwnedVisualAdn acheteurs ne sont PAS supprimés.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    # OFFRES-ADN (migration 0080) : plancher caché sous lequel une offre est
    # rejetée automatiquement. NULL = pas de plancher.
    adn_reserve_credits: Mapped[int | None] = mapped_column(
        Integer, nullable=True
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
    # Ne se met à jour QUE quand l'artiste modifie le contenu (description,
    # usage_guide, example_outputs), pas lors de changements internes.
    last_updated_by_artist_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
