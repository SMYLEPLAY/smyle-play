"""
Router de recherche globale (étape Recherche du chantier profil public).

Deux endpoints, consommés par le modal Recherche injecté dans la topbar
(ui/modals/search.js) :

  GET /watt/search/artists   → Connect (trouver des profils artistes)
  GET /watt/search/tracks    → DNA     (trouver des morceaux / signatures)

Choix design :
  - Recherche par ILIKE "%q%" sur les colonnes textuelles pertinentes
    (artist_name/bio/genre/city pour les users ; title/universe pour les
    tracks). Ça suffit pour un MVP jusqu'à quelques milliers d'items ;
    si le volume explose on migrera sur tsvector/pg_trgm plus tard.
  - Le gate `profile_public = TRUE` s'applique TOUJOURS : on ne remonte
    jamais un artiste non publié, ni une track dont l'artiste n'est pas
    publié (les DNA d'un profil brouillon ne doivent pas leaker dans la
    recherche globale).
  - Endpoints publics (pas de JWT requis) — un viewer non connecté peut
    explorer l'écosystème depuis la homepage. L'auth n'ajoute rien aux
    résultats côté V1.
  - Limite dure à 30 résultats par requête pour protéger le client et
    éviter d'avoir à paginer côté UI au MVP. Pagination en V2 si besoin.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.track import Track
from app.models.user import User
from app.models.user_follow import UserFollow
from app.routers.watt_compat import _derive_artist_slug


router = APIRouter(prefix="/watt/search", tags=["watt-search"])


# Limite dure de résultats renvoyés par endpoint. Volontairement basse au
# MVP : le modal affiche une liste compacte, pas une infinite scroll page.
_MAX_RESULTS = 30

# Longueur mini de la query pour déclencher une recherche côté serveur.
# Permet aux front d'envoyer q="" au premier mount (liste par défaut =
# "top artistes" / "nouveaux DNA") sans pénaliser les perfs.
_MIN_QUERY_LEN = 0


def _apply_text_search(stmt, q: str, *columns):
    """
    Applique un WHERE OR(ILIKE %q%, …) sur les colonnes fournies. Les
    colonnes NULL matchent jamais — ILIKE sur NULL renvoie NULL, donc
    exclu d'un OR.
    """
    pattern = f"%{q}%"
    filters = [col.ilike(pattern) for col in columns]
    return stmt.where(or_(*filters))


# ──────────────────────────────────────────────────────────────────────────
# GET /watt/search/artists
# ──────────────────────────────────────────────────────────────────────────


@router.get("/artists")
async def search_artists(
    q: str = Query(default="", max_length=100),
    role: Optional[str] = Query(default=None, max_length=50),
    genre: Optional[str] = Query(default=None, max_length=50),
    limit: int = Query(default=_MAX_RESULTS, ge=1, le=_MAX_RESULTS),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Recherche d'artistes publiés. Renvoie {artists: [...], count}.

    Paramètres :
      - q     : texte libre, matche artist_name / bio / genre / city
      - role  : filtre casquette (slug unique, ex: 'producer', 'beatmaker')
                La colonne roles est JSON array ; on filtre via un LIKE
                JSON naïf pour rester portable. Si le volume explose, on
                passera à un GIN index sur jsonb.
      - genre : filtre exact (case-insensitive) sur la colonne genre
      - limit : max 30 (cf. _MAX_RESULTS)

    Le tri par défaut pondère plays + followers pour remonter les
    profils actifs en premier. Quand q est vide, c'est un "top artistes".
    """
    # Agrégats plays + followers pour enrichir les cartes (même convention
    # que /watt/artists).
    plays_subq = (
        select(
            Track.artist_id.label("aid"),
            func.coalesce(func.sum(Track.plays), 0).label("total_plays"),
            func.count(Track.id).label("track_count"),
        )
        .group_by(Track.artist_id)
        .subquery()
    )
    followers_subq = (
        select(
            UserFollow.followee_id.label("uid"),
            func.count(UserFollow.id).label("followers_count"),
        )
        .group_by(UserFollow.followee_id)
        .subquery()
    )

    stmt = (
        select(
            User,
            func.coalesce(plays_subq.c.total_plays, 0).label("plays"),
            func.coalesce(plays_subq.c.track_count, 0).label("tracks"),
            func.coalesce(followers_subq.c.followers_count, 0).label("followers"),
        )
        .outerjoin(plays_subq, User.id == plays_subq.c.aid)
        .outerjoin(followers_subq, User.id == followers_subq.c.uid)
        .where(User.profile_public.is_(True))
    )

    if q and len(q) >= _MIN_QUERY_LEN:
        stmt = _apply_text_search(
            stmt, q, User.artist_name, User.bio, User.genre, User.city
        )

    if genre:
        stmt = stmt.where(User.genre.ilike(genre))

    if role:
        # JSON array stocké en texte — ILIKE '"<role>"' attrape les entrées
        # exactes du type ["producer","beatmaker"]. Approximatif mais OK
        # au MVP : on re-filtrera côté Python si besoin d'exactitude.
        stmt = stmt.where(User.roles.cast(func.text()).ilike(f'%"{role}"%'))  # type: ignore[attr-defined]

    stmt = stmt.order_by(
        desc("plays"), desc("followers"), desc(User.created_at)
    ).limit(limit)

    rows = (await db.execute(stmt)).all()

    artists = []
    for user, plays, tracks, followers in rows:
        artists.append({
            "id":             str(user.id),
            "slug":           _derive_artist_slug(user),
            "artistName":     user.artist_name or "",
            "genre":          user.genre or "",
            "city":           user.city or "",
            "bio":            (user.bio or "")[:200],
            "brandColor":     user.brand_color or "",
            "avatarUrl":      user.avatar_url or "",
            "roles":          user.roles or [],
            "plays":          int(plays),
            "trackCount":     int(tracks),
            "followersCount": int(followers),
        })

    return {"query": q, "count": len(artists), "artists": artists}


