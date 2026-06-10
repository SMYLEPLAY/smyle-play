"""
Routeur Beats (Phase 2 Marketplace VF, 2026-06-09).

  POST /artist/me/beats          → créer un beat à vendre (pas d'ADN requis)
  GET  /beats/{beat_id}/download → télécharger le fichier (réservé acheteurs)

Achat d'un beat : via le circuit prompts existant (POST /unlocks/prompt avec
le beat_id), puisqu'un beat est une ligne `prompts`. Le retrait à l'achat
(exclusif) est géré dans services/unlocks.py.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.beat import BeatCreate, BeatRead, PackBuyResult
from app.services.beats import create_beat
from app.services.pack_purchase import PackNotPurchasable, buy_pack_atomic
from app.services.unlocks import (
    AlreadyUnlocked,
    InsufficientCredits,
    SelfPurchaseForbidden,
)

router = APIRouter(tags=["beats"])

_AUDIO_MIME_BY_EXT = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
}


@router.post(
    "/artist/me/beats",
    response_model=BeatRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_beat(
    payload: BeatCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Crée un beat vendable. Aucun pré-requis ADN (décision 2026-06-09)."""
    beat = await create_beat(
        db,
        artist_id=current_user.id,
        title=payload.title,
        description=payload.description,
        price_credits=payload.price_credits,
        license_type=payload.license_type,
        max_supply=payload.max_supply,
        is_published=payload.is_published,
    )
    await db.commit()
    await db.refresh(beat)
    return BeatRead.model_validate(beat)


@router.post("/pack/{track_id}/buy", response_model=PackBuyResult)
async def buy_pack(
    track_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Achète le PACK d'un morceau : débloque la recette ET le beat en une seule
    transaction, au prix pack (track.pack_price_credits). 404 si pas d'offre
    pack, 403 self-purchase, 402 solde insuffisant, 409 déjà possédé.
    """
    try:
        result = await buy_pack_atomic(
            db, buyer_id=current_user.id, track_id=track_id
        )
        await db.commit()
    except SelfPurchaseForbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InsufficientCredits as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "insufficient_credits",
                "required": e.required,
                "available": e.available,
            },
        )
    except AlreadyUnlocked as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PackNotPurchasable as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # Email 💸 vendeur + reçu acheteur — best-effort, après commit
    # (chantier hygiène revenu 2026-06-10).
    try:
        from sqlalchemy import select as _select

        from app.models.track import Track as _Track
        from app.services.emails import send_purchase_emails
        row = (await db.execute(
            _select(_Track.title, _Track.artist_id).where(_Track.id == track_id)
        )).first()
        if row:
            await send_purchase_emails(
                db,
                buyer=current_user,
                seller_id=row.artist_id,
                amount=result["price_paid"],
                item_title=f"Beat · {row.title}",
                item_kind="prompt",
            )
    except Exception:
        pass
    return PackBuyResult(**result)


@router.get("/beats/{beat_id}/download")
async def download_beat(
    beat_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Télécharge le fichier audio d'un beat — RÉSERVÉ aux acheteurs (ou à
    l'artiste). C'est ça, le produit "beat" : l'écoute streaming est libre,
    le téléchargement est gaté par l'achat.

    404 indistinct si le beat n'existe pas (anti-énumération). 403 si l'user
    ne possède pas le beat. La vérification de possession précède tout accès
    R2 (testable sans R2).
    """
    beat = (await db.execute(
        select(Prompt).where(
            Prompt.id == beat_id,
            Prompt.product_type == "beat",
            Prompt.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    if beat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beat not found")

    # Possession : une ligne UnlockedPrompt pour ce beat, ou l'artiste lui-même.
    owns = (await db.execute(
        select(UnlockedPrompt.id).where(
            UnlockedPrompt.prompt_id == beat_id,
            UnlockedPrompt.current_owner_id == current_user.id,
        )
    )).scalar_one_or_none()
    if owns is None and beat.artist_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Achète ce beat pour pouvoir le télécharger.",
        )

    # Fichier = audio du track lié (track.beat_id = ce beat), le plus récent.
    track = (await db.execute(
        select(Track).where(
            Track.beat_id == beat_id,
            Track.is_deleted.is_(False),
        ).order_by(Track.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if track is None or not track.r2_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fichier audio indisponible pour ce beat.",
        )

    from app.services.r2 import get_r2_client, is_configured

    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 storage not configured",
        )
    client = get_r2_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 client unavailable",
        )

    key = track.r2_key
    try:
        obj = client.get_object(Bucket=settings.R2_BUCKET, Key=key)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"R2 object not found: {type(e).__name__}",
        )

    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    mime = _AUDIO_MIME_BY_EXT.get(ext, "application/octet-stream")
    safe_name = (beat.title or "beat").replace('"', "").strip() or "beat"
    filename = f"{safe_name}.{ext}" if ext else safe_name

    def _iter_chunks():
        try:
            for chunk in obj["Body"].iter_chunks(chunk_size=65536):
                yield chunk
        finally:
            try:
                obj["Body"].close()
            except Exception:
                pass

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    content_length = obj.get("ContentLength")
    if content_length:
        headers["Content-Length"] = str(content_length)

    return StreamingResponse(_iter_chunks(), media_type=mime, headers=headers)
