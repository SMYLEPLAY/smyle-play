"""
Router playlists — étape 3 du chantier profil public.

Convention d'URL :
  - `/playlists/...`                  → actions sur mes playlists (auth JWT)
  - `/watt/users/{slug}/playlists`    → listing public des playlists
                                         publiques d'un artiste, par slug
                                         (non authentifié, consommé côté
                                         /u/<slug> à l'étape 5).

Le router /playlists est monté séparément du /watt pour garder la séparation
"API moderne" vs "compat layer historique" ; le listing slug-par-slug vit
sous /watt puisqu'il est consommé par les mêmes couches front que le reste
du profil public (/watt/artists/{slug}, /watt/users/{slug}/dna-catalog).

Gestion d'erreurs :
  - 404 playlist introuvable → aucune distinction avec "je ne suis pas owner"
    pour ne pas leak d'info de présence (équivalent d'un GET d'un UUID random).
  - 403 owner mismatch → réservé aux tracks (règle métier plus parlante côté
    client, qui veut afficher un message explicite).
  - 422 visibility public + track étrangère → même traitement : on veut que
    le front puisse afficher "cette track n'est pas à toi, tu ne peux pas
    l'ajouter dans une playlist publique".
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.playlist import (
    AddTrackRequest,
    PlaylistCreate,
    PlaylistRead,
    PlaylistUpdate,
    PlaylistWithTracks,
)
from app.schemas.track import TrackRead
from app.services import playlists as svc


router = APIRouter(prefix="/playlists", tags=["playlists"])
public_router = APIRouter(prefix="/watt", tags=["watt-playlists"])


# ─── Owner-facing : /playlists/... ───────────────────────────────────────
@router.post(
    "",
    response_model=PlaylistRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_playlist_endpoint(
    data: PlaylistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlaylistRead:
    playlist = await svc.create_playlist(db, current_user, data)
    return PlaylistRead.model_validate(playlist)


@router.get("/me", response_model=list[PlaylistRead])
async def list_my_playlists(
    visibility: Optional[str] = Query(
        default=None,
        pattern=r"^(public|private)$",
        description="Filtre optionnel — sinon renvoie toutes mes playlists.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PlaylistRead]:
    items = await svc.list_user_playlists(
        db, current_user.id, visibility=visibility
    )
    return [PlaylistRead.model_validate(p) for p in items]


@router.get("/wishlist", response_model=PlaylistRead)
async def get_my_wishlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlaylistRead:
    """Raccourci : retourne (et crée si besoin) la wishlist privée du user
    courant. Idempotent : peut être appelé au chargement du dashboard sans
    crainte de créer des doublons."""
    wishlist = await svc.ensure_default_wishlist(db, current_user)
    return PlaylistRead.model_validate(wishlist)


@router.get("/{playlist_id}", response_model=PlaylistWithTracks)
async def get_playlist_endpoint(
    playlist_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlaylistWithTracks:
    """
    Lecture détaillée d'une playlist (avec tracks).

    Règle de visibilité :
      - Owner : peut lire n'importe laquelle de ses playlists.
      - Non-owner : peut lire uniquement si visibility=public. Sinon 404
        (pas 403, pour ne pas leak l'existence d'une playlist privée).
    """
    try:
        playlist = await svc.get_playlist(db, playlist_id)
    except svc.PlaylistNotFound:
        raise HTTPException(status_code=404, detail="Playlist introuvable")

    if playlist.owner_id != current_user.id and playlist.visibility != "public":
        raise HTTPException(status_code=404, detail="Playlist introuvable")

    tracks = await svc.list_playlist_tracks(db, playlist.id)
    return PlaylistWithTracks(
        id=playlist.id,
        owner_id=playlist.owner_id,
        title=playlist.title,
        visibility=playlist.visibility,  # type: ignore[arg-type]
        color=playlist.color,
        cover_video_url=playlist.cover_video_url,
        seed_prompt=playlist.seed_prompt,
        created_at=playlist.created_at,
        tracks=[TrackRead.model_validate(t) for t in tracks],
    )


@router.patch("/{playlist_id}", response_model=PlaylistRead)
async def update_playlist_endpoint(
    playlist_id: uuid.UUID,
    patch: PlaylistUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlaylistRead:
    try:
        playlist = await svc.update_playlist(db, current_user, playlist_id, patch)
    except svc.PlaylistNotFound:
        raise HTTPException(status_code=404, detail="Playlist introuvable")
    except svc.PlaylistForbidden:
        # 404 volontaire : pas de distinction "je ne suis pas owner" vs
        # "n'existe pas" pour ne pas leak les IDs.
        raise HTTPException(status_code=404, detail="Playlist introuvable")
    except svc.PlaylistPublicOwnerMismatch:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Impossible de passer la playlist en public : elle "
                    "contient des sons qui ne sont pas à toi."
                ),
                "code": "public_owner_mismatch",
            },
        )
    return PlaylistRead.model_validate(playlist)


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist_endpoint(
    playlist_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await svc.delete_playlist(db, current_user, playlist_id)
    except svc.PlaylistNotFound:
        raise HTTPException(status_code=404, detail="Playlist introuvable")
    except svc.PlaylistForbidden:
        raise HTTPException(status_code=404, detail="Playlist introuvable")


@router.post("/{playlist_id}/tracks", status_code=status.HTTP_201_CREATED)
async def add_track_endpoint(
    playlist_id: uuid.UUID,
    body: AddTrackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        link = await svc.add_track(
            db,
            current_user,
            playlist_id,
            body.track_id,
            position=body.position,
        )
    except svc.PlaylistNotFound:
        raise HTTPException(status_code=404, detail="Playlist introuvable")
    except svc.PlaylistForbidden:
        raise HTTPException(status_code=404, detail="Playlist introuvable")
    except svc.TrackNotFound:
        raise HTTPException(status_code=404, detail="Track introuvable")
    except svc.PlaylistPublicOwnerMismatch:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Une playlist publique ne peut contenir que tes propres "
                    "sons. Passe-la en privée ou ajoute un de tes sons."
                ),
                "code": "public_owner_mismatch",
            },
        )
    return {
        "ok": True,
        "playlistId": str(link.playlist_id),
        "trackId": str(link.track_id),
        "position": link.position,
    }


@router.delete(
    "/{playlist_id}/tracks/{track_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_track_endpoint(
    playlist_id: uuid.UUID,
    track_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await svc.remove_track(db, current_user, playlist_id, track_id)
    except svc.PlaylistNotFound:
        raise HTTPException(status_code=404, detail="Playlist introuvable")
    except svc.PlaylistForbidden:
        raise HTTPException(status_code=404, detail="Playlist introuvable")


# ─── Public-facing : /watt/users/{slug}/playlists ────────────────────────
@public_router.get("/users/{slug}/playlists", response_model=list[PlaylistRead])
async def list_public_playlists_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> list[PlaylistRead]:
    """
    Playlists publiques d'un artiste exposées sur /u/<slug>.

    Réutilise le helper `_find_artist_by_slug` de follows.py (lui-même câblé
    sur le gate profile_public) pour ne pas dupliquer la logique de
    slugification et de préservation du profil non publié.
    """
    # Import local pour éviter la dépendance circulaire au démarrage.
    from app.routers.follows import _find_artist_by_slug

    target = await _find_artist_by_slug(db, slug)
    items = await svc.list_user_playlists(
        db, target.id, visibility="public"
    )
    return [PlaylistRead.model_validate(p) for p in items]
