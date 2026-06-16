"""
Router albums d'images — équivalent VISUEL des playlists (chantier C4 My Mix).

Calque STRICTEMENT le router playlists (app/routers/playlists.py), adapté aux
images. Un album est une curation PERSO d'images NON vendable (pure collection
type Pinterest). Aucune logique de prix / achat / rareté.

Convention d'URL (miroir playlists) :
  - `/albums/...`                  → actions sur mes albums (auth JWT)
  - `/watt/users/{slug}/albums`    → listing public des albums publics d'un
                                     artiste, par slug (non authentifié,
                                     consommé côté /u/<slug>).

Gestion d'erreurs (miroir playlists) :
  - 404 album introuvable → aucune distinction avec "je ne suis pas owner"
    pour ne pas leak d'info de présence.
  - Album privé → 404 pour les tiers (pas 403).

Anti-fuite : les images d'un album ne sont exposées qu'en APERÇU PUBLIC
(_image_public_dict de images.py) — JAMAIS prompt_text / image_r2_key /
image_settings / negative_prompt.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.album import (
    AddImageRequest,
    AlbumCreate,
    AlbumRead,
    AlbumUpdate,
    AlbumWithImages,
)
from app.services import albums as svc


router = APIRouter(prefix="/albums", tags=["albums"])
public_router = APIRouter(prefix="/watt", tags=["watt-albums"])


# ─── Helpers ──────────────────────────────────────────────────────────────
async def _album_reads_with_meta(
    db: AsyncSession, items: list
) -> list[AlbumRead]:
    """Remplit imageCount + coverPreviewKey via DEUX requêtes groupées (pas de
    N+1) sans charger les images. Projection compacte pour le dashboard."""
    counts = await svc.count_images_by_albums(db, [a.id for a in items])
    covers = await svc.cover_preview_keys_by_albums(db, items)
    out = []
    for a in items:
        ar = AlbumRead.model_validate(a)
        ar.image_count = counts.get(a.id, 0)
        ar.cover_preview_key = covers.get(a.id)
        out.append(ar)
    return out


def _image_preview(p: Prompt) -> dict:
    """Aperçu PUBLIC d'une image d'album. Réutilise _image_public_dict de
    images.py (single source of truth anti-fuite) puis projette le sous-ensemble
    demandé par la fiche album (id / previewKey / title / priceCredits /
    productType). N'expose AUCUN champ gaté."""
    from app.routers.images import _image_public_dict

    full = _image_public_dict(p, sold_count=None)
    return {
        "id":           full["id"],
        "previewKey":   full["previewKey"],
        "title":        full["title"],
        "priceCredits": full["priceCredits"],
        "productType":  full["productType"],
    }


async def _album_with_images(db: AsyncSession, album) -> AlbumWithImages:
    """Construit AlbumWithImages : métadonnées + aperçus PUBLICS des images."""
    images = await svc.list_album_images(db, album.id)
    counts = await svc.count_images_by_albums(db, [album.id])
    covers = await svc.cover_preview_keys_by_albums(db, [album])
    return AlbumWithImages(
        id=album.id,
        owner_id=album.owner_id,
        title=album.title,
        visibility=album.visibility,  # type: ignore[arg-type]
        cover_preview_key=covers.get(album.id),
        image_count=counts.get(album.id, 0),
        created_at=album.created_at,
        images=[_image_preview(p) for p in images],
    )


