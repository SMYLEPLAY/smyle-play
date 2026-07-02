"""
Schémas Pydantic ADN Visuel artiste (signature visuelle).

Calque STRICT des schémas ADN musical (marketplace.py : AdnCreate /
AdnUpdate / AdnRead), camelCase en lecture publique géré ailleurs.

Conventions (alignées sur marketplace.py) :
  - extra="forbid" sur les payloads input → refus des champs inconnus
  - str_strip_whitespace=True → trim auto
  - Bornes encodées DEUX FOIS : Pydantic (422) ET DB CHECK (filet)
  - Lock description après vente : géré côté SERVICE (query DB requise)

Spécifique visuel : `style` (code STYLES) + `palette` (génome, gaté).
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Aligné avec marketplace.AiReference.
AiReference = Literal[
    "chatgpt", "claude", "grok", "gemini", "mistral", "perplexity", "autre"
]

# Codes STYLES — copie statique de routers/images.py STYLES (source unique
# côté création image). Validation souple : valeur hors-liste rejetée 422.
VisualStyle = Literal[
    "realiste",
    "cartoon",
    "anime",
    "3d",
    "peinture",
    "aquarelle",
    "croquis",
    "pixel_art",
    "cyberpunk",
    "fantasy",
    "minimaliste",
    "retro",
    "abstrait",
    "surrealiste",
    "comics",
    "photo",
]

# Bornes (mirror des bornes ADN musical).
VISUAL_ADN_PRICE_MIN = 30
VISUAL_ADN_PRICE_MAX = 500
VISUAL_ADN_DESCRIPTION_MIN = 200
VISUAL_ADN_DESCRIPTION_MAX = 5000
VISUAL_ADN_USAGE_GUIDE_MAX = 3000
VISUAL_ADN_EXAMPLE_OUTPUTS_MAX = 5000
VISUAL_ADN_MAX_SUPPLY_MIN = 1
VISUAL_ADN_MAX_SUPPLY_MAX = 2147483647
VISUAL_ADN_PALETTE_MAX = 255


class VisualAdnCreate(BaseModel):
    """
    Création ADN visuel. 1 par artiste max (UNIQUE artist_id + check
    applicatif → 409). Crée TOUJOURS en draft (is_published=False).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str = Field(
        min_length=VISUAL_ADN_DESCRIPTION_MIN,
        max_length=VISUAL_ADN_DESCRIPTION_MAX,
        description="Signature visuelle de l'artiste (200..5000 chars).",
    )
    usage_guide: str | None = Field(
        default=None, max_length=VISUAL_ADN_USAGE_GUIDE_MAX
    )
    example_outputs: str | None = Field(
        default=None, max_length=VISUAL_ADN_EXAMPLE_OUTPUTS_MAX
    )
    price_credits: int = Field(
        ge=VISUAL_ADN_PRICE_MIN,
        le=VISUAL_ADN_PRICE_MAX,
        description=(
            f"Prix en crédits "
            f"({VISUAL_ADN_PRICE_MIN}..{VISUAL_ADN_PRICE_MAX})."
        ),
    )
    ai_reference: AiReference | None = None
    max_supply: int | None = Field(
        default=None,
        ge=VISUAL_ADN_MAX_SUPPLY_MIN,
        le=VISUAL_ADN_MAX_SUPPLY_MAX,
    )
    # ── Spécifique visuel ────────────────────────────────────────────────
    style: VisualStyle | None = None
    palette: str | None = Field(
        default=None, max_length=VISUAL_ADN_PALETTE_MAX
    )


class VisualAdnUpdate(BaseModel):
    """
    PATCH ADN visuel — `description` figé après 1ère vente (enforce SERVICE).
    Tous les champs optionnels (PATCH partiel).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str | None = Field(
        default=None,
        min_length=VISUAL_ADN_DESCRIPTION_MIN,
        max_length=VISUAL_ADN_DESCRIPTION_MAX,
    )
    usage_guide: str | None = Field(
        default=None, max_length=VISUAL_ADN_USAGE_GUIDE_MAX
    )
    example_outputs: str | None = Field(
        default=None, max_length=VISUAL_ADN_EXAMPLE_OUTPUTS_MAX
    )
    price_credits: int | None = Field(
        default=None, ge=VISUAL_ADN_PRICE_MIN, le=VISUAL_ADN_PRICE_MAX
    )
    is_published: bool | None = None
    ai_reference: AiReference | None = None
    max_supply: int | None = Field(
        default=None,
        ge=VISUAL_ADN_MAX_SUPPLY_MIN,
        le=VISUAL_ADN_MAX_SUPPLY_MAX,
    )
    style: VisualStyle | None = None
    palette: str | None = Field(
        default=None, max_length=VISUAL_ADN_PALETTE_MAX
    )


class VisualAdnRead(BaseModel):
    """Vue owner / library — contenu complet (description, palette)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artist_id: UUID
    description: str
    usage_guide: str | None = None
    example_outputs: str | None = None
    price_credits: int
    is_published: bool
    ai_reference: str | None = None
    max_supply: int | None = None
    style: str | None = None
    palette: str | None = None
    created_at: datetime
    updated_at: datetime
    last_updated_by_artist_at: datetime | None = None
