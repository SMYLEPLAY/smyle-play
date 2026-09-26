"""Brique 5 — achat de Smyles par carte (Stripe Checkout). Lot 3.

  POST /credits/checkout   (connecté, SHOW_ACHAT_SMYLES) → URL de paiement Stripe
  POST /stripe/webhook     (Stripe, signé)               → crédit / reprise
  GET  /admin/paiements/signales (admin)                 → comptes à examiner

Le crédit n'a lieu QUE sur le webhook signé (jamais sur la page de retour).
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.jwt import get_current_user
from app.config import settings
from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.database import get_db
from app.models.user import User
from app.services.stripe_payments import (
    AchatCarteBloque,
    StripeRequestError,
    StripeSignatureError,
    StripeUnavailable,
    create_checkout,
    handle_event,
    paiements_signales,
    verify_signature,
)

router = APIRouter(tags=["paiements"])


class CheckoutIn(BaseModel):
    pack_id: str = Field(min_length=1, max_length=32)
    # Case OBLIGATOIRE : « Je demande la fourniture immédiate du contenu
    # numérique et je renonce à mon droit de rétractation. »
    renonce_retractation: bool = False


@router.post("/credits/checkout")
@limiter.limit(LIMIT_PURCHASE)
async def credits_checkout(
    payload: CheckoutIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = os.getenv("PUBLIC_BASE_URL") or str(request.base_url)
    try:
        out = await create_checkout(
            db, user=current_user, pack_id=payload.pack_id,
            consent=payload.renonce_retractation, base_url=base,
        )
    except StripeRequestError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except StripeUnavailable as e:
        await db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except AchatCarteBloque as e:
        await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(e))
    await db.commit()
    return out


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    try:
        event = verify_signature(
            payload, request.headers.get("stripe-signature"), settings.STRIPE_WEBHOOK_SECRET
        )
    except StripeUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook non configuré.")
    except StripeSignatureError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Signature invalide.")
    statut = await handle_event(db, event)
    await db.commit()
    return {"ok": True, "statut": statut}


@router.get("/admin/paiements/signales")
async def admin_paiements_signales(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Paiements remboursés / contestés dont les Smyles étaient déjà dépensés
    (manque non repris), et montants incohérents. À examiner à la main."""
    return {"paiements": await paiements_signales(db)}
