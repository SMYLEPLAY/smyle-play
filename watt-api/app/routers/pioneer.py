"""Programme Pionnier — endpoint PUBLIC (Brique 2).

    GET /pioneer/places  → { "total": 100, "attribuees": n, "restantes": 100 - n }

Levier de motivation : afficher « X places Pionnier restantes » incite les
premiers créateurs à publier. Derrière `FEATURE_PIONEER` : répond 404 tant que
le programme n'est pas lancé (même comportement qu'un item masqué du mode
lancement — rien n'est révélé avant l'activation).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.pioneer import pioneer_stats

router = APIRouter(prefix="/pioneer", tags=["pioneer"])


@router.get("/places")
async def places_pionnier(db: AsyncSession = Depends(get_db)) -> dict:
    if not settings.FEATURE_PIONEER:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return await pioneer_stats(db)
