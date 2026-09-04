"""
Router marché secondaire — revente de prompts (2026-06-08).

Endpoints :
  GET    /resale/market                     → listings publics (auth)
  POST   /resale/prompts/{prompt_id}/list   → mettre en vente (auth, possédé)
  DELETE /resale/prompts/{prompt_id}/list   → retirer de la vente (auth)
  POST   /resale/{unlocked_prompt_id}/buy   → acheter une revente (auth)
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.launch import require_launch_item
from app.auth.dependencies import get_current_user
from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.database import get_db
from app.models.user import User
from app.schemas.resale import ResaleBuyResult, ResaleListRequest, ResaleMarketItem
from app.services.resale import (
    ResaleAlreadyOwned,
    ResaleInsufficientCredits,
    ResaleLinkedAccounts,
    ResaleNotListed,
    ResaleNotOwned,
    ResaleSelfBuy,
    buy_resale_atomic,
    get_prompt_market,
    get_resale_market,
    list_prompt_for_resale,
    unlist_prompt_for_resale,
)

# S-08 (2026-09-02) — MODE LANCEMENT gaté côté API : tant que l'item est
# masqué, toutes les routes de ce routeur répondent 404 (audit A §M8).
router = APIRouter(
    prefix="/resale",
    tags=["resale"],
    dependencies=[Depends(require_launch_item("resale"))],
)


@router.get("/market", response_model=list[ResaleMarketItem])
async def market(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await get_resale_market(db)
    return [ResaleMarketItem(**it) for it in items]


@router.get("/by-seller/{seller_id}", response_model=list[ResaleMarketItem])
async def by_seller(
    seller_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reventes d'un vendeur — PUBLIC (pas d'auth), affiché dans la section
    Revente de son profil /u/<slug>. Chaque item porte l'attribution du
    créateur d'origine (nom + slug → lien vers son profil)."""
    items = await get_resale_market(db, seller_id=seller_id)
    return [ResaleMarketItem(**it) for it in items]


@router.get("/prompt/{prompt_id}/market")
async def prompt_market(
    prompt_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Marché CANONIQUE d'un morceau — PUBLIC : offre primaire (créateur, si
    stock) + offres secondaires (reventes) sur UNE fiche. Modèle StockX."""
    data = await get_prompt_market(db, prompt_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Prompt introuvable")
    return data


@router.post("/prompts/{prompt_id}/list", status_code=status.HTTP_204_NO_CONTENT)
async def list_for_resale(
    prompt_id: UUID,
    payload: ResaleListRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await list_prompt_for_resale(
            db, owner_id=current_user.id, prompt_id=prompt_id, price=payload.price
        )
        await db.commit()
    except ResaleNotOwned as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/prompts/{prompt_id}/list", status_code=status.HTTP_204_NO_CONTENT)
async def unlist_for_resale(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await unlist_prompt_for_resale(db, owner_id=current_user.id, prompt_id=prompt_id)
        await db.commit()
    except ResaleNotOwned as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{unlocked_prompt_id}/buy", response_model=ResaleBuyResult)
@limiter.limit(LIMIT_PURCHASE)
async def buy(
    unlocked_prompt_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await buy_resale_atomic(
            db, buyer_id=current_user.id, unlocked_prompt_id=unlocked_prompt_id
        )
        await db.commit()
    except ResaleNotListed as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResaleSelfBuy as e:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ResaleLinkedAccounts as e:
        await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(e))
    except ResaleAlreadyOwned as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    except ResaleInsufficientCredits as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail={"error": "insufficient_credits", "required": e.required, "available": e.available},
        )
    return ResaleBuyResult(**result)
