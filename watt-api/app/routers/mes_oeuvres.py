"""Écran « Mes Œuvres » — routes du créateur connecté (Parcours V1).

  GET   /artist/me/oeuvres               liste de MES Œuvres
  POST  /artist/me/oeuvres/actions       action groupée (masquer, republier,
                                         prix, supprimer)
  PATCH /artist/me/oeuvres/{track_id}    modifier une Œuvre (titre,
                                         description, pochette, prix)

Toutes les routes ne touchent qu'aux Œuvres du compte connecté (un
identifiant d'un autre compte est traité comme introuvable). Les
administrateurs gardent leurs propres outils (/admin/…).
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import mes_oeuvres as svc
from app.services.media_ownership import MediaOwnershipError

router = APIRouter(prefix="/artist/me/oeuvres", tags=["mes-oeuvres"])


class ActionGroupee(BaseModel):
    track_ids: list[UUID] = Field(min_length=1, max_length=svc.MAX_PAR_LOT)
    action: Literal["masquer", "republier", "prix", "supprimer"]
    prix: int | None = None
    cible: Literal["les_deux", "recette", "image"] = "les_deux"


class Modification(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    cover_url: str | None = Field(default=None, max_length=2048)
    recipe_price: int | None = None
    image_price: int | None = None


@router.get("")
async def lister_mes_oeuvres(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items = await svc.lister(db, current_user)
    return {"items": items, "total": len(items)}


@router.post("/actions")
async def action_sur_mes_oeuvres(
    body: ActionGroupee,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        res = await svc.action_groupee(
            db, current_user, track_ids=body.track_ids, action=body.action,
            prix=body.prix, cible=body.cible,
        )
    except svc.OeuvreErreur as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    await db.commit()
    return res


@router.patch("/{track_id}")
async def modifier_mon_oeuvre(
    track_id: UUID,
    body: Modification,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        res = await svc.modifier(
            db, current_user, track_id, body.model_dump(exclude_unset=True)
        )
    except LookupError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Œuvre introuvable.")
    except (svc.OeuvreErreur, MediaOwnershipError) as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    await db.commit()
    return res
