from uuid import UUID

from pydantic import BaseModel


class RarityOdds(BaseModel):
    """Une rareté et sa probabilité (%) — pour la légende UI."""

    name: str       # commun / rare / epique / legendaire
    weight: int     # poids brut
    pct: int        # probabilité en % (arrondi)


class PackInfo(BaseModel):
    """Infos du mystery pack (GET /packs/mystery)."""

    price: int                  # coût d'un tirage en Smyles
    pool_count: int             # nb de prompts encore tirables pour ce user
    odds: list[RarityOdds]      # chances par rareté (transparence)


class PackOpenResult(BaseModel):
    """Résultat d'un tirage (POST /packs/mystery/open)."""

    prompt_id: UUID
    title: str
    artist_id: UUID
    rarity: str         # commun / rare / epique / legendaire
    price_paid: int
    new_balance: int
