from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import is_admin_user
from app.auth.jwt import get_current_user
from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.database import get_db
from app.models.user import User
from app.schemas.credit import (
    CreditPack,
    CreditPacksResponse,
    GrantCreditsRequest,
    TransactionRead,
)
from app.services.credits import CREDIT_PACKS, grant_credits_atomic

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/packs", response_model=CreditPacksResponse)
async def list_packs():
    """Liste publique des packs de crédits disponibles."""
    packs = [
        CreditPack(
            id=p["id"],
            credits=p["credits"],
            price_eur_cents=p["price_eur_cents"],
            price_eur_display=f"{p['price_eur_cents'] / 100:.2f} €",
            unit_price_cents=p["price_eur_cents"] // p["credits"],
        )
        for p in CREDIT_PACKS
    ]
    return CreditPacksResponse(packs=packs)


@router.post("/grant", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(LIMIT_PURCHASE)
async def grant_credits(
    payload: GrantCreditsRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Attribution manuelle de crédits — RÉSERVÉE aux administrateurs
    (is_official OU is_admin, K-01). Crédite UNIQUEMENT l'appelant.

    SÉCURITÉ (Phase 0 lancement, 2026-07-23) : cet endpoint créditait librement
    le compte connecté (stub « en attendant Stripe »). Ouvert au public, il
    permettait à n'importe qui de se fabriquer des Smyles à volonté et de
    détruire l'économie. Il est désormais gaté sur is_official ; les Smyles des
    utilisateurs se gagnent (streak, parrainage) ou, plus tard, s'achètent via
    un webhook Stripe signé et vérifié côté serveur — jamais par appel direct.
    """
    # K-01 : is_official OU is_admin (règle partagée). Message inchangé :
    # cet endpoint est atteignable par n'importe quel membre connecté.
    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Réservé. Les Smyles se gagnent en explorant, en publiant et en jouant.",
        )
    try:
        tx = await grant_credits_atomic(
            db=db,
            user_id=current_user.id,
            amount=payload.credits,
            reason=payload.reason,
        )
        await db.commit()
        await db.refresh(tx)
        return tx
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