# ─── Owner-facing : /albums/... ───────────────────────────────────────────
@router.post(
    "",
    response_model=AlbumRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_album_endpoint(
    data: AlbumCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlbumRead:
    album = await svc.create_album(db, current_user, data)
    return AlbumRead.model_validate(album)


@router.get("/me", response_model=list[AlbumRead])
async def list_my_albums(
    visibility: Optional[str] = Query(
        default=None,
        pattern=r"^(public|private)$",
        description="Filtre optionnel — sinon renvoie tous mes albums.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AlbumRead]:
    items = await svc.list_user_albums(
        db, current_user.id, visibility=visibility
    )
    return await _album_reads_with_meta(db, items)


@router.get("/{album_id}", response_model=AlbumWithImages)
async def get_album_endpoint(
    album_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlbumWithImages:
    """
    Lecture détaillée d'un album (avec aperçus publics des images).

    Règle de visibilité (miroir playlists) :
      - Owner : peut lire n'importe lequel de ses albums.
      - Non-owner : peut lire uniquement si visibility=public. Sinon 404
        (pas 403, pour ne pas leak l'existence d'un album privé).
    """
    try:
        album = await svc.get_album(db, album_id)
    except svc.AlbumNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable")

    if album.owner_id != current_user.id and album.visibility != "public":
        raise HTTPException(status_code=404, detail="Album introuvable")

    return await _album_with_images(db, album)


@router.patch("/{album_id}", response_model=AlbumRead)
async def update_album_endpoint(
    album_id: uuid.UUID,
    patch: AlbumUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlbumRead:
    try:
        album = await svc.update_album(db, current_user, album_id, patch)
    except svc.AlbumNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable")
    except svc.AlbumForbidden:
        # 404 volontaire : pas de distinction "pas owner" vs "n'existe pas".
        raise HTTPException(status_code=404, detail="Album introuvable")
    return AlbumRead.model_validate(album)


@router.delete("/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_album_endpoint(
    album_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await svc.delete_album(db, current_user, album_id)
    except svc.AlbumNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable")
    except svc.AlbumForbidden:
        raise HTTPException(status_code=404, detail="Album introuvable")


@router.post("/{album_id}/images", status_code=status.HTTP_201_CREATED)
async def add_image_endpoint(
    album_id: uuid.UUID,
    body: AddImageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        link = await svc.add_image(
            db,
            current_user,
            album_id,
            body.prompt_id,
            position=body.position,
        )
    except svc.AlbumNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable")
    except svc.AlbumForbidden:
        raise HTTPException(status_code=404, detail="Album introuvable")
    except svc.ImageNotFound:
        raise HTTPException(status_code=404, detail="Image introuvable")
    except svc.AlbumImageExists:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cette image est déjà dans l'album.",
                "code": "album_image_exists",
            },
        )
    return {
        "ok": True,
        "albumId": str(link.album_id),
        "promptId": str(link.prompt_id),
        "position": link.position,
    }


@router.delete(
    "/{album_id}/images/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_image_endpoint(
    album_id: uuid.UUID,
    prompt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await svc.remove_image(db, current_user, album_id, prompt_id)
    except svc.AlbumNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable")
    except svc.AlbumForbidden:
        raise HTTPException(status_code=404, detail="Album introuvable")


# ─── Public-facing : /watt/users/{slug}/albums ─────────────────────────────
@public_router.get("/users/{slug}/albums", response_model=list[AlbumRead])
async def list_public_albums_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> list[AlbumRead]:
    """
    Albums publics d'un artiste exposés sur /u/<slug> (miroir de
    /watt/users/{slug}/playlists). Réutilise _find_artist_by_slug (gate
    profile_public).
    """
    from app.routers.follows import _find_artist_by_slug

    target = await _find_artist_by_slug(db, slug)
    items = await svc.list_user_albums(db, target.id, visibility="public")
    return await _album_reads_with_meta(db, items)


# ─── Public-facing : /watt/albums/{id} — quick-view ─────────────────────────
@public_router.get("/albums/{album_id}", response_model=AlbumWithImages)
async def get_public_album_with_images(
    album_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AlbumWithImages:
    """
    Détail d'un album public avec ses aperçus d'images — sans authentification.
    Retourne 404 si l'album est privé ou inexistant (miroir playlists).
    """
    try:
        album = await svc.get_album(db, album_id)
    except svc.AlbumNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable")

    if album.visibility != "public":
        raise HTTPException(status_code=404, detail="Album introuvable")

    return await _album_with_images(db, album)
