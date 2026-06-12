"""
Phase 9.3 — Endpoints unlock atomic.

Routes (auth requise sur toutes) :
  POST /unlocks/prompts/{prompt_id}    → débloque un prompt
  POST /unlocks/adns/{adn_id}          → achète un ADN

Le buyer vient toujours du JWT (jamais du body), et l'identifiant cible
vient de l'URL. Pas de body.

Mapping HTTP des erreurs métier :
  SelfPurchaseForbidden        → 400
  InsufficientCredits          → 402 Payment Required (avec required/available)
  PromptNotPurchasable / Adn   → 404
  AlreadyUnlocked / AlreadyOwn → 409
  IntegrityError résiduel      → 409 (course critique)
  Exception                    → 500 + rollback
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.ratelimit import LIMIT_PURCHASE, limiter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.notification import NotificationType
from app.models.user import User
from app.services.emails import send_purchase_emails
from app.services.notifications import create_notification
from app.schemas.unlock import (
    OwnedAdnRead,
    UnlockAdnResponse,
    UnlockedPromptRead,
    UnlockPromptResponse,
)
from app.schemas.voice import OwnedVoiceRead, UnlockVoiceResponse
from app.services.unlocks import (
    AdnNotPurchasable,
    AlreadyOwned,
    AlreadyUnlocked,
    InsufficientCredits,
    PromptNotPurchasable,
    SelfPurchaseForbidden,
    unlock_adn_atomic,
    unlock_playlist_adn_atomic,
    unlock_prompt_atomic,
)
from app.services.voices import (
    VoiceNotPurchasable,
    VoiceSoldOut,
    unlock_voice_atomic,
)

router = APIRouter(prefix="/unlocks", tags=["unlocks"])


# -----------------------------------------------------------------------------
# Mapping centralisé des exceptions métier → HTTP
# -----------------------------------------------------------------------------

def _raise_unlock_error(exc: ValueError) -> None:
    if isinstance(exc, SelfPurchaseForbidden):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, InsufficientCredits):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": str(exc),
                "required": exc.required,
                "available": exc.available,
            },
        )
    if isinstance(
        exc, (PromptNotPurchasable, AdnNotPurchasable, VoiceNotPurchasable)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (AlreadyUnlocked, AlreadyOwned)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, VoiceSoldOut):
        # Chantier Voix — édition limitée épuisée (#N/N vendus).
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


# -----------------------------------------------------------------------------
# POST /unlocks/prompts/{prompt_id}
# -----------------------------------------------------------------------------

@router.post(
    "/prompts/{prompt_id}",
    response_model=UnlockPromptResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(LIMIT_PURCHASE)
async def unlock_prompt(
    prompt_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Débloque un prompt.

    - Le buyer est toujours `current_user` (JWT) — jamais accepté en body
    - Refus si buyer == artiste, balance insuffisante, ou déjà unlocked
    - Perk -30% appliqué automatiquement si buyer possède l'ADN de l'artiste
    - Réponse enrichie : objet unlock + transaction + détail prix
    """
    try:
        result = await unlock_prompt_atomic(
            db=db,
            buyer_id=current_user.id,
            prompt_id=prompt_id,
        )
        await db.commit()
        await db.refresh(result.unlocked_prompt)
        await db.refresh(result.transaction)

        # Notif 💸 au vendeur (fire-and-forget)
        if result.unlocked_prompt.original_artist_id:
            await create_notification(
                db,
                user_id=result.unlocked_prompt.original_artist_id,
                type=NotificationType.PURCHASE,
                actor_id=current_user.id,
                target_type="prompt",
                target_id=prompt_id,
                metadata={
                    "amount": result.paid,
                    "buyer_name": current_user.artist_name or "Artiste",
                    "item_type": "prompt",
                },
            )
            await db.commit()

            # Email 💸 vendeur + reçu acheteur — best-effort, APRÈS commit
            # (chantier hygiène revenu 2026-06-10). Titre résolu en DB.
            try:
                from sqlalchemy import select as _select

                from app.models.prompt import Prompt as _Prompt
                _title = (await db.execute(
                    _select(_Prompt.title).where(_Prompt.id == prompt_id)
                )).scalar_one_or_none()
                await send_purchase_emails(
                    db,
                    buyer=current_user,
                    seller_id=result.unlocked_prompt.original_artist_id,
                    amount=result.paid,
                    item_title=_title,
                    item_kind="prompt",
                )
            except Exception:
                pass

        # Parrainage (mécanique 1) : 1er achat = action qualifiante qui
        # débloque la récompense si le buyer a été parrainé. Idempotent et
        # best-effort — un échec ici ne casse jamais l'achat déjà committé.
        try:
            from app.services.referrals import maybe_reward_referral
            if await maybe_reward_referral(db, current_user.id):
                await db.commit()
        except Exception:
            await db.rollback()

        return UnlockPromptResponse(
            unlocked_prompt=UnlockedPromptRead.model_validate(result.unlocked_prompt),
            transaction=result.transaction,
            perk_applied=result.perk_applied,
            base_price=result.base_price,
            paid=result.paid,
        )
    except ValueError as e:
        await db.rollback()
        _raise_unlock_error(e)
    except IntegrityError:
        # Filet : course critique non rattrapée par les checks applicatifs
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Concurrent unlock conflict, please retry",
        )
    except Exception:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlock prompt",
        )


# -----------------------------------------------------------------------------
# POST /unlocks/adns/{adn_id}
# -----------------------------------------------------------------------------

