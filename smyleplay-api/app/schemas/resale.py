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
    # #X/N — numéro d'exemplaire de CE listing dans l'édition limitée.
    # NULL pour les tirages illimités. Le front affiche "#X/N" si
    # edition_number ET max_supply sont présents.
    edition_number: int | None = None
    # C4 ④ — nature ('recipe' | 'beat' | 'image' | 'voice'). Le front rend une
    # vignette + label image quand product_type == 'image'.
    product_type: str | None = None
    # Aperçu public d'une image revendue (None pour l'audio). Sert via le proxy
    # /watt/images/{preview_r2_key}. Jamais l'original ni la recette.
    preview_r2_key: str | None = None


class ResaleBuyResult(BaseModel):
    """Résultat d'un achat en revente."""

    prompt_id: UUID
    price_paid: int
    seller_cut: int
    artist_royalty: int
    platform_fee: int
    new_balance: int
