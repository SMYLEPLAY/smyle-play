import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OwnedPlaylistAdn(Base):
    """
    Possession d'un ADN Playlist par un utilisateur.

    - PK composite (user_id, playlist_id) : un user ne peut acheter l'ADN
      d'une playlist qu'une seule fois.
    - Donne droit à une réduction sur les ADN Track présents dans la playlist
      (logique perk calculée dans unlock_adn_atomic).
    - ondelete=CASCADE : si user ou playlist supprimée, la possession disparaît.
    """

    __tablename__ = "owned_playlist_adns"
    __table_args__ = (
        PrimaryKeyConstraint(
            "user_id", "playlist_id", name="pk_owned_playlist_adns"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    playlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
