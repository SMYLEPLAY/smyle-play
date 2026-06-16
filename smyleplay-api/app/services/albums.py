"""
Service Album d'images — couche métier entre le routeur et SQLAlchemy.

Calque STRICTEMENT le service Playlist (app/services/playlists.py), adapté aux
images (lignes `prompts` product_type='image') au lieu des tracks.

Règles métier centralisées ici :

  - Un album est une curation PERSO NON vendable. Aucune logique de prix /
    achat / rareté. On peut ajouter N'IMPORTE QUELLE image (de n'importe quel
    artiste, type Pinterest) — il suffit d'être owner de l'ALBUM, pas de
    l'image. Contrairement aux playlists publiques (qui imposent que les tracks
    soient de l'owner), un album public peut donc agréger les images des
    autres : c'est une collection, pas une vitrine de production.

  - L'image ajoutée doit être product_type='image' et non soft-deleted
    (sinon ImageNotFound / ImageNotAddable).

  - `position` : l'ajout sans position précisée insère en fin de liste
    (MAX(position) + 1 sur l'album donné). PK composite (album_id, prompt_id)
    empêche les doublons (re-ajout = 409 côté router via AlbumImageExists).
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.album import Album, AlbumImage
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.album import AlbumCreate, AlbumUpdate


# ─── Erreurs métier remontées au routeur ─────────────────────────────────
class AlbumNotFound(Exception):
    pass


class AlbumForbidden(Exception):
    """L'utilisateur courant n'est pas l'owner de l'album."""


class ImageNotFound(Exception):
    """L'image ciblée n'existe pas / n'est pas product_type='image' / est
    soft-deleted."""


class AlbumImageExists(Exception):
    """L'image est déjà présente dans l'album (PK composite)."""


# ─── CRUD albums ──────────────────────────────────────────────────────────
async def create_album(
    db: AsyncSession,
    owner: User,
    data: AlbumCreate,
) -> Album:
    album = Album(
        owner_id=owner.id,
        title=data.title,
        visibility=data.visibility,
    )
    db.add(album)
    await db.commit()
    await db.refresh(album)
    return album


async def get_album(
    db: AsyncSession,
    album_id: uuid.UUID,
) -> Album:
    res = await db.execute(select(Album).where(Album.id == album_id))
    album = res.scalar_one_or_none()
    if album is None:
        raise AlbumNotFound()
    return album


async def list_user_albums(
    db: AsyncSession,
    owner_id: uuid.UUID,
    visibility: str | None = None,
) -> list[Album]:
    """Liste tous les albums d'un user, éventuellement filtrés par visibilité.
    Index (owner_id, visibility) conçu pour cette requête."""
    stmt = select(Album).where(Album.owner_id == owner_id)
    if visibility is not None:
        stmt = stmt.where(Album.visibility == visibility)
    stmt = stmt.order_by(Album.created_at.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def count_images_by_albums(
    db: AsyncSession,
    album_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Nb d'images par album en UNE requête GROUP BY (pas de N+1, pas de
    chargement des images). Utilisé par les routeurs liste pour remplir
    AlbumRead.image_count."""
    if not album_ids:
        return {}
    stmt = (
        select(AlbumImage.album_id, func.count())
        .where(AlbumImage.album_id.in_(album_ids))
        .group_by(AlbumImage.album_id)
    )
    res = await db.execute(stmt)
    return {aid: n for aid, n in res.all()}


async def cover_preview_keys_by_albums(
    db: AsyncSession,
    albums: list[Album],
) -> dict[uuid.UUID, str | None]:
    """Résout la clé d'aperçu PUBLIC (preview_r2_key) de l'image de couverture
    de chaque album en UNE requête groupée (pas de N+1). Retourne
    {album_id: preview_key | None}. JAMAIS l'original image_r2_key."""
    cover_ids = {a.cover_prompt_id for a in albums if a.cover_prompt_id is not None}
    if not cover_ids:
        return {a.id: None for a in albums}
    rows = (await db.execute(
        select(Prompt.id, Prompt.preview_r2_key).where(
            Prompt.id.in_(list(cover_ids)),
            Prompt.is_deleted.is_(False),
        )
    )).all()
    preview_by_prompt = {pid: (pk or None) for pid, pk in rows}
    return {
        a.id: preview_by_prompt.get(a.cover_prompt_id)
        for a in albums
    }


async def update_album(
    db: AsyncSession,
    owner: User,
    album_id: uuid.UUID,
    patch: AlbumUpdate,
) -> Album:
    album = await get_album(db, album_id)
    if album.owner_id != owner.id:
        raise AlbumForbidden()

    updates = patch.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(album, key, value)

    await db.commit()
    await db.refresh(album)
    return album


async def delete_album(
    db: AsyncSession,
    owner: User,
    album_id: uuid.UUID,
) -> None:
    album = await get_album(db, album_id)
    if album.owner_id != owner.id:
        raise AlbumForbidden()
    await db.delete(album)
    await db.commit()


# ─── Gestion des images dans un album ─────────────────────────────────────
async def add_image(
    db: AsyncSession,
    owner: User,
    album_id: uuid.UUID,
    prompt_id: uuid.UUID,
    position: int | None = None,
) -> AlbumImage:
    album = await get_album(db, album_id)
    if album.owner_id != owner.id:
        raise AlbumForbidden()

    # L'image peut appartenir à N'IMPORTE QUI (curation type Pinterest) : on
    # vérifie seulement qu'elle existe, est bien une image et non supprimée.
    image = (await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.product_type == "image",
            Prompt.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    if image is None:
        raise ImageNotFound()

    # Doublon → 409 (PK composite). On lève AVANT d'insérer pour donner un
    # message clair au front plutôt qu'un IntegrityError.
    existing = (await db.execute(
        select(AlbumImage).where(
            AlbumImage.album_id == album_id,
            AlbumImage.prompt_id == prompt_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise AlbumImageExists()

    # Position : si absente, placer en queue.
    if position is None:
        max_pos = (await db.execute(
            select(func.coalesce(func.max(AlbumImage.position), -1)).where(
                AlbumImage.album_id == album_id
            )
        )).scalar_one()
        position = int(max_pos) + 1

    link = AlbumImage(
        album_id=album_id,
        prompt_id=prompt_id,
        position=position,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


async def remove_image(
    db: AsyncSession,
    owner: User,
    album_id: uuid.UUID,
    prompt_id: uuid.UUID,
) -> None:
    album = await get_album(db, album_id)
    if album.owner_id != owner.id:
        raise AlbumForbidden()
    await db.execute(
        delete(AlbumImage).where(
            AlbumImage.album_id == album_id,
            AlbumImage.prompt_id == prompt_id,
        )
    )
    await db.commit()


async def list_album_images(
    db: AsyncSession,
    album_id: uuid.UUID,
) -> list[Prompt]:
    """Retourne les images (lignes prompts) ordonnées par `position` croissant
    puis par `added_at`. Exclut les images soft-deleted (une image retirée de
    la vente ne doit plus apparaître dans l'album public). Les lignes de
    jonction résiduelles sont simplement ignorées au rendu."""
    stmt = (
        select(Prompt)
        .join(AlbumImage, AlbumImage.prompt_id == Prompt.id)
        .where(
            AlbumImage.album_id == album_id,
            Prompt.product_type == "image",
            Prompt.is_deleted.is_(False),
        )
        .order_by(AlbumImage.position.asc(), AlbumImage.added_at.asc())
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())
