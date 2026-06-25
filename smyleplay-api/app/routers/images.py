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
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pathlib import Path as _Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse

# index.html à la racine du repo (smyleplay-api/app/routers/images.py → parents[3]).
# Sert à rendre la PAGE marketplace quand un navigateur ouvre /images en direct
# (sinon l'API JSON ci-dessous masque la page HTML Flask — cf. content-nego).
_INDEX_HTML = _Path(__file__).resolve().parents[3] / "index.html"
from pydantic import ValidationError
from sqlalchemy import desc, false as sa_false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.prompt import Prompt
from app.models.prompt_gallery_image import PromptGalleryImage
from app.models.prompt_like import PromptLike
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.image import ImageCreate, ImageOwnerRead, ImageUpdate
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

# ──────────────────────────────────────────────────────────────────────────
# Taxonomie visuelle (C4 DNA image, migration 0061) — listes autorisées.
#
# Validation LÉGÈRE et SOUPLE (décision : valeur hors-liste = IGNORÉE, pas de
# 400) : le style/les tags sont des aides à la découverte, pas un contrat
# strict — on ne veut pas faire échouer une création d'image parce qu'un front
# a envoyé une valeur exotique. Une valeur inconnue est simplement droppée
# (style → None, tag → retiré de la CSV). Le style et les tags restent
# OPTIONNELS : ne renseigner ni l'un ni l'autre ne casse RIEN.
# ──────────────────────────────────────────────────────────────────────────
STYLES: tuple[str, ...] = (
    "realiste",
    "cartoon",
    "anime",
    "3d",
    "peinture",
    "aquarelle",
    "croquis",
    "pixel_art",
    "cyberpunk",
    "fantasy",
    "minimaliste",
    "retro",
    "abstrait",
    "surrealiste",
    "comics",
    "photo",
)
USAGE_TAGS: tuple[str, ...] = (
    "cover",
    "portrait",
    "paysage",
    "logo",
    "banniere",
    "avatar",
    "wallpaper",
    "mockup",
    "illustration",
    "texture",
    "fx",
)
# Nombre max de tags retenus sur une image (garde-fou anti-payload).
_MAX_IMAGE_TAGS = len(USAGE_TAGS)


def _clean_image_style(raw: str | None) -> str | None:
    """
    Normalise + valide un style d'image. Renvoie None si absent ou hors-liste
    (validation souple : on n'échoue pas, on ignore). Casse insensible.
    """
    if raw is None:
        return None
    s = raw.strip().lower()
    if not s:
        return None
    return s if s in STYLES else None


def _clean_image_tags(raw: str | None) -> str | None:
    """
    Normalise une CSV de tags d'usage : split sur virgule, lowercase, ne garde
    que les tags connus (USAGE_TAGS), déduplique en conservant l'ordre, plafonne
    à _MAX_IMAGE_TAGS. Renvoie une CSV propre ("cover,fx") ou None si vide.
    Validation souple : les tags inconnus sont silencieusement retirés.
    """
    if raw is None:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for part in raw.split(","):
        tag = part.strip().lower()
        if not tag or tag not in USAGE_TAGS or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
        if len(out) >= _MAX_IMAGE_TAGS:
            break
    return ",".join(out) if out else None


def _tags_to_list(csv: str | None) -> list[str]:
    """CSV stockée → liste de tags pour le payload public ([] si vide)."""
    if not csv:
        return []
    return [t for t in (x.strip() for x in csv.split(",")) if t]


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
    # ── Taxonomie visuelle (C4 DNA image) — OPTIONNELS ─────────────────────
    # style : un seul code parmi STYLES (recommandé, pas obligatoire).
    # tags  : CSV de codes parmi USAGE_TAGS (incl. 'fx'). Validation souple :
    # valeurs hors-liste ignorées (cf. _clean_image_style / _clean_image_tags).
    image_style: str | None = Form(default=None),
    image_tags: str | None = Form(default=None),
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
        # Taxonomie visuelle : nettoyée/validée souplement avant stockage.
        image_style=_clean_image_style(image_style),
        image_tags=_clean_image_tags(image_tags),
    )
    # Trophées IMAGE_CREATOR (parité avec l'audio) — l'axe compte les images
    # PUBLIÉES ; on ne hooke donc que si l'image est créée déjà publiée. Le
    # service utilise ses propres begin_nested ; le commit final est ci-dessous.
    if image.is_published:
        from app.models.achievement import AchievementAxis
        from app.services.achievements import check_and_grant_achievements
        await check_and_grant_achievements(
            db, user_id=current_user.id, axis=AchievementAxis.IMAGE_CREATOR
        )
    await db.commit()
    await db.refresh(image)
    # L'artiste créateur est propriétaire → lecture complète (recette dévoilée).
    # Une image fraichement creee n'a pas encore de partenaire (linkedSound=None).
    return await _owner_read_with_link(db, image)


# ──────────────────────────────────────────────────────────────────────────
# Helpers de sérialisation publique (aperçu + provenance + rareté — JAMAIS
# image_r2_key / prompt_text / image_settings / negative_prompt).
# ──────────────────────────────────────────────────────────────────────────


