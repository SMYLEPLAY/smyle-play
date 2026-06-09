"""
Schémas Beats (Phase 2 Marketplace VF, 2026-06-09).

Un "beat" est un produit vendable de la même table `prompts`
(product_type='beat'), mais SANS prompt_text ni réglages IA : on vend un
fichier audio + une licence (lease | exclusive). Achat/possession/revente
réutilisent toute la machinerie des prompts.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.marketplace import (
    PROMPT_DESCRIPTION_MAX,
    PROMPT_PRICE_MIN,
    PROMPT_TITLE_MAX,
    PROMPT_TITLE_MIN,
)

BeatLicense = Literal["lease", "exclusive"]


class BeatCreate(BaseModel):
    """
    Création d'un beat à vendre. Pas de pré-requis ADN (décision Tom
    2026-06-09 : un beatmaker vend sans signature IA).

    - `license_type` obligatoire (lease | exclusive).
    - Pas de prompt_text ni de réglages génération (un beat n'est pas une
      recette).
    - `max_supply` : édition limitée pour les LEASE. Pour un EXCLUSIVE, le
      service force max_supply=1 (vente unique) — inutile de l'envoyer.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=PROMPT_TITLE_MIN, max_length=PROMPT_TITLE_MAX)
    description: str | None = Field(default=None, max_length=PROMPT_DESCRIPTION_MAX)
    # Prix libre (min 3 crédits, comme les prompts). Pas de plafond ressenti.
    price_credits: int = Field(ge=PROMPT_PRICE_MIN)
    license_type: BeatLicense
    # Édition limitée pour les lease (None = illimité). Ignoré si exclusive.
    max_supply: int | None = Field(default=None, ge=1)
    is_published: bool = False


class BeatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None = None
    price_credits: int
    product_type: str
    license_type: str | None = None
    max_supply: int | None = None
    is_published: bool
    created_at: datetime
