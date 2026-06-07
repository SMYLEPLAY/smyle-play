"""
Router packs aléatoires — mystery pack (mécanique 3).

Endpoints :
  GET  /packs/mystery       → prix + taille du pool tirable (auth)
  POST /packs/mystery/open  → ouvre un pack, tire 1 prompt (auth)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.pack import PackInfo, PackOpenResult, RarityOdds
from app.services.packs import (
    MYSTERY_PACK_PRICE,
    RARITY_TIERS,
    PackInsufficientCredits,
    PackPoolEmpty,
    PackError,
    count_pack_pool,
    open_mystery_pack_atomic,
)

router = APIRouter(prefix="/packs", tags=["packs"])


@router.get("/mystery", response_model=PackInfo)
async def mystery_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pool = await count_pack_pool(db, current_user.id)
    total_w = sum(t["weight"] for t in RARITY_TIERS)
    odds = [
        RarityOdds(
            name=t["name"],
            weight=t["weight"],
            pct=round(t["weight"] * 100 / total_w),
        )
        for t in RARITY_TIERS
    ]
    return PackInfo(price=MYSTERY_PACK_PRICE, pool_count=pool, odds=odds)


@router.post("/mystery/open", response_model=PackOpenResult)
async def open_mystery(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await open_mystery_pack_atomic(db, current_user.id)
        await db.commit()
    except PackPoolEmpty:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "pack_pool_empty",
                "message": "Tu possèdes déjà tous les sons disponibles au tirage.",
            },
        )
    except PackInsufficientCredits as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "insufficient_credits",
                "message": f"Il te faut {e.required} Smyles (tu en as {e.available}).",
                "required": e.required,
                "available": e.available,
            },
        )
    except PackError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "pack_error", "message": str(e)},
        )
    return PackOpenResult(**result)
