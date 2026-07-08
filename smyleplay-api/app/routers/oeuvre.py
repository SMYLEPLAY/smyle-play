"""
Routeur « Œuvre » — PORT depuis watt-api (l'app servie = smyleplay-api).

  GET    /watt/oeuvre/{slug}      → { son, visuel, isComplete }  (public)
  POST   /artist/me/oeuvre        → lie playlist (son) + album (visuel)  (owner)
  DELETE /artist/me/oeuvre/{slug} → dissout l'œuvre                       (owner)

Une Œuvre relie une PLAYLIST entière (face SON) et un ALBUM entier (face VISUEL)
partageant le MÊME `oeuvre_slug` ET le MÊME owner_id. C'est la primitive de
« binarité self-service » : un artiste lie ses deux faces en une œuvre.

NOTE PORT : le pack d'achat groupé (buy-complete, C5) n'est PAS porté ici —
l'achat de chaque face passe par les offres ADN (playlist/album) déjà servies.
Le champ `universe` (face visuelle officielle) n'est pas exposé (non mappé).

Lecture PUBLIQUE (auth OPTIONNELLE) : seul le TEASER des ADN + l'aperçu public
des unités sont renvoyés. Le GÉNOME gaté (seed_prompt) n'est JAMAIS renvoyé ici.
`owned` n'est calculé que si un token valide est fourni.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.core.slug import slugify
from app.database import get_db
from app.models.album import Album, AlbumImage
from app.models.playlist import Playlist, PlaylistTrack
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.services.users import get_user_by_email
from app.auth.dependencies import get_current_user

# Préfixe /watt : convention des LECTURES PUBLIQUES. La PAGE /oeuvre/<slug> est
# servie par Flask ; l'API doit donc vivre sous /watt pour ne pas l'intercepter.
router = APIRouter(prefix="/watt", tags=["oeuvre"])

# Router OWNER (actions artiste) — hors /watt, comme /artist/me/images.
owner_router = APIRouter(tags=["oeuvre"])

_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _optional_user(
    token: str | None = Depends(_optional_oauth2),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Utilisateur courant si token valide, sinon None (route reste publique)."""
    if not token:
        return None
    email = decode_access_token(token)
    if not email:
        return None
    return await get_user_by_email(db, email)


async def _owned_prompt_ids(
    db: AsyncSession, user: User | None, prompt_ids: list[UUID]
) -> set[str]:
    """Sous-ensemble des prompt_ids possédés par `user` (via UnlockedPrompt)."""
    if user is None or not prompt_ids:
        return set()
    rows = (
        await db.execute(
            select(UnlockedPrompt.prompt_id).where(
                UnlockedPrompt.current_owner_id == user.id,
                UnlockedPrompt.prompt_id.in_(prompt_ids),
            )
        )
    ).all()
    return {str(r.prompt_id) for r in rows}


async def _son_payload(db: AsyncSession, p: Playlist, owned: set[str]) -> dict:
    """Face SON (playlist) : teaser ADN public + tracks achetables."""
    rows = (
        await db.execute(
            select(Track.id, Track.title, Track.prompt_id, Prompt.price_credits)
            .select_from(PlaylistTrack)
            .join(Track, Track.id == PlaylistTrack.track_id)
            .join(Prompt, Prompt.id == Track.prompt_id, isouter=True)
            .where(PlaylistTrack.playlist_id == p.id)
            .order_by(PlaylistTrack.position.asc())
        )
    ).all()
    tracks = []
    for r in rows:
        pid = str(r.prompt_id) if r.prompt_id else None
        tracks.append({
            "trackId": str(r.id),
            "title": r.title,
            "promptId": pid,
            "price": r.price_credits if r.prompt_id else None,
            "owned": pid in owned if pid else False,
        })
    return {
        "playlistId": str(p.id),
        "title": p.title,
        "color": p.color,
        "adnForSale": p.adn_for_sale,
        "adnPrice": p.adn_price,
        "dnaDescription": p.dna_description,
        "tracks": tracks,
    }


async def _visuel_payload(db: AsyncSession, a: Album, owned: set[str]) -> dict:
    """Face VISUEL (album) : teaser ADN public + images achetables (aperçu)."""
    rows = (
        await db.execute(
            select(
                Prompt.id,
                Prompt.title,
                Prompt.preview_r2_key,
                Prompt.price_credits,
            )
            .select_from(AlbumImage)
            .join(Prompt, Prompt.id == AlbumImage.prompt_id)
            .where(AlbumImage.album_id == a.id)
            .order_by(AlbumImage.position.asc())
        )
    ).all()
    images = []
    for r in rows:
        iid = str(r.id)
        images.append({
            "imageId": iid,
            "title": r.title,
            "previewKey": r.preview_r2_key,
            "price": r.price_credits,
            "owned": iid in owned,
        })
    return {
        "albumId": str(a.id),
        "title": a.title,
        "coverPromptId": str(a.cover_prompt_id) if a.cover_prompt_id else None,
        "adnForSale": a.adn_for_sale,
        "adnPrice": a.adn_price,
        "adnStyle": a.adn_style,
        "dnaDescription": a.dna_description,
        "images": images,
    }


