import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PromptLike(Base):
    """
    Like durable d'un prompt par un utilisateur (C4 livraison 5).

    Store dédié, générique (clé prompt) mais utilisé pour les IMAGES en V1.
    Remplace le hack localStorage `sp_img_likes_v1` de la livraison 4.

    - PK composite (user_id, prompt_id) : un like unique par (user, prompt),
      rend POST /me/likes/prompts/{id} idempotent.
    - ondelete=CASCADE : si user ou prompt supprimé, le like disparaît.
    - Séparation son/image : le ❤️ audio reste sur la wishlist (playlist
      privée → track). Les likes image ont leur propre store et ne polluent
      jamais la wishlist audio.
    """

    __tablename__ = "prompt_likes"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "prompt_id", name="pk_prompt_likes"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