def _image_public_dict(
    p: Prompt, sold_count: int | None, artist: User | None = None
) -> dict:
    """
    Carte-aperçu publique d'une image. Reproduit les champs rareté/supply des
    cartes ADN/prompts (compute_rarity_tier + sold/available) attendus par
    SpBadges côté front. N'expose AUCUN champ gaté.

    `artist` (optionnel) : le User créateur, pour exposer nom + slug PUBLICS
    (artistName / artistSlug) — parité avec la fiche son. AUCUN champ privé de
    l'artiste n'est exposé. Si None, les deux clés sont omises (le front
    n'affiche rien plutôt qu'un « — » moche).
    """
    from app.services.marketplace import compute_rarity_tier
    from app.routers.watt_compat import _derive_artist_slug

    max_sup = p.max_supply
    ratio = None
    # `ratio` est purement descriptif et vit dans image_settings (clé 'ratio')
    # OU absent ; on ne dévoile RIEN d'autre de image_settings.
    if isinstance(p.image_settings, dict):
        r = p.image_settings.get("ratio")
        if isinstance(r, str):
            ratio = r[:20]
    out = {
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
        # Taxonomie visuelle (DNA image) — champs PUBLICS (aide à la
        # découverte, aucune fuite). style = code ou None ; tags = liste.
        "style":            p.image_style,
        "tags":             _tags_to_list(p.image_tags),
        "priceCredits":     p.price_credits,
        "maxSupply":        max_sup,
        "rarityTier":       compute_rarity_tier(max_sup),
        "soldCount":        (sold_count if max_sup is not None else None),
        "availableCount":   ((max_sup - (sold_count or 0)) if max_sup is not None else None),
        "isSoldOut":        (max_sup is not None and (sold_count or 0) >= max_sup),
        "createdAt":        p.created_at.isoformat() if p.created_at else None,
        # C4 « Oeuvre complete » : flag + partenaire son. linkedSound est
        # rempli a posteriori par _enrich_linked_sounds (requete Track groupee).
        "isOeuvreComplete": p.linked_prompt_id is not None,
        "linkedSound":      None,
        # Nature du lien : True = « ne ensemble » (cette image ne s'affiche
        # PAS en carte individuelle sur les surfaces publiques ; les listings
        # publics la filtrent deja en amont). Expose pour la vue owner qui,
        # elle, l'affiche quand meme — le front s'en sert pour ne pas dupliquer.
        "bundleExclusive":  bool(p.bundle_exclusive),
        # C4 galerie avatar — APERÇUS publics de la galerie (jamais les
        # originaux). galleryCount = nb d'images supplementaires, galleryPreviews
        # = liste de previewKey publics. Peuples a posteriori par
        # _enrich_galleries (requete groupee, pas de N+1) ; defaut vide pour ne
        # rien casser si l'enrichissement n'est pas appele.
        "galleryCount":     0,
        "galleryPreviews":  [],
    }
    # Artiste public (nom + slug) — parité fiche son. Omis si non résolu.
    if artist is not None:
        out["artistName"] = artist.artist_name or ""
        out["artistSlug"] = _derive_artist_slug(artist)
    return out


async def _artist_map_for(
    db: AsyncSession, prompts: list[Prompt]
) -> dict[UUID, User]:
    """
    Charge en UNE requête groupée (pas de N+1) les User créateurs d'un lot
    d'images, indexés par id. Sert à enrichir _image_public_dict avec le nom +
    slug PUBLICS de l'artiste sans requête par image.
    """
    artist_ids = {p.artist_id for p in prompts if p.artist_id is not None}
    if not artist_ids:
        return {}
    users = (await db.execute(
        select(User).where(User.id.in_(list(artist_ids)))
    )).scalars().all()
    return {u.id: u for u in users}


async def _enrich_linked_sounds(
    db: AsyncSession, prompts: list[Prompt], dicts: list[dict]
) -> None:
    """
    Renseigne dicts[i]['linkedSound'] pour chaque image liee a un SON, en UNE
    requete groupee (pas de N+1). N'expose QUE id/titre/cover/prix/productType
    du son partenaire — jamais de recette/lyrics. La cover du son = cover_url
    du Track qui pointe ce prompt (track.prompt_id == son.id).
    """
    from app.models.track import Track

    # Map image_id -> linked_prompt_id (le son partenaire), pour les images liees.
    son_ids = [p.linked_prompt_id for p in prompts if p.linked_prompt_id is not None]
    if not son_ids:
        return
    # Charge les prompts-son lies (non supprimes, nature son), + leur cover Track.
    son_rows = (await db.execute(
        select(Prompt).where(
            Prompt.id.in_(son_ids),
            Prompt.is_deleted.is_(False),
            Prompt.product_type.in_(("recipe", "beat")),
        )
    )).scalars().all()
    son_by_id = {s.id: s for s in son_rows}
    cover_rows = (await db.execute(
        select(Track.prompt_id, Track.cover_url).where(
            Track.prompt_id.in_(list(son_by_id.keys())),
            Track.is_deleted.is_(False),
        )
    )).all() if son_by_id else []
    cover_by_son = {pid: (cu or "") for pid, cu in cover_rows}

    for p, d in zip(prompts, dicts):
        son = son_by_id.get(p.linked_prompt_id) if p.linked_prompt_id else None
        if son is None:
            d["isOeuvreComplete"] = False
            continue
        d["isOeuvreComplete"] = True
        d["linkedSound"] = {
            "id":           str(son.id),
            "title":        son.title,
            "coverUrl":     cover_by_son.get(son.id, ""),
            "priceCredits": son.price_credits,
            "productType":  son.product_type,
        }


