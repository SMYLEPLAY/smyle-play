"""Schémas OFFRES-ADN — offre cash sur un ADN (chantier 2026-07-03)."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.trade import TradeStatus

AdnTargetType = Literal[
    "playlist_adn", "album_adn", "visual_adn", "profile_adn"
]


class AdnOfferCreate(BaseModel):
    target_type: AdnTargetType
    target_id: UUID
    # Montant proposé en Smyles. Borne haute 100 000 = garde anti-fat-finger.
    amount_credits: int = Field(ge=1, le=100_000)
    message: str | None = Field(default=None, max_length=500)


class AdnOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: str
    target_id: UUID
    target_title: str | None = None   # enrichi
    amount_credits: int
    buyer_id: UUID                    # = sender_id
    buyer_name: str | None = None     # enrichi
    seller_id: UUID                   # = receiver_id
    seller_name: str | None = None    # enrichi
    status: TradeStatus
    message: str | None = None
    expires_at: datetime | None = None
    created_at: datetime
    resolved_at: datetime | None = None
