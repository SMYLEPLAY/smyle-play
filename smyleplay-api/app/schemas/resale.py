from uuid import UUID

from pydantic import BaseModel, Field


class ResaleListRequest(BaseModel):
    """Mise en vente d'un prompt possédé."""

    price: int = Field(ge=1, le=100000)


class ResaleMarketItem(BaseModel):
    """Un listing du marché secondaire."""

    unlocked_prompt_id: UUID
    prompt_id: UUID
    title: str
    resale_price: int
    seller_id: UUID
    original_artist_id: UUID | None = None
    original_artist_name: str | None = None
    original_artist_slug: str | None = None
    max_supply: int | None = None


class ResaleBuyResult(BaseModel):
    """Résultat d'un achat en revente."""

    prompt_id: UUID
    price_paid: int
    seller_cut: int
    artist_royalty: int
    platform_fee: int
    new_balance: int