async def _owner_read_with_link(db: AsyncSession, image: Prompt) -> ImageOwnerRead:
    """
    ImageOwnerRead enrichi du partenaire son lie (linkedSound + flag). Owner
    voit sa propre recette (heritee de ImageOwnerRead) MAIS le partenaire reste
    limite a l'apercu public (id/titre/cover/prix) — la recette du SON n'est
    JAMAIS exposee via le lien.
    """
    from app.services.links import linked_sound_payload

    model = ImageOwnerRead.model_validate(image)
    model.isOeuvreComplete = image.linked_prompt_id is not None
    model.linkedSound = await linked_sound_payload(db, image)
    # Taxonomie visuelle : la CSV stockée (image_tags) → liste pour le front.
    # model_validate a déjà renseigné `style` via l'alias image_style ; `tags`
    # ne peut pas se déduire automatiquement d'une CSV, on le peuple ici.
    model.tags = _tags_to_list(image.image_tags)
    # C4 galerie avatar — galerie complète pour l'OWNER : apercu public +
    # downloadUrl (route GATÉE de l'original). L'owner passe le gate du download,
    # le front peut télécharger tout le set. galleryCount/galleryPreviews
    # (publics) restent renseignés sur la carte publique via _enrich_galleries.
    gallery_items = (await db.execute(
        select(PromptGalleryImage)
        .where(PromptGalleryImage.prompt_id == image.id)
        .order_by(PromptGalleryImage.position, PromptGalleryImage.created_at)
    )).scalars().all()
    model.gallery = [
        {
            "id":          str(g.id),
            "previewKey":  g.preview_r2_key or "",
            "position":    g.position,
            "downloadUrl": f"/images/{image.id}/gallery/{g.id}/download",
        }
        for g in gallery_items
    ]
    model.galleryCount = len(gallery_items)
    model.galleryPreviews = [g.preview_r2_key for g in gallery_items if g.preview_r2_key]
    return model


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


async def _galleries_for(
    db: AsyncSession, image_ids: list[UUID]
) -> dict[UUID, list[PromptGalleryImage]]:
    """
    Charge en UNE requête groupée (pas de N+1) toutes les images de galerie
    d'un lot d'images-produits, indexées par prompt_id et triées par position.
    Sert à enrichir les payloads publics (apercus) ET owner/biblio (download).
    """
    if not image_ids:
        return {}
    rows = (await db.execute(
        select(PromptGalleryImage)
        .where(PromptGalleryImage.prompt_id.in_(image_ids))
        .order_by(PromptGalleryImage.position, PromptGalleryImage.created_at)
    )).scalars().all()
    out: dict[UUID, list[PromptGalleryImage]] = {}
    for g in rows:
        out.setdefault(g.prompt_id, []).append(g)
    return out


async def _enrich_galleries(
    db: AsyncSession, prompts: list[Prompt], dicts: list[dict]
) -> None:
    """
    Renseigne galleryCount + galleryPreviews (APERÇUS publics SEULEMENT) pour un
    lot de cartes-image, en UNE requête groupée. N'expose JAMAIS d'original
    (image_r2_key de galerie) — uniquement les previewKey publics.
    """
    galleries = await _galleries_for(db, [p.id for p in prompts])
    for p, d in zip(prompts, dicts):
        items = galleries.get(p.id, [])
        d["galleryCount"] = len(items)
        d["galleryPreviews"] = [g.preview_r2_key for g in items if g.preview_r2_key]


def _apply_image_filters(
    stmt,
    *,
    q: str | None,
    platform: str | None,
    rarity: str | None,
    price_min: int | None,
    price_max: int | None,
    ratio: str | None,
    style: str | None = None,
    tag: str | None = None,
):
    """
    Filtres serveur partagés (miroir du style /watt/search/tracks). La facette
    nature ('image') est appliquée par l'appelant ; ici on raffine provenance,
    prix, rareté et texte. Le ratio est filtré en JSONB (image_settings->>ratio).

    Taxonomie visuelle (DNA image) :
      - style : égalité stricte sur image_style (valeur hors STYLES → 0 résultat
                volontairement, on n'invente pas de match).
      - tag   : présence du tag dans la CSV image_tags. On encadre par des
                virgules (",cover," LIKE) pour éviter qu'un tag soit un préfixe
                d'un autre (ex 'paysage' ne doit pas matcher un faux 'paysages').
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
    if style:
        s = style.strip().lower()
        if s in STYLES:
            stmt = stmt.where(Prompt.image_style == s)
        else:
            # Style inconnu demandé : aucun résultat (filtre non satisfiable).
            stmt = stmt.where(sa_false())
    if tag:
        t = tag.strip().lower()
        if t in USAGE_TAGS:
            # Présence dans la CSV, encadrée de virgules pour un match exact de
            # token (couvre tête / milieu / fin via concat ',' + value + ',').
            wrapped = func.concat(",", Prompt.image_tags, ",")
            stmt = stmt.where(wrapped.ilike(f"%,{t},%"))
        else:
            stmt = stmt.where(sa_false())
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
    request: Request,
    q: str = Query(default="", max_length=100),
    platform: Optional[str] = Query(default=None, max_length=50),
    rarity: Optional[str] = Query(default=None, max_length=20),
    price_min: Optional[int] = Query(default=None, ge=0),
    price_max: Optional[int] = Query(default=None, ge=0),
    ratio: Optional[str] = Query(default=None, max_length=20),
    style: Optional[str] = Query(default=None, max_length=40),
    tag: Optional[str] = Query(default=None, max_length=40),
    artist_id: Optional[UUID] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=_MAX_IMAGE_RESULTS, ge=1, le=_MAX_IMAGE_RESULTS),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Catalogue public d'images IA publiées (artistes publiés uniquement).

    `artist_id` (optionnel) : restreint aux images publiques d'un artiste donné.
    Sert notamment au sélecteur d'échange (Part A parité visuel) pour proposer
    les images d'un autre artiste comme produit demandé dans un trade.

    Emplacement choisi : sous le router /images (même router que la création
    et le download) plutôt que dans watt_compat. Raison : cohérence — toute la
    nature 'image' vit dans ce module dédié, on évite d'alourdir le compat
    layer historique destiné à disparaître. Le gate profile_public est appliqué
    en JOIN sur User, comme /watt/search/tracks.

    Renvoie {images:[ImagePublicRead-like], count} — aperçu + provenance +
    rareté + prix. JAMAIS image_r2_key / prompt_text / image_settings (hors
    'ratio' descriptif) / negative_prompt.
    """
    # Le chemin /images est à la fois cette API JSON (sans préfixe → prioritaire
    # sur le mount Flask) ET l'URL de la PAGE vitrine images. Une navigation
    # navigateur (Accept: text/html) doit recevoir la PAGE, pas du JSON brut
    # (sinon un lien direct/partagé/crawler SEO affiche le JSON). Les appels
    # data passent par apiFetch (Accept: application/json) ou fetch (*/*) → JSON.
    if "text/html" in request.headers.get("accept", ""):
        return FileResponse(_INDEX_HTML)

    base = (
        select(Prompt, User)
        .join(User, Prompt.artist_id == User.id)
        .where(
            Prompt.product_type == "image",
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            User.profile_public.is_(True),
            # C4 « Oeuvre complete » — une image « nee ensemble »
            # (bundle_exclusive=True) ne s'affiche PAS en carte individuelle
            # sur le catalogue public ; elle n'apparait que via la carte
            # oeuvre (cote son). L'achat separe reste possible depuis l'oeuvre.
            Prompt.bundle_exclusive.is_(False),
        )
    )
    if artist_id is not None:
        base = base.where(Prompt.artist_id == artist_id)
    base = _apply_image_filters(
        base,
        q=q or None,
        platform=platform,
        rarity=rarity,
        price_min=price_min,
        price_max=price_max,
        ratio=ratio,
        style=style,
        tag=tag,
    )
    base = base.order_by(desc(Prompt.created_at)).offset(offset).limit(limit)

    rows = (await db.execute(base)).all()
    prompts = [p for (p, _u) in rows]
    # Le User créateur est déjà joint dans les rows → map sans requête extra.
    artist_map = {u.id: u for (_p, u) in rows if u is not None}
    sold = await _sold_counts_for(db, [p.id for p in prompts])
    images = [
        _image_public_dict(p, sold.get(p.id), artist_map.get(p.artist_id))
        for p in prompts
    ]
    await _enrich_linked_sounds(db, prompts, images)
    await _enrich_galleries(db, prompts, images)
    return {"query": q, "count": len(images), "images": images}


