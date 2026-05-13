from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.track import (
    DNARead,
    TrackCreate,
    TrackRead,
    TrackUpdate,
    TrackWithDNA,
)
from app.services.tracks import (
    create_track_with_dna,
    delete_track,
    get_tracks,
    get_user_tracks,
    patch_track,
)

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.post(
    "/",
    response_model=TrackWithDNA,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    data: TrackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── Gate "profil publié" (Étape 1) ────────────────────────────────────────
    # Cohérent avec le gate Flask /api/watt/tracks : un son ne se publie
    # qu'après la publication du profil sur /u/<slug>. Le flag est porté
    # par users.profile_public. 409 = intention-utilisateur non remplie
    # (pas un 400 validation, pas un 403 permissions).
    if not bool(getattr(current_user, "profile_public", False)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error":    "profile_not_published",
                "message":  "Publie d'abord ton profil pour pouvoir publier un son.",
                "redirect": "/u/me",
            },
        )
    try:
        track, dna = await create_track_with_dna(db, current_user, data)
    except Exception as e:
        # Debug temporaire 2026-05-05 — on expose le type d'exception et
        # son message au lieu d'un détail générique. Permet de diagnostiquer
        # un bug en prod (ex: migration manquante, contrainte DB, payload
        # invalide). À retirer / remplacer par log structuré une fois le
        # bug actuel résolu.
        import logging
        logging.exception("create_track_with_dna failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create track: {type(e).__name__}: {str(e)[:300]}",
        )
    return TrackWithDNA(
        track=TrackRead.model_validate(track),
        dna=DNARead.model_validate(dna),
    )


@router.get("/", response_model=list[TrackRead])
async def list_tracks(db: AsyncSession = Depends(get_db)):
    return await get_tracks(db)


@router.get("/me", response_model=list[TrackRead])
async def list_my_tracks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_user_tracks(db, current_user)


@router.patch("/{track_id}", response_model=TrackRead)
async def update_track(
    track_id: UUID,
    payload: TrackUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sprint 1 (2026-05-04) — PATCH partiel d'un track.

    Cas d'usage principal : workflow dashboard où on crée le track puis
    le prompt, puis on lie les 2 via PATCH { prompt_id }. Permet aussi
    de mettre à jour cover_url ou title sans recréer le track.

    Authz : track doit appartenir à l'utilisateur courant. 404
    indistingable si track inexistant ou pas owner (anti-énumération).
    """
    track = await patch_track(
        db, track_id=track_id, user=current_user, payload=payload
    )
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Track not found",
        )
    return TrackRead.model_validate(track)


@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_track(
    track_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Soft-delete d'un track appartenant à l'artiste connecté.

    - Le track disparaît des listings publics et du dashboard.
    - 404 si track inexistant, déjà supprimé, ou n'appartient pas à l'artiste.
    - Retourne 204 No Content (succès sans body).
    """
    track = await delete_track(
        db, track_id=track_id, user=current_user
    )
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Track not found",
        )
