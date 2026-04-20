"""
Phase 9.2 — Endpoints catalogue artiste.

Routes (toutes scope `/artist/me`, JWT requis) :
  GET    /artist/me/adn                  → mon ADN (404 si pas créé)
  POST   /artist/me/adn                  → créer mon ADN (1 max → 409 sinon)
  PATCH  /artist/me/adn                  → maj mon ADN (lock description après vente)

  GET    /artist/me/prompts              → liste paginée mes prompts (drafts + publiés)
  POST   /artist/me/prompts              → créer un prompt (404 si pas d'ADN)
  GET    /artist/me/prompts/{id}         → un de mes prompts (404 si pas mien)
  PATCH  /artist/me/prompts/{id}         → maj un prompt (lock prompt_text après vente)

  PATCH  /artist/me/brand-color          → ma couleur signature (#RRGGBB, normalisée MAJ)

Convention de gestion d'erreurs (alignée sur credits.py existant) :
  - ValueError métier → 400 (default) / 404 / 409 selon sous-type
  - IntegrityError DB → 409 (course critique non rattrapée par check applicatif)
  - Autre Exception   → 500 + rollback
Le commit final est dans le router (jamais dans le service).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.marketplace import (
    AdnCreate,
    AdnRead,
    AdnUpdate,
    BrandColorUpdate,
    PromptCreate,
    PromptRead,
    PromptsListResponse,
    PromptUpdate,
)
from app.schemas.user import UserRead
from app.services.marketplace import (
    AdnAlreadyExists,
    AdnNotFound,
    ContentLockedAfterSale,
    PromptNotFound,
    create_adn,
    create_prompt,
    get_adn_by_artist,
    get_prompt_for_artist,
    list_prompts_for_artist,
    update_adn,
    update_prompt,
)

router = APIRouter(prefix="/artist/me", tags=["artist-catalog"])


# -----------------------------------------------------------------------------
# Helper: traduit les exceptions métier en HTTPException
# -----------------------------------------------------------------------------

def _raise_marketplace_error(exc: ValueError) -> None:
    """Mappe les sous-types ValueError → status code HTTP."""
    if isinstance(exc, AdnAlreadyExists):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, AdnNotFound) or isinstance(exc, PromptNotFound):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ContentLockedAfterSale):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


# -----------------------------------------------------------------------------
# ADN
# -----------------------------------------------------------------------------

@router.get("/adn", response_model=AdnRead)
async def read_my_adn(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adn = await get_adn_by_artist(db, current_user.id)
    if adn is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="No ADN yet for this artist"
        )
    return adn


@router.post(
    "/adn",
    response_model=AdnRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_adn(
    payload: AdnCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        adn = await create_adn(
            db=db,
            artist_id=current_user.id,
            description=payload.description,
            usage_guide=payload.usage_guide,
            example_outputs=payload.example_outputs,
            price_credits=payload.price_credits,
        )
        await db.commit()
        await db.refresh(adn)
        return adn
    except ValueError as e:
        await db.rollback()
        _raise_marketplace_error(e)
    except IntegrityError:
        # Filet de sécurité : course critique entre check applicatif et
        # commit (uniquement le commit() peut échouer après le flush si
        # le savepoint a été commit avant un autre POST concurrent).
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Artist already has an ADN"
        )
    except Exception:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ADN",
        )


@router.patch("/adn", response_model=AdnRead)
async def update_my_adn(
    payload: AdnUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    try:
        adn = await update_adn(
            db=db, artist_id=current_user.id, payload=data
        )
        await db.commit()
        await db.refresh(adn)
        return adn
    except ValueError as e:
        await db.rollback()
        _raise_marketplace_error(e)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ADN",
        )


# -----------------------------------------------------------------------------
# Prompts
# -----------------------------------------------------------------------------

@router.get("/prompts", response_model=PromptsListResponse)
async def list_my_prompts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_prompts_for_artist(
        db, artist_id=current_user.id, page=page, per_page=per_page
    )
    return PromptsListResponse(
        items=items, total=total, page=page, per_page=per_page
    )


@router.post(
    "/prompts",
    response_model=PromptRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_prompt(
    payload: PromptCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        prompt = await create_prompt(
            db=db,
            artist_id=current_user.id,
            title=payload.title,
            description=payload.description,
            prompt_text=payload.prompt_text,
            price_credits=payload.price_credits,
        )
        await db.commit()
        await db.refresh(prompt)
        return prompt
    except ValueError as e:
        await db.rollback()
        _raise_marketplace_error(e)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create prompt",
        )


@router.get("/prompts/{prompt_id}", response_model=PromptRead)
async def read_my_prompt(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prompt = await get_prompt_for_artist(
        db, artist_id=current_user.id, prompt_id=prompt_id
    )
    if prompt is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )
    return prompt


@router.patch("/prompts/{prompt_id}", response_model=PromptRead)
async def update_my_prompt(
    prompt_id: UUID,
    payload: PromptUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    try:
        prompt = await update_prompt(
            db=db,
            artist_id=current_user.id,
            prompt_id=prompt_id,
            payload=data,
        )
        await db.commit()
        await db.refresh(prompt)
        return prompt
    except ValueError as e:
        await db.rollback()
        _raise_marketplace_error(e)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update prompt",
        )


# -----------------------------------------------------------------------------
# Brand color (profil)
# -----------------------------------------------------------------------------

@router.patch("/brand-color", response_model=UserRead)
async def update_my_brand_color(
    payload: BrandColorUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Met à jour la couleur signature de l'artiste.

    Endpoint dédié (vs /users/me) parce que sémantiquement c'est un
    paramètre "marketplace" (visible publiquement sur la fiche artiste +
    prompts), pas un paramètre privé de profil.

    Normalisation uppercase via le validator Pydantic, donc la valeur
    qu'on stocke est toujours canonique (`#FFAA00`).
    """
    data = payload.model_dump(exclude_unset=True)
    if "brand_color" in data:
        current_user.brand_color = data["brand_color"]
        try:
            await db.commit()
            await db.refresh(current_user)
        except Exception:
            await db.rollback()
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update brand color",
            )
    return current_user
