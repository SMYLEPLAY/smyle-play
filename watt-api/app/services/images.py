"""
Service Images IA (C4 Monde Visuel V1, 2026-06-14).

Une image est une ligne `prompts` avec product_type='image'. Pas de Track :
le fichier original ET son aperçu réduit vivent sur la ligne `prompts`
(image_r2_key / preview_r2_key). Achat/possession/revente/royalties
réutilisent la machinerie des prompts (UnlockedPrompt, unlock_prompt_atomic).

Pipeline upload :
  1. Validation MIME (PNG/JPG/WebP) + taille (≤ 20 Mo).
  2. Upload de l'ORIGINAL vers R2, préfixe `images/originals/` (jamais public).
  3. Génération d'un APERÇU via Pillow (max 1024px côté long, JPEG q80).
  4. Upload de l'aperçu vers R2, préfixe `images/previews/` (public).
  5. INSERT de la ligne `prompts` (product_type='image', provenance, settings,
     max_supply pour le #X/N — le mint des exemplaires se fait à l'ACHAT, dans
     unlock_prompt_atomic, comme pour tous les prompts).
"""
from __future__ import annotations

import asyncio
import io
import uuid as _uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.prompt import Prompt
from app.services.r2 import get_r2_client, is_configured

# Formats acceptés (extension → MIME). PNG / JPG / WebP uniquement.
IMAGE_MIME_BY_EXT: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
# Validation par content-type (le front peut envoyer image/jpg ou image/jpeg).
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

IMAGE_MAX_BYTES = 20 * 1024 * 1024  # 20 Mo
PREVIEW_MAX_SIDE = 1024  # côté long de l'aperçu
PREVIEW_JPEG_QUALITY = 80


class R2NotConfigured(RuntimeError):
    """R2 indisponible (secrets manquants). → HTTP 503."""


class ImageUploadError(RuntimeError):
    """Échec d'upload R2 ou de génération d'aperçu. → HTTP 500."""


def _ext_for(filename: str | None, content_type: str | None) -> str:
    """Déduit une extension normalisée (png|jpg|webp) à partir du nom/MIME."""
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in IMAGE_MIME_BY_EXT:
            return "jpg" if ext == "jpeg" else ext
    ct = (content_type or "").lower()
    if ct in ("image/jpeg", "image/jpg"):
        return "jpg"
    if ct == "image/png":
        return "png"
    if ct == "image/webp":
        return "webp"
    return "jpg"


def _generate_preview(data: bytes) -> bytes:
    """
    Génère un aperçu JPEG (max 1024px côté long, qualité 80) à partir des
    octets de l'image originale. Synchrone (Pillow) → appelé via executor.

    NB Railway : un très gros PNG peut être coûteux en mémoire à décoder ;
    surveiller (cf. note livraison). On aplatit la transparence sur fond
    blanc (JPEG ne supporte pas l'alpha).
    """
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGBA") if img.mode in ("P", "LA") else img
        if img.mode in ("RGBA", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        img.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE), Image.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=PREVIEW_JPEG_QUALITY, optimize=True)
        return out.getvalue()


async def upload_image_assets(
    *, data: bytes, filename: str | None, content_type: str | None
) -> tuple[str, str]:
    """
    Upload original + aperçu vers R2. Retourne (image_r2_key, preview_r2_key).

    Lève R2NotConfigured si R2 indisponible, ImageUploadError sur échec.
    La validation MIME/taille est faite côté router AVANT d'appeler ce service.
    """
    if not is_configured():
        raise R2NotConfigured("R2 storage not configured")
    client = get_r2_client()
    if client is None:
        raise R2NotConfigured("R2 client unavailable")

    ext = _ext_for(filename, content_type)
    mime = IMAGE_MIME_BY_EXT.get(ext, "image/jpeg")
    uid = _uuid.uuid4().hex
    image_r2_key = f"images/originals/{uid}.{ext}"
    preview_r2_key = f"images/previews/{uid}.jpg"
    # L'ORIGINAL payant part dans le bucket PRIVÉ (sécurité : clé devinable →
    # jamais servable publiquement). L'APERÇU reste dans le bucket PUBLIC, servi
    # tel quel par le proxy /watt/images. Tant que R2_PRIVATE_BUCKET n'est pas
    # défini, effective_private_bucket == R2_BUCKET → comportement identique.
    private_bucket = settings.effective_private_bucket
    public_bucket = settings.R2_BUCKET

    loop = asyncio.get_event_loop()

    # Aperçu (CPU/mémoire-bound → executor)
    try:
        preview_bytes = await loop.run_in_executor(None, _generate_preview, data)
    except Exception as exc:  # noqa: BLE001
        raise ImageUploadError(
            f"Préview impossible : {type(exc).__name__}: {str(exc)[:200]}"
        ) from exc

    def _sync_put_original() -> None:
        # ORIGINAL → bucket PRIVÉ (jamais public).
        client.put_object(
            Bucket=private_bucket, Key=image_r2_key, Body=data, ContentType=mime
        )

    def _sync_put_preview() -> None:
        # APERÇU → bucket PUBLIC (inchangé).
        client.put_object(
            Bucket=public_bucket, Key=preview_r2_key, Body=preview_bytes, ContentType="image/jpeg"
        )

    try:
        await loop.run_in_executor(None, _sync_put_original)
        await loop.run_in_executor(None, _sync_put_preview)
    except Exception as exc:  # noqa: BLE001
        raise ImageUploadError(
            f"Upload R2 échoué : {type(exc).__name__}: {str(exc)[:200]}"
        ) from exc

    return image_r2_key, preview_r2_key


async def create_image(
    db: AsyncSession,
    *,
    artist_id: _uuid.UUID,
    title: str,
    description: str | None,
    prompt_text: str,
    image_platform: str,
    image_model_version: str,
    image_settings: dict[str, Any] | None,
    negative_prompt: str | None,
    price_credits: int,
    max_supply: int | None,
    image_r2_key: str,
    preview_r2_key: str,
    is_published: bool = False,
    image_style: str | None = None,
    image_tags: str | None = None,
) -> Prompt:
    """
    Crée une image vendable (product_type='image').

    - prompt_text NOT NULL (recette d'image), sans borne de longueur.
    - provenance obligatoire (plateforme + version modèle).
    - max_supply porte la rareté #X/N ; le mint des exemplaires est fait à
      l'achat (unlock_prompt_atomic), pas ici — on ne réimplémente rien.
    """
    image = Prompt(
        artist_id=artist_id,
        title=title,
        description=description,
        prompt_text=prompt_text,
        price_credits=price_credits,
        is_published=is_published,
        max_supply=max_supply,
        product_type="image",
        image_platform=image_platform,
        image_model_version=image_model_version,
        image_settings=image_settings,
        negative_prompt=negative_prompt,
        image_r2_key=image_r2_key,
        preview_r2_key=preview_r2_key,
        image_style=image_style,
        image_tags=image_tags,
    )
    db.add(image)
    await db.flush()
    return image
