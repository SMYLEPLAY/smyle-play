import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OwnedAlbumAdn(Base):
    """
    Possession d'un ADN Album (génome de style visuel) par un utilisateur.

    Analogue VISUEL de OwnedPlaylistAdn — calque STRICT :
    - PK composite (user_id, album_id) : un user ne peut acheter l'ADN
      d'un album qu'une seule fois.
    - Donne accès au génome complet (seed_prompt + palette) via la library.
    - ondelete=CASCADE : si user ou album supprimé, la possession disparaît.
    """

    __tablename__ = "owned_album_adns"
    __table_args__ = (
        PrimaryKeyConstraint(
            "user_id", "album_id", name="pk_owned_album_adns"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    album_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("albums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
