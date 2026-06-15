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
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import desc, func, or_, select
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

# Limite dure de résultats (miroir de /watt/search/*). Pagination simple par
# offset/limit ; l'UI affiche une grille compacte, pas d'infinite scroll au MVP.
_MAX_IMAGE_RESULTS = 60

# Plateformes reconnues pour le filtre provenance (miroir de ImagePlatform).
_VALID_PLATFORMS = {"midjourney", "dalle", "stable_diffusion", "flux", "autre"}


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


# ──────────────────────────────────────────────────────────────────────────
# Helpers de sérialisation publique (aperçu + provenance + rareté — JAMAIS
# image_r2_key / prompt_text / image_settings / negative_prompt).
# ──────────────────────────────────────────────────────────────────────────


def _image_public_dict(p: Prompt, sold_count: int | None) -> dict:
    """
    Carte-aperçu publique d'une image. Reproduit les champs rareté/supply des
    cartes ADN/prompts (compute_rarity_tier + sold/available) attendus par
    SpBadges côté front. N'expose AUCUN champ gaté.
    """
    from app.services.marketplace import compute_rarity_tier

    max_sup = p.max_supply
    ratio = None
    # `ratio` est purement descriptif et vit dans image_settings (clé 'ratio')
    # OU absent ; on ne dévoile RIEN d'autre de image_settings.
    if isinstance(p.image_settings, dict):
        r = p.image_settings.get("ratio")
        if isinstance(r, str):
            ratio = r[:20]
    return {
        "id":               str(p.id),
        "artistId":         str(p.artist_id),
        "title":            p.title,
        "description":      p.description or "",
        "productType":      p.product_type,
        "imagePlatform":    p.image_platform,
        "imageModelVersion": p.image_model_version,
        # Clé d'aperçu uniquement — l'original image_r2_key est OMIS. Le front
        # construit l'URL proxy via /watt/images/<previewKey>.
        "previewKey":       p.preview_r2_key or "",
        "ratio":            ratio,
        "priceCredits":     p.price_credits,
        "maxSupply":        max_sup,
        "rarityTier":       compute_rarity_tier(max_sup),
        "soldCount":        (sold_count if max_sup is not None else None),
        "availableCount":   ((max_sup - (sold_count or 0)) if max_sup is not None else None),
        "isSoldOut":        (max_sup is not None and (sold_count or 0) >= max_sup),
        "createdAt":        p.created_at.isoformat() if p.created_at else None,
    }


async def _sold_counts_for(db: AsyncSession, image_ids: list[UUID]) -> dict:
    """
    Compte vendu (UnlockedPrompt) pour un lot d'images en UNE requête groupée
    (pas de N+1). Retourne {prompt_id: sold_count}.
    """
    if not image_ids:
        return {}
    rows = (await db.execute(
        select(
            UnlockedPrompt.prompt_id,
            func.count(UnlockedPrompt.id),
        )
        .where(UnlockedPrompt.prompt_id.in_(image_ids))
        .group_by(UnlockedPrompt.prompt_id)
    )).all()
    return {pid: int(cnt) for pid, cnt in rows}


def _apply_image_filters(
    stmt,
    *,
    q: str | None,
    platform: str | None,
    rarity: str | None,
    price_min: int | None,
    price_max: int | None,
    ratio: str | None,
):
    """
    Filtres serveur partagés (miroir du style /watt/search/tracks). La facette
    nature ('image') est appliquée par l'appelant ; ici on raffine provenance,
    prix, rareté et texte. Le ratio est filtré en JSONB (image_settings->>ratio).
    """
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Prompt.title.ilike(pattern), User.artist_name.ilike(pattern)))
    if platform and platform in _VALID_PLATFORMS:
        stmt = stmt.where(Prompt.image_platform == platform)
    if price_min is not None:
        stmt = stmt.where(Prompt.price_credits >= price_min)
    if price_max is not None:
        stmt = stmt.where(Prompt.price_credits <= price_max)
    if ratio:
        # image_settings->>'ratio' (JSONB). Si la clé manque → exclu.
        stmt = stmt.where(Prompt.image_settings["ratio"].astext == ratio)
    if rarity:
        # Filtre par tier dérivé du max_supply (pas une colonne stockée).
        if rarity == "unlimited":
            stmt = stmt.where(Prompt.max_supply.is_(None))
        elif rarity == "mythic":
            stmt = stmt.where(Prompt.max_supply == 1)
        elif rarity == "legendary":
            stmt = stmt.where(Prompt.max_supply.between(2, 10))
        elif rarity == "limited":
            stmt = stmt.where(Prompt.max_supply.between(11, 10000))
        elif rarity == "open":
            stmt = stmt.where(Prompt.max_supply > 10000)
    return stmt


