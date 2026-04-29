from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.config import settings
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


# C4 (2026-04-29) — Liste des environnements où /credits/grant est ACTIF.
# Pour ouverture publique : passer ENVIRONMENT à "production" sur Railway,
# ce qui désactive automatiquement le grant gratuit. Côté front, la modale
# d'achat (ui/modals/credits-buy.js) capture le 403 et affiche le bandeau
# "Paiement réel arrive bientôt".
_GRANT_ENABLED_ENVS = {"development", "staging", "test"}


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
async def grant_credits(
    payload: GrantCreditsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    STUB V1 : ajoute manuellement des crédits au user connecté.
    À remplacer par Stripe checkout en Phase 11.

    C4 (2026-04-29) — Verrou de sécurité : actif uniquement en environnement
    dev/staging/test. En production publique, retourne 403 pour empêcher
    tout user de s'auto-créditer ∞ SMYLES en attendant Stripe.
    """
    if settings.ENVIRONMENT not in _GRANT_ENABLED_ENVS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "grant_disabled_in_prod",
                "message": "L'achat direct de crédits est désactivé. Le paiement réel (Stripe) arrive bientôt.",
            },
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
