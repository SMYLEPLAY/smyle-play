from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Étape 2 — format couleur hex "#RRGGBB" utilisé partout (track.color,
# futures extensions UI). Regex volontairement stricte (6 chars, majuscules
# ou minuscules) pour éviter les formats à 3 chars ou sans dièse. Null reste
# permis et signifie "hérite de la brandColor de l'artiste".
HEX_COLOR_RE = r"^#[0-9a-fA-F]{6}$"


class TrackCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    full_prompt: str = Field(min_length=1)
    # Optionnel ; null = fallback brandColor. Validé par la longueur
    # VARCHAR(7) en base + la regex Pydantic pour garantir l'intégrité.
    color: str | None = Field(default=None, pattern=HEX_COLOR_RE)


class DNARead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_prompt: str


class TrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    audio_url: str | None
    color: str | None
    created_at: datetime


class TrackWithDNA(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    track: TrackRead
    dna: DNARead
