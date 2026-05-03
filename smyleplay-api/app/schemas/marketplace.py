"""
Phase 9.2 — Schémas Pydantic marketplace (catalogue artiste).

Conventions strictes (alignées sur user.py / credit.py existants):
  - extra="forbid" sur tous les payloads input → refus des champs inconnus
  - str_strip_whitespace=True → trim auto sur tous les str entrants
  - Bornes encodées DEUX FOIS : Pydantic (réponse 422) ET DB CHECK (réponse 500
    si bypass). Cohérence garantie par les tests d'intégration Phase 9.5.
  - pack_eligible volontairement absent des payloads d'écriture Phase 9 :
    réservé Phase 10 (système de packs aléatoires), default DB = True.
  - Lock après vente : géré côté SERVICE (pas Pydantic) car nécessite query DB.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# -----------------------------------------------------------------------------
# Limites partagées (source unique pour Pydantic + tests)
# -----------------------------------------------------------------------------

ADN_PRICE_MIN = 30
ADN_PRICE_MAX = 500
ADN_DESCRIPTION_MIN = 200       # Cohérent avec ck_adns_description_min_length
ADN_DESCRIPTION_MAX = 5000      # Plafond applicatif (DB n'a pas de max)
ADN_USAGE_GUIDE_MAX = 3000
ADN_EXAMPLE_OUTPUTS_MAX = 5000

PROMPT_PRICE_MIN = 3
PROMPT_PRICE_MAX = 500          # Cohérent avec ADN (économique)
PROMPT_TITLE_MIN = 5
PROMPT_TITLE_MAX = 200          # Cohérent avec String(200) en DB
# Bornes prompt_text resserrées : Suno n'accepte pas plus de 1000 chars en
# entrée, vendre un prompt > 1000 chars reviendrait à vendre un prompt
# inutilisable. Le plancher 100 garantit un minimum de substance (≈ style +
# BPM + mood + 1-2 références). Cohérence totale : Pydantic ↔ DB CHECK
# ↔ validation JS côté dashboard.
PROMPT_TEXT_MIN = 100
PROMPT_TEXT_MAX = 1000
PROMPT_DESCRIPTION_MAX = 2000

# Paroles complètes du morceau (gated jusqu'à unlock côté backend, mais
# acceptées dans le payload de création — le front dashboard les envoie
# depuis longtemps mais Pydantic les rejetait silencieusement à cause de
# extra="forbid". Bug détecté lors du 1er test bout-en-bout achat prompt
# 2026-05-04). Plafond 4000 chars : largement assez pour un morceau
# vocal complet (chanson moyenne ≈ 2000 chars).
PROMPT_LYRICS_MAX = 4000


# -----------------------------------------------------------------------------
# ADN — Create / Update / Read
# -----------------------------------------------------------------------------

class AdnCreate(BaseModel):
    """
    Création ADN. 1 par artiste max (enforced DB via UniqueConstraint
    artist_id + check applicatif → 409 plutôt que 500 sur IntegrityError).

    is_published volontairement absent : un ADN se crée TOUJOURS en draft
    (is_published=False), publication via PATCH /artist/me/adn explicit.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str = Field(
        min_length=ADN_DESCRIPTION_MIN,
        max_length=ADN_DESCRIPTION_MAX,
        description="Signature créative de l'artiste (200..5000 chars).",
    )
    usage_guide: str | None = Field(
        default=None, max_length=ADN_USAGE_GUIDE_MAX
    )
    example_outputs: str | None = Field(
        default=None, max_length=ADN_EXAMPLE_OUTPUTS_MAX
    )
    price_credits: int = Field(
        ge=ADN_PRICE_MIN,
        le=ADN_PRICE_MAX,
        description=f"Prix en crédits ({ADN_PRICE_MIN}..{ADN_PRICE_MAX}).",
    )


