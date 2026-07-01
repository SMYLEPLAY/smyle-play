"""Endpoints d'administration (A4) — cockpit économique, lecture seule.

Gardé par `is_official` (le compte admin Smyle). Réservé : ne pas exposer
publiquement les données de solvabilité / réserve.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.dashboard import eco_cockpit_data

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/eco-cockpit")
async def eco_cockpit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_official:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Réservé à l'administration"
        )
    return await eco_cockpit_data(db)
