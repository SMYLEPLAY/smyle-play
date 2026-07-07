"""
Schémas Pydantic pour l'API Album d'images (chantier C4 My Mix).

Équivalent VISUEL des schémas Playlist (app/schemas/playlist.py). Un album est
une curation perso d'images (product_type='image') NON vendable — aucun champ
prix/rareté/ADN.

Conventions :
  - `visibility` est une Literal[...] (cohérent avec le CHECK SQL), comme les
    playlists.
  - Les projections de LECTURE (`AlbumRead`, `AlbumWithImages`) exposent le
    front en camelCase via des alias (coverPreviewKey / imageCount / createdAt),
    aligné sur la convention des schémas image (populate_by_name + alias).
  - `AlbumRead` reste léger (métadonnées + imageCount) pour "liste mes albums".
    Le détail des images est fourni via `AlbumWithImages`.
  - Anti-fuite : les images d'un album ne sont JAMAIS exposées en entier ici —
    le router renvoie des aperçus PUBLICS (dict léger), jamais prompt_text /
    image_r2_key / image_settings / negative_prompt.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


Visibility = Literal["public", "private"]


class AlbumCreate(BaseModel):
    """Payload création d'un album d'images."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    visibility: Visibility = "private"


class AlbumUpdate(BaseModel):
    """Patch partiel d'un album (PATCH /albums/{id})."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    visibility: Visibility | None = None
    # Image de couverture optionnelle (id d'une ligne prompts product_type=
    # 'image'). None explicite NON distinguable de "non fourni" en PATCH — on
    # ne permet pas de "retirer" la couverture via ce champ ; retirer l'image
    # de l'album OU supprimer l'image (ON DELETE SET NULL) remet à NULL.
    cover_prompt_id: UUID | None = None

    # ─── ADN Album — mise en vente / édition du génome (owner only) ────────
    # Calque STRICT du PATCH ADN Playlist. Tous optionnels (PATCH partiel) ;
    # un champ absent = inchangé. RAPPEL : l'ADN ne se vend QUE si l'album est
    # public ET adn_for_sale=True ET adn_price IS NOT NULL (le front doit
    # exposer ces réglages explicitement).
    seed_prompt: str | None = Field(default=None, max_length=10000)
    dna_description: str | None = Field(default=None, max_length=2000)
    adn_style: str | None = Field(default=None, max_length=40)
    adn_palette: str | None = Field(default=None, max_length=255)
    adn_for_sale: bool | None = None
    adn_price: int | None = Field(default=None, ge=1)
    # OFFRES-ADN étape 5 : plancher CACHÉ (owner only). WRITE-ONLY — jamais
    # exposé dans AlbumRead (servi aussi en public). 0 = pas de plancher.
    adn_reserve_credits: int | None = Field(default=None, ge=0, le=100_000)


class AlbumRead(BaseModel):
    """Projection "liste" : métadonnées + nb d'images, sans charger les images.

    Sérialisé en camelCase pour le front (coverPreviewKey / imageCount /
    createdAt). `imageCount` et `coverPreviewKey` sont remplis par les routeurs
    liste (requêtes groupées) — défauts neutres pour rétro-compat.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    owner_id: UUID = Field(serialization_alias="ownerId")
    title: str
    visibility: Visibility
    # Clé d'aperçu PUBLIC de la couverture (preview_r2_key de l'image de
    # couverture). JAMAIS l'original. None si pas de couverture résolue.
    cover_preview_key: str | None = Field(
        default=None, serialization_alias="coverPreviewKey"
    )
    image_count: int = Field(default=0, serialization_alias="imageCount")
    # Collections Phase A (07/07) : slug d'appariement Œuvre — camelCase front.
    oeuvre_slug: str | None = Field(
        default=None, serialization_alias="oeuvreSlug"
    )
    created_at: datetime = Field(serialization_alias="createdAt")


class AlbumWithImages(AlbumRead):
    """Projection "détail" : AlbumRead + la liste des aperçus PUBLICS d'images.

    `images` est une liste de dicts d'aperçu public (id / previewKey / title /
    priceCredits / productType), construite par le router via le helper
    anti-fuite. AUCUN champ gaté n'est exposé.

    ADN Album (calque ADN Playlist) :
      - adnForSale / adnPrice / adnStyle / dnaDescription : TOUJOURS exposés
        (teaser — ils décrivent l'offre sans révéler le génome).
      - seedPrompt / adnPalette : GATÉS — le génome. Le router les renvoie
        NULL si l'album est en vente (adn_for_sale) ET que le viewer n'est ni
        l'owner ni détenteur de l'ADN. Révélés à l'owner / acheteur uniquement.
    """

    images: list[dict] = Field(default_factory=list)

    adn_for_sale: bool = Field(default=False, serialization_alias="adnForSale")
    adn_price: int | None = Field(default=None, serialization_alias="adnPrice")
    adn_style: str | None = Field(default=None, serialization_alias="adnStyle")
    dna_description: str | None = Field(
        default=None, serialization_alias="dnaDescription"
    )
    # Génome — gaté par le router (NULL si en vente et viewer non autorisé).
    adn_palette: str | None = Field(
        default=None, serialization_alias="adnPalette"
    )
    seed_prompt: str | None = Field(
        default=None, serialization_alias="seedPrompt"
    )


class AddImageRequest(BaseModel):
    """Payload POST /albums/{id}/images.

    `position` optionnel — si absent, le service insère en fin de liste.
    """

    prompt_id: UUID
    position: int | None = Field(default=None, ge=0)
