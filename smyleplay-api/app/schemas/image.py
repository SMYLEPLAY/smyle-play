"""
Schémas Images IA (C4 Monde Visuel V1, 2026-06-14).

Une "image" est un produit vendable de la même table `prompts`
(product_type='image'). Différence clé vs recette/beat : pas de Track —
le fichier (original + aperçu) vit sur la ligne `prompts`. La recette
(prompt_text) est gatée derrière l'achat. Achat/possession/revente/royalties
réutilisent toute la machinerie des prompts (UnlockedPrompt,
unlock_prompt_atomic, mint #X/N).

Visibilité (règle Tom — prompts jamais visibles sans achat) :
  - Lecture PUBLIQUE (ImagePublicRead) : aperçu + provenance + métadonnées
    SEULEMENT. JAMAIS image_r2_key ni prompt_text ni image_settings.
  - Lecture OWNER/après-achat (ImageOwnerRead) : recette complète + settings
    + provenance, et autorise le download de l'original.
"""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.marketplace import (
    PROMPT_DESCRIPTION_MAX,
    PROMPT_PRICE_MAX,
    PROMPT_PRICE_MIN,
    PROMPT_TITLE_MAX,
    PROMPT_TITLE_MIN,
)

# 4 plateformes + Autre (décision Tom 2026-06-14). Pas d'images de référence
# en V1. La validation enum est portée côté Pydantic ; la DB ne contraint que
# la présence (NOT NULL) via ck_prompts_image_provenance.
ImagePlatform = Literal["midjourney", "dalle", "stable_diffusion", "flux", "autre"]

# Borne lâche sur le prompt d'image : NOT NULL mais sans plafond strict
# (un prompt d'image peut faire 3 mots comme 500). On garde un plafond
# technique généreux pour éviter les abus / payloads géants.
IMAGE_PROMPT_MIN = 1
IMAGE_PROMPT_MAX = 5000
IMAGE_NEGATIVE_PROMPT_MAX = 5000
IMAGE_MODEL_VERSION_MAX = 100
IMAGE_RATIO_MAX = 20


class ImageCreate(BaseModel):
    """
    Création d'une image IA à vendre.

    Le fichier lui-même est transmis en multipart (UploadFile côté router) ;
    ce schéma porte les CHAMPS texte/numériques du formulaire. Le router
    construit ce modèle à partir des Form() avant d'appeler le service.

    - `prompt_text` obligatoire, sans borne (NOT NULL côté DB pour image).
    - `image_platform` + `image_model_version` = provenance obligatoire.
    - `image_settings` : JSON libre (steps, cfg, seed, sampler...).
    - `max_supply` : édition limitée #X/N (None = illimité, 1 = pièce unique).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=PROMPT_TITLE_MIN, max_length=PROMPT_TITLE_MAX)
    description: str | None = Field(default=None, max_length=PROMPT_DESCRIPTION_MAX)
    prompt_text: str = Field(min_length=IMAGE_PROMPT_MIN, max_length=IMAGE_PROMPT_MAX)
    image_platform: ImagePlatform
    image_model_version: str = Field(min_length=1, max_length=IMAGE_MODEL_VERSION_MAX)
    image_settings: dict[str, Any] | None = None
    negative_prompt: str | None = Field(default=None, max_length=IMAGE_NEGATIVE_PROMPT_MAX)
    # Ratio/format affiché (ex "1:1", "16:9") — purement descriptif, optionnel.
    ratio: str | None = Field(default=None, max_length=IMAGE_RATIO_MAX)
    price_credits: int = Field(ge=PROMPT_PRICE_MIN, le=PROMPT_PRICE_MAX)
    max_supply: int | None = Field(default=None, ge=1)
    is_published: bool = False


class ImageUpdate(BaseModel):
    """
    Édition des métadonnées de VENTE d'une image (owner only, C4 ④).

    V1 : titre / description / prix / publication. On ne touche NI au fichier
    (image_r2_key / preview_r2_key) NI au prompt_text / image_settings —
    re-uploader une image = en créer une nouvelle. Tous les champs sont
    optionnels (PATCH partiel) ; on applique seulement ceux fournis.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=PROMPT_TITLE_MIN, max_length=PROMPT_TITLE_MAX)
    description: str | None = Field(default=None, max_length=PROMPT_DESCRIPTION_MAX)
    price_credits: int | None = Field(default=None, ge=PROMPT_PRICE_MIN, le=PROMPT_PRICE_MAX)
    is_published: bool | None = None
    # ── Taxonomie visuelle (C4 DNA image, migration 0061) — éditables ──────
    # style : code unique parmi STYLES (router). tags : CSV de codes parmi
    # USAGE_TAGS (incl. 'fx'). Validation souple côté router (valeurs hors-liste
    # ignorées). Le champ reçu est brut (str) ; "" autorisé pour effacer.
    image_style: str | None = Field(default=None, max_length=40)
    image_tags: str | None = Field(default=None, max_length=255)


