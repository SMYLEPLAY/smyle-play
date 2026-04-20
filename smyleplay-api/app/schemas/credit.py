from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreditPack(BaseModel):
    id: str
    credits: int
    price_eur_cents: int
    price_eur_display: str
    unit_price_cents: int


class CreditPacksResponse(BaseModel):
    packs: list[CreditPack]


class GrantCreditsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credits: int = Field(gt=0, le=10000, description="Nombre de crédits à accorder")
    reason: str | None = Field(default=None, max_length=500)


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: Literal["unlock", "credit_purchase", "earning", "refund", "bonus", "grant"]
    status: Literal["pending", "completed", "failed", "rolled_back"]
    credits_amount: int
    platform_fee: int
    artist_revenue: int
    euro_amount_cents: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class TransactionsListResponse(BaseModel):
    items: list[TransactionRead]
    total: int
    page: int
    per_page: int