@router.post(
    "/adns/{adn_id}",
    response_model=UnlockAdnResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(LIMIT_PURCHASE)
async def unlock_adn(
    adn_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Achète un ADN. Pas de perk applicable. Une fois acheté, débloque le
    perk -30% sur tous les futurs prompts de cet artiste.
    """
    try:
        result = await unlock_adn_atomic(
            db=db,
            buyer_id=current_user.id,
            adn_id=adn_id,
        )
        await db.commit()
        await db.refresh(result.owned_adn)
        await db.refresh(result.transaction)

        # Notif 💸 au vendeur ADN (seller_id dans la transaction)
        if result.transaction.seller_id:
            await create_notification(
                db,
                user_id=result.transaction.seller_id,
                type=NotificationType.PURCHASE,
                actor_id=current_user.id,
                target_type="adn",
                target_id=adn_id,
                metadata={
                    "amount": result.paid,
                    "buyer_name": current_user.artist_name or "Artiste",
                    "item_type": "adn",
                },
            )
            await db.commit()

            # Email 💸 vendeur + reçu acheteur — best-effort, après commit.
            try:
                await send_purchase_emails(
                    db,
                    buyer=current_user,
                    seller_id=result.transaction.seller_id,
                    amount=result.paid,
                    item_kind="adn",
                )
            except Exception:
                pass

        # Parrainage (mécanique 1) : 1er achat = action qualifiante. Idempotent.
        try:
            from app.services.referrals import maybe_reward_referral
            if await maybe_reward_referral(db, current_user.id):
                await db.commit()
        except Exception:
            await db.rollback()

        return UnlockAdnResponse(
            owned_adn=OwnedAdnRead.model_validate(result.owned_adn),
            transaction=result.transaction,
            paid=result.paid,
        )
    except ValueError as e:
        await db.rollback()
        _raise_unlock_error(e)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Concurrent unlock conflict, please retry",
        )
    except Exception:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlock ADN",
        )


# -----------------------------------------------------------------------------
# POST /unlocks/voices/{voice_id}  (P1-F9 — vente de voix)
# -----------------------------------------------------------------------------

@router.post(
    "/voices/{voice_id}",
    response_model=UnlockVoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(LIMIT_PURCHASE)
async def unlock_voice(
    voice_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Achète une voix (sample audio + licence). Pas de perk applicable
    (le perk -30% est réservé aux prompts pour les détenteurs d'ADN).

    Réponse enrichie avec `sample_url` pour permettre au front d'amorcer
    le téléchargement immédiatement, sans 2e round-trip vers
    /api/voices/{id}.
    """
    try:
        result = await unlock_voice_atomic(
            db=db,
            buyer_id=current_user.id,
            voice_id=voice_id,
        )
        await db.commit()
        await db.refresh(result.owned_voice)
        await db.refresh(result.transaction)

        # Notif 💸 au vendeur voix
        if result.transaction.seller_id:
            await create_notification(
                db,
                user_id=result.transaction.seller_id,
                type=NotificationType.PURCHASE,
                actor_id=current_user.id,
                target_type="voice",
                target_id=voice_id,
                metadata={
                    "amount": result.paid,
                    "buyer_name": current_user.artist_name or "Artiste",
                    "item_type": "voice",
                },
            )
            await db.commit()

            # Email 💸 vendeur + reçu acheteur — best-effort, après commit.
            try:
                from sqlalchemy import select as _select

                from app.models.voice import Voice as _Voice
                _vname = (await db.execute(
                    _select(_Voice.name).where(_Voice.id == voice_id)
                )).scalar_one_or_none()
                await send_purchase_emails(
                    db,
                    buyer=current_user,
                    seller_id=result.transaction.seller_id,
                    amount=result.paid,
                    item_title=(f"Voix · {_vname}" if _vname else None),
                    item_kind="voice",
                )
            except Exception:
                pass

        # Parrainage (mécanique 1) : 1er achat = action qualifiante. Idempotent.
        try:
            from app.services.referrals import maybe_reward_referral
            if await maybe_reward_referral(db, current_user.id):
                await db.commit()
        except Exception:
            await db.rollback()

        return UnlockVoiceResponse(
            owned_voice=OwnedVoiceRead.model_validate(result.owned_voice),
            transaction=result.transaction,
            paid=result.paid,
            sample_url=result.sample_url,
        )
    except ValueError as e:
        await db.rollback()
        _raise_unlock_error(e)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Concurrent unlock conflict, please retry",
        )
    except Exception:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlock voice",
        )


# -----------------------------------------------------------------------------
# POST /unlocks/playlist-adn/{playlist_id}
# -----------------------------------------------------------------------------

@router.post(
    "/playlist-adn/{playlist_id}",
    status_code=status.HTTP_200_OK,
    summary="Achète l'ADN d'une playlist publique",
)
@limiter.limit(LIMIT_PURCHASE)
async def unlock_playlist_adn(
    playlist_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Achète l'ADN d'une playlist publique avec des Smyles.
    Donne ensuite droit au perk -20% sur les ADN Track de cette playlist.
    """
    try:
        result = await unlock_playlist_adn_atomic(
            db=db,
            buyer_id=current_user.id,
            playlist_id=playlist_id,
        )
        await db.commit()

        # Parrainage (mécanique 1) : 1er achat = action qualifiante. Idempotent.
        try:
            from app.services.referrals import maybe_reward_referral
            if await maybe_reward_referral(db, current_user.id):
                await db.commit()
        except Exception:
            await db.rollback()

        return {
            "ok": True,
            "playlist_id": str(playlist_id),
            "paid": result.paid,
            "message": "ADN playlist débloqué — réduction -20% sur les ADN Track de cette playlist",
        }
    except ValueError as e:
        await db.rollback()
        _raise_unlock_error(e)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Tu possèdes déjà l'ADN de cette playlist",
        )
    except Exception:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Échec de l'achat",
        )