class ImagePublicRead(BaseModel):
    """
    Lecture PUBLIQUE (visiteur / acheteur potentiel).

    N'expose JAMAIS image_r2_key, prompt_text, image_settings ni
    negative_prompt. Seulement l'aperçu + provenance + métadonnées de vente.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    artist_id: UUID
    title: str
    description: str | None = None
    product_type: str
    image_platform: str | None = None
    image_model_version: str | None = None
    # Clé de l'aperçu public uniquement (l'original image_r2_key est OMIS).
    preview_r2_key: str | None = None
    price_credits: int
    max_supply: int | None = None
    is_published: bool
    created_at: datetime
    # C4 Taxonomie visuelle (DNA image, migration 0061) — champs PUBLICS.
    # style : code de rendu (image_style) ou None. tags : liste de codes
    # d'usage dérivée de la CSV image_tags (incl. 'fx'). Le router renseigne
    # `tags` (liste) dans _image_public_dict pour les listings ; ici on garde
    # le mapping ORM pour les payloads validés directement (create/update PATCH
    # qui renvoient ImageOwnerRead.model_validate). Alias camelCase pour le front.
    style: str | None = Field(default=None, validation_alias="image_style")
    tags: list[str] = Field(default_factory=list)
    # C4 « Oeuvre complete » — partenaire SON lie (apercu public uniquement :
    # id/titre/cover/prix/productType). None si l'image n'est pas liee.
    # isOeuvreComplete est un raccourci front (= linkedSound is not None).
    # Peuple a posteriori par le router (requete Track), pas par model_validate.
    linkedSound: dict | None = None
    isOeuvreComplete: bool = False
    # Nature du lien (migration 0059). True = « ne ensemble » : cette image
    # ne s'affiche PAS en carte individuelle sur les surfaces publiques (les
    # listings publics la filtrent en amont) ; elle n'apparait que via
    # l'oeuvre. La vue OWNER l'affiche quand meme — le front s'en sert pour
    # ne pas dupliquer l'affichage. Peuple depuis l'attribut ORM
    # bundle_exclusive via model_validate (alias camelCase pour le front).
    bundleExclusive: bool = Field(default=False, validation_alias="bundle_exclusive")


class ImageOwnerRead(ImagePublicRead):
    """
    Lecture OWNER / après-achat : la recette complète est dévoilée.

    Ajoute prompt_text + image_settings + negative_prompt. N'expose toujours
    PAS image_r2_key directement (le download passe par l'endpoint gaté
    /images/{id}/download qui vérifie la possession à chaque appel).
    """

    # populate_by_name conservé (hérité de ImagePublicRead) pour que les alias
    # de validation (bundle_exclusive, image_style) marchent + qu'on puisse
    # réassigner par nom Python (model.tags = ...) après model_validate.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    prompt_text: str | None = None
    image_settings: dict[str, Any] | None = None
    negative_prompt: str | None = None
