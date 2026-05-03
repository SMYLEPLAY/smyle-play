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
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Prompt(Base):
    """
    Prompt vendu par un artiste sur la marketplace.

    - N par artiste, autant qu'il en publie
    - Transférable en Phase 10 (P2P) — cf. UnlockedPrompt qui a son propre
      UUID pour être tradeable plus tard
    - Plancher prix : 3 crédits
    - pack_eligible : prêt pour Phase 10 (packs aléatoires), default True
    - Validations au niveau DB (title 5+, prompt_text 100..1000).
      prompt_text est plafonné à 1000 car Suno n'accepte pas plus — vendre
      un prompt plus long reviendrait à vendre du contenu inutilisable.
    """

    __tablename__ = "prompts"
    __table_args__ = (
        CheckConstraint(
            "price_credits >= 3",
            name="ck_prompts_price_credits_min",
        ),
        CheckConstraint(
            "char_length(title) >= 5",
            name="ck_prompts_title_min_length",
        ),
        CheckConstraint(
            "char_length(prompt_text) BETWEEN 100 AND 1000",
            name="ck_prompts_prompt_text_length",
        ),
        # P1-F4 (2026-05-04) — enums réglages génération.
        # Conditionnelles (IS NULL OR IN ...) pour rétro-compat des
        # prompts existants en DB qui n'ont pas ces champs.
        CheckConstraint(
            "prompt_platform IS NULL OR prompt_platform IN "
            "('suno', 'udio', 'riffusion', 'stable_audio', 'autre')",
            name="ck_prompts_platform_enum",
        ),
        CheckConstraint(
            "prompt_vocal_gender IS NULL OR prompt_vocal_gender IN "
            "('masculin', 'feminin', 'instrumental')",
            name="ck_prompts_vocal_gender_enum",
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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Paroles complètes (gated behind unlock — ne JAMAIS retourner sans paiement)
    # Nullable car la majorité des morceaux sont instrumentaux ; rempli pour HIT MIX.
    lyrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    pack_eligible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # ── P1-F4 (2026-05-04) — Réglages de génération de la fiche prompt ──
    # Tous nullable côté DB pour rétro-compat. La validation strict
    # (4 obligatoires) est portée par PromptCreate Pydantic — les anciens
    # prompts restent valides en DB, les nouveaux doivent renseigner.
    prompt_platform: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    prompt_model_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    prompt_weirdness: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    prompt_style_influence: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    prompt_vocal_gender: Mapped[str | None] = mapped_column(
        String(20), nullable=True
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
