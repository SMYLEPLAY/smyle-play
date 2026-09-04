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

from pydantic import BaseModel, ConfigDict, Field


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
    """Carte + métadonnées teaser (avant achat) : plateforme, modèle, présence
    de paroles. Le prompt_text et les paroles restent gated (pas exposés ici) ;
    ces champs servent juste l'argumentaire de vente sur la fiche."""

    platform: str | None = None        # ex: "suno"
    model_version: str | None = None   # ex: "v5.5"
    has_lyrics: bool = False           # paroles incluses (sans les révéler)


class PromptCatalogResponse(BaseModel):
    items: list[PromptPublicCard]
    total: int
    page: int
    per_page: int


# -----------------------------------------------------------------------------
# ADN — vues publiques (PAS de génome : ni description, ni usage_guide,
# ni example_outputs)
# -----------------------------------------------------------------------------

class AdnPublicCard(BaseModel):
    """
    Vignette ADN publique. S-04 sécurité (2026-09-02) : `description` (le
    génome vendu), `usage_guide` et `example_outputs` sont GATED — le
    catalogue n'expose que la longueur et des booléens de présence, comme
    la page artiste (`/watt/artists/{slug}` → characterCount/hasUsageGuide/
    hasExampleOutputs). Le contenu complet ne sort que par `LibraryAdnItem`
    (`/me/library/adns`, possession vérifiée).
    """

    id: UUID
    artist: ArtistPublicCard
    description_length: int
    has_usage_guide: bool
    has_example_outputs: bool
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
    """
    Un prompt débloqué possédé par l'utilisateur, contenu complet.

    Évolution Sprint 1 PR3 (2026-05-04) : on expose maintenant les
    réglages de génération P1-F4 *gated* (weirdness + style_influence)
    qui sont retirés de la vue publique. Le payload library devient
    le seul endroit où l'acheteur les voit, après paiement.
    Plateforme + modèle + vocal_gender restent dupliqués ici pour
    tout regrouper dans la fiche library (UX cohérente).
    """

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
    # P1-F4 — réglages génération (gated weirdness + style_influence)
    prompt_platform: str | None = None
    prompt_model_version: str | None = None
    prompt_weirdness: str | None = None       # ← gated, révélé après unlock
    prompt_style_influence: str | None = None  # ← gated, révélé après unlock
    prompt_vocal_gender: str | None = None
    # P1-B8 (2026-05-11) — audio + cover du track lié au prompt.
    # NULL si aucun track lié (ancien prompt sans audio attaché).
    # Frontend : si audio_url présent → afficher player ; sinon masquer.
    audio_url: str | None = None
    cover_url: str | None = None
    # Couleur du track lié — repère visuel cohérent avec la marketplace.
    # NULL si aucun track lié ou si le track n'a pas de couleur définie.
    track_color: str | None = None
    # Marché secondaire (2026-06-08) : prix de revente courant. NULL = pas en
    # vente. Permet à la bibliothèque d'afficher l'état "en vente" + le prix.
    resale_price: int | None = None
    # #X/N (2026-06-09) — numéro d'exemplaire possédé + taille d'édition.
    # edition_number NULL = tirage illimité → le front n'affiche pas de badge.
    edition_number: int | None = None
    max_supply: int | None = None
    # Beats (2026-06-09) — 'recipe' | 'beat'. Sur un beat possédé, le front
    # affiche le bouton Télécharger (download gaté).
    product_type: str | None = None
    license_type: str | None = None
    # C4 galerie avatar — pour une IMAGE possédée, galerie complète : par item
    # {id, previewKey (apercu), position, downloadUrl (route GATÉE de l'original
    # /images/{id}/gallery/{gid}/download)}. [] pour l'audio. Le front itère sur
    # `gallery` pour télécharger tout le set à l'achat. L'original lui-même n'est
    # JAMAIS sérialisé — uniquement le chemin de download gaté.
    gallery: list[dict] = Field(default_factory=list)


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


# -----------------------------------------------------------------------------
# Voix publiques (catalog marketplace — sans sample_url gated)
# -----------------------------------------------------------------------------

class VoicePublicCard(BaseModel):
    """
    Vignette voix dans un listing public.
    `sample_url` (full) est gated — seul `preview_url` (30s) est exposé.
    """

    id: UUID
    artist: ArtistPublicCard
    name: str
    style: str
    genres: list[str] = []
    license: str
    price_credits: int
    preview_url: str | None = None  # clip 30s public ; None = pas encore uploadé


class VoiceCatalogResponse(BaseModel):
    items: list[VoicePublicCard]
    total: int
    page: int
    per_page: int


# -----------------------------------------------------------------------------
# Playlists ADN publiques (catalog marketplace — adn_for_sale=True)
# -----------------------------------------------------------------------------

class PlaylistAdnCard(BaseModel):
    """
    Vignette playlist dont l'ADN est en vente.
    N'expose pas le contenu détaillé des tracks (juste le titre + prix ADN).
    """

    id: UUID
    owner: ArtistPublicCard
    title: str
    color: str | None = None
    adn_price: int


class PlaylistAdnCatalogResponse(BaseModel):
    items: list[PlaylistAdnCard]
    total: int
    page: int
    per_page: int


# -----------------------------------------------------------------------------
# Albums ADN publics (catalog marketplace — génome de style visuel en vente)
# -----------------------------------------------------------------------------

class AlbumAdnCard(BaseModel):
    """
    Vignette album dont l'ADN (génome de style) est en vente.
    GATING : n'expose que le teaser (dna_description, adn_style) + prix.
    Le génome (seed_prompt + adn_palette) n'est révélé qu'après achat.
    """

    id: UUID
    owner: ArtistPublicCard
    title: str
    dna_description: str | None = None
    adn_style: str | None = None
    adn_price: int


class AlbumAdnCatalogResponse(BaseModel):
    items: list[AlbumAdnCard]
    total: int
    page: int
    per_page: int