# ──────────────────────────────────────────────────────────────────────────
# GET /images — listing PUBLIC filtrable (vitrine + page /images)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/images")
async def list_public_images(
    q: str = Query(default="", max_length=100),
    platform: Optional[str] = Query(default=None, max_length=50),
    rarity: Optional[str] = Query(default=None, max_length=20),
    price_min: Optional[int] = Query(default=None, ge=0),
    price_max: Optional[int] = Query(default=None, ge=0),
    ratio: Optional[str] = Query(default=None, max_length=20),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=_MAX_IMAGE_RESULTS, ge=1, le=_MAX_IMAGE_RESULTS),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Catalogue public d'images IA publiées (artistes publiés uniquement).

    Emplacement choisi : sous le router /images (même router que la création
    et le download) plutôt que dans watt_compat. Raison : cohérence — toute la
    nature 'image' vit dans ce module dédié, on évite d'alourdir le compat
    layer historique destiné à disparaître. Le gate profile_public est appliqué
    en JOIN sur User, comme /watt/search/tracks.

    Renvoie {images:[ImagePublicRead-like], count} — aperçu + provenance +
    rareté + prix. JAMAIS image_r2_key / prompt_text / image_settings (hors
    'ratio' descriptif) / negative_prompt.
    """
    base = (
        select(Prompt, User)
        .join(User, Prompt.artist_id == User.id)
        .where(
            Prompt.product_type == "image",
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            User.profile_public.is_(True),
        )
    )
    base = _apply_image_filters(
        base,
        q=q or None,
        platform=platform,
        rarity=rarity,
        price_min=price_min,
        price_max=price_max,
        ratio=ratio,
    )
    base = base.order_by(desc(Prompt.created_at)).offset(offset).limit(limit)

    rows = (await db.execute(base)).all()
    prompts = [p for (p, _u) in rows]
    sold = await _sold_counts_for(db, [p.id for p in prompts])
    images = [_image_public_dict(p, sold.get(p.id)) for p in prompts]
    return {"query": q, "count": len(images), "images": images}


# ──────────────────────────────────────────────────────────────────────────
# GET /watt/users/{slug}/images — listing PUBLIC par artiste (profil)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/watt/users/{slug}/images")
async def list_public_images_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Images publiées d'un artiste exposées sur /u/<slug> (miroir de
    /watt/users/{slug}/playlists). Réutilise _find_artist_by_slug (gate
    profile_public). Renvoie {images, count} en lecture publique.
    """
    from app.routers.follows import _find_artist_by_slug

    target = await _find_artist_by_slug(db, slug)
    rows = (await db.execute(
        select(Prompt)
        .where(
            Prompt.artist_id == target.id,
            Prompt.product_type == "image",
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
        )
        .order_by(desc(Prompt.created_at))
        .limit(_MAX_IMAGE_RESULTS)
    )).scalars().all()
    sold = await _sold_counts_for(db, [p.id for p in rows])
    images = [_image_public_dict(p, sold.get(p.id)) for p in rows]
    return {"slug": slug, "count": len(images), "images": images}


# ──────────────────────────────────────────────────────────────────────────
# GET /artist/me/images — listing OWNER (compte / WattBoard)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/artist/me/images", response_model=list[ImageOwnerRead])
async def list_my_images(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImageOwnerRead]:
    """
    Mes images (owner) — recette dévoilée (ImageOwnerRead). Inclut les
    brouillons (is_published=False) pour que le WattBoard montre l'état.
    Exclut les soft-deleted.
    """
    rows = (await db.execute(
        select(Prompt)
        .where(
            Prompt.artist_id == current_user.id,
            Prompt.product_type == "image",
            Prompt.is_deleted.is_(False),
        )
        .order_by(desc(Prompt.created_at))
    )).scalars().all()
    return [ImageOwnerRead.model_validate(p) for p in rows]


# ──────────────────────────────────────────────────────────────────────────
# GET /artist/me/images/count — compteur (tuile WattBoard)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/artist/me/images/count")
async def count_my_images(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Compteur d'images de l'artiste connecté (publiées + brouillons, hors
    soft-deleted) pour la tuile « Images IA » du WattBoard. Une seule requête
    COUNT — pas de N+1.
    """
    total = (await db.execute(
        select(func.count(Prompt.id)).where(
            Prompt.artist_id == current_user.id,
            Prompt.product_type == "image",
            Prompt.is_deleted.is_(False),
        )
    )).scalar_one()
    published = (await db.execute(
        select(func.count(Prompt.id)).where(
            Prompt.artist_id == current_user.id,
            Prompt.product_type == "image",
            Prompt.is_deleted.is_(False),
            Prompt.is_published.is_(True),
        )
    )).scalar_one()
    return {"count": int(total), "published": int(published)}


# ──────────────────────────────────────────────────────────────────────────
# GET /watt/images/{key} — proxy aperçu PUBLIC (preview_r2_key uniquement)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/watt/images/{key:path}")
async def stream_image_preview(key: str):
    """
    Proxy same-origin de l'APERÇU R2 (miroir de /watt/stream pour l'audio).
    Sert UNIQUEMENT les clés du préfixe `images/previews/` : l'original
    `images/originals/...` n'est JAMAIS atteignable par ce proxy (gate dur
    ci-dessous) — il passe exclusivement par /images/{id}/download après achat.
    """
    # Gate dur : seules les clés d'aperçu sont servables publiquement.
    if not key.startswith("images/previews/"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
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
    mime = IMAGE_MIME_BY_EXT.get(ext, "image/jpeg")

    def _iter_chunks():
        try:
            for chunk in obj["Body"].iter_chunks(chunk_size=65536):
                yield chunk
        finally:
            try:
                obj["Body"].close()
            except Exception:
                pass

    headers = {"Cache-Control": "public, max-age=3600"}
    content_length = obj.get("ContentLength")
    if content_length:
        headers["Content-Length"] = str(content_length)

    return StreamingResponse(_iter_chunks(), media_type=mime, headers=headers)


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
