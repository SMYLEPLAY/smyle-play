from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.trade import TradeStatus


class TradeOfferCreate(BaseModel):
    receiver_id: UUID
    offered_prompt_id: UUID | None = None
    requested_prompt_id: UUID | None = None
    credit_supplement: int = Field(default=0, ge=0)
    message: str | None = Field(default=None, max_length=500)


class PromptSnap(BaseModel):
    """Snapshot léger du prompt pour l'affichage dans l'offre."""
    id: UUID
    title: str
    price_credits: int
    artist_name: str | None = None
    artist_slug: str | None = None
    # Audio du track lié au prompt → "écouter avant d'accepter" l'échange.
    audio_url: str | None = None


class TradeOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_id: UUID
    sender_name: str | None = None    # enrichi
    sender_avatar: str | None = None  # enrichi
    receiver_id: UUID
    receiver_name: str | None = None
    offered_prompt: PromptSnap | None = None    # enrichi
    requested_prompt: PromptSnap | None = None  # enrichi
    credit_supplement: int
    status: TradeStatus
    message: str | None = None
    offered_price_at_trade: int | None = None
    requested_price_at_trade: int | None = None
    expires_at: datetime | None = None
    created_at: datetime
    resolved_at: datetime | None = None
