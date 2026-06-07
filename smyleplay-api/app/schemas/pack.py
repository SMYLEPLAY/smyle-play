from uuid import UUID

from pydantic import BaseModel


class PackInfo(BaseModel):
    """Infos du mystery pack (GET /packs/mystery)."""

    price: int          # coût d'un tirage en Smyles
    pool_count: int     # nb de prompts encore tirables pour ce user


class PackOpenResult(BaseModel):
    """Résultat d'un tirage (POST /packs/mystery/open)."""

    prompt_id: UUID
    title: str
    artist_id: UUID
    price_paid: int
    new_balance: int
