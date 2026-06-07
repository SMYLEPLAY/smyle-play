"""
Router marché secondaire — revente de prompts (2026-06-08).

Endpoints :
  GET    /resale/market                     → listings publics (auth)
  POST   /resale/prompts/{prompt_id}/list   → mettre en vente (auth, possédé)
  DELETE /resale/prompts/{prompt_id}/list   → retirer de la vente (auth)
  POST   /resale/{unlocked_prompt_id}/buy   → acheter une revente (auth)
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.resale import ResaleBuyResult, ResaleListRequest, ResaleMarketItem
from app.services.resale import (
    ResaleAlreadyOwned,
    ResaleInsufficientCredits,
    ResaleNotListed,
    ResaleNotOwned,
    ResaleSelfBuy,
    buy_resale_atomic,
    get_resale_market,
    list_prompt_for_resale,
    unlist_prompt_for_resale,
)

router = APIRouter(prefix="/resale", tags=["resale"])


@router.get("/market", response_model=list[ResaleMarketItem])
async def market(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await get_resale_market(db)
    return [ResaleMarketItem(**it) for it in items]


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
async def buy(
    unlocked_prompt_id: UUID,
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
