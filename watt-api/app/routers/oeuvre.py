"""
Routeur « Œuvre » (chantier C3 / C3-bis) — lecture agrégée des DEUX faces.

  GET /watt/oeuvre/{slug}   → { son, visuel, isComplete }

Une Œuvre relie une PLAYLIST entière (face SON) et un ALBUM entier (face
VISUEL) partageant le MÊME oeuvre_slug ET le MÊME owner_id (cf. migration
0076). Ce endpoint agrège les deux faces publiques en un seul payload pour
alimenter la page binaire /oeuvre/<slug> et le CTA « œuvre complète » (C4/C5).

C3-bis (placement des achats) : chaque face embarque la LISTE de ses unités
ACHETABLES, pour que la page binaire puisse poser les 4 points d'achat
(ADN collection + unité par item) sans second appel :
  • son.tracks[]   → { trackId, title, promptId, price, owned }
  • visuel.images[] → { imageId, title, previewKey, price, owned }

Lecture PUBLIQUE (auth OPTIONNELLE) : on n'expose que le TEASER des ADN +
l'aperçu public des unités. Le GÉNOME gaté (seed_prompt côté playlist,
seed_prompt + adn_palette côté album) et la RECETTE des unités (prompt_text,
image_r2_key original) ne sont JAMAIS renvoyés ici — ils restent réservés aux
endpoints owner/library, conformément à la doctrine IP. `owned` n'est calculé
que si un token valide est fourni (sinon false partout).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import decode_access_token
from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.core.slug import slugify
from app.database import get_db
from app.models.album import Album
from app.models.album import AlbumImage
from app.models.playlist import Playlist, PlaylistTrack
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.services.users import get_user_by_email

# Préfixe /watt : convention des LECTURES PUBLIQUES (cf. /watt/playlists,
# /watt/albums, /watt/images…). CRITIQUE pour le routing : `main.py` monte
# Flask en fallback sous "/" et les routes FastAPI ont précédence. Sans le
# préfixe, `GET /oeuvre/{slug}` (JSON) intercepterait la navigation navigateur
# vers la PAGE /oeuvre/<slug> (servie par Flask) → la page ne se chargerait
# jamais. On sépare donc : API = /watt/oeuvre/{slug}, PAGE = /oeuvre/<slug>.
router = APIRouter(prefix="/watt", tags=["oeuvre"])

# Router OWNER (actions de l'artiste) — hors /watt, comme /artist/me/images.
# C'est le primitive de « binarité qui se complète » : un artiste LIE sa
# playlist (face son) et son album (face visuel) en une œuvre, ou la délie.
owner_router = APIRouter(tags=["oeuvre"])

# Auth OPTIONNELLE : auto_error=False → pas de 401 si le header manque. Le
# endpoint reste public (un visiteur voit l'œuvre) ; `owned` n'est enrichi
# que si un token valide accompagne la requête.
_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _optional_user(
    token: str | None = Depends(_optional_oauth2),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Renvoie l'utilisateur courant si un token valide est présent, sinon None
    (jamais d'exception — la route reste accessible aux visiteurs)."""
    if not token:
        return None
    email = decode_access_token(token)
    if not email:
        return None
    return await get_user_by_email(db, email)


async def _owned_prompt_ids(
    db: AsyncSession, user: User | None, prompt_ids: list[UUID]
) -> set[str]:
    """Sous-ensemble des prompt_ids possédés par `user` (via UnlockedPrompt).
    Une image EST une ligne `prompts` (prompt_id == image.id) ; une recette de
    track est son `prompt_id` lié → la même table de possession couvre les deux.
    Renvoie un set vide si pas d'utilisateur ou pas d'ids."""
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


async def _son_payload(
    db: AsyncSession, p: Playlist, owned: set[str]
) -> dict:
    """Face SON (playlist) : teaser ADN public + tracks achetables.

    Génome (seed_prompt) JAMAIS exposé ici. Une track est « achetable » si elle
    porte un prompt_id (recette vendable) ; sans prompt_id elle reste listée
    mais sans bouton d'achat (price=None)."""
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


