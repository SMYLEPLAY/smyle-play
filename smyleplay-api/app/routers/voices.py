"""
Router /api/voices — CRUD pour les voix mises en vente (P1-F9).

Endpoints :
  POST   /api/voices                 → créer un brouillon (auth artist)
  GET    /api/voices/me              → mes voix (publiées + brouillons)
  GET    /api/voices/me/unlocked     → voix que j'ai achetées
  GET    /api/voices/by-artist/{slug} → voix publiées d'un artiste (public)
  GET    /api/voices/{voice_id}      → détail d'une voix (sample_url gated
                                        sauf si owner ou unlocked)
  PATCH  /api/voices/{voice_id}      → modifier (auth + ownership)
  DELETE /api/voices/{voice_id}      → supprimer (auth + ownership)

L'unlock est dans /unlocks/voices/{id} (cohérent avec /unlocks/adns
et /unlocks/prompts). Voir routers/unlocks.py.

Le sample_url est gated : visible uniquement si demandeur == artiste OU
si demandeur a unlock (OwnedVoice). Les visiteurs anonymes voient
toujours `VoicePublicRead` (sans sample_url). Conforme à la règle Tom
project_prompt_visibility_rule (prompts/ADN/voix verrouillés publiquement).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.voice import Voice
from app.schemas.voice import (
    VoiceCreate,
    VoiceFullRead,
    VoicePublicRead,
    VoiceUpdate,
)
from app.services.voices import (
    list_voices_for_artist,
    list_voices_owned_by,
)


router = APIRouter(prefix="/api/voices", tags=["voices"])


# -----------------------------------------------------------------------------
# Helpers internes
# -----------------------------------------------------------------------------

async def _get_voice_or_404(db: AsyncSession, voice_id: UUID) -> Voice:
    voice = (await db.execute(
        select(Voice).where(Voice.id == voice_id)
    )).scalar_one_or_none()
    if voice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice not found",
        )
    return voice


def _ensure_owner(voice: Voice, current_user: User) -> None:
    """Refus 403 si l'utilisateur courant n'est pas l'artiste de la voix."""
    if voice.artist_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't own this voice",
        )


# -----------------------------------------------------------------------------
# POST /api/voices — création (brouillon par défaut)
# -----------------------------------------------------------------------------

@router.post(
    "",
    response_model=VoiceFullRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_voice(
    payload: VoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Crée une voix à vendre. `is_published=False` à la création — l'artiste
    publie ensuite via PATCH explicite (pas de "publication implicite à la
    création", on veut un toggle explicite façon ADN).
    """
    voice = Voice(
        artist_id=current_user.id,
        name=payload.name,
        style=payload.style,
        genres=payload.genres,
        sample_url=str(payload.sample_url),
        license=payload.license,
        price_credits=payload.price_credits,
        is_published=False,
    )
    db.add(voice)
    try:
        await db.commit()
        await db.refresh(voice)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create voice",
        )
    return VoiceFullRead.model_validate(voice)


# -----------------------------------------------------------------------------
# GET /api/voices/me — toutes mes voix (publiées + brouillons)
# -----------------------------------------------------------------------------

@router.get("/me", response_model=list[VoiceFullRead])
async def list_my_voices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    voices = await list_voices_for_artist(
        db, artist_id=current_user.id, only_published=False
    )
    return [VoiceFullRead.model_validate(v) for v in voices]


# -----------------------------------------------------------------------------
# GET /api/voices/me/unlocked — voix que j'ai achetées
# -----------------------------------------------------------------------------

@router.get("/me/unlocked", response_model=list[VoiceFullRead])
async def list_my_unlocked_voices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retourne les voix que l'user a unlock. `sample_url` exposée car owned.
    Triées par owned_at desc (plus récents d'abord).
    """
    voices = await list_voices_owned_by(db, user_id=current_user.id)
    return [VoiceFullRead.model_validate(v) for v in voices]


# -----------------------------------------------------------------------------
# GET /api/voices/by-artist/{artist_id} — voix publiées d'un artiste
# -----------------------------------------------------------------------------

@router.get(
    "/by-artist/{artist_id}",
    response_model=list[VoicePublicRead],
)
async def list_artist_voices(
    artist_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Vue publique des voix d'un artiste. Pas d'auth requise.
    `sample_url` JAMAIS renvoyée ici — gating publique stricte.
    """
    voices = await list_voices_for_artist(
        db, artist_id=artist_id, only_published=True
    )
    return [VoicePublicRead.model_validate(v) for v in voices]


# -----------------------------------------------------------------------------
# GET /api/voices/{voice_id} — détail public (gated)
# -----------------------------------------------------------------------------

@router.get("/{voice_id}", response_model=VoicePublicRead)
async def get_voice(
    voice_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Détail d'une voix — vue publique uniquement (jamais sample_url ici).

    Pour récupérer le sample_url :
      - L'artiste passe par GET /api/voices/me (toutes ses voix avec sample)
      - L'acheteur passe par GET /api/voices/me/unlocked
      - Le flux d'unlock POST /unlocks/voices/{id} renvoie sample_url dans
        la réponse pour éviter un 2e round-trip après l'achat.

    Cette route reste publique (sans auth) parce que la fiche métadonnées
    est conçue pour être indexable (SEO marketplace) et liée depuis /u/<slug>.
    Un brouillon (is_published=False) renvoie 404 ici — l'auteur le voit
    via /api/voices/me.
    """
    voice = await _get_voice_or_404(db, voice_id)
    if not voice.is_published:
        # On ne révèle pas l'existence d'un brouillon publiquement.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice not found",
        )
    return VoicePublicRead.model_validate(voice)


# -----------------------------------------------------------------------------
# PATCH /api/voices/{voice_id} — modifier
# -----------------------------------------------------------------------------

@router.patch("/{voice_id}", response_model=VoiceFullRead)
async def update_voice(
    voice_id: UUID,
    payload: VoiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Patch partiel. L'artiste peut toggler `is_published` indépendamment du
    contenu — ex publier sans modifier le prix, ou retirer de la vente
    sans toucher aux métadonnées.
    """
    voice = await _get_voice_or_404(db, voice_id)
    _ensure_owner(voice, current_user)

    data = payload.model_dump(exclude_unset=True)
    # HttpUrl → str pour le stockage
    if "sample_url" in data and data["sample_url"] is not None:
        data["sample_url"] = str(data["sample_url"])

    for field, value in data.items():
        setattr(voice, field, value)

    try:
        await db.commit()
        await db.refresh(voice)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update voice",
        )
    return VoiceFullRead.model_validate(voice)


# -----------------------------------------------------------------------------
# DELETE /api/voices/{voice_id}
# -----------------------------------------------------------------------------

@router.delete(
    "/{voice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_voice(
    voice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Supprime une voix.

    Note importante : la suppression CASCADE sur owned_voices supprime aussi
    les achats. Les transactions historiques sont préservées (FK NULL ou
    pas de FK selon le design transactions). Une amélioration future :
    soft-delete via `deleted_at` pour permettre aux acheteurs de récupérer
    leur sample même après que l'artiste ait dépublié.
    """
    voice = await _get_voice_or_404(db, voice_id)
    _ensure_owner(voice, current_user)

    await db.delete(voice)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete voice",
        )
    return None
