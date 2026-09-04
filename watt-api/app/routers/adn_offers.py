"""
Endpoints OFFRES-ADN (chantier 2026-07-03) — vente d'ADN sur proposition.

Routes (toutes auth requise) :
  POST  /adn-offers                    → faire une offre en Smyles sur un ADN
  GET   /adn-offers/me                 → mes offres ADN (envoyées + reçues)
  PATCH /adn-offers/{id}/accept        → accepter (vendeur uniquement)
  PATCH /adn-offers/{id}/reject        → refuser (vendeur uniquement)
  PATCH /adn-offers/{id}/cancel        → annuler (acheteur uniquement)

Règles métier :
  - sender = ACHETEUR, receiver = VENDEUR (créateur de l'ADN). Réutilise la
    table trade_offers (extension migration 0080), PAS un nouveau système.
  - Reserve caché : offre < adn_reserve_credits → rejet automatique à la
    création (422 générique, la valeur du plancher n'est JAMAIS révélée)
    ET re-vérifié à l'accept.
  - Accept = atomique (services/adn_offers.py) : transfert AU MONTANT DE
    L'OFFRE + livraison Owned* + Transaction, verrous ordonnés, sous-soldes.
  - Une seule offre pending par (acheteur, cible) à la fois → 409.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.database import get_db
from app.models.achievement import AchievementAxis
from app.models.notification import NotificationType
from app.models.trade import TradeOffer, TradeStatus
from app.models.user import User
from app.schemas.adn_offer import AdnOfferCreate, AdnOfferRead
from app.services.achievements import check_and_grant_achievements
from app.services.adn_offers import (
    ReserveNotMet,
    accept_adn_offer_atomic,
    resolve_adn_target,
)
from app.services.notifications import create_notification
from app.services.unlocks import (
    AdnNotPurchasable,
    AlreadyOwned,
    InsufficientCredits,
)

router = APIRouter(prefix="/adn-offers", tags=["adn-offers"])

_OFFER_TTL_DAYS = 7  # même TTL que les trades prompts

# Message VOLONTAIREMENT générique : ne révèle ni l'existence précise ni la
# valeur du plancher (anti-sondage par dichotomie… au moins pas trivialement).
_RESERVE_MSG = "Offre refusée automatiquement — propose un montant plus élevé"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_adn_offer_or_404(offer_id: UUID, db: AsyncSession,
                                *, for_update: bool = False) -> TradeOffer:
    q = select(TradeOffer).where(
        TradeOffer.id == offer_id,
        TradeOffer.target_type.is_not(None),  # une offre ADN, pas un trade
    )
    if for_update:
        q = q.with_for_update()
    offer = (await db.execute(q)).scalar_one_or_none()
    if not offer:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail="Offre introuvable")
    return offer


async def _enrich(offer: TradeOffer, db: AsyncSession) -> AdnOfferRead:
    async def _name(uid: UUID | None) -> str | None:
        if not uid:
            return None
        row = (await db.execute(
            select(User.artist_name).where(User.id == uid)
        )).first()
        return row.artist_name if row else None

    target_title = None
    try:
        target = await resolve_adn_target(
            db, target_type=offer.target_type, target_id=offer.target_id
        )
        target_title = target.title
    except AdnNotPurchasable:
        pass  # cible retirée de la vente depuis → titre absent, offre listée quand même

    return AdnOfferRead(
        id=offer.id,
        target_type=offer.target_type,
        target_id=offer.target_id,
        target_title=target_title,
        amount_credits=offer.amount_credits or 0,
        buyer_id=offer.sender_id,
        buyer_name=await _name(offer.sender_id),
        seller_id=offer.receiver_id,
        seller_name=await _name(offer.receiver_id),
        status=offer.status,
        message=offer.message,
        expires_at=offer.expires_at,
        created_at=offer.created_at,
        resolved_at=offer.resolved_at,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=AdnOfferRead,
             status_code=status.HTTP_201_CREATED)
@limiter.limit(LIMIT_PURCHASE)
async def create_adn_offer(
    payload: AdnOfferCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdnOfferRead:
    """Fait une offre en Smyles sur un ADN (playlist / album / visuel)."""
    try:
        target = await resolve_adn_target(
            db, target_type=payload.target_type, target_id=payload.target_id
        )
    except AdnNotPurchasable as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))

    if target.seller_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Impossible de faire une offre sur ton propre ADN")

    # Reserve caché : rejet automatique, message générique.
    if target.reserve is not None and payload.amount_credits < int(target.reserve):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=_RESERVE_MSG)

    # L'acheteur doit pouvoir couvrir son offre au moment où il la fait
    # (garde soft — re-vérifié à l'accept, seul moment où ça débite).
    if current_user.credits_balance < payload.amount_credits:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Crédits insuffisants (dispo: {current_user.credits_balance},"
                   f" offre: {payload.amount_credits})",
        )

    # Déjà possédé → pas d'offre.
    from app.services.adn_offers import _already_owned
    if await _already_owned(
        db, target_type=payload.target_type,
        target_id=payload.target_id, buyer_id=current_user.id,
    ):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Tu possèdes déjà cet ADN")

    # Une seule offre pending par (acheteur, cible).
    existing = (await db.execute(
        select(TradeOffer).where(
            TradeOffer.status == TradeStatus.PENDING,
            TradeOffer.sender_id == current_user.id,
            TradeOffer.target_type == payload.target_type,
            TradeOffer.target_id == payload.target_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Tu as déjà une offre en attente sur cet ADN")

    offer = TradeOffer(
        sender_id=current_user.id,
        receiver_id=target.seller_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        amount_credits=payload.amount_credits,
        message=payload.message,
        expires_at=datetime.now(timezone.utc) + timedelta(days=_OFFER_TTL_DAYS),
    )
    db.add(offer)
    await db.flush()

    await create_notification(
        db,
        user_id=target.seller_id,
        type=NotificationType.TRADE,
        actor_id=current_user.id,
        target_type="adn_offer",
        target_id=offer.id,
        metadata={
            "action": "adn_offer_received",
            "buyer_name": current_user.artist_name or "Artiste",
            "amount": payload.amount_credits,
            "adn_type": payload.target_type,
            "adn_title": target.title,
        },
    )

    await db.commit()
    await db.refresh(offer)
    return await _enrich(offer, db)


@router.get("/me", response_model=list[AdnOfferRead])
async def list_my_adn_offers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AdnOfferRead]:
    """Toutes mes offres ADN (envoyées + reçues), triées par date."""
    offers = (await db.execute(
        select(TradeOffer)
        .where(
            TradeOffer.target_type.is_not(None),
            or_(
                TradeOffer.sender_id == current_user.id,
                TradeOffer.receiver_id == current_user.id,
            ),
        )
        .order_by(TradeOffer.created_at.desc())
        .limit(50)
    )).scalars().all()
    return [await _enrich(o, db) for o in offers]


@router.patch("/{offer_id}/accept", response_model=AdnOfferRead)
async def accept_adn_offer(
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdnOfferRead:
    """
    Accepte une offre ADN (vendeur uniquement).
    Atomique : transfert des Smyles au montant de l'offre + livraison ADN.
    """
    # FOR UPDATE : sérialise les acceptations concurrentes (même garantie
    # que les trades prompts — H0.3).
    offer = await _get_adn_offer_or_404(offer_id, db, for_update=True)

    if offer.receiver_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Seul le vendeur peut accepter")
    if offer.status != TradeStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"Offre non pending (statut: {offer.status})")
    if offer.expires_at and offer.expires_at < datetime.now(timezone.utc):
        offer.status = TradeStatus.EXPIRED
        await db.commit()
        raise HTTPException(status.HTTP_410_GONE, detail="Offre expirée")

    try:
        result = await accept_adn_offer_atomic(db, offer=offer)
    except InsufficientCredits:
        await db.rollback()
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="L'acheteur n'a plus assez de crédits pour couvrir son offre",
        )
    except ReserveNotMet as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    except AlreadyOwned as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    except AdnNotPurchasable as e:
        await db.rollback()
        raise HTTPException(status.HTTP_410_GONE, detail=str(e))

    offer.status = TradeStatus.ACCEPTED
    offer.resolved_at = datetime.now(timezone.utc)

    await create_notification(
        db,
        user_id=offer.sender_id,
        type=NotificationType.TRADE,
        actor_id=current_user.id,
        target_type="adn_offer",
        target_id=offer.id,
        metadata={
            "action": "adn_offer_accepted",
            "seller_name": current_user.artist_name or "Artiste",
            "amount": offer.amount_credits,
            "adn_type": offer.target_type,
        },
    )

    # Snapshots AVANT commit : les hooks post-commit ne doivent pas dépendre
    # de l'état de session de `offer`.
    _buyer_id = offer.sender_id
    _seller_id = current_user.id
    _target_type = offer.target_type

    await db.commit()

    # ── K-06 (2026-09-04, annexe B §1.9b-c) — hooks post-commit ────────────
    # L'offre ADN est le SEUL canal de vente d'ADN, et c'était le seul flux
    # d'achat sans trophées ni parrainage : `fan_first_adn` restait verrouillé
    # alors que progress.fan valait déjà 1, l'axe ARTIST du vendeur n'avançait
    # pas, et un lien de parrainage restait PENDING après un 1er achat d'ADN.
    # Best-effort et APRÈS commit (pattern routers/unlocks.py:175-180) : un
    # échec ici ne défait jamais une vente déjà enregistrée.
    try:
        # Les soldes du vendeur ont été écrits en SQL brut par le service :
        # l'objet User déjà chargé en session porte encore l'ancien
        # credits_earned_total, or c'est LUI que lit l'axe ARTIST. On expire
        # le cache d'identité avant de mesurer la progression.
        db.expire_all()
        await check_and_grant_achievements(
            db, user_id=_buyer_id, axis=AchievementAxis.FAN
        )
        await check_and_grant_achievements(
            db, user_id=_seller_id, axis=AchievementAxis.ARTIST
        )
        if _target_type == "visual_adn":
            await check_and_grant_achievements(
                db, user_id=_seller_id, axis=AchievementAxis.VISUAL_DNA
            )
        await db.commit()
    except Exception:
        await db.rollback()

    # Parrainage (mécanique 1) : le 1er achat du filleul est l'action
    # qualifiante. Idempotent — maybe_reward_referral ne verse qu'une fois.
    try:
        from app.services.referrals import maybe_reward_referral
        if await maybe_reward_referral(db, _buyer_id):
            await db.commit()
    except Exception:
        await db.rollback()

    await db.refresh(offer)
    return await _enrich(offer, db)


@router.patch("/{offer_id}/reject", response_model=AdnOfferRead)
async def reject_adn_offer(
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdnOfferRead:
    """Refuse une offre ADN (vendeur uniquement)."""
    offer = await _get_adn_offer_or_404(offer_id, db)

    if offer.receiver_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Seul le vendeur peut refuser")
    if offer.status != TradeStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"Offre non pending (statut: {offer.status})")

    offer.status = TradeStatus.REJECTED
    offer.resolved_at = datetime.now(timezone.utc)

    await create_notification(
        db,
        user_id=offer.sender_id,
        type=NotificationType.TRADE,
        actor_id=current_user.id,
        target_type="adn_offer",
        target_id=offer.id,
        metadata={"action": "adn_offer_rejected",
                  "adn_type": offer.target_type},
    )

    await db.commit()
    await db.refresh(offer)
    return await _enrich(offer, db)


@router.patch("/{offer_id}/cancel", response_model=AdnOfferRead)
async def cancel_adn_offer(
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdnOfferRead:
    """Annule une offre ADN (acheteur uniquement, avant acceptation)."""
    offer = await _get_adn_offer_or_404(offer_id, db)

    if offer.sender_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Seul l'acheteur peut annuler")
    if offer.status != TradeStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"Offre non pending (statut: {offer.status})")

    offer.status = TradeStatus.CANCELLED
    offer.resolved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(offer)
    return await _enrich(offer, db)
