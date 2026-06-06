"""
Endpoints trading de prompts entre créateurs.

Routes (toutes auth requise) :
  POST  /trades/offers                       → créer une offre de trade
  GET   /trades/offers/me                    → mes offres (envoyées + reçues)
  PATCH /trades/offers/{id}/accept           → accepter (receiver uniquement)
  PATCH /trades/offers/{id}/reject           → rejeter (receiver uniquement)
  PATCH /trades/offers/{id}/cancel           → annuler (sender uniquement)

Règles métier :
  - Le sender ne peut offrir que ses propres créations (artist_id = sender)
  - Le receiver ne peut être demandé que sur ses propres créations
  - Un seul trade pending par paire de prompts à la fois (check côté service)
  - Acceptation = atomique : 2 UnlockedPrompt créés + notifs + snapshot prix
  - credit_supplement : si > 0, déduit du sender et crédité au receiver
  - Prix plancher : au moins 1 des deux prompts doit valoir > 0 crédits
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.notification import NotificationType
from app.models.prompt import Prompt
from app.models.trade import TradeOffer, TradeStatus
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.trade import PromptSnap, TradeOfferCreate, TradeOfferRead
from app.services.notifications import create_notification

router = APIRouter(prefix="/trades", tags=["trades"])

_TRADE_TTL_DAYS = 7  # expire automatiquement après 7 jours


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_offer_or_404(offer_id: UUID, db: AsyncSession) -> TradeOffer:
    offer = (await db.execute(
        select(TradeOffer).where(TradeOffer.id == offer_id)
    )).scalar_one_or_none()
    if not offer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Offre introuvable")
    return offer


async def _enrich_offer(offer: TradeOffer, db: AsyncSession) -> TradeOfferRead:
    """Enrichit une offre avec les données user + prompt."""

    async def _user_snap(uid: UUID | None):
        if not uid:
            return None, None
        u = (await db.execute(
            select(User.artist_name, User.avatar_url).where(User.id == uid)
        )).first()
        return (u.artist_name, u.avatar_url) if u else (None, None)

    async def _prompt_snap(pid: UUID | None) -> PromptSnap | None:
        if not pid:
            return None
        p = (await db.execute(
            select(Prompt, User.artist_name)
            .join(User, Prompt.artist_id == User.id)
            .where(Prompt.id == pid)
        )).first()
        if not p:
            return None
        prompt, artist_name = p
        # Audio du track lié (pour écouter avant d'accepter). On prend le
        # premier track non supprimé pointant sur ce prompt. audio_url direct
        # si présent, sinon le proxy /watt/stream à partir de la clé R2.
        trow = (await db.execute(
            select(Track.audio_url, Track.r2_key)
            .where(Track.prompt_id == pid, Track.is_deleted.is_(False))
            .limit(1)
        )).first()
        audio_url = None
        if trow:
            audio_url = trow.audio_url or (
                f"/watt/stream/{trow.r2_key}" if trow.r2_key else None
            )
        return PromptSnap(
            id=prompt.id,
            title=prompt.title,
            price_credits=prompt.price_credits,
            artist_name=artist_name,
            audio_url=audio_url,
        )

    sender_name, sender_avatar = await _user_snap(offer.sender_id)
    receiver_name, _ = await _user_snap(offer.receiver_id)
    offered_prompt = await _prompt_snap(offer.offered_prompt_id)
    requested_prompt = await _prompt_snap(offer.requested_prompt_id)

    return TradeOfferRead(
        id=offer.id,
        sender_id=offer.sender_id,
        sender_name=sender_name,
        sender_avatar=sender_avatar,
        receiver_id=offer.receiver_id,
        receiver_name=receiver_name,
        offered_prompt=offered_prompt,
        requested_prompt=requested_prompt,
        credit_supplement=offer.credit_supplement,
        status=offer.status,
        message=offer.message,
        offered_price_at_trade=offer.offered_price_at_trade,
        requested_price_at_trade=offer.requested_price_at_trade,
        expires_at=offer.expires_at,
        created_at=offer.created_at,
        resolved_at=offer.resolved_at,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/offers", response_model=TradeOfferRead,
             status_code=status.HTTP_201_CREATED)
async def create_trade_offer(
    payload: TradeOfferCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradeOfferRead:
    """
    Crée une offre de trade.
    Le sender doit être le créateur du offered_prompt.
    Le receiver doit être le créateur du requested_prompt.
    Au moins un des deux prompts doit être renseigné.
    """
    if payload.receiver_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Impossible de se trader avec soi-même")

    if not payload.offered_prompt_id and not payload.requested_prompt_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Au moins un prompt doit être spécifié")

    offered_price = 0
    requested_price = 0

    # Vérifier ownership du prompt offert
    if payload.offered_prompt_id:
        offered = (await db.execute(
            select(Prompt).where(Prompt.id == payload.offered_prompt_id)
        )).scalar_one_or_none()
        if not offered:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                detail="Prompt offert introuvable")
        if offered.artist_id != current_user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail="Vous n'êtes pas le créateur de ce prompt")
        if not offered.is_published:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                detail="Le prompt offert doit être publié")
        offered_price = offered.price_credits or 0

    # Vérifier ownership du prompt demandé
    if payload.requested_prompt_id:
        requested = (await db.execute(
            select(Prompt).where(Prompt.id == payload.requested_prompt_id)
        )).scalar_one_or_none()
        if not requested:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                detail="Prompt demandé introuvable")
        if requested.artist_id != payload.receiver_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail="Le prompt demandé n'appartient pas au receiver")
        if not requested.is_published:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                detail="Le prompt demandé doit être publié")
        requested_price = requested.price_credits or 0

    # Vérifier crédits suffisants si supplement > 0
    if payload.credit_supplement > 0:
        if current_user.credits_balance < payload.credit_supplement:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Crédits insuffisants (dispo: {current_user.credits_balance},"
                       f" requis: {payload.credit_supplement})"
            )

    # Pas deux trades pending pour la même paire de prompts
    existing = (await db.execute(
        select(TradeOffer).where(
            TradeOffer.status == TradeStatus.PENDING,
            TradeOffer.sender_id == current_user.id,
            TradeOffer.receiver_id == payload.receiver_id,
            TradeOffer.offered_prompt_id == payload.offered_prompt_id,
            TradeOffer.requested_prompt_id == payload.requested_prompt_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Une offre identique est déjà en attente")

    offer = TradeOffer(
        sender_id=current_user.id,
        receiver_id=payload.receiver_id,
        offered_prompt_id=payload.offered_prompt_id,
        requested_prompt_id=payload.requested_prompt_id,
        credit_supplement=payload.credit_supplement,
        message=payload.message,
        offered_price_at_trade=offered_price,
        requested_price_at_trade=requested_price,
        expires_at=datetime.now(timezone.utc) + timedelta(days=_TRADE_TTL_DAYS),
    )
    db.add(offer)
    await db.flush()

    # Notif au receiver — sauf si proposé depuis une conversation (notify=False) :
    # dans ce cas la proposition apparaît comme une carte dans le fil de messages,
    # pas besoin de doubler en notification.
    if payload.notify:
        await create_notification(
            db,
            user_id=payload.receiver_id,
            type=NotificationType.TRADE,
            actor_id=current_user.id,
            target_type="trade",
            target_id=offer.id,
            metadata={
                "action": "offer_received",
                "sender_name": current_user.artist_name or "Artiste",
            },
        )

    await db.commit()
    await db.refresh(offer)
    return await _enrich_offer(offer, db)


@router.get("/offers/me", response_model=list[TradeOfferRead])
async def list_my_offers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TradeOfferRead]:
    """Retourne toutes les offres envoyées ET reçues, triées par date."""
    offers = (await db.execute(
        select(TradeOffer)
        .where(
            or_(
                TradeOffer.sender_id == current_user.id,
                TradeOffer.receiver_id == current_user.id,
            )
        )
        .order_by(TradeOffer.created_at.desc())
        .limit(50)
    )).scalars().all()

    return [await _enrich_offer(o, db) for o in offers]


@router.patch("/offers/{offer_id}/accept", response_model=TradeOfferRead)
async def accept_trade(
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradeOfferRead:
    """
    Accepte une offre de trade (receiver uniquement).
    Atomique : crée les UnlockedPrompt + transfère les crédits supplement.
    """
    offer = await _get_offer_or_404(offer_id, db)

    if offer.receiver_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Seul le receiver peut accepter")
    if offer.status != TradeStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"Offre non pending (statut: {offer.status})")
    if offer.expires_at and offer.expires_at < datetime.now(timezone.utc):
        offer.status = TradeStatus.EXPIRED
        await db.commit()
        raise HTTPException(status.HTTP_410_GONE, detail="Offre expirée")

    now = datetime.now(timezone.utc)

    # 1. Créer UnlockedPrompt pour le sender (accès au prompt du receiver)
    if offer.requested_prompt_id:
        existing = (await db.execute(
            select(UnlockedPrompt).where(
                UnlockedPrompt.current_owner_id == offer.sender_id,
                UnlockedPrompt.prompt_id == offer.requested_prompt_id,
            )
        )).scalar_one_or_none()
        if not existing:
            db.add(UnlockedPrompt(
                current_owner_id=offer.sender_id,
                prompt_id=offer.requested_prompt_id,
                original_artist_id=offer.receiver_id,
            ))

    # 2. Créer UnlockedPrompt pour le receiver (accès au prompt du sender)
    if offer.offered_prompt_id:
        existing = (await db.execute(
            select(UnlockedPrompt).where(
                UnlockedPrompt.current_owner_id == offer.receiver_id,
                UnlockedPrompt.prompt_id == offer.offered_prompt_id,
            )
        )).scalar_one_or_none()
        if not existing:
            db.add(UnlockedPrompt(
                current_owner_id=offer.receiver_id,
                prompt_id=offer.offered_prompt_id,
                original_artist_id=offer.sender_id,
            ))

    # 3. Frais d'échange (BRÛLÉS) + transfert du credit_supplement.
    #
    # Frais = 20% du prix du prompt REÇU par chaque partie, plancher 2 crédits,
    # débité de chaque côté et retiré de la circulation (burn). Brûler des
    # crédits pré-achetés en € = la plateforme garde la valeur (rien n'est
    # reversé). Un échange coûte donc bien moins cher qu'acheter les deux
    # prompts (100%), ce qui pousse à l'échange tout en protégeant l'économie.
    #
    # NB v1 : pas d'écriture Transaction d'audit pour le burn (à ajouter lors
    # de l'audit global de fin de site). Royalties artiste d'origine = phase 2.
    TRADE_FEE_RATE = 0.20
    TRADE_FEE_FLOOR = 2

    def _trade_fee(price: int | None) -> int:
        if not price or price <= 0:
            return TRADE_FEE_FLOOR
        return max(TRADE_FEE_FLOOR, round(price * TRADE_FEE_RATE))

    sender = (await db.execute(
        select(User).where(User.id == offer.sender_id)
    )).scalar_one()
    receiver = (await db.execute(
        select(User).where(User.id == current_user.id)
    )).scalar_one()

    # Le sender reçoit le prompt DEMANDÉ ; le receiver reçoit le prompt OFFERT.
    sender_fee = _trade_fee(offer.requested_price_at_trade)
    receiver_fee = _trade_fee(offer.offered_price_at_trade)
    supplement = offer.credit_supplement if offer.credit_supplement > 0 else 0

    # Gardes de solde : le sender couvre son frais + le supplément.
    if sender.credits_balance < sender_fee + supplement:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="Le sender n'a plus assez de crédits (frais + supplément)",
        )
    if receiver.credits_balance < receiver_fee:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="Tu n'as pas assez de crédits pour le frais d'échange",
        )

    # Débit des frais (burn — aucun crédit reversé en face).
    sender.credits_balance -= sender_fee
    receiver.credits_balance -= receiver_fee

    # Transfert du supplément (sender → receiver), si présent.
    if supplement > 0:
        sender.credits_balance -= supplement
        receiver.credits_balance += supplement
        receiver.credits_earned_total += supplement

    # 4. Clore l'offre
    offer.status = TradeStatus.ACCEPTED
    offer.resolved_at = now

    # 5. Notifs
    await create_notification(
        db,
        user_id=offer.sender_id,
        type=NotificationType.TRADE,
        actor_id=current_user.id,
        target_type="trade",
        target_id=offer.id,
        metadata={"action": "offer_accepted",
                  "receiver_name": current_user.artist_name or "Artiste"},
    )

    # 6. Trophées d'échange (axe TRADER) — pour les DEUX parties.
    # L'offre est déjà passée ACCEPTED ci-dessus → le compteur la voit (autoflush).
    # check_and_grant ne commit pas (le caller commit) ; il grant les Smyles bonus.
    from app.models.achievement import AchievementAxis
    from app.services.achievements import check_and_grant_achievements
    await check_and_grant_achievements(
        db, user_id=offer.sender_id, axis=AchievementAxis.TRADER
    )
    await check_and_grant_achievements(
        db, user_id=offer.receiver_id, axis=AchievementAxis.TRADER
    )

    await db.commit()
    await db.refresh(offer)
    return await _enrich_offer(offer, db)


@router.patch("/offers/{offer_id}/reject", response_model=TradeOfferRead)
async def reject_trade(
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradeOfferRead:
    """Rejette une offre (receiver uniquement)."""
    offer = await _get_offer_or_404(offer_id, db)

    if offer.receiver_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Seul le receiver peut rejeter")
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
        target_type="trade",
        target_id=offer.id,
        metadata={"action": "offer_rejected"},
    )

    await db.commit()
    await db.refresh(offer)
    return await _enrich_offer(offer, db)


@router.patch("/offers/{offer_id}/cancel", response_model=TradeOfferRead)
async def cancel_trade(
    offer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradeOfferRead:
    """Annule une offre (sender uniquement, avant acceptation)."""
    offer = await _get_offer_or_404(offer_id, db)

    if offer.sender_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Seul le sender peut annuler")
    if offer.status != TradeStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"Offre non pending (statut: {offer.status})")

    offer.status = TradeStatus.CANCELLED
    offer.resolved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(offer)
    return await _enrich_offer(offer, db)