# ──────────────────────────────────────────────────────────────────────────
# GET /watt/search/tracks
# ──────────────────────────────────────────────────────────────────────────


@router.get("/tracks")
async def search_tracks(
    q: str = Query(default="", max_length=100),
    universe: Optional[str] = Query(default=None, max_length=50),
    genre: Optional[str] = Query(default=None, max_length=50),
    limit: int = Query(default=_MAX_RESULTS, ge=1, le=_MAX_RESULTS),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Recherche de tracks dont l'artiste est publié. Renvoie {tracks, count}.

    Matche sur title + universe côté serveur ; les tags sont laissés au
    filtrage client (pas de colonne normalisée côté tracks aujourd'hui).

    Paramètres :
      - q        : texte libre (title, universe)
      - universe : filtre exact slug (sunset-lover, jungle-osmose, …)
      - genre    : filtre exact sur le genre de l'artiste (les tracks
                   héritent du genre de leur artiste dans cette V1 —
                   track.genre n'existe pas encore comme colonne dédiée).
      - limit    : max 30.

    Chaque track renvoie : id, title, artistSlug, artistName, color,
    universe, plays, audioUrl. Le front utilise ces champs pour rendre
    une cellule cliquable qui mène à /u/<artistSlug>#track-<id> (ou qui
    pousse le player WATT directement).
    """
    stmt = (
        select(Track, User)
        .join(User, Track.artist_id == User.id)
        .where(User.profile_public.is_(True))
    )

    if q and len(q) >= _MIN_QUERY_LEN:
        stmt = _apply_text_search(stmt, q, Track.title, Track.universe)

    if universe:
        stmt = stmt.where(Track.universe == universe)

    if genre:
        stmt = stmt.where(User.genre.ilike(genre))

    stmt = stmt.order_by(desc(Track.plays), desc(Track.created_at)).limit(limit)

    rows = (await db.execute(stmt)).all()

    tracks = []
    for track, user in rows:
        tracks.append({
            "id":          str(track.id),
            "legacyId":    track.legacy_id,
            "title":       track.title,
            "universe":    track.universe or "",
            "color":       track.color or user.brand_color or "",
            "audioUrl":    track.audio_url or "",
            "plays":       int(track.plays or 0),
            "artistId":    str(user.id),
            "artistSlug":  _derive_artist_slug(user),
            "artistName":  user.artist_name or "",
        })

    return {"query": q, "count": len(tracks), "tracks": tracks}
