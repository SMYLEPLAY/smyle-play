"""
Télémétrie D0 — journal d'événements produit, privacy-first.

Mesure le funnel (visiteur → inscrit → 1er achat → revient) SANS donnée
personnelle : pas d'IP, pas de user-agent, pas d'e-mail. L'identifiant de
session est un jeton aléatoire généré côté client (localStorage), non
réversible vers une personne. Lot D (0102) : `user_id` est TOUJOURS NULL
(CHECK en base) — la mesure n'est jamais rattachée à un compte. La colonne est
conservée pour ne pas casser les lectures existantes. Conservation 13 mois.

Best-effort : la collecte ne doit JAMAIS bloquer une action utilisateur.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Identifiant de session anonyme (client-side, non-PII), indexé pour le funnel.
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Toujours NULL depuis le Lot D (ck_analytics_events_sans_compte).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Nom d'événement (whitelisté côté router). Ex. 'visit', 'signup', 'purchase'.
    name: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # Contexte non-PII.
    path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(256), nullable=True)
    props: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
