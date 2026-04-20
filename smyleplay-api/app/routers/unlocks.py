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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.unlock import (
    OwnedAdnRead,
    UnlockAdnResponse,
    UnlockedPromptRead,
    UnlockPromptResponse,
)
from app.services.unlocks import (
    AdnNotPurchasable,
    AlreadyOwned,
    AlreadyUnlocked,
    InsufficientCredits,
    PromptNotPurchasable,
    SelfPurchaseForbidden,
    unlock_adn_atomic,
    unlock_prompt_atomic,
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
    if isinstance(exc, (PromptNotPurchasable, AdnNotPurchasable)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (AlreadyUnlocked, AlreadyOwned)):
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
async def unlock_prompt(
    prompt_id: UUID,
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
async def unlock_adn(
    adn_id: UUID,
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
