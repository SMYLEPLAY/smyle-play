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
    # Lot 3 — mention légale à afficher sous les prix (franchise de TVA), ou None.
    mention_tva: str | None = None
    # Lot 3 — paiement par carte réellement disponible (clé Stripe posée).
    paiement_carte: bool = False


class GrantCreditsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credits: int = Field(gt=0, le=10000, description="Nombre de crédits à accorder")
    reason: str | None = Field(default=None, max_length=500)


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # NB : doit couvrir TOUTES les valeurs de TransactionType susceptibles
    # d'apparaître dans l'historique d'un user (buyer_id/seller_id), sinon
    # GET /credits/transactions lève une ValidationError. "resale" manquait
    # (latent) ; "burn" est ajouté par D6 (frais de troc brûlés).
    type: Literal[
        "unlock", "credit_purchase", "earning", "refund", "bonus", "grant",
        "resale", "burn",
    ]
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
