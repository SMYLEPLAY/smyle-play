"""Étape 3 — moteurs de croissance : endpoints publics / utilisateur.

    GET /objectif/actifs      (public)  barre « {n} / 1000 actifs » — 404 si
                                        FEATURE_GOAL est OFF (comme le compteur
                                        Pionnier : rien n'est révélé avant).
    GET /me/droit-de-vendre   (connecté) le créateur peut-il mettre en vente ?
                                        (seuil d'abonnés, FEATURE_SELL_GATE) —
                                        sert au message « Encore X abonnés ».
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.droit_de_vendre import statut_vente
from app.services.objectif_actifs import CACHE_SECONDES, objectif_public

router = APIRouter(tags=["croissance"])


@router.get("/objectif/actifs")
async def objectif_actifs(response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    if not settings.FEATURE_GOAL:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # Chiffre public et identique pour tous : cache navigateur/CDN court.
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDES}"
    return await objectif_public(db)


@router.get("/me/droit-de-vendre")
async def droit_de_vendre(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await statut_vente(db, current_user)
