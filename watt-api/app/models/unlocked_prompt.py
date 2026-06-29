import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UnlockedPrompt(Base):
    """
    Représente un prompt débloqué/possédé par un user.

    Modèle conçu dès Phase 9 pour supporter le P2P trade en Phase 10 :

    - id propre (UUID) : l'unlock est une entité de plein droit, pas
      juste une jointure (pour permettre transfert P2P en Phase 10)
    - current_owner_id : possesseur actuel, mutable (cf. Phase 10)
    - original_artist_id : snapshot à la création, immutable, sert de
      base pour les royalties à perpétuité (Phase 10)
    - UNIQUE (current_owner_id, prompt_id) : un user ne peut posséder
      qu'un exemplaire d'un même prompt à un instant T
    - ondelete=SET NULL sur original_artist_id : si l'artiste est
      supprimé, on garde l'unlock mais la trace de l'auteur originel
      est rompue (audit Transaction prévaut)
    """

    __tablename__ = "unlocked_prompts"
    __table_args__ = (
        UniqueConstraint(
            "current_owner_id",
            "prompt_id",
            name="uq_unlocked_prompts_owner_prompt",
        ),
        # #X/N (2026-06-09) — deux exemplaires d'un même prompt ne peuvent pas
        # porter le même numéro d'édition. NULL autorisé en multiple (Postgres
        # traite les NULL comme distincts) → les tirages illimités, non
        # numérotés, ne déclenchent pas la contrainte.
        UniqueConstraint(
            "prompt_id",
            "edition_number",
            name="uq_unlocked_prompts_prompt_edition",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    current_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_artist_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Marché secondaire (2026-06-08) : NULL = pas en vente. Sinon, prix fixé
    # par le propriétaire actuel. À l'achat, la propriété est TRANSFÉRÉE
    # (current_owner_id change) et resale_price repasse à NULL. Split 30%
    # artiste d'origine (royaltie) / 20% plateforme / 50% vendeur.
    resale_price: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # #X/N (2026-06-09) — numéro d'exemplaire dans l'édition limitée.
    # Assigné séquentiellement au mint (1..max_supply) UNIQUEMENT pour les
    # éditions limitées (prompt.max_supply non NULL). NULL = tirage illimité,
    # non numéroté. Voir services/unlocks.py + services/packs.py (mint) et
    # migration 0051 (backfill par ordre d'achat).
    edition_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
