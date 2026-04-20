"""
Schémas Pydantic pour l'API Playlist (étape 3 du chantier profil public).

Conventions :
  - `visibility` est une Literal[...] plutôt qu'un Enum Pydantic pour rester
    trivialement JSON-sérialisable et cohérent avec le CHECK SQL.
  - `color` reutilise le regex HEX_COLOR_RE défini dans schemas.track —
    single source of truth pour la validation hex côté API.
  - `PlaylistRead` reste léger (métadonnées de la playlist sans ses tracks)
    pour couvrir "liste mes playlists" ; les tracks sont fournis en détail
    via `PlaylistWithTracks` au chargement d'un /playlists/{id}.
  - Les champs forward-compat V2 (`dna_description`) sont volontairement
    absents des schémas V1 : la colonne existe en base mais n'est ni lue
    ni écrite par l'API tant que le feature flag V2 n'est pas activé.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.track import HEX_COLOR_RE, TrackRead


Visibility = Literal["public", "private"]


class PlaylistCreate(BaseModel):
    """Payload création d'une playlist.

    `visibility` par défaut est "private" : on encourage les playlists de
    consommation (wishlist, favoris) plutôt que de forcer un partage public
    accidentel. Passer explicitement "public" rend la playlist visible sur
    /u/<slug> et impose la règle "tracks de l'owner uniquement" côté service.
    """

    title: str = Field(min_length=1, max_length=200)
    visibility: Visibility = "private"
    color: str | None = Field(default=None, pattern=HEX_COLOR_RE)
    cover_video_url: str | None = Field(default=None, max_length=2048)
    seed_prompt: str | None = None


class PlaylistUpdate(BaseModel):
    """Patch partiel d'une playlist (PATCH /playlists/{id}).

    Tous les champs sont optionnels. Passer explicitement `None` n'est pas
    distingué de "ne pas toucher" côté API V1 — on ne supporte que les
    patches additifs pour simplifier. Le service applique un `setattr`
    uniquement pour les champs présents (`model_dump(exclude_unset=True)`).
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    visibility: Visibility | None = None
    color: str | None = Field(default=None, pattern=HEX_COLOR_RE)
    cover_video_url: str | None = Field(default=None, max_length=2048)
    seed_prompt: str | None = None


class PlaylistRead(BaseModel):
    """Projection "liste" : pas de tracks pour rester compact côté dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    title: str
    visibility: Visibility
    color: str | None
    cover_video_url: str | None
    created_at: datetime


class PlaylistWithTracks(BaseModel):
    """Projection "détail" : renvoie les tracks ordonnés par `position`."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    title: str
    visibility: Visibility
    color: str | None
    cover_video_url: str | None
    seed_prompt: str | None
    created_at: datetime
    tracks: list[TrackRead] = Field(default_factory=list)


class AddTrackRequest(BaseModel):
    """Payload POST /playlists/{id}/tracks.

    `position` optionnel — si absent, le service insère en fin de liste.
    On ne force pas le client à fournir l'ordre pour un usage courant
    "ajouter à ma wishlist".
    """

    track_id: UUID
    position: int | None = Field(default=None, ge=0)
