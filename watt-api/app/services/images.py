"""
Service Images IA (C4 Monde Visuel V1, 2026-06-14).

Une image est une ligne `prompts` avec product_type='image'. Pas de Track :
le fichier original ET son aperçu réduit vivent sur la ligne `prompts`
(image_r2_key / preview_r2_key). Achat/possession/revente/royalties
réutilisent la machinerie des prompts (UnlockedPrompt, unlock_prompt_atomic).

Pipeline upload :
  1. Validation (côté router, app.core.fichiers) : type RÉEL par signature
     (PNG/JPG/WebP), refus SVG/HTML/scripts, image décodable, taille ≤ 20 Mo.
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

# Étape 5 : la limite vit dans config.py (UPLOAD_MAX_IMAGE_MB, défaut 20 Mo).
IMAGE_MAX_BYTES = settings.UPLOAD_MAX_IMAGE_MB * 1024 * 1024
PREVIEW_MAX_SIDE = 1024  # côté long de l'aperçu
PREVIEW_JPEG_QUALITY = 80


class R2NotConfigured(RuntimeError):
    """R2 indisponible (secrets manquants). → HTTP 503."""


class R2Unavailable(R2NotConfigured):
    """Lot E — R2 injoignable ou en erreur pendant l'envoi. → HTTP 503."""


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

    from app.core.fichiers import appliquer_plafond_pillow

    appliquer_plafond_pillow()
    from PIL import ImageOps

    with Image.open(io.BytesIO(data)) as img:
        # Photo de téléphone : le sens est noté dans l'EXIF, pas dans les
        # pixels. On l'applique, sinon l'aperçu (sans EXIF) sort couché.
        img = ImageOps.exif_transpose(img) or img
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
    # Sécurité (2026-07-30) : l'uid de l'ORIGINAL est DÉCORRÉLÉ de celui de
    # l'aperçu. Auparavant original et aperçu partageaient le même uid → la clé
    # de l'original (`images/originals/{uid}.ext`) était DEVINABLE depuis
    # l'aperçu public (`images/previews/{uid}.jpg`). On génère donc un uid
    # aléatoire SÉPARÉ pour l'original ; cette clé n'est JAMAIS renvoyée par une
    # réponse API → inatteignable sans achat, même dans un bucket public.
    uid = _uuid.uuid4().hex           # aperçu (public, clé exposée)
    orig_uid = _uuid.uuid4().hex      # original (secret, clé jamais exposée)
    image_r2_key = f"images/originals/{orig_uid}.{ext}"
    preview_r2_key = f"images/previews/{uid}.jpg"
    # L'ORIGINAL comme l'APERÇU vivent dans le bucket PUBLIC (settings.R2_BUCKET) :
    # le token R2 courant sait y écrire (le bucket privé n'est pas garanti
    # accessible). La sécurité de l'original ne repose plus sur le bucket mais sur
    # le caractère SECRET + aléatoire de sa clé (jamais transmise).
    public_bucket = settings.R2_BUCKET

    # Aperçu (CPU/mémoire-bound → thread)
    try:
        preview_bytes = await asyncio.to_thread(_generate_preview, data)
    except Exception as exc:  # noqa: BLE001
        raise ImageUploadError(
            f"Préview impossible : {type(exc).__name__}: {str(exc)[:200]}"
        ) from exc

    # ORIGINAL → bucket PUBLIC, mais clé SECRÈTE (uid aléatoire séparé,
    # jamais renvoyée par l'API) → inatteignable sans achat.
    # APERÇU → bucket PUBLIC (inchangé).
    # Lot E : envois hors boucle asyncio, délais courts ; panne R2 → 503.
    from app.services.r2 import R2Absent, R2Indisponible, appel_r2

    try:
        await appel_r2(
            client.put_object, Bucket=public_bucket, Key=image_r2_key,
            Body=data, ContentType=mime, operation="put_object", key=image_r2_key,
        )
        await appel_r2(
            client.put_object, Bucket=public_bucket, Key=preview_r2_key,
            Body=preview_bytes, ContentType="image/jpeg",
            operation="put_object", key=preview_r2_key,
        )
    except (R2Indisponible, R2Absent) as exc:
        raise R2Unavailable(
            "Stockage des fichiers momentanément indisponible. Réessaie dans un instant."
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


# ── Lot M (B1) : redresser les aperçus déjà créés ─────────────────────────────
# Avant le correctif EXIF, une photo prise au téléphone donnait un aperçu
# couché. On relit l'original ; s'il porte une orientation EXIF, on refait
# l'aperçu sous une NOUVELLE clé (le CDN garde l'ancienne en cache) et on met
# la ligne à jour. L'ancien aperçu n'est pas supprimé.

def _orientation_exif(data: bytes) -> int:
    from PIL import Image

    from app.core.fichiers import appliquer_plafond_pillow

    appliquer_plafond_pillow()
    try:
        with Image.open(io.BytesIO(data)) as img:
            return int(img.getexif().get(0x0112, 1) or 1)
    except Exception:  # noqa: BLE001
        return 1


async def redresser_apercus(db: AsyncSession, *, limite: int = 300) -> dict[str, Any]:
    """Refait les aperçus des images dont l'original est tourné par l'EXIF."""
    from sqlalchemy import select

    from app.models.prompt_gallery_image import PromptGalleryImage
    from app.services.r2 import R2Absent, R2Indisponible, appel_r2

    if not is_configured():
        raise R2NotConfigured("R2 storage not configured")
    client = get_r2_client()
    if client is None:
        raise R2NotConfigured("R2 client unavailable")
    bucket = settings.R2_BUCKET

    lignes: list[Any] = []
    for modele in (Prompt, PromptGalleryImage):
        res = await db.execute(
            select(modele).where(
                modele.image_r2_key.is_not(None),
                modele.preview_r2_key.is_not(None),
            ).limit(limite)
        )
        lignes.extend(res.scalars().all())

    bilan = {"examinees": 0, "redressees": 0, "erreurs": 0}
    for ligne in lignes[:limite]:
        bilan["examinees"] += 1
        try:
            obj = await appel_r2(client.get_object, Bucket=bucket,
                                 Key=ligne.image_r2_key, operation="get_object",
                                 key=ligne.image_r2_key)
            data = await asyncio.to_thread(obj["Body"].read)
            if await asyncio.to_thread(_orientation_exif, data) in (1, 0):
                continue
            apercu = await asyncio.to_thread(_generate_preview, data)
            cle = f"images/previews/{_uuid.uuid4().hex}.jpg"
            await appel_r2(client.put_object, Bucket=bucket, Key=cle,
                           Body=apercu, ContentType="image/jpeg",
                           operation="put_object", key=cle)
            ligne.preview_r2_key = cle
            bilan["redressees"] += 1
        except (R2Absent, R2Indisponible, Exception):  # noqa: BLE001
            bilan["erreurs"] += 1
    if bilan["redressees"]:
        await db.commit()
    return bilan