@router.get("/oeuvre/{slug}")
async def get_oeuvre(
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(_optional_user),
) -> dict:
    """Agrège les deux faces PUBLIQUES d'une œuvre (son + visuel)."""
    playlist = (
        await db.execute(
            select(Playlist)
            .where(Playlist.oeuvre_slug == slug, Playlist.visibility == "public")
            .order_by(Playlist.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    album = (
        await db.execute(
            select(Album)
            .where(Album.oeuvre_slug == slug, Album.visibility == "public")
            .order_by(Album.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if playlist is None and album is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "oeuvre_not_found", "slug": slug},
        )

    owner_id = playlist.owner_id if playlist is not None else album.owner_id
    if album is not None and album.owner_id != owner_id:
        album = None

    if playlist is not None:
        ptracks = (
            await db.execute(
                select(Track.prompt_id)
                .select_from(PlaylistTrack)
                .join(Track, Track.id == PlaylistTrack.track_id)
                .where(
                    PlaylistTrack.playlist_id == playlist.id,
                    Track.prompt_id.isnot(None),
                )
            )
        ).all()
    else:
        ptracks = []
    if album is not None:
        pimgs = (
            await db.execute(
                select(AlbumImage.prompt_id).where(
                    AlbumImage.album_id == album.id
                )
            )
        ).all()
    else:
        pimgs = []

    all_ids = [r.prompt_id for r in ptracks] + [r.prompt_id for r in pimgs]
    owned = await _owned_prompt_ids(db, user, all_ids)

    son = visuel = None
    if playlist is not None:
        son = await _son_payload(db, playlist, owned)
    if album is not None:
        visuel = await _visuel_payload(db, album, owned)

    return {
        "oeuvreSlug": slug,
        "ownerId": str(owner_id),
        "universe": None,
        "son": son,
        "visuel": visuel,
        "isComplete": son is not None and visuel is not None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# OWNER — composer / dissoudre une œuvre (binarité self-service)
# ─────────────────────────────────────────────────────────────────────────────

class OeuvreBindBody(BaseModel):
    playlist_id: UUID
    album_id: UUID
    title: str | None = None


@owner_router.post(
    "/artist/me/oeuvre",
    status_code=status.HTTP_200_OK,
    summary="Lie une playlist (son) et un album (visuel) en une œuvre",
)
async def bind_oeuvre(
    body: OeuvreBindBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pose un `oeuvre_slug` PARTAGÉ sur une playlist ET un album de l'owner."""
    playlist = (await db.execute(
        select(Playlist).where(Playlist.id == body.playlist_id)
    )).scalar_one_or_none()
    if playlist is None or playlist.owner_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Playlist introuvable")

    album = (await db.execute(
        select(Album).where(Album.id == body.album_id)
    )).scalar_one_or_none()
    if album is None or album.owner_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Album introuvable")

    slug = slugify(body.title or playlist.title or album.title or "")
    if not slug:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Impossible de dériver un slug — donne un titre à l'œuvre.",
        )

    clash_pl = (await db.execute(
        select(Playlist.id).where(
            Playlist.owner_id == current_user.id,
            Playlist.oeuvre_slug == slug,
            Playlist.id != playlist.id,
        )
    )).first()
    clash_al = (await db.execute(
        select(Album.id).where(
            Album.owner_id == current_user.id,
            Album.oeuvre_slug == slug,
            Album.id != album.id,
        )
    )).first()
    if clash_pl is not None or clash_al is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Ce slug d'œuvre est déjà utilisé — choisis un autre titre.",
        )

    playlist.oeuvre_slug = slug
    album.oeuvre_slug = slug
    await db.commit()

    return {
        "ok": True,
        "slug": slug,
        "playlistId": str(playlist.id),
        "albumId": str(album.id),
        "url": "/oeuvre/" + slug,
    }


@owner_router.delete(
    "/artist/me/oeuvre/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dissout une œuvre (retire le lien des deux faces)",
)
async def unbind_oeuvre(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remet `oeuvre_slug` à NULL sur les playlist(s)/album(s) de l'owner."""
    pls = (await db.execute(
        select(Playlist).where(
            Playlist.owner_id == current_user.id,
            Playlist.oeuvre_slug == slug,
        )
    )).scalars().all()
    als = (await db.execute(
        select(Album).where(
            Album.owner_id == current_user.id,
            Album.oeuvre_slug == slug,
        )
    )).scalars().all()
    for p in pls:
        p.oeuvre_slug = None
    for a in als:
        a.oeuvre_slug = None
    await db.commit()
