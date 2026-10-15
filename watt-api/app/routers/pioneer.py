"""Programme Pionnier — endpoint PUBLIC (Brique 2).

    GET /pioneer/places  → { "total": 100, "attribuees": n, "restantes": 100 - n }

Levier de motivation : afficher « X places Pionnier restantes » incite les
premiers créateurs à publier. Derrière `FEATURE_PIONEER` : répond 404 tant que
le programme n'est pas lancé (même comportement qu'un item masqué du mode
lancement — rien n'est révélé avant l'activation).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.config import settings
from app.core.ratelimit import LIMIT_CODE_PIONNIER, limiter
from app.database import get_db
from app.models.user import User
from app.services.pioneer import award_pioneer, pioneer_stats
from app.services.pioneer_codes import (
    CodeDejaUtilise,
    CodeInvalide,
    CompteNonEligible,
    a_un_code,
    utiliser,
)

router = APIRouter(prefix="/pioneer", tags=["pioneer"])


@router.get("/places")
async def places_pionnier(db: AsyncSession = Depends(get_db)) -> dict:
    if not settings.FEATURE_PIONEER:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return await pioneer_stats(db)


class CodePionnierIn(BaseModel):
    code: str = Field(min_length=4, max_length=20)


@router.get("/moi")
async def mon_statut_pionnier(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lot I — état Pionnier du compte connecté (pour la page d'invitation)."""
    return {
        "rang": user.pioneer_rank,
        "code_utilise": await a_un_code(db, user.id),
        "programme_actif": bool(settings.FEATURE_PIONEER),
        "code_requis": bool(settings.PIONEER_CODE_REQUIRED),
    }


@router.post("/code")
@limiter.limit(LIMIT_CODE_PIONNIER)
async def utiliser_code_pionnier(
    payload: CodePionnierIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lot I — un créateur déjà inscrit ajoute son code Pionnier. S'il a déjà
    une œuvre en ligne (et le programme actif), le rang est attribué tout de
    suite ; sinon, à sa première publication."""
    try:
        code = await utiliser(db, user.id, payload.code)
        await db.commit()
    except (CodeDejaUtilise, CompteNonEligible) as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    except CodeInvalide as e:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Tu as déjà utilisé un code Pionnier.")
    rang = None
    if settings.FEATURE_PIONEER:
        rang = await award_pioneer(db, user.id, live=True)
        await db.commit()
    return {"ok": True, "code": code, "rang": rang}
