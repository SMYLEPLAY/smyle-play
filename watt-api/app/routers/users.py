from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Suppression de compte RGPD (pack légal v1, 2026-06-10).

    Anonymisation immédiate + retrait public des contenus + déconnexion
    définitive (l'email anonymisé invalide tous les JWT émis, sub=email).
    Les exemplaires achetés par d'autres restent dans leur bibliothèque —
    voir services/account_deletion.py et /legal#confidentialite.
    """
    from app.services.account_deletion import delete_account

    await delete_account(db, current_user)


@router.get("/me/export")
async def export_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export des données personnelles (RGPD art. 15/20 — accès/portabilité).
    Renvoie un JSON téléchargeable de tout ce que le compte possède.
    Lecture seule.
    """
    from fastapi.responses import JSONResponse

    from app.services.account_export import export_account_data

    data = await export_account_data(db, current_user)
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": 'attachment; filename="mes-donnees-watt.json"'
        },
    )


@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/me/listing-slots")
async def read_my_listing_slots(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Jauge d'emplacements de vente (C6.3) : produits publiés vs limite du
    palier. `enforced=False` tant que les paliers payants ne sont pas ouverts
    (la jauge s'affiche mais ne bloque pas)."""
    from app.services.listings import listing_slots_status

    return await listing_slots_status(db, current_user.id, current_user.tier)


@router.get("/eco-cockpit")
async def eco_cockpit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A4 — cockpit économique (admin only, lecture seule). Gardé par is_official
    (le compte Smyle). Solvabilité + Smyles en circulation + canari + business."""
    if not current_user.is_official:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Réservé à l'administration"
        )
    from app.services.dashboard import eco_cockpit_data

    return await eco_cockpit_data(db)


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return current_user
