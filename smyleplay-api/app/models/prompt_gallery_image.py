import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PromptGalleryImage(Base):
    """
    Image supplémentaire rattachée à un produit IMAGE (C4 galerie avatar).

    Cas d'usage : un avatar = un personnage avec 10+ visuels. À l'achat de
    l'image-produit (ligne `prompts`, product_type='image'), l'acheteur récupère
    TOUTES les images originales de la galerie + la recette. Le SCHÉMA reste
    générique sur les images (la restriction « avatars » est une convention UX
    côté front, non contrainte ici).

    Symétrie avec la ligne `prompts` :
      - image_r2_key   = ORIGINAL gaté (préfixe images/originals/, jamais public)
      - preview_r2_key = APERÇU public (préfixe images/previews/, ≤ 1024 px)

    Le gating reprend EXACTEMENT celui de l'image principale : l'original ne
    sort que via la route download gatée (acheteur possédant l'image OU owner) ;
    l'aperçu est public comme le preview principal.

    ON DELETE CASCADE : si l'image-produit est hard-deleted, sa galerie suit.
    (Le soft-delete d'une image ne touche pas la galerie : l'acheteur garde son
    accès, comme pour le download principal.)
    """

    __tablename__ = "prompt_gallery_images"
    __table_args__ = (
        Index("ix_prompt_gallery_images_prompt_id", "prompt_id"),
        Index("ix_prompt_gallery_images_prompt_position", "prompt_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # ORIGINAL gaté (jamais exposé publiquement, download gaté uniquement).
    image_r2_key: Mapped[str] = mapped_column(String(500), nullable=False)
    # APERÇU public (servi via le proxy /watt/images/, comme le preview principal).
    preview_r2_key: Mapped[str] = mapped_column(String(500), nullable=False)
    # Ordre d'affichage dans la galerie (0-based, max+1 à l'ajout).
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
