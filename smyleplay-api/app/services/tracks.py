from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dna import DNA
from app.models.track import Track
from app.models.user import User
from app.schemas.track import TrackCreate


class BeatLinkInvalid(Exception):
    """beat_id fourni au PATCH track invalide : inexistant, pas un beat,
    supprimé, ou appartenant à un autre artiste. → 422 côté router."""


async def create_track_with_dna(
    db: AsyncSession,
    user: User,
    data: TrackCreate,
) -> tuple[Track, DNA]:
    """Atomic creation: NO DNA = NO TRACK.

    Track and DNA are inserted in the same transaction.
    If anything fails, both are rolled back.

    Sprint 1 (2026-05-04) : `cover_url` et `prompt_id` sont passés tels
    quels depuis le payload TrackCreate. Le workflow dashboard typique :
      1. POST /tracks (avec cover_url, sans prompt_id)
      2. POST /artist/me/prompts (crée le prompt, récupère prompt.id)
      3. PATCH /tracks/{id} { prompt_id } pour lier
    Mais on accepte aussi le cas POST direct avec prompt_id (si le
    prompt préexiste) pour réduire le nombre de round-trips.
    """
    # Étape 2 — la couleur est optionnelle : si l'artiste n'en a pas choisi,
    # on la laisse à NULL et le front retombera sur sa brandColor.
    track = Track(
        title=data.title,
        artist_id=user.id,
        color=data.color,
        # Sprint 1 PR2 — fields ajoutés pour la migration POST Flask→FastAPI
        audio_url=data.audio_url,
        r2_key=data.r2_key,
        cover_url=data.cover_url,
        prompt_id=data.prompt_id,
        # Tags/moods (migration 0038) — étaient silencieusement perdus à la
        # création : le schéma TrackCreate les accepte et le front les envoie,
        # mais ils n'étaient pas reportés dans le Track → tags=NULL → la
        # recherche par mood (Track.tags ILIKE) ne retrouvait jamais le son.
        tags=data.tags,
        # Plateforme/IA d'origine (migration 0048) — même problème : le
        # <select> dashTrackPlatform était choisi mais jamais persisté.
        # Affiché sur la carte ID avant achat.
        platform=data.platform,
        # C2 — drapeau beat (placement /beats) + BPM optionnel.
        is_beat=bool(getattr(data, "is_beat", False)),
        bpm=getattr(data, "bpm", None),
    )
    db.add(track)
    await db.flush()  # get track.id from the DB

    dna = DNA(
        track_id=track.id,
        artist_id=user.id,
        full_prompt=data.full_prompt,
    )
    db.add(dna)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(track)
    await db.refresh(dna)
    return track, dna


async def patch_track(
    db: AsyncSession,
    *,
    track_id,
    user: User,
    payload,
) -> Track | None:
    """
    PATCH partiel d'un track. Utilisé par le workflow dashboard pour
    lier un prompt_id après coup (track créé d'abord, puis prompt créé,
    puis liaison).

    Renvoie None si track introuvable ou pas owner (le router transforme
    en 404). Sinon retourne le track mis à jour.
    """
    result = await db.execute(
        select(Track).where(
            Track.id == track_id,
            Track.artist_id == user.id,
        )
    )
    track = result.scalar_one_or_none()
    if track is None:
        return None

    # exclude_unset=True pour éviter d'écraser avec None les champs non
    # envoyés. Le caller envoie uniquement ce qu'il veut changer.
    data = payload.model_dump(exclude_unset=True)

    # C1 (2026-06-10) — liaison beat : on ne lie JAMAIS un beat qui
    # n'appartient pas à l'artiste courant (sinon n'importe qui pourrait
    # vampiriser le beat d'un autre en pointant son track dessus).
    if data.get("beat_id") is not None:
        from app.models.prompt import Prompt

        beat = (await db.execute(
            select(Prompt).where(
                Prompt.id == data["beat_id"],
                Prompt.product_type == "beat",
                Prompt.is_deleted.is_(False),
            )
        )).scalar_one_or_none()
        if beat is None or beat.artist_id != user.id:
            raise BeatLinkInvalid(
                "beat_id invalide : beat introuvable ou pas à toi."
            )

    for field, value in data.items():
        setattr(track, field, value)

    await db.commit()
    await db.refresh(track)
    return track


async def delete_track(
    db: AsyncSession,
    *,
    track_id,
    user: User,
) -> Track | None:
    """
    Soft-delete d'un track (migration 0028).

    - is_deleted=True → disparaît des listings publics et du dashboard.
    - Idempotent : déjà supprimé → None (le router retourne 404).
    - Le DNA associé reste en DB (archivage).
    """
    result = await db.execute(
        select(Track).where(
            Track.id == track_id,
            Track.artist_id == user.id,
            Track.is_deleted.is_(False),
        )
    )
    track = result.scalar_one_or_none()
    if track is None:
        return None

    track.is_deleted = True
    await db.commit()
    await db.refresh(track)
    return track


async def get_tracks(db: AsyncSession) -> list[Track]:
    result = await db.execute(
        select(Track)
        .where(Track.is_deleted.is_(False))
        .order_by(Track.created_at.desc())
    )
    return list(result.scalars().all())


async def get_user_tracks(db: AsyncSession, user: User) -> list[Track]:
    result = await db.execute(
        select(Track)
        .where(Track.artist_id == user.id, Track.is_deleted.is_(False))
        .order_by(Track.created_at.desc())
    )
    return list(result.scalars().all())
