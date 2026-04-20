from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dna import DNA
from app.models.track import Track
from app.models.user import User
from app.schemas.track import TrackCreate


async def create_track_with_dna(
    db: AsyncSession,
    user: User,
    data: TrackCreate,
) -> tuple[Track, DNA]:
    """Atomic creation: NO DNA = NO TRACK.

    Track and DNA are inserted in the same transaction.
    If anything fails, both are rolled back.
    """
    # Étape 2 — la couleur est optionnelle : si l'artiste n'en a pas choisi,
    # on la laisse à NULL et le front retombera sur sa brandColor.
    track = Track(title=data.title, artist_id=user.id, color=data.color)
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


async def get_tracks(db: AsyncSession) -> list[Track]:
    result = await db.execute(select(Track).order_by(Track.created_at.desc()))
    return list(result.scalars().all())


async def get_user_tracks(db: AsyncSession, user: User) -> list[Track]:
    result = await db.execute(
        select(Track)
        .where(Track.artist_id == user.id)
        .order_by(Track.created_at.desc())
    )
    return list(result.scalars().all())