# ──────────────────────────────────────────────────────────────────────────
# Helpers de score (C4 étape 2 — Mode Image à parité)
#
# Une image n'a pas d'« écoutes » : le classement combine donc VENTES + LIKES,
# départagés par la récence. Formule SCORE = ventes*5 + likes*2 (la vente, acte
# d'engagement le plus fort, pèse plus que le like). Comptage groupé (pas de
# N+1), miroir de _sold_counts_for.
# ──────────────────────────────────────────────────────────────────────────

_SCORE_SOLD_WEIGHT = 5
_SCORE_LIKE_WEIGHT = 2


async def _like_counts_for(db: AsyncSession, image_ids: list[UUID]) -> dict:
    """
    Compte les likes (prompt_likes) pour un lot d'images en UNE requête groupée
    (pas de N+1). Retourne {prompt_id: likes_count}.
    """
    if not image_ids:
        return {}
    rows = (await db.execute(
        select(
            PromptLike.prompt_id,
            func.count(PromptLike.user_id),
        )
        .where(PromptLike.prompt_id.in_(image_ids))
        .group_by(PromptLike.prompt_id)
    )).all()
    return {pid: int(cnt) for pid, cnt in rows}


# ──────────────────────────────────────────────────────────────────────────
# GET /images/top — Top Images (miroir public de « Top Sons »)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/images/top")
async def list_top_images(
    limit: int = Query(default=10, ge=1, le=_MAX_IMAGE_RESULTS),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Classement public des images IA (Mode Image, à parité avec Top Sons).

    SCORE = ventes*5 + likes*2, départagé par created_at DESC (récence). Mêmes
    filtres que /images (image publiée, artiste public, non supprimée,
    bundle_exclusive=False → les images « nées ensemble » ne figurent qu'en
    section Œuvre complète). Comptages groupés (pas de N+1). Réutilise
    _image_public_dict — JAMAIS de champ gaté.
    """
    base = (
        select(Prompt)
        .join(User, Prompt.artist_id == User.id)
        .where(
            Prompt.product_type == "image",
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            User.profile_public.is_(True),
            Prompt.bundle_exclusive.is_(False),
        )
    )
    # On charge un pool large (cap dur) puis on classe par score en Python :
    # le score dépend de deux agrégats (ventes + likes) qu'on compte en deux
    # requêtes groupées — plus simple et lisible qu'un double LEFT JOIN/COALESCE
    # en SQL, et le volume reste borné par _MAX_IMAGE_RESULTS.
    prompts = (await db.execute(
        base.order_by(desc(Prompt.created_at)).limit(_MAX_IMAGE_RESULTS)
    )).scalars().all()

    ids = [p.id for p in prompts]
    sold = await _sold_counts_for(db, ids)
    likes = await _like_counts_for(db, ids)

    def _score(p: Prompt) -> int:
        return (
            sold.get(p.id, 0) * _SCORE_SOLD_WEIGHT
            + likes.get(p.id, 0) * _SCORE_LIKE_WEIGHT
        )

    _EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def _created(p: Prompt) -> datetime:
        # tie-break récence (created_at DESC) ; sentinel si NULL pour ne jamais
        # comparer datetime et int dans le tuple de tri.
        c = p.created_at
        if c is None:
            return _EPOCH
        if c.tzinfo is None:
            return c.replace(tzinfo=timezone.utc)
        return c

    ranked = sorted(
        prompts,
        key=lambda p: (_score(p), _created(p)),
        reverse=True,
    )[:limit]

    artist_map = await _artist_map_for(db, ranked)
    images = [
        _image_public_dict(p, sold.get(p.id), artist_map.get(p.artist_id))
        for p in ranked
    ]
    # Enrichit le badge likeCount sur la carte (utile pour un futur compteur),
    # sans jamais exposer de champ gaté.
    for p, d in zip(ranked, images):
        d["likesCount"] = likes.get(p.id, 0)
        d["score"] = _score(p)
    await _enrich_linked_sounds(db, ranked, images)
    await _enrich_galleries(db, ranked, images)
    return {"count": len(images), "images": images}


# ──────────────────────────────────────────────────────────────────────────
# GET /artists/images-top — Top Artistes Image (miroir de « Top Artistes »)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/artists/images-top")
async def list_top_image_artists(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Classement public des artistes du Monde Image (miroir de /watt/artists pour
    le Mode Image). Un artiste est classé par la somme (ventes + likes) de ses
    images PUBLIQUES (mêmes filtres que /images, bundle_exclusive exclus comme
    pour le catalogue individuel). Seuls les artistes ayant ≥1 image publique
    apparaissent. Renvoie la même forme d'objet artiste que /watt/artists
    (slug, artistName, avatar, stats) enrichie de imagesSold/imagesLikes/
    imageScore. Comptages groupés (pas de N+1).
    """
    from app.routers.watt_compat import _derive_artist_slug

    # Images publiques éligibles (mêmes filtres que /images).
    img_rows = (await db.execute(
        select(Prompt.id, Prompt.artist_id)
        .join(User, Prompt.artist_id == User.id)
        .where(
            Prompt.product_type == "image",
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            User.profile_public.is_(True),
            Prompt.bundle_exclusive.is_(False),
        )
    )).all()
    if not img_rows:
        return {"count": 0, "artists": []}

    image_ids = [iid for (iid, _aid) in img_rows]
    artist_by_image = {iid: aid for (iid, aid) in img_rows}

    sold = await _sold_counts_for(db, image_ids)
    likes = await _like_counts_for(db, image_ids)

    # Agrège ventes + likes par artiste.
    agg: dict[UUID, dict] = {}
    for iid in image_ids:
        aid = artist_by_image[iid]
        slot = agg.setdefault(aid, {"sold": 0, "likes": 0})
        slot["sold"] += sold.get(iid, 0)
        slot["likes"] += likes.get(iid, 0)

    # Charge les profils artistes correspondants (publics, déjà garantis par le
    # JOIN ci-dessus mais on revérifie profile_public par sûreté).
    artist_ids = list(agg.keys())
    users = (await db.execute(
        select(User).where(
            User.id.in_(artist_ids),
            User.profile_public.is_(True),
        )
    )).scalars().all()

    out = []
    for u in users:
        slot = agg.get(u.id, {"sold": 0, "likes": 0})
        score = (
            slot["sold"] * _SCORE_SOLD_WEIGHT
            + slot["likes"] * _SCORE_LIKE_WEIGHT
        )
        out.append({
            "id":            str(u.id),
            "userId":        str(u.id),
            "slug":          _derive_artist_slug(u),
            "artistName":    u.artist_name or "",
            "genre":         u.genre or "",
            "city":          u.city or "",
            "avatarColor":   u.brand_color or "",
            "brandColor":    u.brand_color or "",
            "avatarUrl":     u.avatar_url or "",
            "isOfficial":    bool(u.is_official),
            "profilePublic": True,
            "imagesSold":    slot["sold"],
            "imagesLikes":   slot["likes"],
            "imageScore":    score,
        })

    # Tri : score image décroissant, départage récence de compte.
    out.sort(
        key=lambda a: (a["imageScore"], a["imagesSold"]),
        reverse=True,
    )
    out = out[:limit]
    return {"count": len(out), "artists": out}


# ──────────────────────────────────────────────────────────────────────────
# GET /oeuvres — listing PUBLIC des « Œuvres complètes » (paires son+image)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/oeuvres")
async def list_oeuvres(
    limit: int = Query(default=24, ge=1, le=_MAX_IMAGE_RESULTS),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Listing public des Œuvres complètes (un SON + une IMAGE liés). Affiché dans
    les DEUX modes (Musique et Image). Une paire = UNE entrée (dé-dupliquée :
    on itère côté SON et on résout l'image partenaire, jamais les deux côtés).

    Aperçu PUBLIC strict — réutilise les helpers anti-fuite de services/links.py
    (linked_image_payload). N'expose JAMAIS recette / prompt_text / lyrics /
    image_r2_key / image_settings / negative_prompt. Filtre : produits publics,
    non soft-deleted (les deux côtés). bundle_exclusive autorisé ici (c'est
    précisément la surface où les œuvres « nées ensemble » s'affichent).
    """
    from app.models.track import Track
    from app.services.links import linked_image_payload

    # Côté SON (recipe/beat) lié à un partenaire, publié, public, non supprimé.
    son_rows = (await db.execute(
        select(Prompt)
        .join(User, Prompt.artist_id == User.id)
        .where(
            Prompt.product_type.in_(("recipe", "beat")),
            Prompt.linked_prompt_id.isnot(None),
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            User.profile_public.is_(True),
        )
        .order_by(desc(Prompt.created_at))
        .limit(_MAX_IMAGE_RESULTS)
    )).scalars().all()
    if not son_rows:
        return {"count": 0, "oeuvres": []}

    # Cover du son = cover_url du Track qui pointe ce prompt (requête groupée).
    son_ids = [s.id for s in son_rows]
    cover_rows = (await db.execute(
        select(Track.prompt_id, Track.cover_url).where(
            Track.prompt_id.in_(son_ids),
            Track.is_deleted.is_(False),
        )
    )).all()
    cover_by_son = {pid: (cu or "") for pid, cu in cover_rows}

    oeuvres = []
    for son in son_rows:
        # Image partenaire via le helper anti-fuite (id/previewKey/prix only).
        img_payload = await linked_image_payload(db, son)
        if img_payload is None:
            continue  # partenaire manquant / supprimé / pas une image → on saute
        oeuvres.append({
            "sound": {
                "id":           str(son.id),
                "title":        son.title,
                "coverUrl":     cover_by_son.get(son.id, ""),
                "priceCredits": son.price_credits,
                "productType":  son.product_type,
            },
            "image": img_payload,  # {id, previewKey, priceCredits}
        })
        if len(oeuvres) >= limit:
            break

    return {"count": len(oeuvres), "oeuvres": oeuvres}


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
            # C4 — vitrine PUBLIQUE d'un tiers : pas de carte image
            # individuelle pour une image « nee ensemble » (elle figure cote
            # son via l'oeuvre). La vue OWNER passe par /artist/me/images.
            Prompt.bundle_exclusive.is_(False),
        )
        .order_by(desc(Prompt.created_at))
        .limit(_MAX_IMAGE_RESULTS)
    )).scalars().all()
    sold = await _sold_counts_for(db, [p.id for p in rows])
    # Toutes les images appartiennent à `target` → pas de requête par image.
    images = [_image_public_dict(p, sold.get(p.id), target) for p in rows]
    await _enrich_linked_sounds(db, list(rows), images)
    await _enrich_galleries(db, list(rows), images)
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
    return [await _owner_read_with_link(db, p) for p in rows]


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
# PATCH /artist/me/images/{image_id} — édition métadonnées de vente (owner)
# ──────────────────────────────────────────────────────────────────────────


async def _get_owned_image_or_404(
    db: AsyncSession, *, image_id: UUID, owner_id: UUID
) -> Prompt:
    """
    Charge une image appartenant à l'utilisateur courant, ou lève 404
    (anti-énumération : inexistante / pas une image / soft-deleted / pas owner
    → même 404 indistinct). Source de vérité : Prompt.artist_id == owner_id.
    """
    image = (await db.execute(
        select(Prompt).where(
            Prompt.id == image_id,
            Prompt.product_type == "image",
            Prompt.is_deleted.is_(False),
            Prompt.artist_id == owner_id,
        )
    )).scalar_one_or_none()
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )
    return image


@router.patch("/artist/me/images/{image_id}", response_model=ImageOwnerRead)
async def update_my_image(
    image_id: UUID,
    payload: ImageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Édite les métadonnées de VENTE d'une image possédée (title, description,
    price_credits 3..500, is_published) + taxonomie visuelle (image_style,
    image_tags). Ne touche NI au fichier NI à la recette (re-uploader = créer
    une nouvelle image). PATCH partiel : seuls les champs fournis sont
    appliqués. Les bornes sont validées par ImageUpdate ; style/tags sont
    nettoyés souplement (valeurs hors-liste ignorées, "" efface).
    """
    image = await _get_owned_image_or_404(
        db, image_id=image_id, owner_id=current_user.id
    )
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        image.title = data["title"]
    if "description" in data:
        image.description = data["description"]
    if "price_credits" in data and data["price_credits"] is not None:
        image.price_credits = data["price_credits"]
    if "is_published" in data and data["is_published"] is not None:
        image.is_published = data["is_published"]
    # Taxonomie visuelle : validation souple. Fournir "" (ou que des valeurs
    # hors-liste) efface le champ (→ None). Non fourni = inchangé.
    if "image_style" in data:
        image.image_style = _clean_image_style(data["image_style"])
    if "image_tags" in data:
        image.image_tags = _clean_image_tags(data["image_tags"])
    # Trophées IMAGE_CREATOR — l'axe compte les images publiées ; on hooke dès
    # qu'on touche is_published (passage draft → publié inclus). Le service est
    # idempotent : re-hooker sur une image déjà comptée ne re-grant rien.
    if image.is_published:
        await db.flush()  # le count voit l'état à jour
        from app.models.achievement import AchievementAxis
        from app.services.achievements import check_and_grant_achievements
        await check_and_grant_achievements(
            db, user_id=current_user.id, axis=AchievementAxis.IMAGE_CREATOR
        )
    await db.commit()
    await db.refresh(image)
    return await _owner_read_with_link(db, image)


# ──────────────────────────────────────────────────────────────────────────
# DELETE /artist/me/images/{image_id} — soft-delete (owner)
# ──────────────────────────────────────────────────────────────────────────


@router.delete(
    "/artist/me/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_my_image(
    image_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-delete d'une image possédée (réutilise Prompt.is_deleted, cf migration
    0028 — même mécanique que tracks/beats). L'image disparaît des listings
    publics, du profil et du WattBoard. Les exemplaires DÉJÀ VENDUS
    (UnlockedPrompt) ne sont PAS touchés : l'acheteur garde sa biblio et son
    download (le filtre is_deleted n'est appliqué qu'aux listings, pas au
    download possédé). 404 indistinct si inexistante / pas owner.
    """
    image = await _get_owned_image_or_404(
        db, image_id=image_id, owner_id=current_user.id
    )
    # C4 « Oeuvre complete » — si l'image est moitie d'une oeuvre, on coupe le
    # lien et on remet le SON survivant visible+vendable individuellement
    # (bundle_exclusive=False) : jamais de produit fantome invisible.
    from app.services.links import detach_partner_on_removal
    await detach_partner_on_removal(db, prompt=image)
    image.is_deleted = True
    image.is_published = False
    await db.commit()


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

    NB (C4 ④) : on n'exclut PAS is_deleted ici. Si l'artiste soft-delete une
    image après l'avoir vendue, l'acheteur qui la possède (UnlockedPrompt) doit
    conserver son download. La possession ci-dessous reste le seul gate d'accès.
    """
    product = (await db.execute(
        select(Prompt).where(
            Prompt.id == image_id,
            Prompt.product_type == "image",
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


# ──────────────────────────────────────────────────────────────────────────
# Galerie d'images d'un produit IMAGE (C4 galerie avatar)
#
# Un produit IMAGE (ligne prompts, product_type='image') peut porter une
# GALERIE de plusieurs images (cas d'usage : un avatar = un personnage avec
# 10+ visuels). À l'achat, l'acheteur récupère TOUTES les images originales de
# la galerie + la recette. Schéma générique sur les images ; la restriction
# « avatars » est une convention UX côté front (PAS de règle « min 10 » ici).
#
# Gating (IDENTIQUE au download principal) :
#   - preview_r2_key de galerie → APERÇU public (proxy /watt/images/).
#   - image_r2_key de galerie  → ORIGINAL gaté, sert UNIQUEMENT via
#     /images/{id}/gallery/{gid}/download (acheteur possédant l'image OU owner).
# ──────────────────────────────────────────────────────────────────────────


def _gallery_item_dict(g: PromptGalleryImage) -> dict:
    """Item de galerie pour la vue OWNER (apercu + position, JAMAIS l'original)."""
    return {
        "id":         str(g.id),
        "previewKey": g.preview_r2_key or "",
        "position":   g.position,
    }


@router.get("/artist/me/images/{image_id}/gallery")
async def list_my_image_gallery(
    image_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Liste la galerie d'une image possédée (owner). 404 si pas la sienne.
    Renvoie les APERÇUS (previewKey) + position ; jamais l'original.
    """
    await _get_owned_image_or_404(db, image_id=image_id, owner_id=current_user.id)
    items = (await db.execute(
        select(PromptGalleryImage)
        .where(PromptGalleryImage.prompt_id == image_id)
        .order_by(PromptGalleryImage.position, PromptGalleryImage.created_at)
    )).scalars().all()
    return {"count": len(items), "gallery": [_gallery_item_dict(g) for g in items]}


@router.post(
    "/artist/me/images/{image_id}/gallery",
    status_code=status.HTTP_201_CREATED,
)
async def add_my_image_gallery(
    image_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ajoute PLUSIEURS images à la galerie d'une image possédée (owner only).
    Multipart `files` (List[UploadFile]). Pour chaque fichier : même validation
    type/taille que la création d'image, upload_image_assets (original + apercu)
    puis INSERT d'une ligne PromptGalleryImage (position = max+1, croissante).

    Renvoie la galerie à jour ({id, previewKey, position}). 404 si l'image n'est
    pas celle de l'utilisateur. Aucune règle « min 10 » (reco front seulement).
    """
    await _get_owned_image_or_404(db, image_id=image_id, owner_id=current_user.id)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun fichier fourni.",
        )

    # Position de départ = max(position) + 1 (ordre stable, croissant).
    current_max = (await db.execute(
        select(func.max(PromptGalleryImage.position)).where(
            PromptGalleryImage.prompt_id == image_id
        )
    )).scalar()
    next_position = (current_max + 1) if current_max is not None else 0

    for f in files:
        ct = (f.content_type or "").lower()
        filename = f.filename or ""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ct not in ALLOWED_CONTENT_TYPES and ext not in IMAGE_MIME_BY_EXT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Format non supporté. Utilise PNG, JPG ou WebP.",
            )
        data = await f.read()
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
        try:
            g_image_key, g_preview_key = await upload_image_assets(
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
        db.add(PromptGalleryImage(
            prompt_id=image_id,
            image_r2_key=g_image_key,
            preview_r2_key=g_preview_key,
            position=next_position,
        ))
        next_position += 1

    await db.commit()

    items = (await db.execute(
        select(PromptGalleryImage)
        .where(PromptGalleryImage.prompt_id == image_id)
        .order_by(PromptGalleryImage.position, PromptGalleryImage.created_at)
    )).scalars().all()
    return {"count": len(items), "gallery": [_gallery_item_dict(g) for g in items]}


@router.delete(
    "/artist/me/images/{image_id}/gallery/{gallery_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_my_image_gallery_item(
    image_id: UUID,
    gallery_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retire une image de galerie (owner only). 404 si l'image-produit n'est pas
    celle de l'utilisateur, ou si l'item de galerie n'existe pas / n'appartient
    pas à cette image. Supprime aussi les fichiers R2 (original + apercu) en
    best-effort (idempotent, ne bloque pas la suppression de la ligne).
    """
    await _get_owned_image_or_404(db, image_id=image_id, owner_id=current_user.id)
    item = (await db.execute(
        select(PromptGalleryImage).where(
            PromptGalleryImage.id == gallery_id,
            PromptGalleryImage.prompt_id == image_id,
        )
    )).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Gallery image not found"
        )

    # Best-effort R2 cleanup (delete_r2_object est idempotent + log-only).
    from app.services.r2 import delete_r2_object
    for k in (item.image_r2_key, item.preview_r2_key):
        if k:
            try:
                await delete_r2_object(k)
            except Exception:  # noqa: BLE001
                pass

    await db.delete(item)
    await db.commit()


@router.get("/images/{image_id}/gallery/{gallery_id}/download")
async def download_image_gallery_item(
    image_id: UUID,
    gallery_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Télécharge l'ORIGINAL d'une image de galerie — MÊME gate que
    /images/{id}/download : acheteur possédant l'image-produit (UnlockedPrompt
    current_owner_id) OU artiste propriétaire. À l'achat, le front itère sur la
    galerie et appelle cette route pour chaque item afin de récupérer tout le set.

    404 indistinct si l'image ou l'item n'existe pas (anti-énumération). 403 si
    l'user ne possède pas l'image. La possession précède tout accès R2.
    NB : on n'exclut PAS is_deleted (l'acheteur garde son download après un
    soft-delete de l'image-produit), comme pour le download principal.
    """
    product = (await db.execute(
        select(Prompt).where(
            Prompt.id == image_id,
            Prompt.product_type == "image",
        )
    )).scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found"
        )

    # Possession : MÊME gate que /images/{id}/download.
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

    item = (await db.execute(
        select(PromptGalleryImage).where(
            PromptGalleryImage.id == gallery_id,
            PromptGalleryImage.prompt_id == image_id,
        )
    )).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Gallery image not found"
        )

    key = item.image_r2_key
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
    base = (product.title or "image").replace('"', "").strip() or "image"
    safe_name = f"{base}-{item.position + 1}"
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


# ──────────────────────────────────────────────────────────────────────────
# Likes durables de prompts (C4 livraison 5)
#
# Store dédié `prompt_likes` (PK composite user_id+prompt_id) — remplace le hack
# localStorage `sp_img_likes_v1`. Générique (clé prompt) mais utilisé pour les
# IMAGES en V1. Séparation son/image respectée : le ❤️ audio reste sur la
# wishlist (playlist privée → track), les likes image ont leur propre store.
#
# Emplacement : ici, dans images.py, plutôt qu'un router likes.py dédié, parce
# que l'usage V1 est 100 % image et que toute la sérialisation publique d'image
# (_image_public_dict, _sold_counts_for) vit déjà dans ce module — un router
# séparé devrait réimporter ces helpers. Les routes restent génériques
# (/me/likes/prompts/...) donc réutilisables si un autre type devient likable.
#
# IMPORTANT : un like ne débloque RIEN. Le payload renvoyé pour "mes images
# likées" est l'aperçu public (_image_public_dict) — JAMAIS image_r2_key /
# prompt_text / image_settings / negative_prompt.
# ──────────────────────────────────────────────────────────────────────────


@router.post("/me/likes/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def like_prompt(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Like un prompt (idempotent). 404 si le prompt n'existe pas ou est
    soft-deleted. Un re-like ne crée pas de doublon (PK composite +
    vérification d'existence). Ne débloque aucun contenu gaté.
    """
    prompt = (await db.execute(
        select(Prompt.id).where(
            Prompt.id == prompt_id,
            Prompt.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )

    existing = (await db.execute(
        select(PromptLike.user_id).where(
            PromptLike.user_id == current_user.id,
            PromptLike.prompt_id == prompt_id,
        )
    )).scalar_one_or_none()
    if existing is None:
        db.add(PromptLike(user_id=current_user.id, prompt_id=prompt_id))
        await db.commit()


@router.delete("/me/likes/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_prompt(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retire le like d'un prompt (idempotent : 204 même si pas liké).
    On ne 404 pas sur un prompt soft-deleted ici : l'utilisateur doit
    pouvoir nettoyer un like résiduel.
    """
    like = (await db.execute(
        select(PromptLike).where(
            PromptLike.user_id == current_user.id,
            PromptLike.prompt_id == prompt_id,
        )
    )).scalar_one_or_none()
    if like is not None:
        await db.delete(like)
        await db.commit()


@router.get("/me/likes/prompts")
async def list_my_liked_prompts(
    product_type: Optional[str] = Query(default=None, max_length=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Liste mes prompts likés, filtrable par product_type.

    - Avec product_type='image' (cas V1) : renvoie {ids, images} où `images`
      sont les aperçus publics (_image_public_dict) — sert à la fois à hydrater
      l'état des ❤️ (set d'ids) ET à afficher « mes images likées ».
    - Sans filtre : renvoie {ids} (les UUID likés, tous types), suffisant pour
      hydrater l'état des boutons.

    Les prompts soft-deleted sont exclus (un like résiduel n'apparaît plus).
    Ne renvoie AUCUN champ gaté.
    """
    base = (
        select(Prompt)
        .join(PromptLike, PromptLike.prompt_id == Prompt.id)
        .where(
            PromptLike.user_id == current_user.id,
            Prompt.is_deleted.is_(False),
        )
    )
    if product_type:
        base = base.where(Prompt.product_type == product_type)
    base = base.order_by(desc(PromptLike.created_at))

    prompts = (await db.execute(base)).scalars().all()
    ids = [str(p.id) for p in prompts]

    if product_type == "image":
        images_only = [p for p in prompts if p.product_type == "image"]
        sold = await _sold_counts_for(db, [p.id for p in images_only])
        artist_map = await _artist_map_for(db, images_only)
        images = [
            _image_public_dict(p, sold.get(p.id), artist_map.get(p.artist_id))
            for p in images_only
        ]
        await _enrich_linked_sounds(db, images_only, images)
        await _enrich_galleries(db, images_only, images)
        return {"ids": ids, "count": len(images), "images": images}

    return {"ids": ids, "count": len(ids)}
