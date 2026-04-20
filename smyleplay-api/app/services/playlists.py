"""
Service Playlist — couche métier entre les routeurs et SQLAlchemy.

Règles métier centralisées ici (pas dans les routeurs) :

  - Une playlist `visibility="public"` ne peut contenir QUE des tracks
    appartenant à son owner. Cette règle est appliquée à l'ajout (`add_track`)
    ET à la bascule de visibilité (`update_playlist` → si on passe de
    private à public, on vérifie que toutes les tracks déjà ajoutées sont
    bien de l'owner, sinon on refuse).

  - La wishlist est la playlist privée par défaut de chaque user. Créée
    paresseusement par `ensure_default_wishlist(user)` — idempotent, hook
    au register + fallback à la première utilisation d'une route qui en
    aurait besoin. Identifiée par son `title` fixe "Ma Wishlist" côté
    service (pas de flag dédié en base pour ne pas introduire de colonne
    qui servirait uniquement à ça).

  - `position` : l'ajout sans position précisée insère en fin de liste
    (MAX(position) + 1 sur la playlist donnée).
"""
from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playlist import Playlist, PlaylistTrack
from app.models.track import Track
from app.models.user import User
from app.schemas.playlist import PlaylistCreate, PlaylistUpdate


WISHLIST_TITLE = "Ma Wishlist"


# ─── Erreurs métier remontées au routeur ─────────────────────────────────
class PlaylistNotFound(Exception):
    pass


class PlaylistForbidden(Exception):
    """L'utilisateur courant n'est pas l'owner de la playlist."""


class PlaylistPublicOwnerMismatch(Exception):
    """Tentative d'ajouter/garder dans une playlist publique une track
    qui n'appartient pas à l'owner de la playlist."""


class TrackNotFound(Exception):
    pass


# ─── CRUD playlists ──────────────────────────────────────────────────────
async def create_playlist(
    db: AsyncSession,
    owner: User,
    data: PlaylistCreate,
) -> Playlist:
    playlist = Playlist(
        owner_id=owner.id,
        title=data.title,
        visibility=data.visibility,
        color=data.color,
        cover_video_url=data.cover_video_url,
        seed_prompt=data.seed_prompt,
    )
    db.add(playlist)
    await db.commit()
    await db.refresh(playlist)
    return playlist


async def get_playlist(
    db: AsyncSession,
    playlist_id: uuid.UUID,
) -> Playlist:
    res = await db.execute(select(Playlist).where(Playlist.id == playlist_id))
    playlist = res.scalar_one_or_none()
    if playlist is None:
        raise PlaylistNotFound()
    return playlist


