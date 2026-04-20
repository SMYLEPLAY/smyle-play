"""
Phase 9.4 — Schémas Pydantic pour découverte (catalogue public) et library
(contenu possédé).

Règle de gating critique :
  - Vues publiques  : on EXCLUT le contenu "premium" (prompt_text, example_outputs)
  - Vues library    : on EXPOSE tout, car le user a payé pour
  - Vue artiste self-edit (/artist/me/*) : déjà couverte par schemas/marketplace.py

Les schémas publics sont volontairement minimaux et stables : ils servent de
"contrat affiché" et ne doivent pas fuiter d'info qui pourrait être utilisée
pour bypass un unlock.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# -----------------------------------------------------------------------------
# Carte artiste publique (réutilisée dans tous les listings)
# -----------------------------------------------------------------------------

class ArtistPublicCard(BaseModel):
    """
    Vue publique minimale d'un artiste. Pas d'email, pas de bio longue,
    juste ce qui sert à rendre une vignette ou un crédit.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artist_name: str  # garanti non-null par les filters côté query
    slug: str | None = None  # dérivé côté service, utile pour URL /artiste/<slug>
    brand_color: str | None = None
    avatar_url: str | None = None


class ArtistPublicProfile(BaseModel):
    """
    Vue publique enrichie d'un artiste (page profil dédiée).
    Aggrégats has_adn / prompts_published_count calculés côté service.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artist_name: str
    bio: str | None = None
    universe_description: str | None = None
    brand_color: str | None = None
    avatar_url: str | None = None
    has_adn: bool
    prompts_published_count: int


class ArtistsListResponse(BaseModel):
    items: list[ArtistPublicCard]
    total: int
    page: int
    per_page: int


# -----------------------------------------------------------------------------
# Prompt — vues publiques (PAS de prompt_text)
# -----------------------------------------------------------------------------

class PromptPublicCard(BaseModel):
    """
    Vignette prompt dans un listing public. SURTOUT pas de prompt_text :
    c'est ce qui justifie l'achat.
    """

    id: UUID
    title: str
    description: str | None = None
    price_credits: int
    artist: ArtistPublicCard
    created_at: datetime


class PromptPublicDetail(PromptPublicCard):
    """Identique à la card pour Phase 9 — extensible plus tard (popularité, tags…)."""

    pass


class PromptCatalogResponse(BaseModel):
    items: list[PromptPublicCard]
    total: int
    page: int
    per_page: int


# -----------------------------------------------------------------------------
# ADN — vues publiques (PAS de example_outputs)
# -----------------------------------------------------------------------------

class AdnPublicCard(BaseModel):
    """
    Vignette ADN. `description` et `usage_guide` sont publiques (le buyer
    doit savoir ce qu'il achète). `example_outputs` est gated.
    """

    id: UUID
    artist: ArtistPublicCard
    description: str
    usage_guide: str | None = None
    price_credits: int


class AdnPublicDetail(AdnPublicCard):
    pass


class AdnCatalogResponse(BaseModel):
    items: list[AdnPublicCard]
    total: int
    page: int
    per_page: int


# -----------------------------------------------------------------------------
# Effective price preview (compute perk pour current_user, sans unlock)
# -----------------------------------------------------------------------------

class EffectivePricePreview(BaseModel):
    """
    Réponse à GET /me/effective-price/prompts/{id}.
    Permet à l'UI d'afficher "10 → 7 crédits (perk -30%)" sans déclencher
    l'achat. Auth requis car le perk dépend du user.
    """

    base_price: int
    paid: int
    perk_applied: bool


# -----------------------------------------------------------------------------
# Library — contenu PAYÉ, donc tout exposé (prompt_text + example_outputs)
# -----------------------------------------------------------------------------

class LibraryPromptItem(BaseModel):
    """Un prompt débloqué possédé par l'utilisateur, contenu complet."""

    unlocked_id: UUID  # id du UnlockedPrompt (utile Phase 10 pour transferts)
    unlocked_at: datetime
    prompt_id: UUID
    title: str
    description: str | None = None
    prompt_text: str  # ← contenu gated, accessible car possédé
    lyrics: str | None = None  # ← gated, nullable (instrumental vs vocal)
    price_credits: int  # prix payé au moment du unlock (cohérence catalog)
    created_at: datetime  # date de création du prompt (cohérence catalog)
    artist: ArtistPublicCard


class LibraryPromptsResponse(BaseModel):
    items: list[LibraryPromptItem]
    total: int
    page: int
    per_page: int


class LibraryAdnItem(BaseModel):
    """Un ADN possédé, contenu complet."""

    adn_id: UUID
    owned_at: datetime
    description: str
    usage_guide: str | None = None
    example_outputs: str | None = None  # ← contenu gated, accessible car possédé
    price_credits: int
    artist: ArtistPublicCard


class LibraryAdnsResponse(BaseModel):
    items: list[LibraryAdnItem]
    total: int
    page: int
    per_page: int
