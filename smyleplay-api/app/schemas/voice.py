"""
Schémas Pydantic pour les endpoints `/api/voices` et `/unlocks/voices/*`.

Pourquoi 2 shapes (Public / OwnerOrUnlocked) :

  - Sur le profil public `/u/<slug>`, un visiteur voit la fiche de la voix
    (nom, style, genres, licence, prix) MAIS pas le `sample_url` — règle
    Tom (project_prompt_visibility_rule) : prompts/ADN/voix verrouillés
    publiquement, teaser métadonnées uniquement.
  - Une fois la voix unlockée OU si l'utilisateur en est l'artiste,
    l'API renvoie aussi `sample_url`. Cette logique est portée par les
    services (qui choisissent quel schéma renvoyer), les schemas eux ne
    "filtrent" pas — ils décrivent juste les 2 formes possibles.

Validation :
  - `price_credits` : 50-5000 (aligné migration + modèle)
  - `name` : 1-40 chars
  - `style` : 1-80 chars
  - `genres` : array de strings, max 10 entrées
  - `license` : enum 'personnel' / 'commercial' / 'exclusif'
  - `sample_url` : URL valide, max 500 chars

Enrichissement artist (2026-05-03 — feat/voices-enriched-payload) :
  - VoicePublicRead et VoiceFullRead exposent désormais un sous-objet
    `artist` avec id + artist_name + slug + brand_color. Permet à
    /library d'afficher "par <Artiste>" + lien /u/<slug> sans 2e fetch.
  - artist est `None` uniquement si la query backend n'a pas pu joindre
    le User (cas extrême, FK CASCADE devrait l'empêcher en pratique).
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.schemas.credit import TransactionRead


# Type literal aligné avec models.voice.VOICE_LICENSES et la CHECK constraint.
VoiceLicense = Literal["personnel", "commercial", "exclusif"]


# -----------------------------------------------------------------------------
# Sous-objet artist embarqué dans Voice*Read
# -----------------------------------------------------------------------------

class VoiceArtistInfo(BaseModel):
    """
    Infos minimales sur l'artiste pour afficher correctement la voix côté
    front (/library, page profil, etc.) sans 2e round-trip.

    On limite volontairement aux champs nécessaires à l'affichage card :
      - `id` pour clé React éventuelle / déduplication
      - `artist_name` pour le nom affiché
      - `slug` pour construire un lien /u/<slug>
      - `brand_color` pour la coloration de la card

    Pas de bio / avatar_url / socials ici — si le front en a besoin il
    fait un fetch dédié /watt/artists/<slug>.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artist_name: str | None = None
    slug: str | None = None
    brand_color: str | None = None


# -----------------------------------------------------------------------------
# Payload d'entrée — POST /api/voices
# -----------------------------------------------------------------------------

class VoiceCreate(BaseModel):
    """
    Création d'une voix à vendre. L'artiste vient du JWT, jamais du body.
    `is_published` n'est PAS dans le payload de création — création = brouillon
    par défaut. La publication passe par PATCH dédié pour un toggle explicite.
    """

    name: str = Field(min_length=1, max_length=40)
    style: str = Field(min_length=1, max_length=80)
    genres: list[str] = Field(default_factory=list, max_length=10)
    sample_url: HttpUrl = Field(max_length=500)
    license: VoiceLicense
    price_credits: int = Field(ge=50, le=5000)


class VoiceUpdate(BaseModel):
    """
    Patch d'une voix. Tous les champs optionnels — l'artiste peut toggler
    `is_published` indépendamment, ou changer le prix sans toucher au reste.
    """

    name: str | None = Field(default=None, min_length=1, max_length=40)
    style: str | None = Field(default=None, min_length=1, max_length=80)
    genres: list[str] | None = Field(default=None, max_length=10)
    sample_url: HttpUrl | None = Field(default=None, max_length=500)
    license: VoiceLicense | None = None
    price_credits: int | None = Field(default=None, ge=50, le=5000)
    is_published: bool | None = None


# -----------------------------------------------------------------------------
# Read shapes — public (gated) vs owner/unlocked
# -----------------------------------------------------------------------------

class VoicePublicRead(BaseModel):
    """
    Vue publique d'une voix (visiteur non-acheteur, profil /u/<slug>).
    PAS de `sample_url` — gated jusqu'à l'unlock.

    `artist` est optionnel pour rétrocompat — un client legacy qui ne
    consomme pas ce champ ignore simplement la clé. Les nouveaux endpoints
    le remplissent toujours (cf services.voices.enrich_voices_with_artist).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artist_id: UUID
    artist: VoiceArtistInfo | None = None
    name: str
    style: str
    genres: list[str]
    license: VoiceLicense
    price_credits: int
    is_published: bool
    created_at: datetime


class VoiceFullRead(VoicePublicRead):
    """
    Vue complète : ajoute `sample_url`. Renvoyée à l'artiste sur ses propres
    voix, ou à un acheteur après unlock (via /api/voices/me/unlocked et
    /api/voices/{id} avec auth si owned).
    """

    sample_url: str
    updated_at: datetime


# -----------------------------------------------------------------------------
# Unlock — owned + transaction (parallèle aux schemas ADN/Prompt)
# -----------------------------------------------------------------------------

class OwnedVoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    voice_id: UUID
    owned_at: datetime


class UnlockVoiceResponse(BaseModel):
    """
    Réponse à POST /unlocks/voices/{voice_id}. Pas de perk applicable
    (le perk -30% est réservé aux prompts pour les détenteurs d'ADN).
    """

    owned_voice: OwnedVoiceRead
    transaction: TransactionRead
    paid: int
    # Sample URL renvoyée immédiatement après unlock pour que le front
    # puisse proposer le téléchargement sans 2e round-trip.
    sample_url: str