async def list_user_playlists(
    db: AsyncSession,
    owner_id: uuid.UUID,
    visibility: str | None = None,
) -> list[Playlist]:
    """Liste toutes les playlists d'un user, éventuellement filtrées par
    visibilité. Index (owner_id, visibility) conçu pour cette requête."""
    stmt = select(Playlist).where(Playlist.owner_id == owner_id)
    if visibility is not None:
        stmt = stmt.where(Playlist.visibility == visibility)
    stmt = stmt.order_by(Playlist.created_at.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def update_playlist(
    db: AsyncSession,
    owner: User,
    playlist_id: uuid.UUID,
    patch: PlaylistUpdate,
) -> Playlist:
    playlist = await get_playlist(db, playlist_id)
    if playlist.owner_id != owner.id:
        raise PlaylistForbidden()

    updates = patch.model_dump(exclude_unset=True)

    # Si on bascule vers public, vérifier que toutes les tracks déjà
    # attachées sont de l'owner.
    new_visibility = updates.get("visibility", playlist.visibility)
    if new_visibility == "public" and playlist.visibility != "public":
        await _assert_all_tracks_owned_by(db, playlist.id, owner.id)

    for key, value in updates.items():
        setattr(playlist, key, value)

    await db.commit()
    await db.refresh(playlist)
    return playlist


async def delete_playlist(
    db: AsyncSession,
    owner: User,
    playlist_id: uuid.UUID,
) -> None:
    playlist = await get_playlist(db, playlist_id)
    if playlist.owner_id != owner.id:
        raise PlaylistForbidden()
    await db.delete(playlist)
    await db.commit()


# ─── Gestion des tracks dans une playlist ────────────────────────────────
async def add_track(
    db: AsyncSession,
    owner: User,
    playlist_id: uuid.UUID,
    track_id: uuid.UUID,
    position: int | None = None,
) -> PlaylistTrack:
    playlist = await get_playlist(db, playlist_id)
    if playlist.owner_id != owner.id:
        raise PlaylistForbidden()

    track_res = await db.execute(select(Track).where(Track.id == track_id))
    track = track_res.scalar_one_or_none()
    if track is None:
        raise TrackNotFound()

    # Règle : une playlist publique ne peut contenir que des tracks de
    # l'owner. Les privées (wishlist) peuvent contenir n'importe quoi.
    if playlist.visibility == "public" and track.artist_id != owner.id:
        raise PlaylistPublicOwnerMismatch()

    # Position : si absente, placer en queue.
    if position is None:
        max_pos_res = await db.execute(
            select(func.coalesce(func.max(PlaylistTrack.position), -1)).where(
                PlaylistTrack.playlist_id == playlist_id
            )
        )
        position = int(max_pos_res.scalar_one()) + 1

    # Si la ligne existe déjà (PK composite), on met juste à jour la
    # position — évite un IntegrityError pour l'appelant.
    existing_res = await db.execute(
        select(PlaylistTrack).where(
            PlaylistTrack.playlist_id == playlist_id,
            PlaylistTrack.track_id == track_id,
        )
    )
    link = existing_res.scalar_one_or_none()
    if link is None:
        link = PlaylistTrack(
            playlist_id=playlist_id,
            track_id=track_id,
            position=position,
        )
        db.add(link)
    else:
        link.position = position

    await db.commit()
    await db.refresh(link)
    return link


async def remove_track(
    db: AsyncSession,
    owner: User,
    playlist_id: uuid.UUID,
    track_id: uuid.UUID,
) -> None:
    playlist = await get_playlist(db, playlist_id)
    if playlist.owner_id != owner.id:
        raise PlaylistForbidden()
    await db.execute(
        delete(PlaylistTrack).where(
            PlaylistTrack.playlist_id == playlist_id,
            PlaylistTrack.track_id == track_id,
        )
    )
    await db.commit()


async def list_playlist_tracks(
    db: AsyncSession,
    playlist_id: uuid.UUID,
) -> list[Track]:
    """Retourne les tracks ordonnés par `position` croissant puis par
    `added_at` pour départager en cas d'égalité."""
    stmt = (
        select(Track)
        .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
        .where(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position.asc(), PlaylistTrack.added_at.asc())
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


# ─── Seed wishlist par user ──────────────────────────────────────────────
async def ensure_default_wishlist(
    db: AsyncSession,
    owner: User,
) -> Playlist:
    """Idempotent : retourne la wishlist de l'user, la crée si elle n'existe
    pas. Identifiée par (owner_id, title="Ma Wishlist", visibility="private")."""
    res = await db.execute(
        select(Playlist).where(
            Playlist.owner_id == owner.id,
            Playlist.title == WISHLIST_TITLE,
            Playlist.visibility == "private",
        )
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        return existing

    wishlist = Playlist(
        owner_id=owner.id,
        title=WISHLIST_TITLE,
        visibility="private",
    )
    db.add(wishlist)
    await db.commit()
    await db.refresh(wishlist)
    return wishlist


# ─── Helpers internes ────────────────────────────────────────────────────
async def _assert_all_tracks_owned_by(
    db: AsyncSession,
    playlist_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> None:
    """Lève PlaylistPublicOwnerMismatch s'il existe au moins une track liée
    à la playlist qui n'appartient pas à l'owner. Utilisé quand on bascule
    une playlist vers la visibilité publique."""
    res = await db.execute(
        select(func.count())
        .select_from(PlaylistTrack)
        .join(Track, Track.id == PlaylistTrack.track_id)
        .where(
            PlaylistTrack.playlist_id == playlist_id,
            Track.artist_id != owner_id,
        )
    )
    foreign_count = int(res.scalar_one())
    if foreign_count > 0:
        raise PlaylistPublicOwnerMismatch()


def serialize_tracks(tracks: Iterable[Track]) -> list[dict]:
    """Utilitaire : convertit une liste SQLAlchemy en dicts pour
    PlaylistWithTracks. Laissé simple — Pydantic fait le reste via
    from_attributes côté schéma."""
    return [
        {
            "id": t.id,
            "title": t.title,
            "audio_url": t.audio_url,
            "color": t.color,
            "created_at": t.created_at,
        }
        for t in tracks
    ]