async def _visuel_payload(
    db: AsyncSession, a: Album, owned: set[str]
) -> dict:
    """Face VISUEL (album) : teaser ADN public + images achetables.

    Génome (seed_prompt / adn_palette) JAMAIS exposé. On ne renvoie que
    l'APERÇU public (previewKey) de chaque image — jamais l'original
    (image_r2_key) ni la recette (prompt_text)."""
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
        "universe": a.universe,
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
    """
    Agrège les deux faces PUBLIQUES d'une œuvre identifiée par son slug, avec
    leurs unités achetables (C3-bis).

      - 404 si AUCUNE face publique ne porte ce slug.
      - Si seule une face existe, l'autre est `null` et `isComplete=false`.
      - L'owner de l'œuvre est défini par la face SON si présente, sinon VISUEL ;
        une face d'un AUTRE owner partageant le slug n'est PAS rattachée.
      - `owned` par unité : true seulement si un token valide accompagne la
        requête ET que l'utilisateur possède l'unité (UnlockedPrompt).
    """
    playlist = (
        await db.execute(
            select(Playlist)
            .where(
                Playlist.oeuvre_slug == slug,
                Playlist.visibility == "public",
            )
            .order_by(Playlist.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    album = (
        await db.execute(
            select(Album)
            .where(
                Album.oeuvre_slug == slug,
                Album.visibility == "public",
            )
            .order_by(Album.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if playlist is None and album is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "oeuvre_not_found", "slug": slug},
        )

    # Owner de référence : face SON prioritaire, sinon face VISUEL.
    owner_id = playlist.owner_id if playlist is not None else album.owner_id

    # On ne rattache l'album QUE s'il appartient au même owner (même slug chez
    # un autre artiste = œuvre distincte, pas une demi-œuvre de celui-ci).
    if album is not None and album.owner_id != owner_id:
        album = None

    # ── Possession : on rassemble TOUS les prompt_ids des deux faces en UNE
    # requête (recettes de tracks + images), puis on marque chaque unité. ──
    son = visuel = None
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

    if playlist is not None:
        son = await _son_payload(db, playlist, owned)
    if album is not None:
        visuel = await _visuel_payload(db, album, owned)

    return {
        "oeuvreSlug": slug,
        "ownerId": str(owner_id),
        "universe": album.universe if album is not None else None,
        "son": son,
        "visuel": visuel,
        "isComplete": son is not None and visuel is not None,
    }


@router.post(
    "/oeuvre/{slug}/buy-complete",
    status_code=status.HTTP_200_OK,
    summary="Achète l'œuvre complète (ADN Playlist + ADN Album) au tarif pack",
)
@limiter.limit(LIMIT_PURCHASE)
async def buy_oeuvre_complete(
    slug: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Pack « œuvre complète » (C5) : débloque en UNE transaction l'ADN Playlist
    (face son) ET l'ADN Album (face visuel) d'une même œuvre, au prix bundle
    -15% (perk artiste -30% appliqué par face en amont). Exige les deux faces
    publiques, en vente, et non déjà possédées par l'acheteur.
    """
    from app.routers.unlocks import _raise_unlock_error
    from app.services.oeuvre_purchase import buy_oeuvre_atomic

    try:
        result = await buy_oeuvre_atomic(db, buyer_id=current_user.id, slug=slug)
        await db.commit()

        # Parrainage (mécanique 1) : 1er achat qualifiant. Idempotent.
        try:
            from app.services.referrals import maybe_reward_referral
            if await maybe_reward_referral(db, current_user.id):
                await db.commit()
        except Exception:
            await db.rollback()

        return {
            "ok": True,
            "slug": slug,
            "paid": result.paid,
            "playlist_id": str(result.playlist_id),
            "album_id": str(result.album_id),
            "message": "Œuvre complète débloquée — ADN son + visuel dans ta bibliothèque",
        }
    except ValueError as e:
        await db.rollback()
        _raise_unlock_error(e)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Tu possèdes déjà une face de cette œuvre",
        )
    except Exception:
        await db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Échec de l'achat de l'œuvre",
        )


# ─────────────────────────────────────────────────────────────────────────────
# OWNER — composer / dissoudre une œuvre (binarité self-service)
# ─────────────────────────────────────────────────────────────────────────────

class OeuvreBindBody(BaseModel):
    playlist_id: UUID
    album_id: UUID
    # Titre source du slug. Optionnel : à défaut on dérive du titre playlist.
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
    """
    Compose une œuvre : pose un `oeuvre_slug` PARTAGÉ sur une playlist ET un
    album appartenant TOUS DEUX à l'utilisateur courant. C'est l'action qui
    « complète » la binarité côté artiste lambda (l'équivalent manuel du seed
    SMYLE). Idempotent au re-bind (réécrit le slug). 404 si une face n'est pas
    possédée ; 409 si le slug est déjà pris par une AUTRE œuvre du même owner.
    """
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

    # Garde-fou collision : une AUTRE playlist/album du même owner porte déjà ce
    # slug → on refuse (un slug = une œuvre par artiste).
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
    """
    Délie une œuvre : remet `oeuvre_slug` à NULL sur la/les playlist(s) et
    album(s) du current_user portant ce slug. Idempotent (204 même si rien à
    délier). Ne supprime RIEN d'autre (les collections survivent).
    """
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