class AdnUpdate(BaseModel):
    """
    PATCH ADN — option (b) : `description` figé après 1ère vente,
    enforce côté SERVICE (pas Pydantic, on doit query owned_adns).

    Tous les champs sont optionnels (PATCH partiel). Si un champ n'est pas
    fourni, on ne touche pas. Le service traduit `description` modifié
    après vente en HTTP 409.

    `last_updated_by_artist_at` est mis à jour automatiquement par le
    service quand un champ "contenu" change (description / usage_guide /
    example_outputs), mais PAS quand seul price_credits / is_published
    changent.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str | None = Field(
        default=None,
        min_length=ADN_DESCRIPTION_MIN,
        max_length=ADN_DESCRIPTION_MAX,
    )
    usage_guide: str | None = Field(
        default=None, max_length=ADN_USAGE_GUIDE_MAX
    )
    example_outputs: str | None = Field(
        default=None, max_length=ADN_EXAMPLE_OUTPUTS_MAX
    )
    price_credits: int | None = Field(
        default=None, ge=ADN_PRICE_MIN, le=ADN_PRICE_MAX
    )
    is_published: bool | None = None


class AdnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artist_id: UUID
    description: str
    usage_guide: str | None = None
    example_outputs: str | None = None
    price_credits: int
    is_published: bool
    created_at: datetime
    updated_at: datetime
    last_updated_by_artist_at: datetime | None = None


# -----------------------------------------------------------------------------
# Prompt — Create / Update / Read
# -----------------------------------------------------------------------------

# Enums P1-F4 (2026-05-04) — alignés avec ck_prompts_*_enum côté DB.
PromptPlatform = Literal[
    "suno", "udio", "riffusion", "stable_audio", "autre"
]
PromptVocalGender = Literal["masculin", "feminin", "instrumental"]


class PromptCreate(BaseModel):
    """
    Création prompt. Pré-requis (enforce SERVICE) : l'artiste doit avoir
    un ADN existant (même non publié — il peut préparer son catalogue
    avant de tout publier d'un coup).

    is_published absent (idem ADN : draft par défaut).
    pack_eligible absent : réservé Phase 10.

    P1-F4 (2026-05-04) : 4 nouveaux champs OBLIGATOIRES + 1 optionnel
    pour que le prompt soit reproductible côté acheteur (sans ces
    réglages, l'acheteur tape le texte dans Suno mais obtient une
    variante divergente — taux de conversion en chute).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(
        min_length=PROMPT_TITLE_MIN, max_length=PROMPT_TITLE_MAX
    )
    description: str | None = Field(
        default=None, max_length=PROMPT_DESCRIPTION_MAX
    )
    prompt_text: str = Field(
        min_length=PROMPT_TEXT_MIN, max_length=PROMPT_TEXT_MAX
    )
    # Paroles complètes — optionnel (instrumental possible). Gated jusqu'à
    # unlock côté response (jamais retourné par GET public).
    lyrics: str | None = Field(default=None, max_length=PROMPT_LYRICS_MAX)
    price_credits: int = Field(
        ge=PROMPT_PRICE_MIN, le=PROMPT_PRICE_MAX
    )
    # is_published acceptable au create — le front envoie true pour publier
    # immédiatement après upload track. Default False si absent.
    is_published: bool = False

    # ── Réglages génération (4 obligatoires + 1 optionnel) ───────────────
    prompt_platform: PromptPlatform
    prompt_model_version: str | None = Field(
        default=None, max_length=50
    )
    prompt_weirdness: str = Field(min_length=1, max_length=50)
    prompt_style_influence: str = Field(min_length=1, max_length=500)
    prompt_vocal_gender: PromptVocalGender


class PromptUpdate(BaseModel):
    """
    PATCH prompt — option (b) : `prompt_text` figé après 1ère vente
    (cohérent avec lock ADN sur description). Métadonnées + prix +
    publication restent éditables.

    Les 5 champs P1-F4 sont éditables tous le temps (l'artiste peut
    corriger une plateforme erronée même après vente — l'acheteur en
    bénéficie au prochain reload de /library).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(
        default=None, min_length=PROMPT_TITLE_MIN, max_length=PROMPT_TITLE_MAX
    )
    description: str | None = Field(
        default=None, max_length=PROMPT_DESCRIPTION_MAX
    )
    prompt_text: str | None = Field(
        default=None, min_length=PROMPT_TEXT_MIN, max_length=PROMPT_TEXT_MAX
    )
    # Paroles éditables au PATCH (l'artiste peut corriger une faute).
    lyrics: str | None = Field(default=None, max_length=PROMPT_LYRICS_MAX)
    price_credits: int | None = Field(
        default=None, ge=PROMPT_PRICE_MIN, le=PROMPT_PRICE_MAX
    )
    is_published: bool | None = None

    # ── Réglages génération (tous optionnels au PATCH) ───────────────────
    prompt_platform: PromptPlatform | None = None
    prompt_model_version: str | None = Field(default=None, max_length=50)
    prompt_weirdness: str | None = Field(
        default=None, min_length=1, max_length=50
    )
    prompt_style_influence: str | None = Field(
        default=None, min_length=1, max_length=500
    )
    prompt_vocal_gender: PromptVocalGender | None = None


class PromptRead(BaseModel):
    """
    Vue owner / library — le caller a le droit de voir lyrics.

    Pour la vue publique (visiteurs marketplace), utiliser les schemas
    de discovery.py (PromptPublicCard / PromptPublicDetail) qui
    n'exposent JAMAIS lyrics ni prompt_text. Cf règle Tom
    project_prompt_visibility_rule.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artist_id: UUID
    title: str
    description: str | None = None
    prompt_text: str
    # Paroles complètes — exposées dans cette vue (owner ou acheteur après
    # unlock). JAMAIS dans les vues publiques. Bug fix 2026-05-04 :
    # le frontend envoyait `lyrics` au create mais Pydantic rejetait
    # avec extra="forbid" — c'est ce qui bloquait le test bout-en-bout.
    lyrics: str | None = None
    price_credits: int
    is_published: bool
    pack_eligible: bool
    created_at: datetime
    updated_at: datetime
    # ── P1-F4 — réglages génération (None pour les anciens prompts) ──────
    prompt_platform: str | None = None
    prompt_model_version: str | None = None
    prompt_weirdness: str | None = None
    prompt_style_influence: str | None = None
    prompt_vocal_gender: str | None = None


class PromptsListResponse(BaseModel):
    """Liste paginée des prompts d'un artiste (own catalogue)."""

    items: list[PromptRead]
    total: int
    page: int
    per_page: int


# -----------------------------------------------------------------------------
# Brand color (profil artiste)
# -----------------------------------------------------------------------------

# Regex source unique : utilisée par Pydantic + cohérente avec
# CHECK constraint `^#[0-9A-Fa-f]{6}` côté DB. On ajoute le `$` côté
# Pydantic (la DB l'a déjà via `~` postgres anchored).
_BRAND_COLOR_REGEX = r"^#[0-9A-Fa-f]{6}$"


class BrandColorUpdate(BaseModel):
    """
    Mise à jour de la couleur signature de l'artiste.

    Normalisation : uppercase systématique avant validation/stockage,
    sinon `#cc00ff` et `#CC00FF` créeraient des "doublons" sémantiques.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    brand_color: str | None = Field(
        default=None,
        pattern=_BRAND_COLOR_REGEX,
        description="Hex color #RRGGBB (case-insensitive, normalisé en MAJ).",
    )

    @field_validator("brand_color")
    @classmethod
    def normalize_uppercase(cls, v: str | None) -> str | None:
        return v.upper() if v else v
