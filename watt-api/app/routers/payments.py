"""Brique 5 — achat de Smyles par carte (Stripe Checkout). Lot 3.

  POST /credits/checkout   (connecté, SHOW_ACHAT_SMYLES) → URL de paiement Stripe
  POST /stripe/webhook     (Stripe, signé)               → crédit / reprise
  GET  /admin/paiements/signales (admin)                 → comptes à examiner
  GET  /admin/paiements (admin, lot L)                   → tous les paiements + totaux

Le crédit n'a lieu QUE sur le webhook signé (jamais sur la page de retour).
"""
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
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
    EvenementARejouer,
    StripeRequestError,
    StripeSignatureError,
    StripeUnavailable,
    create_checkout,
    handle_event,
    infos_confirmation,
    paiements_signales,
    paiements_tous,
    verify_signature,
)

router = APIRouter(tags=["paiements"])


class CheckoutIn(BaseModel):
    pack_id: str = Field(min_length=1, max_length=32)
    # Case OBLIGATOIRE : « Je demande la fourniture immédiate du contenu
    # numérique et je renonce à mon droit de rétractation. »
    renonce_retractation: bool = False
    # Lot L — « J'ai 18 ans ou plus » (ACHAT_MAJEUR_REQUIS).
    majeur: bool = False


@router.post("/credits/checkout")
@limiter.limit(LIMIT_PURCHASE)
async def credits_checkout(
    payload: CheckoutIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Lot L : adresse de retour fiable (https) — PUBLIC_BASE_URL d'abord.
    base = settings.PUBLIC_BASE_URL or os.getenv("PUBLIC_BASE_URL") or str(request.base_url)
    try:
        out = await create_checkout(
            db, user=current_user, pack_id=payload.pack_id,
            consent=payload.renonce_retractation, base_url=base,
            majeur=payload.majeur,
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
async def stripe_webhook(request: Request, background: BackgroundTasks,
                         db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    try:
        event = verify_signature(
            payload, request.headers.get("stripe-signature"), settings.STRIPE_WEBHOOK_SECRET
        )
    except StripeUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook non configuré.")
    except StripeSignatureError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Signature invalide.")
    try:
        statut = await handle_event(db, event)
    except EvenementARejouer as e:
        # Lot L : rien n'est enregistré (rollback) → Stripe renverra
        # l'événement plus tard, quand le paiement sera connu.
        await db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Événement à rejouer ({e}).")
    await db.commit()
    if statut == "credite":
        # Lot L — confirmation d'achat sur support durable (L221-13), après
        # le commit, sans jamais bloquer la réponse à Stripe.
        session_id = str(((event.get("data") or {}).get("object") or {}).get("id") or "")
        infos = await infos_confirmation(db, session_id) if session_id else None
        if infos and not infos["test"]:
            from app.services.emails import send_confirmation_achat_smyles
            from app.services.stripe_payments import TVA_MENTION

            background.add_task(
                send_confirmation_achat_smyles, infos["email"],
                smyles=infos["smyles"], euros_cents=infos["euros_cents"],
                consentement_le=infos["consentement_le"], cgu_version=infos["cgu_version"],
                paiement_id=infos["paiement_id"],
                mention_tva=TVA_MENTION if settings.MENTION_TVA_FRANCHISE else None,
            )
    return {"ok": True, "statut": statut}


@router.get("/admin/paiements")
async def admin_paiements(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lot L — TOUS les paiements par carte, avec totaux en euros et ceux
    restés en attente (session créée, jamais créditée) depuis plus d'1 h."""
    return await paiements_tous(db)


@router.get("/admin/paiements/signales")
async def admin_paiements_signales(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Paiements remboursés / contestés dont les Smyles étaient déjà dépensés
    (manque non repris), et montants incohérents. À examiner à la main."""
    return {"paiements": await paiements_signales(db)}
