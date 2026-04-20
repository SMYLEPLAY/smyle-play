"""
Phase 9.4 — Catalogue public + preview prix personnalisé.

Routes :
  GET  /catalog/artists                       (public)
  GET  /catalog/artists/{artist_id}           (public)
  GET  /catalog/prompts                       (public, filtre artist_id optionnel)
  GET  /catalog/prompts/{prompt_id}           (public)
  GET  /catalog/adns                          (public, filtre artist_id optionnel)
  GET  /catalog/adns/{adn_id}                 (public)
  GET  /me/effective-price/prompts/{id}       (auth — calcule perk pour current_user)

Le contenu gated (prompt_text, example_outputs) n'est JAMAIS exposé ici.
Pour y accéder : passer par /me/library/* après unlock.

Note : effective-price est mis sous `/me/*` (avec auth) plutôt que
`/catalog/*` parce qu'il dépend du user. C'est cohérent avec le pattern
"tout ce qui dépend du JWT vit sous /me".
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.discovery import (
    AdnCatalogResponse,
    AdnPublicDetail,
    ArtistPublicProfile,
    ArtistsListResponse,
    EffectivePricePreview,
    PromptCatalogResponse,
    PromptPublicDetail,
)
from app.services.credits import compute_effective_price
from app.services.discovery import (
    _artist_card,
    get_public_adn,
    get_public_artist_profile,
    get_public_prompt,
    list_public_adns,
    list_public_artists,
    list_public_prompts,
)
from app.services.marketplace import user_owns_artist_adn

# Router public — pas de Depends d'auth au niveau du router
catalog_router = APIRouter(prefix="/catalog", tags=["catalog"])

# Router /me — auth requis (effective-price)
me_pricing_router = APIRouter(prefix="/me", tags=["pricing"])


# -----------------------------------------------------------------------------
# Artistes publics
# -----------------------------------------------------------------------------

@catalog_router.get("/artists", response_model=ArtistsListResponse)
async def list_artists(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_public_artists(
        db, page=page, per_page=per_page
    )
    return ArtistsListResponse(
        items=[_artist_card(u) for u in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@catalog_router.get("/artists/{artist_id}", response_model=ArtistPublicProfile)
async def get_artist_profile(
    artist_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    profile = await get_public_artist_profile(db, artist_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Artist not found")
    return profile


# -----------------------------------------------------------------------------
# Prompts publics
# -----------------------------------------------------------------------------

@catalog_router.get("/prompts", response_model=PromptCatalogResponse)
async def list_prompts(
    artist_id: UUID | None = Query(None, description="Filtre par artiste"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_public_prompts(
        db, artist_id=artist_id, page=page, per_page=per_page
    )
    return PromptCatalogResponse(
        items=items, total=total, page=page, per_page=per_page
    )


@catalog_router.get("/prompts/{prompt_id}", response_model=PromptPublicDetail)
async def get_prompt(
    prompt_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    detail = await get_public_prompt(db, prompt_id)
    if detail is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Prompt not found or not published"
        )
    return detail


# -----------------------------------------------------------------------------
# ADN publics
# -----------------------------------------------------------------------------

@catalog_router.get("/adns", response_model=AdnCatalogResponse)
async def list_adns(
    artist_id: UUID | None = Query(None, description="Filtre par artiste"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_public_adns(
        db, artist_id=artist_id, page=page, per_page=per_page
    )
    return AdnCatalogResponse(
        items=items, total=total, page=page, per_page=per_page
    )


@catalog_router.get("/adns/{adn_id}", response_model=AdnPublicDetail)
async def get_adn(
    adn_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    detail = await get_public_adn(db, adn_id)
    if detail is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="ADN not found or not published"
        )
    return detail


# -----------------------------------------------------------------------------
# Effective price preview (auth requis)
# -----------------------------------------------------------------------------

@me_pricing_router.get(
    "/effective-price/prompts/{prompt_id}",
    response_model=EffectivePricePreview,
)
async def get_effective_price_for_prompt(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne le prix effectif que paierait `current_user` s'il achetait
    `prompt_id` MAINTENANT, en appliquant le perk -30% si éligible.

    N'effectue AUCUNE mutation — juste un calcul. Sert à l'UI pour
    afficher le prix barré + le prix réduit avant l'achat.

    404 si le prompt n'existe pas ou n'est pas publié (anti-énumération).
    """
    detail = await get_public_prompt(db, prompt_id)
    if detail is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Prompt not found or not published"
        )

    # Self-purchase : pas d'erreur ici (c'est juste un preview), mais le perk
    # ne s'applique pas (un artiste possède implicitement son propre univers).
    # On retourne base_price=paid pour clarté.
    artist_id = detail["artist"]["id"]
    if current_user.id == artist_id:
        return EffectivePricePreview(
            base_price=detail["price_credits"],
            paid=detail["price_credits"],
            perk_applied=False,
        )

    perk_applied = await user_owns_artist_adn(
        db, user_id=current_user.id, artist_id=artist_id
    )
    paid = compute_effective_price(detail["price_credits"], perk_applied)
    return EffectivePricePreview(
        base_price=detail["price_credits"],
        paid=paid,
        perk_applied=perk_applied,
    )
