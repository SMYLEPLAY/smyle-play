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
    # Sprint 1 PR2 (2026-05-04) — migration POST track Flask → FastAPI.
    # audio_url + r2_key sont les retours de l'upload R2 du fichier audio
    # (endpoint Flask /api/watt/upload existant). On accepte aussi
    # cover_url (endpoint Flask /api/watt/upload-image) pour la pochette,
    # et prompt_id pour lier à un prompt préexistant si dispo.
    audio_url: str | None = Field(default=None, max_length=2048)
    r2_key: str | None = Field(default=None, max_length=500)
    cover_url: str | None = Field(default=None, max_length=2048)
    prompt_id: UUID | None = None


class TrackUpdate(BaseModel):
    """
    PATCH partiel d'un track. Permet d'attacher un prompt_id après coup
    (workflow dashboard : créer track → créer prompt → PATCH track avec
    prompt_id obtenu) ou de mettre à jour la cover.
    """

    title: str | None = Field(default=None, min_length=1, max_length=255)
    color: str | None = Field(default=None, pattern=HEX_COLOR_RE)
    cover_url: str | None = Field(default=None, max_length=2048)
    prompt_id: UUID | None = None


class DNARead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_prompt: str


class TrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    audio_url: str | None
    color: str | None
    cover_url: str | None = None
    prompt_id: UUID | None = None
    created_at: datetime


class TrackWithDNA(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    track: TrackRead
    dna: DNARead
