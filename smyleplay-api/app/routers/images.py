"""
Routeur Images IA (C4 Monde Visuel V1, 2026-06-14).

  POST /artist/me/images        → créer une image IA à vendre (multipart)
  GET  /images/{image_id}/download → télécharger l'ORIGINAL (réservé acheteurs)

Achat d'une image : via le circuit prompts existant (POST /unlocks/prompt avec
l'image_id), puisqu'une image est une ligne `prompts`. Le mint #X/N et le
stock-out atomique sont gérés par unlock_prompt_atomic — rien à dupliquer ici.

Download : route DÉDIÉE plutôt que de généraliser download_beat. Raison : le
handler beats est centré Track (il lit track.r2_key via prompt_id/beat_id) ;
une image n'a PAS de Track, le fichier vit sur prompt.image_r2_key. Greffer la
branche image dans ce handler le complexifierait et risquerait de casser les
deux routes existantes (/products/{id}/download, /beats/{id}/download) qui
restent INTACTES. La vérification de possession est identique (UnlockedPrompt
current_owner_id OU artiste propriétaire).
"""
import json
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.prompt import Prompt
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.image import ImageCreate, ImageOwnerRead
from app.services.images import (
    ALLOWED_CONTENT_TYPES,
    IMAGE_MAX_BYTES,
    IMAGE_MIME_BY_EXT,
    ImageUploadError,
    R2NotConfigured,
    create_image,
    upload_image_assets,
)

router = APIRouter(tags=["images"])


@router.post(
    "/artist/me/images",
    response_model=ImageOwnerRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_image(
    file: UploadFile = File(...),
    title: str = Form(...),
    image_platform: str = Form(...),
    image_model_version: str = Form(...),
    prompt_text: str = Form(...),
    image_settings: str | None = Form(default=None),
    negative_prompt: str | None = Form(default=None),
    description: str | None = Form(default=None),
    ratio: str | None = Form(default=None),
    price_credits: int = Form(...),
    max_supply: int | None = Form(default=None),
    is_published: bool = Form(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Crée une image IA vendable (product_type='image'). Aucun pré-requis ADN,
    comme les beats. Le fichier est uploadé en R2 (original + aperçu réduit).

    image_settings est reçu en chaîne JSON (multipart) puis parsé en dict.
    """
    # ── Parse image_settings (JSON string → dict) ───────────────────────────
    settings_dict = None
    if image_settings:
        try:
            parsed = json.loads(image_settings)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="image_settings doit être un JSON valide.",
            )
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="image_settings doit être un objet JSON.",
            )
        settings_dict = parsed

    # ── Validation des champs via Pydantic (bornes prix/titre/provenance) ───
    try:
        payload = ImageCreate(
            title=title,
            description=description,
            prompt_text=prompt_text,
            image_platform=image_platform,
            image_model_version=image_model_version,
            image_settings=settings_dict,
            negative_prompt=negative_prompt,
            ratio=ratio,
            price_credits=price_credits,
            max_supply=max_supply,
            is_published=is_published,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors(include_url=False),
        )

    # ── Validation fichier : type + taille ──────────────────────────────────
    ct = (file.content_type or "").lower()
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ct not in ALLOWED_CONTENT_TYPES and ext not in IMAGE_MIME_BY_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format non supporté. Utilise PNG, JPG ou WebP.",
        )
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Fichier vide."
        )
    if len(data) > IMAGE_MAX_BYTES:
        mb = len(data) / 1024 / 1024
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image trop lourde ({mb:.1f} Mo). Limite : 20 Mo.",
        )

    # ── Upload R2 (original + aperçu) ────────────────────────────────────────
    try:
        image_r2_key, preview_r2_key = await upload_image_assets(
            data=data, filename=filename, content_type=ct
        )
    except R2NotConfigured as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        )
    except ImageUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

    # ── Création de la ligne prompts (product_type='image') ─────────────────
    image = await create_image(
        db,
        artist_id=current_user.id,
        title=payload.title,
        description=payload.description,
        prompt_text=payload.prompt_text,
        image_platform=payload.image_platform,
        image_model_version=payload.image_model_version,
        image_settings=payload.image_settings,
        negative_prompt=payload.negative_prompt,
        price_credits=payload.price_credits,
        max_supply=payload.max_supply,
        image_r2_key=image_r2_key,
        preview_r2_key=preview_r2_key,
        is_published=payload.is_published,
    )
    await db.commit()
    await db.refresh(image)
    # L'artiste créateur est propriétaire → lecture complète (recette dévoilée).
    return ImageOwnerRead.model_validate(image)


@router.get("/images/{image_id}/download")
async def download_image(
    image_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Télécharge l'ORIGINAL d'une image possédée — réservé aux acheteurs
    (ou à l'artiste propriétaire). L'aperçu (preview_r2_key) reste public ;
    seul l'original (image_r2_key) est gaté.

    404 indistinct si l'image n'existe pas (anti-énumération). 403 si l'user
    ne la possède pas. La vérification de possession précède tout accès R2.
    """
    product = (await db.execute(
        select(Prompt).where(
            Prompt.id == image_id,
            Prompt.product_type == "image",
            Prompt.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )

    # Possession : une ligne UnlockedPrompt pour ce produit, ou l'artiste.
    owns = (await db.execute(
        select(UnlockedPrompt.id).where(
            UnlockedPrompt.prompt_id == image_id,
            UnlockedPrompt.current_owner_id == current_user.id,
        )
    )).scalar_one_or_none()
    if owns is None and product.artist_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Achète cet exemplaire pour pouvoir le télécharger.",
        )

    key = product.image_r2_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fichier image indisponible pour cet exemplaire.",
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

    try:
        obj = client.get_object(Bucket=settings.R2_BUCKET, Key=key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"R2 object not found: {type(e).__name__}",
        )

    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    mime = IMAGE_MIME_BY_EXT.get(ext, "application/octet-stream")
    safe_name = (product.title or "image").replace('"', "").strip() or "image"
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
