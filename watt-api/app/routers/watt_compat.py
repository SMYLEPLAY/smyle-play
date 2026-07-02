"""
Router de compatibilité WATT.

Expose des endpoints qui répondent dans la forme EXACTE attendue par le JS
front existant (watt.js, dashboard.js, artiste.js, ui/hub, ui/panels).
Objectif : pouvoir basculer les `fetch()` du site Flask vers FastAPI sans
changer une ligne de logique UI côté navigateur.

Les endpoints ici sont tous préfixés `/watt/` et vivent en parallèle des
routes "modernes" du reste de l'API (/tracks, /users, /marketplace, etc.).
À terme, quand le front aura été refait en profondeur (pages ADN,
marketplace, library), ce router pourra être supprimé.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

import asyncio
import re as _re_slug
import uuid as _uuid_module

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.config import settings
from app.database import get_db
from app.models.adn import Adn
from app.models.playlist import Playlist, PlaylistTrack
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.models.user_follow import UserFollow
from app.models.visual_adn import VisualAdn
from app.models.voice import Voice


router = APIRouter(prefix="/watt", tags=["watt-compat"])


# ──────────────────────────────────────────────────────────────────────────
# Stream proxy R2 — bypass CORS pour permettre le play des audio R2 depuis
# le frontend Railway. Same-origin = aucun problème CORS / CSP / mixed
# content. 2026-05-05 — fix audio injouable bout-en-bout.
# ──────────────────────────────────────────────────────────────────────────

_AUDIO_MIME_BY_EXT = {
    "mp3":  "audio/mpeg",
    "wav":  "audio/wav",
    "m4a":  "audio/mp4",
    "ogg":  "audio/ogg",
    "flac": "audio/flac",
    "aac":  "audio/aac",
}


@router.get("/stream/{key:path}")
async def stream_r2_audio(key: str):
    """
    Proxy le fichier audio R2 par sa clé en streaming.

    Pourquoi ce proxy : malgré que le bucket R2 soit en "public access"
    et que l'URL R2 directe (pub-XXX.r2.dev) marche dans Chrome quand on
    l'ouvre dans un onglet, le tag <audio> sur le profil Railway refusait
    le play (CORS, CSP ou Content-Type incorrect côté R2). En passant
    par cette route same-origin, on élimine toutes ces causes : Chrome
    voit l'audio comme servi par smyleplay.com directement.

    Trade-off : la bande passante est facturée par Railway (sortie) au
    lieu de R2 direct. Acceptable pour alpha (volume faible). Si le
    trafic explose, on pourra migrer vers une URL R2 publique propre
    avec config CORS correcte côté Cloudflare.

    Implementation note : on retourne un StreamingResponse qui itère
    sur le body S3 en chunks (pas de chargement mémoire complet du
    fichier). Pas de support HTTP Range pour l'instant — Chrome
    fallback sur un GET complet, ce qui marche pour des samples de
    quelques Mo. Si seek nécessaire (samples >10 Mo), ajouter Range
    plus tard.
    """
    # Import local pour éviter de tirer boto3 dans tous les imports.
    from app.services.r2 import get_r2_client, is_configured

    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 storage not configured",
        )

    client = get_r2_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 client unavailable",
        )

    bucket = settings.R2_BUCKET

    try:
        # boto3 sync — get_object retourne immédiatement un dict avec
        # Body (StreamingBody). Le streaming réel se fait à la lecture.
        obj = client.get_object(Bucket=bucket, Key=key)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"R2 object not found: {type(e).__name__}",
        )

    # Détection MIME via extension. Le content-type R2 lui-même est
    # parfois application/octet-stream — on l'ignore et on force le
    # bon type, sinon Chrome refuse le play.
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    mime = _AUDIO_MIME_BY_EXT.get(ext, "application/octet-stream")

    # Iterator qui lit le body S3 par chunks de 64 KB. boto3 StreamingBody
    # supporte iter_chunks() qui fait exactement ça.
    def _iter_chunks():
        try:
            for chunk in obj["Body"].iter_chunks(chunk_size=65536):
                yield chunk
        finally:
            try:
                obj["Body"].close()
            except Exception:
                pass

    # Content-Length aide Chrome à afficher la durée totale dès le départ.
    content_length = obj.get("ContentLength")
    headers = {}
    if content_length:
        headers["Content-Length"] = str(content_length)
    # Cache 1h côté browser (les samples R2 sont immuables tant que la
    # clé ne change pas).
    headers["Cache-Control"] = "public, max-age=3600"

    return StreamingResponse(
        _iter_chunks(),
        media_type=mime,
        headers=headers,
    )


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

UNIVERSES_META = {
    "sunset-lover": {
        "label": "SUNSET LOVER",
        "folder": "SUNSET LOVER",
        "r2_folder": "SUNSET LOVER",
        "theme": "sunset-lover",
    },
    "jungle-osmose": {
        "label": "JUNGLE OSMOSE",
        "folder": "JUNGLE OSMOSE",
        "r2_folder": "JUNGLE OSMOSE",
        "theme": "jungle-osmose",
    },
    "night-city": {
        "label": "NIGHT CITY",
        "folder": "NIGHT CITY",
        "r2_folder": "NIGHT CITY",
        "theme": "night-city",
    },
}


def _slugify(name: str) -> str:
    """Port du _slugify Flask (models.py) pour dériver un slug stable."""
    s = unicodedata.normalize("NFD", name or "")
    s = s.encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = s.strip()
    s = re.sub(r"[\s-]+", "-", s)
    return s[:80]


def _derive_artist_slug(user: User) -> str:
    """
    Slug public d'un artiste.

    - User-univers (email '<slug>@smyleplay.local')  → slug = <slug>
    - Autre user                                      → slug = slugify(artist_name) ou email local-part
    """
    if user.email and user.email.endswith("@smyleplay.local"):
        return user.email.split("@", 1)[0]
    if user.artist_name:
        return _slugify(user.artist_name)
    return _slugify(user.email.split("@", 1)[0] if user.email else "artiste")


def _build_stream_url(track: Track) -> str:
    """
    Construit l'URL streamable côté frontend.

    Stratégie 2026-05-05 (révisée) :

      1. Si on a un audio_url valide → on le retourne tel quel (URL R2
         publique pub-XXX.r2.dev qui marche déjà côté browser quand
         configurée correctement). C'est le cas par défaut le plus
         fréquent pour les nouveaux uploads.

      2. Si pas d'audio_url mais on a une r2_key + le service R2
         backend est configuré (secrets dispos) → on génère l'URL
         proxy /watt/stream/<key> qui streame le fichier same-origin.

      3. Si ni l'un ni l'autre → URL vide, le frontend affichera
         "Audio en cours de traitement".

    Le proxy en option 2 est un fallback pour les cas où l'URL R2
    publique n'a pas été stockée correctement au moment de l'upload.
    Il évite de servir une URL morte si la r2_key existe.

    Avant ce fix : on retournait TOUJOURS le proxy si r2_key existait,
    ce qui retournait 503 quand R2 n'était pas configuré côté Railway
    → audio cassé partout. Maintenant on privilégie l'URL R2 directe
    déjà connue.
    """
    if track.audio_url:
        return track.audio_url
    if track.r2_key:
        # Fallback proxy seulement si on a la clé sans URL — évite 503.
        # Import local pour éviter de tirer boto3 si pas utilisé.
        try:
            from app.services.r2 import is_configured
            if is_configured():
                return f"/watt/stream/{track.r2_key}"
        except Exception:
            pass
    return ""


def _track_to_flask_dict(track: Track, artist: Optional[User] = None) -> dict:
    """
    Convertit un Track FastAPI vers la forme attendue par le JS Flask.

    Flask track.to_dict() :
      {id, name, genre, streamUrl, r2Key, plays, uploadedAt, date}

    Sprint 1 enrichi (2026-05-04) :
      - coverUrl : URL R2 de la pochette (NULL = fallback couleur côté UI)
      - promptId : lien vers le prompt vendable (NULL = track écoutable
        seulement, pas achetable). Le détail du prompt (title, price,
        platform, etc.) est récupéré via le payload artist.prompts —
        promptId sert de pointeur pour matcher track ↔ prompt côté front.
    """
    public_id = track.legacy_id or str(track.id)
    uploaded_ms = int(track.created_at.timestamp() * 1000) if track.created_at else 0
    date_fr = track.created_at.strftime("%-d %b") if track.created_at else ""

    out = {
        "id":         public_id,
        "name":       track.title,
        "genre":      "",  # pas de genre par track dans le modèle FastAPI — vide pour compat
        "streamUrl":  _build_stream_url(track),
        "r2Key":      track.r2_key or "",
        "plays":      track.plays or 0,
        "uploadedAt": uploaded_ms,
        "date":       date_fr,
        # Sprint 1 — pivot écoute
        "coverUrl":   track.cover_url or "",
        "color":      track.color or "",
        "trackUuid":         str(track.id),  # UUID réel — utilisé par /playlists/{id}/tracks
        "promptId":          str(track.prompt_id) if track.prompt_id else None,
        # Carte ID enrichie : mood/tags + plateforme IA d'origine, affichés
        # sur la carte avant achat (migrations 0038 + 0048).
        "tags":              track.tags or "",
        "platform":          track.platform or "",
        # Prix de la recette liée — injecté a posteriori par les endpoints
        # qui font un batch query sur Prompt (tracks-recent, /watt/artists).
        # Vaut None si la track n'a pas de prompt ou si non encore injecté.
        "promptPriceCredits": None,
        # C2 — drapeau beat (étagère /beats) + BPM pour les cards.
        "isBeat":            bool(track.is_beat or track.beat_id),
        "bpm":               track.bpm,
    }
    if artist is not None:
        out["artistName"] = artist.artist_name or ""
        out["artistSlug"] = _derive_artist_slug(artist)
    return out


async def _enrich_tracks_dualite(db: AsyncSession, tracks_out: list, rows: list) -> None:
    """
    DUALITÉ ADN (chantier B, 2026-07-01) — enrichit chaque track dict avec :

      - adnMusique : {"has": bool, "price": int|None}
          L'artiste a-t-il un ADN MUSICAL publié (Adn, sommet de la pyramide
          sonore, 1 par artiste) ? price = son price_credits.
      - adnVisuel  : {"has": bool, "price": int|None}
          L'artiste a-t-il un ADN VISUEL publié (VisualAdn, sommet de la
          pyramide visuelle, 1 par artiste) ? price = son price_credits.
      - playlistTag : {"playlistId", "playlistTitle", "playlistColor"}
          Première playlist PUBLIQUE contenant ce son (tag univers cliquable).
          Les playlists publiques ne contiennent que les sons de leur owner
          (invariant modèle) → filtrer visibility='public' suffit à garantir
          que le tag pointe bien vers une playlist de l'artiste du son.

    `tracks_out` et `rows` sont parallèles : tracks_out[i] provient de rows[i]
    = (Track, User). On zippe pour réinjecter sans re-requêter.

    Design badges (front) : ces champs alimentent 2 badges d'angle sur la card
    (musique haut-gauche, visuel haut-droite). Dégradé gracieux mono-artiste :
    si un seul ADN existe, l'autre badge devient une INVITATION (face manquante).
    """
    if not tracks_out:
        return

    artist_ids = {a.id for _, a in rows}
    track_ids = [t.id for t, _ in rows]

    music_adn: dict = {}
    visual_adn: dict = {}
    if artist_ids:
        m_rows = (await db.execute(
            select(Adn.artist_id, Adn.price_credits).where(
                Adn.artist_id.in_(artist_ids),
                Adn.is_published.is_(True),
                Adn.is_deleted.is_(False),
            )
        )).all()
        music_adn = {r.artist_id: r.price_credits for r in m_rows}

        v_rows = (await db.execute(
            select(VisualAdn.artist_id, VisualAdn.price_credits).where(
                VisualAdn.artist_id.in_(artist_ids),
                VisualAdn.is_published.is_(True),
                VisualAdn.is_deleted.is_(False),
            )
        )).all()
        visual_adn = {r.artist_id: r.price_credits for r in v_rows}

    playlist_by_track: dict = {}
    if track_ids:
        p_rows = (await db.execute(
            select(
                PlaylistTrack.track_id,
                Playlist.id.label("pl_id"),
                Playlist.title.label("pl_title"),
                Playlist.color.label("pl_color"),
            )
            .join(Playlist, Playlist.id == PlaylistTrack.playlist_id)
            .where(
                PlaylistTrack.track_id.in_(track_ids),
                Playlist.visibility == "public",
            )
            .order_by(PlaylistTrack.added_at)
        )).all()
        for r in p_rows:
            if r.track_id not in playlist_by_track:
                playlist_by_track[r.track_id] = {
                    "playlistId":    str(r.pl_id),
                    "playlistTitle": r.pl_title or "",
                    "playlistColor": r.pl_color or "",
                }

    for (t, a), td in zip(rows, tracks_out):
        td["adnMusique"] = {
            "has":   a.id in music_adn,
            "price": music_adn.get(a.id),
        }
        td["adnVisuel"] = {
            "has":   a.id in visual_adn,
            "price": visual_adn.get(a.id),
        }
        pl = playlist_by_track.get(t.id)
        if pl:
            td["playlistTag"] = pl


async def _count_tracks_for_artist(db: AsyncSession, artist_id) -> int:
    stmt = select(func.count(Track.id)).where(Track.artist_id == artist_id)
    return int((await db.execute(stmt)).scalar() or 0)


async def _sum_plays_for_artist(db: AsyncSession, artist_id) -> int:
    stmt = select(func.coalesce(func.sum(Track.plays), 0)).where(
        Track.artist_id == artist_id
    )
    return int((await db.execute(stmt)).scalar() or 0)


# ──────────────────────────────────────────────────────────────────────────
# JWT optionnel — renvoie None si pas connecté (au lieu de 401)
# ──────────────────────────────────────────────────────────────────────────

_optional_oauth = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _optional_current_user(
    token: str | None = Depends(_optional_oauth),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not token:
        return None
    email = decode_access_token(token)
    if not email:
        return None
    stmt = select(User).where(User.email == email)
    return (await db.execute(stmt)).scalar_one_or_none()


# ──────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────

@router.get("/tracks-catalog")
async def tracks_catalog(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Équivalent direct de `GET /tracks.json` côté Flask.

    Renvoie le catalogue complet WATT groupé par univers, dans la forme
    exacte du fichier tracks.json historique :
      {
        "sunset-lover": {
           "label": "SUNSET LOVER",
           "folder": "SUNSET LOVER",
           "r2_folder": "SUNSET LOVER",
           "theme": "sunset-lover",
           "tracks": [{id, file, name, duration, url}, ...]
        },
        ...
      }
    """
    stmt = (
        select(Track)
        .where(Track.universe.is_not(None))
        .order_by(Track.universe, Track.title)
    )
    tracks = (await db.execute(stmt)).scalars().all()

    out: dict = {}
    for slug, meta in UNIVERSES_META.items():
        out[slug] = {**meta, "tracks": []}

    for t in tracks:
        univ_slug = t.universe
        if univ_slug not in out:
            continue
        out[univ_slug]["tracks"].append({
            "id":        t.legacy_id or str(t.id),
            "trackUuid": str(t.id),           # UUID réel pour wishlist/playlist
            "file":      (t.r2_key or "").split("/", 1)[-1] if t.r2_key else "",
            "name":      t.title,
            "duration":  t.duration_seconds,
            "url":       t.audio_url or "",
            # 2026-07-01 — pochette du son (posée via /tracks PATCH cover_url).
            # Sans ce champ, les playlists officielles n'affichaient jamais les
            # covers (le front lit track.cover_url dans loadTrack / mini-bar).
            "cover_url": t.cover_url or "",
            "coverUrl":  t.cover_url or "",   # alias camelCase (parité front)
        })
    return out


@router.get("/artists")
async def list_artists(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Équivalent de `GET /api/artists`.
    Renvoie {'artists': [...]} triés par total de plays décroissant.

    Chantier 1 : seuls les profils `profile_public = TRUE` sont renvoyés.
    Tant qu'aucun artiste n'a publié, la liste est vide — le hub principal
    affiche alors son empty state ("Bientôt des profils ici"). C'est la
    sémantique attendue : pas de fuite de comptes brouillons / privés.
    """
    # Sous-requête : pour chaque artist_id, somme des plays + nb de tracks
    subq = (
        select(
            Track.artist_id.label("aid"),
            func.coalesce(func.sum(Track.plays), 0).label("total_plays"),
            func.count(Track.id).label("track_count"),
        )
        .group_by(Track.artist_id)
        .subquery()
    )

    # Sous-requête : pour chaque artist_id, nombre d'abonnés
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
            subq.c.total_plays,
            subq.c.track_count,
            followers_subq.c.followers_count,
        )
        # P1-B9 (2026-04-28) : OUTER JOIN sur la sous-requête tracks pour
        # que les artistes publiés sans track (vendent uniquement ADN /
        # voix / prompts) apparaissent quand même dans la marketplace.
        # Avant : INNER JOIN excluait silencieusement les profils sans
        # track — bug constaté sur compte officiel Smyle (4 playlists
        # historiques retirées) et sur tout compte fraîchement créé.
        # `total_plays` et `track_count` sont déjà protégés par `or 0`
        # plus bas, donc le fallback NULL est géré côté Python.
        .outerjoin(subq, User.id == subq.c.aid)
        .outerjoin(followers_subq, User.id == followers_subq.c.uid)
        .where(User.profile_public.is_(True))
        # Phase 2 refonte marketplace : le compte officiel Smyle reste
        # toujours en tête de liste, puis tri par plays décroissants.
        .order_by(
            desc(User.is_official),
            desc(subq.c.total_plays),
            desc(User.created_at),
        )
        .limit(50)
    )
    rows = (await db.execute(stmt)).all()

    artists = []
    for user, total_plays, track_count, followers_count in rows:
        artists.append({
            "id":             str(user.id),
            "userId":         str(user.id),
            "slug":           _derive_artist_slug(user),
            "artistName":     user.artist_name or "",
            "genre":          user.genre or "",
            "bio":            user.bio or "",
            "city":           user.city or "",
            # On garde avatarColor pour la compat du JS existant, ET on expose
            # brandColor qui est le nom "canonique" attendu par la refonte.
            "avatarColor":    user.brand_color or "",
            "brandColor":     user.brand_color or "",
            "soundcloud":     user.soundcloud or "",
            "instagram":      user.instagram or "",
            "youtube":        user.youtube or "",
            "plays":          int(total_plays or 0),
            "trackCount":     int(track_count or 0),
            "followersCount": int(followers_count or 0),
            "profilePublic":  True,
            # Phase 2 refonte marketplace : flag officiel Smyle. Le front
            # l'utilise pour afficher le checkmark coloré de confiance.
            "isOfficial":     bool(user.is_official),
            # Page /artistes (2026-06-11) — chips CONNECT inline : le front
            # filtre par rôles (casquettes migration 0018). + avatarUrl que
            # la card lisait déjà sans jamais le recevoir.
            "roles":          list(user.roles) if user.roles else [],
            "avatarUrl":      user.avatar_url or "",
            "created_at":     user.created_at.isoformat() if user.created_at else None,
        })

    # Enrichissement : ADN publié de chaque artiste (pour badge 🧬 marketplace)
    # Une seule requête groupée plutôt que N requêtes par artiste.
    artist_ids = [a["userId"] for a in artists]
    if artist_ids:
        from app.models.adn import Adn as _Adn
        adn_rows = (await db.execute(
            select(_Adn.artist_id, _Adn.id, _Adn.price_credits)
            .where(
                _Adn.artist_id.in_(artist_ids),
                _Adn.is_published.is_(True),
                _Adn.is_deleted.is_(False),
            )
        )).all()
        adn_by_artist = {str(r.artist_id): {"adnId": str(r.id), "adnPrice": r.price_credits} for r in adn_rows}
        for a in artists:
            adn_info = adn_by_artist.get(a["userId"])
            a["artistAdnId"]    = adn_info["adnId"]    if adn_info else None
            a["artistAdnPrice"] = adn_info["adnPrice"] if adn_info else None

        # Enrichissement ADN VISUEL (badge marketplace, mirror ADN musical).
        from app.models.visual_adn import VisualAdn as _VisualAdn
        v_rows = (await db.execute(
            select(_VisualAdn.artist_id, _VisualAdn.id, _VisualAdn.price_credits)
            .where(
                _VisualAdn.artist_id.in_(artist_ids),
                _VisualAdn.is_published.is_(True),
                _VisualAdn.is_deleted.is_(False),
            )
        )).all()
        visual_adn_by_artist = {
            str(r.artist_id): {"id": str(r.id), "price": r.price_credits}
            for r in v_rows
        }
        for a in artists:
            v_info = visual_adn_by_artist.get(a["userId"])
            a["artistVisualAdnId"]    = v_info["id"]    if v_info else None
            a["artistVisualAdnPrice"] = v_info["price"] if v_info else None

    return {"artists": artists}


async def build_artist_detail_payload(
    db: AsyncSession,
    target: User,
    slug: str,
    viewer: User | None,
) -> dict:
    """
    Construit le payload "artist" complet consommé par `/u/<slug>` (mode
    owner ET mode visiteur) et par les endpoints publish/unpublish dans
    follows.py.

    Isolé en helper pour garantir que les deux routes (GET détail + POST
    publish/unpublish) servent strictement la même shape au front. Sans
    ça, le front doit faire un 2e appel après publish pour re-synchroniser,
    et on a vu que ça casse (symptôme "l'interface revient à création").

    `viewer` détermine :
      - `isSelf`           : viewer.id == target.id
      - `isFollowing`      : présence d'un UserFollow (follower=viewer, followee=target)
    Passer `viewer=target` (cas publish/unpublish) donne `isSelf=True`.
    """
    is_self = viewer is not None and viewer.id == target.id

    # Tracks de l'artiste
    stmt_tracks = (
        select(Track)
        .where(Track.artist_id == target.id)
        .order_by(desc(Track.created_at))
        .limit(200)
    )
    tracks = (await db.execute(stmt_tracks)).scalars().all()
    total_plays = sum(t.plays or 0 for t in tracks)

    # Batch query — playlist publique de rattachement pour chaque track.
    # On ne prend que les playlists publiques de l'artiste. Si un track
    # appartient à plusieurs playlists, on prend la première (added_at ASC).
    playlist_by_track: dict = {}
    if tracks:
        track_ids = [t.id for t in tracks]
        pt_stmt = (
            select(
                PlaylistTrack.track_id,
                Playlist.id.label("pl_id"),
                Playlist.title.label("pl_title"),
                Playlist.color.label("pl_color"),
            )
            .join(Playlist, Playlist.id == PlaylistTrack.playlist_id)
            .where(
                PlaylistTrack.track_id.in_(track_ids)
                & (Playlist.owner_id == target.id)
                & (Playlist.visibility == "public")
            )
            .order_by(PlaylistTrack.added_at)
        )
        for row in (await db.execute(pt_stmt)).all():
            if row.track_id not in playlist_by_track:
                playlist_by_track[row.track_id] = {
                    "playlistId":    str(row.pl_id),
                    "playlistTitle": row.pl_title or "",
                    "playlistColor": row.pl_color or "",
                }

    # Rank = nombre d'artistes qui ont strictement plus de plays, +1
    rank_subq = (
        select(
            Track.artist_id,
            func.coalesce(func.sum(Track.plays), 0).label("tp"),
        )
        .group_by(Track.artist_id)
        .subquery()
    )
    stmt_rank = select(func.count()).select_from(rank_subq).where(
        rank_subq.c.tp > total_plays
    )
    rank = int((await db.execute(stmt_rank)).scalar() or 0) + 1

    # Compteurs follow
    followers_count = int(
        (await db.execute(
            select(func.count(UserFollow.id)).where(
                UserFollow.followee_id == target.id
            )
        )).scalar() or 0
    )
    following_count = int(
        (await db.execute(
            select(func.count(UserFollow.id)).where(
                UserFollow.follower_id == target.id
            )
        )).scalar() or 0
    )

    # is_following : le viewer suit-il déjà cet artiste ?
    is_following = False
    if viewer is not None and not is_self:
        existing = (await db.execute(
            select(UserFollow.id).where(
                (UserFollow.follower_id == viewer.id)
                & (UserFollow.followee_id == target.id)
            )
        )).scalar_one_or_none()
        is_following = existing is not None

    # Échantillon d'abonnés (6 derniers) pour la section "Réseau" de la page
    # artiste refondue. On renvoie le minimum pour afficher une mini-carte :
    # id, slug, nom, brandColor. Pas de plays/trackCount pour rester léger.
    stmt_sample = (
        select(User)
        .join(UserFollow, UserFollow.follower_id == User.id)
        .where(UserFollow.followee_id == target.id)
        .order_by(desc(UserFollow.created_at))
        .limit(6)
    )
    sample_users = (await db.execute(stmt_sample)).scalars().all()
    followers_sample = [
        {
            "id":         str(u.id),
            "slug":       _derive_artist_slug(u),
            "artistName": u.artist_name or u.email.split("@", 1)[0] if u.email else "",
            "brandColor": u.brand_color or "",
        }
        for u in sample_users
    ]

    # ─── Chantier "DNA unlock sur profil" ───────────────────────────────────
    # On expose ici l'ADN publié (si présent) + un compteur de prompts
    # publiés, pour que le profil `/u/<slug>` puisse afficher :
    #   - la cellule "🧬 Débloquer l'ADN" si artist.adn existe
    #   - le bandeau "N recettes Suno à débloquer" si promptsForSale > 0
    # Si l'user ne vend rien : adn = None et promptsForSale = 0
    #   → le front n'affiche simplement RIEN (pas de placeholder).
    #
    # On ne renvoie JAMAIS `prompt_text`, `lyrics`, `full_prompt` ou
    # `description` intégrale de l'ADN : ce sont des contenus gated, qu'on
    # débloque via /unlocks/adns/{id} ou /unlocks/prompts/{id}. On se limite
    # à un teaser (200 premiers chars) pour la carte publique.
    adn_stmt = select(Adn).where(
        (Adn.artist_id == target.id)
        & (Adn.is_published == True)  # noqa: E712
        & (Adn.is_deleted == False)  # noqa: E712
    )
    published_adn = (await db.execute(adn_stmt)).scalar_one_or_none()
    adn_payload: dict | None = None
    if published_adn is not None:
        # 2026-05-13 — Calcul rareté (4 tiers) + stock vendu si édition limitée.
        from app.services.marketplace import compute_rarity_tier
        rarity_tier = compute_rarity_tier(published_adn.max_supply)
        sold_count = 0
        if published_adn.max_supply is not None:
            from app.models.owned_adn import OwnedAdn  # noqa: WPS433
            sold_count = int((await db.execute(
                select(func.count(OwnedAdn.adn_id)).where(
                    OwnedAdn.adn_id == published_adn.id
                )
            )).scalar_one() or 0)
        # Pas de teaser exposé : longueur + prix + meta booléens + rareté.
        max_sup = published_adn.max_supply
        adn_payload = {
            "id":               str(published_adn.id),
            "characterCount":   len(published_adn.description or ""),
            "priceCredits":     published_adn.price_credits,
            "hasUsageGuide":    bool(published_adn.usage_guide),
            "hasExampleOutputs": bool(published_adn.example_outputs),
            "createdAt":        published_adn.created_at.isoformat() if published_adn.created_at else None,
            # 2026-05-13 — Rareté + IA pour badges UI publique.
            "aiReference":      published_adn.ai_reference,
            "maxSupply":        max_sup,
            "soldCount":        sold_count if max_sup is not None else None,
            "availableCount":   (max_sup - sold_count) if max_sup is not None else None,
            "isExclusive":      max_sup == 1,
            "isLimited":        max_sup is not None and max_sup > 1,
            "isSoldOut":        max_sup is not None and sold_count >= max_sup,
            # 2026-05-13 — Tier de rareté (Mythic/Legendary/Limited/Open/Unlimited)
            "rarityTier":       rarity_tier,
        }

    # ADN VISUEL publié (sommet de la pyramide visuelle). Gaté EXACTEMENT
    # comme l'ADN musical : on n'expose JAMAIS description / palette /
    # example_outputs (génome) — uniquement characterCount + style + prix +
    # meta booléens + rareté. Révélé après achat via /me/library/visual-adns.
    from app.models.visual_adn import VisualAdn as _VisualAdn
    visual_adn_stmt = select(_VisualAdn).where(
        (_VisualAdn.artist_id == target.id)
        & (_VisualAdn.is_published == True)  # noqa: E712
        & (_VisualAdn.is_deleted == False)  # noqa: E712
    )
    published_visual_adn = (
        await db.execute(visual_adn_stmt)
    ).scalar_one_or_none()
    visual_adn_payload: dict | None = None
    if published_visual_adn is not None:
        from app.services.marketplace import compute_rarity_tier
        v_rarity_tier = compute_rarity_tier(published_visual_adn.max_supply)
        v_sold_count = 0
        if published_visual_adn.max_supply is not None:
            from app.models.owned_visual_adn import OwnedVisualAdn  # noqa: WPS433
            v_sold_count = int((await db.execute(
                select(func.count(OwnedVisualAdn.visual_adn_id)).where(
                    OwnedVisualAdn.visual_adn_id == published_visual_adn.id
                )
            )).scalar_one() or 0)
        v_max_sup = published_visual_adn.max_supply
        visual_adn_payload = {
            "id":               str(published_visual_adn.id),
            "characterCount":   len(published_visual_adn.description or ""),
            "priceCredits":     published_visual_adn.price_credits,
            # style PUBLIC (badge) ; palette GATÉE (jamais exposée ici).
            "style":            published_visual_adn.style,
            "hasUsageGuide":    bool(published_visual_adn.usage_guide),
            "hasExampleOutputs": bool(published_visual_adn.example_outputs),
            "createdAt":        published_visual_adn.created_at.isoformat() if published_visual_adn.created_at else None,
            "aiReference":      published_visual_adn.ai_reference,
            "maxSupply":        v_max_sup,
            "soldCount":        v_sold_count if v_max_sup is not None else None,
            "availableCount":   (v_max_sup - v_sold_count) if v_max_sup is not None else None,
            "isExclusive":      v_max_sup == 1,
            "isLimited":        v_max_sup is not None and v_max_sup > 1,
            "isSoldOut":        v_max_sup is not None and v_sold_count >= v_max_sup,
            "rarityTier":       v_rarity_tier,
        }

    # Prompts publiés de l'artiste (meta seulement — prompt_text/lyrics gated).
    # On ramène jusqu'à 50 items, suffisant pour tous les cas raisonnables
    # (au-delà, l'UI fera un "voir plus" via un endpoint paginé dédié).
    prompts_stmt = (
        select(Prompt)
        .where(
            (Prompt.artist_id == target.id)
            & (Prompt.is_published == True)  # noqa: E712
            & (Prompt.is_deleted == False)  # noqa: E712
            # C4 (séparation son/image) — la section "prompts publiés" du
            # profil ne liste QUE des recettes audio. Les images ont leur
            # propre surface (/images) et ne doivent jamais y apparaître.
            & (Prompt.product_type != "image")
        )
        .order_by(desc(Prompt.created_at))
        .limit(50)
    )
    prompts_rows = (await db.execute(prompts_stmt)).scalars().all()
    from app.services.marketplace import compute_rarity_tier
    # C4 « Oeuvre complete » — image liee a chaque son (apercu public only :
    # id/previewKey/prix). Batch : on charge les images partenaires en UNE
    # requete (pas de N+1). Aucune recette/original n'est exposee.
    _linked_img_ids = [
        p.linked_prompt_id for p in prompts_rows if p.linked_prompt_id is not None
    ]
    _linked_imgs_by_id: dict = {}
    if _linked_img_ids:
        _img_rows = (await db.execute(
            select(Prompt).where(
                Prompt.id.in_(_linked_img_ids),
                Prompt.is_deleted.is_(False),
                Prompt.product_type == "image",
            )
        )).scalars().all()
        _linked_imgs_by_id = {img.id: img for img in _img_rows}

    def _linked_image_for(p: Prompt) -> dict | None:
        img = _linked_imgs_by_id.get(p.linked_prompt_id) if p.linked_prompt_id else None
        if img is None:
            return None
        return {
            "id":           str(img.id),
            "previewKey":   img.preview_r2_key or "",
            "priceCredits": img.price_credits,
        }

    # Map son_prompt_id -> linkedImage, pour injecter aussi dans les cards
    # tracks (qui matchent par promptId). Reste apercu-only (anti-fuite).
    _linked_image_by_son_id = {
        p.id: _linked_image_for(p)
        for p in prompts_rows
        if p.linked_prompt_id is not None
    }

    prompts_payload = [
        {
            "id":           str(p.id),
            "title":        p.title,
            "description":  p.description or "",
            "priceCredits": p.price_credits,
            "hasLyrics":    bool(p.lyrics),
            # Rareté/supply (2026-06-08) — comme les ADN.
            "maxSupply":    p.max_supply,
            "rarityTier":   compute_rarity_tier(p.max_supply),
            # P1-F4 publique partielle (révision 2026-05-04 PR3) :
            # SEULS les réglages "non-reproductibles" sont publics. Ceux
            # qui permettraient à l'acheteur de cloner le son sans payer
            # restent gated jusqu'à l'unlock.
            #
            # PUBLICS (utiles à l'évaluation, pas suffisants pour cloner) :
            "promptPlatform":      p.prompt_platform,
            "promptModelVersion":  p.prompt_model_version,
            "promptVocalGender":   p.prompt_vocal_gender,
            # C4 « Oeuvre complete » — image liee (apercu only) + flag.
            "linkedImage":         _linked_image_for(p),
            "isOeuvreComplete":    p.linked_prompt_id is not None
                                    and _linked_image_for(p) is not None,
            # Nature du lien : True = « ne ensemble » (le son ne s'affiche pas
            # en carte individuelle ; il n'existe que via l'oeuvre / la track
            # card). Le front s'en sert pour ne PAS rendre de carte recette
            # autonome dupliquee. L'achat separe (track card 🧬) reste ouvert.
            "bundleExclusive":     bool(p.bundle_exclusive),
            #
            # GATED (cœur de la recette — révélés seulement après unlock
            # via /library qui consomme PromptRead complet) :
            #   - prompt_weirdness
            #   - prompt_style_influence
            #   - prompt_text complet
            #   - lyrics complets
            #
            # Le frontend artiste.js ne doit PLUS afficher ces 2 champs
            # sur la card publique — ils ne sont plus dans le payload.
        }
        for p in prompts_rows
    ]
    prompts_for_sale = len(prompts_payload)

    return {
        "id":             str(target.id),
        "userId":         str(target.id),
        "slug":           slug,
        "artistName":     target.artist_name or "",
        "genre":          target.genre or "",
        "bio":            target.bio or "",
        "city":           target.city or "",
        "avatarColor":    target.brand_color or "",  # compat JS historique
        "brandColor":     target.brand_color or "",  # nom canonique
        # Chantier "Profil artiste type" (migration 0017) — thème page publique
        "profileBgColor":    target.profile_bg_color    or "",
        "profileBrandColor": target.profile_brand_color or "",
        # Chantier "Profil artiste type" (migration 0016) — médias + influences + socials étendus
        "avatarUrl":      target.avatar_url or "",
        "coverPhotoUrl":  target.cover_photo_url or "",
        "influences":     target.influences or "",
        # Chantier "Page unifiée" — section "Mon univers" éditable sur /u/<slug>
        "universeDescription": target.universe_description or "",
        # Chantier "Positionnement fan/artiste" (migration 0018) — casquettes
        # déclarées par l'utilisateur (artiste, producteur, topliner, ...).
        # JSON array stocké en DB. None (pas encore choisi) → array vide
        # côté front pour simplifier le rendu (chips absents).
        "roles":          list(target.roles) if target.roles else [],
        "soundcloud":     target.soundcloud or "",
        "instagram":      target.instagram or "",
        "youtube":        target.youtube or "",
        "tiktok":         target.tiktok or "",
        "spotify":        target.spotify or "",
        "twitterX":       target.twitter_x or "",
        "plays":          total_plays,
        "trackCount":     len(tracks),
        "rank":           rank,
        "followersCount": followers_count,
        "followingCount": following_count,
        "followersSample": followers_sample,
        "isFollowing":    is_following,
        "isSelf":         is_self,
        "profilePublic":  bool(target.profile_public),
        # Phase 2 refonte marketplace : flag officiel Smyle. Le front
        # affiche le checkmark coloré sur le profil et le priorise dans
        # la vitrine d'accueil.
        "isOfficial":     bool(target.is_official),
        "created_at":     target.created_at.isoformat() if target.created_at else None,
        "tracks":         [
            {
                **_track_to_flask_dict(t),
                **(playlist_by_track.get(t.id) or {}),
                # C4 « Oeuvre complete » — image liee injectee aussi sur la
                # card track (le front matche par promptId). Apercu only.
                "linkedImage":      _linked_image_by_son_id.get(t.prompt_id),
                "isOeuvreComplete": _linked_image_by_son_id.get(t.prompt_id) is not None,
            }
            for t in tracks
        ],
        # Chantier "DNA unlock sur profil" — présents si l'artiste vend,
        # None / 0 / [] sinon. Le front cache la section correspondante
        # si vide. On ne renvoie JAMAIS prompt_text / lyrics en clair :
        # ces champs restent gated jusqu'à /unlocks/prompts/{id}.
        "adn":            adn_payload,
        # ADN VISUEL artiste (gaté) — sommet de la pyramide visuelle.
        "visualAdn":      visual_adn_payload,
        "promptsForSale": prompts_for_sale,
        "prompts":        prompts_payload,
        # Boutique : voix publiées + playlists avec ADN en vente
        "voices":         await _build_voices_payload(db, target.id),
        "playlistsForSale": await _build_playlists_for_sale_payload(db, target.id),
    }


async def _build_voices_payload(db, artist_id) -> list[dict]:
    """Voix publiées par l'artiste pour la section boutique."""
    rows = (await db.execute(
        select(Voice)
        .where(
            (Voice.artist_id == artist_id)
            & (Voice.is_published.is_(True))
            & (Voice.is_deleted.is_(False))
        )
        .order_by(desc(Voice.created_at))
        .limit(20)
    )).scalars().all()
    return [
        {
            "id":           str(v.id),
            "name":         v.name,
            "style":        v.style or "",
            "genres":       list(v.genres or []),
            "license":      v.license or "",
            "priceCredits": v.price_credits,
            "previewUrl":   v.preview_url or "",
        }
        for v in rows
    ]


async def _build_playlists_for_sale_payload(db, artist_id) -> list[dict]:
    """Playlists avec ADN en vente pour la section boutique."""
    rows = (await db.execute(
        select(Playlist)
        .where(
            (Playlist.owner_id == artist_id)
            & (Playlist.adn_for_sale.is_(True))
        )
        .order_by(desc(Playlist.created_at))
        .limit(20)
    )).scalars().all()
    return [
        {
            "id":       str(p.id),
            "title":    p.title,
            "color":    p.color or "#cc88ff",
            "adnPrice": p.adn_price or 0,
        }
        for p in rows
    ]


@router.get("/artists/{slug}")
async def get_artist(
    slug: str,
    viewer: User | None = Depends(_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Équivalent de `GET /api/artists/<slug>`.
    Renvoie {'artist': {…, rank, tracks: [...]}}.

    Chantier 1 :
    - Le profil n'est servi publiquement QUE si profile_public = TRUE.
      Exception : le viewer authentifié peut toujours voir SON propre
      profil même non-publié (preview wattboard).
    - Renvoie en plus followersCount, followingCount, isFollowing
      (false si pas de viewer ou si viewer == artiste).

    Le payload lui-même est construit par `build_artist_detail_payload` —
    même code que les réponses de publish/unpublish pour garantir que le
    front n'a jamais à faire un 2e appel pour se resynchroniser.
    """
    # Récupérer TOUS les users et trouver celui dont le slug dérivé matche.
    # Comme le slug est dérivé (pas stocké), on doit parcourir. OK pour < 1000 users.
    #
    # Chantier "Page unifiée" : on ne filtre PLUS sur artist_name IS NOT NULL,
    # car un user fraîchement inscrit n'a pas encore rempli son nom d'artiste
    # et doit pouvoir atterrir sur /artiste/<email-local-part> pour CRÉER son
    # profil en mode owner. Le gating visibilité publique (plus bas) protège
    # toujours les fans : un profil non publié reste invisible pour les tiers.
    stmt_all = select(User)
    users = (await db.execute(stmt_all)).scalars().all()

    # Résolution DÉTERMINISTE en cas de slugs en doublon (homonymes).
    # Incident 2026-06-07 : deux comptes "Smyle" → /u/smyle tombait sur le
    # doublon VIDE car ce scan renvoyait le 1er match dans un ordre DB non
    # garanti (réordonné par le backfill du parrainage, migration 0042).
    # On préfère le compte OFFICIEL, puis le plus ancien (created_at).
    matches = [u for u in users if _derive_artist_slug(u) == slug]
    if not matches:
        raise HTTPException(status_code=404, detail="Artiste introuvable")
    matches.sort(key=lambda u: (not bool(u.is_official), u.created_at))

    # Gatekeeping visibilité : on renvoie le 1er homonyme VISIBLE pour ce
    # viewer (public, OU son propre profil même non publié — preview wattboard).
    target: User | None = None
    for u in matches:
        if u.profile_public or (viewer is not None and viewer.id == u.id):
            target = u
            break
    if target is None:
        # Tous les homonymes sont privés et le viewer n'en possède aucun.
        raise HTTPException(status_code=404, detail="Artiste introuvable")

    payload = await build_artist_detail_payload(db, target, slug, viewer)
    return {"artist": payload}


@router.get("/tracks-recent")
async def tracks_recent(
    limit: int = 12,
    beats_only: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Équivalent de `GET /api/tracks/recent` — les N derniers sons tous
    artistes confondus, pour la playlist communautaire de l'accueil.

    Filtre P1-F2 (2026-05-03) : on n'inclut que les tracks d'artistes
    avec `profile_public = TRUE`. Cohérent avec /watt/artists qui filtre
    déjà ainsi. Sans ce filtre, un compte fraîchement créé dont le profil
    n'est pas encore publié verrait ses sons fuités sur la home publique.

    `limit` accepté en query (1-50). Default 12 pour conserver la shape
    historique consommée par ui/hub/community.js et ui/panels/agent.js.
    """
    safe_limit = max(1, min(int(limit or 12), 100))
    stmt = (
        select(Track, User)
        .join(User, User.id == Track.artist_id)
        .where(User.profile_public.is_(True))
        .order_by(desc(Track.created_at))
        .limit(safe_limit)
    )
    # C2 — étagère /beats : sons flagués beat (nouveau drapeau) OU liés à
    # un produit beat legacy (beat_id, pré-C2).
    if beats_only:
        from sqlalchemy import or_ as _or

        stmt = stmt.where(
            _or(Track.is_beat.is_(True), Track.beat_id.isnot(None))
        )
    rows = (await db.execute(stmt)).all()
    tracks_out = [_track_to_flask_dict(t, a) for t, a in rows]

    # Batch-fetch du prix des recettes liées (promptId → priceCredits).
    # Une seule requête pour tous les tracks ayant un prompt_id.
    prompt_ids = [
        t.prompt_id for t, _ in rows if t.prompt_id is not None
    ]
    if prompt_ids:
        from app.models.prompt import Prompt as _Prompt
        price_rows = (await db.execute(
            select(_Prompt.id, _Prompt.price_credits)
            .where(_Prompt.id.in_(prompt_ids))
        )).all()
        price_by_id = {str(r.id): r.price_credits for r in price_rows}
        for td in tracks_out:
            if td.get("promptId"):
                td["promptPriceCredits"] = price_by_id.get(td["promptId"])

    # Carte scindée SON|VISUEL (1.2, 02/07) — image liée (aperçu only,
    # anti-fuite : jamais image_r2_key/prompt) + PROVENANCE (image_platform)
    # pour la zone VISUEL des cards : « ⚡ Suno » côté son ↔ « ⚡ ChatGPT »
    # côté image. Batch en 2 requêtes, même pattern que le profil.
    if prompt_ids:
        from app.models.prompt import Prompt as _Prompt
        link_rows = (await db.execute(
            select(_Prompt.id, _Prompt.linked_prompt_id).where(
                _Prompt.id.in_(prompt_ids),
                _Prompt.linked_prompt_id.isnot(None),
            )
        )).all()
        img_by_id: dict = {}
        if link_rows:
            img_rows = (await db.execute(
                select(_Prompt).where(
                    _Prompt.id.in_([r.linked_prompt_id for r in link_rows]),
                    _Prompt.product_type == "image",
                    _Prompt.is_published.is_(True),
                    _Prompt.is_deleted.is_(False),
                )
            )).scalars().all()
            img_by_id = {i.id: i for i in img_rows}
        link_by_son = {str(r.id): r.linked_prompt_id for r in link_rows}
        for td in tracks_out:
            img = img_by_id.get(link_by_son.get(td.get("promptId") or ""))
            if img is not None:
                td["linkedImage"] = {
                    "id": str(img.id),
                    "previewKey": img.preview_r2_key or "",
                    "priceCredits": img.price_credits,
                    "platform": img.image_platform or "",
                }

    # DUALITÉ ADN (B) — badges musique/visuel + tag playlist par son.
    await _enrich_tracks_dualite(db, tracks_out, rows)

    return {"tracks": tracks_out}


@router.post("/plays/{public_id}")
async def increment_plays(
    public_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Équivalent de `POST /api/watt/plays/<id>` (P1-F8).

    Incrémente le compteur de plays d'une track. `public_id` peut être :
    - un legacy_id (ex. 'sl-sw001amberdrivedriftwav')
    - un UUID (pour les tracks uploadées après migration)

    Note : pas de plays_total agrégé sur User côté FastAPI — la somme est
    calculée à la volée dans /watt/artists et build_artist_detail_payload
    via func.sum(Track.plays). Donc on n'a qu'un seul compteur à toucher.

    Pas d'auth : un play est anonyme par design (catalogue d'écoute public).
    Le throttling éventuel est laissé à un middleware en aval (Cloudflare).

    Atomicité : on évite la race "lecture +1 → écriture" en faisant un
    UPDATE arithmétique direct via .update() — comme ça deux plays
    simultanés finissent bien à +2 même si la transaction overlapping est
    planifiée par Postgres.
    """
    # Lookup par legacy_id en priorité (cas majoritaire — tracks legacy WATT).
    track = (await db.execute(
        select(Track).where(Track.legacy_id == public_id)
    )).scalar_one_or_none()

    # Fallback UUID si pas trouvé via legacy_id (tracks uploadées post-migration)
    if track is None:
        try:
            import uuid
            uid = uuid.UUID(public_id)
            track = (await db.execute(
                select(Track).where(Track.id == uid)
            )).scalar_one_or_none()
        except (ValueError, AttributeError):
            track = None

    if track is None:
        return {"ok": False, "plays": 0}

    # Incrément arithmétique direct (anti-race) — équivalent à
    # `UPDATE tracks SET plays = COALESCE(plays, 0) + 1 WHERE id = :id`.
    # Le re-fetch ensuite renvoie la valeur committée fraîche.
    from sqlalchemy import update
    await db.execute(
        update(Track)
        .where(Track.id == track.id)
        .values(plays=func.coalesce(Track.plays, 0) + 1)
    )

    # Vraies stats (2026-06-10) : chaque play insère AUSSI un événement
    # horodaté play_events → la courbe 7j/30j du dashboard devient réelle
    # (avant : données simulées côté front). Anonyme — pas de user ni d'IP.
    # Best-effort : un échec ici ne casse pas le compteur total.
    try:
        from app.models.play_event import PlayEvent
        db.add(PlayEvent(track_id=track.id))
    except Exception:
        pass

    await db.commit()
    await db.refresh(track)
    return {"ok": True, "plays": int(track.plays or 0)}


@router.get("/me/plays-history")
async def my_plays_history(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    token: str | None = Depends(OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)),
) -> dict:
    """
    Courbe d'écoutes RÉELLE de l'artiste connecté (chantier vraies stats,
    2026-06-10) : nombre de plays par jour sur ses tracks, sur `days` jours
    (1..90), zéros inclus pour les jours sans écoute.

    Réponse : {"days": N, "since": "YYYY-MM-DD", "series": [int, ...]}
    (series[0] = il y a N-1 jours … series[-1] = aujourd'hui, fuseau UTC).

    Les écoutes antérieures au déploiement de play_events n'existent pas
    dans la table : la courbe démarre à cette date (assumé — le TOTAL
    affiché ailleurs reste Track.plays, lui complet).
    """
    from datetime import datetime, timedelta, timezone

    from app.models.play_event import PlayEvent

    # Auth manuelle (le router watt-compat n'a pas de dépendance auth
    # globale) : token requis, résolu par email comme partout.
    if not token:
        return {"days": 0, "since": None, "series": []}
    email = decode_access_token(token)
    if email is None:
        return {"days": 0, "since": None, "series": []}
    user = (await db.execute(
        select(User).where(User.email == email)
    )).scalar_one_or_none()
    if user is None:
        return {"days": 0, "since": None, "series": []}

    days = max(1, min(int(days or 30), 90))
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    rows = (await db.execute(
        select(
            func.date_trunc("day", PlayEvent.created_at).label("day"),
            func.count(PlayEvent.id),
        )
        .join(Track, Track.id == PlayEvent.track_id)
        .where(
            Track.artist_id == user.id,
            PlayEvent.created_at >= since,
        )
        .group_by("day")
    )).all()
    by_day = {row[0].date().isoformat(): int(row[1]) for row in rows}

    series = []
    for i in range(days):
        d = (since + timedelta(days=i)).date().isoformat()
        series.append(by_day.get(d, 0))

    return {"days": days, "since": since.date().isoformat(), "series": series}


@router.get("/stats")
async def global_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Équivalent de `GET /api/watt/stats` (n'existait pas côté Flask, 404).

    Compteurs globaux WATT pour les widgets d'accueil.
    """
    total_tracks = int(
        (await db.execute(select(func.count(Track.id)))).scalar() or 0
    )
    total_artists = int(
        (await db.execute(
            select(func.count(func.distinct(Track.artist_id)))
        )).scalar() or 0
    )
    total_plays = int(
        (await db.execute(
            select(func.coalesce(func.sum(Track.plays), 0))
        )).scalar() or 0
    )
    return {
        "tracks":  total_tracks,
        "artists": total_artists,
        "plays":   total_plays,
    }


@router.get("/me/stats")
async def my_stats(
    user: User | None = Depends(_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Équivalent de `GET /api/watt/me/stats`.

    Stats personnelles de l'artiste connecté. Renvoie des zéros si pas de
    JWT fourni — le widget s'affiche quand même, juste vide.
    """
    if user is None:
        return {"authenticated": False, "tracks": 0, "plays": 0, "rank": None}

    track_count = await _count_tracks_for_artist(db, user.id)
    plays = await _sum_plays_for_artist(db, user.id)

    # Rank parmi tous les artistes
    rank_subq = (
        select(
            Track.artist_id,
            func.coalesce(func.sum(Track.plays), 0).label("tp"),
        )
        .group_by(Track.artist_id)
        .subquery()
    )
    stmt_rank = select(func.count()).select_from(rank_subq).where(
        rank_subq.c.tp > plays
    )
    rank = int((await db.execute(stmt_rank)).scalar() or 0) + 1

    return {
        "authenticated": True,
        "tracks": track_count,
        "plays":  plays,
        "rank":   rank,
        "artistName": user.artist_name or "",
        "brandColor": user.brand_color or "",
    }


@router.delete("/tracks/{public_id}")
async def delete_track(
    public_id: str,
    user: User | None = Depends(_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Équivalent de `DELETE /api/watt/tracks/<id>` (P1-F5 — port complet).

    Supprime une track côté DB ET côté R2 (sample audio). L'auth est requise
    (sinon un curl anonyme pourrait tout effacer) et l'appelant doit être
    propriétaire de la track.

    Ordre des opérations :
      1. Lookup track (par legacy_id puis fallback UUID)
      2. Authz : owner check
      3. Capture la `r2_key` AVANT le delete DB (sinon Python perd la
         référence à la row détachée)
      4. Delete DB + commit
      5. Delete R2 (best-effort — un échec R2 ne rollback pas la DB ; on
         préfère une row supprimée + un orphelin R2 (cleanup batch)
         qu'une track qui réapparaît mystérieusement après un échec
         réseau côté R2). Cohérent avec le comportement Flask historique
         (logger.warning + swallow).
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Auth requise")

    stmt = select(Track).where(Track.legacy_id == public_id)
    track = (await db.execute(stmt)).scalar_one_or_none()

    if track is None:
        try:
            import uuid
            uid = uuid.UUID(public_id)
            track = (await db.execute(select(Track).where(Track.id == uid))).scalar_one_or_none()
        except (ValueError, AttributeError):
            track = None

    if track is None:
        raise HTTPException(status_code=404, detail="Track introuvable")

    if track.artist_id != user.id:
        raise HTTPException(status_code=403, detail="Pas ton son")

    # Capture la r2_key avant que la row soit détachée par db.delete()
    r2_key_to_purge = track.r2_key

    await db.delete(track)
    await db.commit()

    # Delete R2 best-effort (P1-F5). Lazy import pour éviter de tirer
    # boto3 dans tous les imports du router quand R2 n'est pas utilisé.
    if r2_key_to_purge:
        from app.services.r2 import delete_r2_object
        await delete_r2_object(r2_key_to_purge)

    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────
# Marketplace — DNA Playlists (Adn) + Prompts
# ──────────────────────────────────────────────────────────────────────────

@router.get("/adns")
async def list_adns(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Liste publique des DNA Playlists (Adn.is_published = True).

    Renvoie {'adns': [...]} avec, pour chaque ADN :
      slug, artistName, brandColor, description, usageGuide,
      exampleOutputs, priceCredits, trackCount, promptCount, universe.

    Trié par nombre de tracks descendant (les univers les plus fournis
    apparaissent en premier).
    """
    stmt = (
        select(Adn, User)
        .join(User, User.id == Adn.artist_id)
        .where(Adn.is_published == True, Adn.is_deleted == False)  # noqa: E712
    )
    rows = (await db.execute(stmt)).all()

    adns = []
    for adn, artist in rows:
        track_count = await _count_tracks_for_artist(db, artist.id)
        prompt_count_stmt = select(func.count(Prompt.id)).where(
            (Prompt.artist_id == artist.id)
            & (Prompt.is_published == True)  # noqa: E712
        )
        prompt_count = int((await db.execute(prompt_count_stmt)).scalar() or 0)

        # Univers = universe slug de la premiere track de l'artiste
        univ_stmt = (
            select(Track.universe)
            .where(Track.artist_id == artist.id)
            .limit(1)
        )
        universe = (await db.execute(univ_stmt)).scalar_one_or_none()

        adns.append({
            "id":             str(adn.id),
            "slug":           _derive_artist_slug(artist),
            "artistId":       str(artist.id),
            "artistName":     artist.artist_name or "",
            "brandColor":     artist.brand_color or "",
            "description":    adn.description,
            "usageGuide":     adn.usage_guide or "",
            "exampleOutputs": adn.example_outputs or "",
            "priceCredits":   adn.price_credits,
            "trackCount":     track_count,
            "promptCount":    prompt_count,
            "universe":       universe or "",
            "createdAt":      adn.created_at.isoformat() if adn.created_at else None,
        })

    # Tri : nombre de tracks decroissant
    adns.sort(key=lambda a: a["trackCount"], reverse=True)
    return {"adns": adns}


@router.get("/adns/{slug}")
async def get_adn(slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Fiche complete d'une DNA Playlist, par slug artiste.

    Inclut : l'ADN + les N prompts publics de l'artiste + les 20 dernieres
    tracks exemples (pour preview).
    """
    # Retrouver l'artiste par slug (parcours — OK pour < 1000 artistes)
    stmt_users = select(User).where(
        (User.artist_name.is_not(None)) | (User.email.like("%@smyleplay.local"))
    )
    users = (await db.execute(stmt_users)).scalars().all()

    # Résolution déterministe en cas de slugs en doublon (cf. get_artist) :
    # compte officiel d'abord, puis le plus ancien.
    matches = [u for u in users if _derive_artist_slug(u) == slug]
    if not matches:
        raise HTTPException(status_code=404, detail="Artiste introuvable")
    matches.sort(key=lambda u: (not bool(u.is_official), u.created_at))
    target = matches[0]

    # ADN
    adn_stmt = select(Adn).where(
        (Adn.artist_id == target.id) & (Adn.is_published == True)  # noqa: E712
    )
    adn = (await db.execute(adn_stmt)).scalar_one_or_none()
    if adn is None:
        raise HTTPException(status_code=404, detail="DNA Playlist non publiée")

    # Prompts publics de l'artiste (recettes audio uniquement — C4 séparation
    # son/image : les images ne sont pas listées sur cette surface audio).
    prompts_stmt = (
        select(Prompt)
        .where(
            (Prompt.artist_id == target.id)
            & (Prompt.is_published == True)  # noqa: E712
            & (Prompt.product_type != "image")
            # C4 « Oeuvre complete » — surface publique : pas de carte
            # individuelle pour un son « ne ensemble » (bundle_exclusive).
            & (Prompt.bundle_exclusive == False)  # noqa: E712
        )
        .order_by(Prompt.title)
    )
    prompts = (await db.execute(prompts_stmt)).scalars().all()

    # Tracks exemples (20 plus recentes)
    tracks_stmt = (
        select(Track)
        .where(Track.artist_id == target.id)
        .order_by(desc(Track.created_at))
        .limit(20)
    )
    tracks = (await db.execute(tracks_stmt)).scalars().all()

    universe = tracks[0].universe if tracks else ""

    return {
        "adn": {
            "id":             str(adn.id),
            "slug":           slug,
            "artistId":       str(target.id),
            "artistName":     target.artist_name or "",
            "brandColor":     target.brand_color or "",
            "description":    adn.description,
            "usageGuide":     adn.usage_guide or "",
            "exampleOutputs": adn.example_outputs or "",
            "priceCredits":   adn.price_credits,
            "universe":       universe,
            "createdAt":      adn.created_at.isoformat() if adn.created_at else None,
        },
        "prompts": [
            {
                "id":           str(p.id),
                "title":        p.title,
                "description":  p.description or "",
                "priceCredits": p.price_credits,
                # Flag UI : indique si des paroles existent (sans les révéler)
                "hasLyrics":    bool(p.lyrics),
                # prompt_text et lyrics volontairement omis — gated (unlock requis)
            }
            for p in prompts
        ],
        "tracks": [_track_to_flask_dict(t) for t in tracks],
    }


@router.get("/prompts")
async def list_prompts(
    universe: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Liste publique des prompts (Prompt.is_published = True).

    Params query optionnels :
      - universe=sunset-lover | jungle-osmose | night-city | hit-mix

    Renvoie {'prompts': [...]} avec le prompt_text OMIS (gated).
    """
    stmt = (
        select(Prompt, User)
        .join(User, User.id == Prompt.artist_id)
        .where(Prompt.is_published == True)  # noqa: E712
        # C4 (séparation son/image) — catalogue public des recettes audio :
        # jamais d'images (elles ont leur propre surface /images).
        .where(Prompt.product_type != "image")
        # C4 « Oeuvre complete » — pas de carte individuelle pour un son
        # « ne ensemble » (bundle_exclusive) : il n'apparait que via l'oeuvre.
        .where(Prompt.bundle_exclusive.is_(False))
    )

    if universe:
        # Filtre via l'univers des tracks de l'artiste : on ne veut garder
        # que les prompts dont l'artiste possede au moins une track dans
        # l'univers demande (ce qui colle parce qu'on a 1 user-univers).
        univ_artists_stmt = (
            select(Track.artist_id).where(Track.universe == universe).distinct()
        )
        univ_artists = (await db.execute(univ_artists_stmt)).scalars().all()
        if not univ_artists:
            return {"prompts": []}
        stmt = stmt.where(Prompt.artist_id.in_(univ_artists))

    stmt = stmt.order_by(Prompt.title).limit(max(1, min(limit, 500)))
    rows = (await db.execute(stmt)).all()

    prompts = []
    for prompt, artist in rows:
        prompts.append({
            "id":           str(prompt.id),
            "title":        prompt.title,
            "description":  prompt.description or "",
            "priceCredits": prompt.price_credits,
            "artistId":     str(artist.id),
            "artistSlug":   _derive_artist_slug(artist),
            "artistName":   artist.artist_name or "",
            "brandColor":   artist.brand_color or "",
            # Flag UI : indique si des paroles existent (sans les divulguer)
            "hasLyrics":    bool(prompt.lyrics),
        })
    return {"prompts": prompts}


@router.get("/prompts/{prompt_id}")
async def get_prompt(prompt_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Fiche publique d'un prompt.

    GATED — JAMAIS exposes sans preuve d'unlock :
      - prompt_text  (la recette Suno exacte)
      - lyrics       (les paroles complètes pour les morceaux vocaux)

    Le flag `hasLyrics` est sûr : il dit juste s'il existe des paroles
    sans les révéler. Permet à l'UI de poser un badge 🎤 "Avec paroles".
    """
    try:
        import uuid as _uuid
        pid = _uuid.UUID(prompt_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="ID prompt invalide")

    stmt = (
        select(Prompt, User)
        .join(User, User.id == Prompt.artist_id)
        .where(Prompt.id == pid)
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Prompt introuvable")

    prompt, artist = row
    if not prompt.is_published:
        raise HTTPException(status_code=404, detail="Prompt non publié")
    # C4 (séparation son/image) — cette fiche dessert une recette audio. Une
    # image a sa propre fiche via /images : on renvoie 404 pour un id image.
    if prompt.product_type == "image":
        raise HTTPException(status_code=404, detail="Prompt introuvable")
    # C4 « Oeuvre complete » — une fiche individuelle publique d'un produit
    # « ne ensemble » (bundle_exclusive) n'est pas servie : il n'existe
    # publiquement que via l'oeuvre. L'achat separe passe par /unlocks (non
    # filtre) et reste possible.
    if prompt.bundle_exclusive:
        raise HTTPException(status_code=404, detail="Prompt introuvable")

    # C4 « Oeuvre complete » — image liee (apercu public only : id/previewKey/prix).
    from app.services.links import linked_image_payload
    linked_image = await linked_image_payload(db, prompt)

    return {
        "prompt": {
            "id":           str(prompt.id),
            "title":        prompt.title,
            "description":  prompt.description or "",
            "priceCredits": prompt.price_credits,
            "artistId":     str(artist.id),
            "artistSlug":   _derive_artist_slug(artist),
            "artistName":   artist.artist_name or "",
            "brandColor":   artist.brand_color or "",
            "hasLyrics":    bool(prompt.lyrics),
            # C4 « Oeuvre complete » — image liee + flag.
            "linkedImage":      linked_image,
            "isOeuvreComplete": linked_image is not None,
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# Upload d'image vers R2 — port de l'ancien endpoint Flask /api/watt/upload-image
# Utilisé par dashboard.js (_uploadTrackCover, _uploadDashIdImage)
#                  artiste.js (avatar / cover depuis /u/<slug>)
# kind : 'avatar' | 'cover' | 'track-cover'
# ──────────────────────────────────────────────────────────────────────────────

_IMAGE_MIME: dict[str, str] = {
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "png":  "image/png",
    "webp": "image/webp",
    "gif":  "image/gif",
}
_IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5 Mo (aligné avec la validation client)


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    userId: str = Form(default=""),
    kind: str = Form(default="image"),
):
    """
    Upload d'image vers R2 (avatar, cover, track-cover).

    Remplace l'ancien endpoint Flask /api/watt/upload-image.
    Le frontend l'appelle via fetch() direct (pas apiFetch) car il
    envoie un FormData multipart — pas un JSON.

    Retourne : { "url": "/watt/images/<key>", "key": "<key>" }
    Le front stocke l'URL et la passe ensuite à PATCH /users/me ou
    PATCH /tracks/{id} selon le contexte.
    """
    from app.services.r2 import get_r2_client, is_configured

    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 storage not configured",
        )

    # ── Validation MIME ───────────────────────────────────────────────────────
    ct = (file.content_type or "").lower()
    if not ct.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le fichier doit être une image (image/*).",
        )

    # ── Lecture + validation taille ───────────────────────────────────────────
    data = await file.read()
    if len(data) > _IMAGE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image trop lourde ({len(data) // 1024} KB) — max 5 Mo.",
        )

    # ── Extension / MIME ──────────────────────────────────────────────────────
    filename = file.filename or "image.jpg"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    if ext not in _IMAGE_MIME:
        ext = "jpg"
    mime = _IMAGE_MIME[ext]

    # ── Clé R2 unique par kind ────────────────────────────────────────────────
    uid = _uuid_module.uuid4().hex
    safe_kind = re.sub(r"[^a-z0-9\-]", "", (kind or "image").lower()) or "image"
    r2_key = f"images/{safe_kind}/{uid}.{ext}"

    # ── Upload R2 (boto3 sync → executor) ────────────────────────────────────
    client = get_r2_client()
    bucket = settings.R2_BUCKET

    def _sync_put() -> None:
        client.put_object(
            Bucket=bucket,
            Key=r2_key,
            Body=data,
            ContentType=mime,
        )

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _sync_put)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload R2 échoué : {type(exc).__name__}: {str(exc)[:200]}",
        )

    return {"url": f"/watt/images/{r2_key}", "key": r2_key}


@router.post("/upload-playlist-cover")
async def upload_playlist_cover(
    file: UploadFile = File(...),
    userId: str = Form(default=""),
    name: str = Form(default="cover"),
):
    """
    Upload d'une vidéo de cover de playlist vers R2 (max 25 Mo).

    Port 1:1 de l'ancien endpoint Flask /api/watt/upload-playlist-cover.
    Le générique /watt/upload-image refuse les vidéos (image/* uniquement),
    d'où cette route dédiée. La durée (<= 3s) est validée côté front ;
    côté serveur on valide la taille (<= 25 Mo) et l'extension.

    Retourne : { "ok": true, "cover_url": "/watt/stream/<key>", "r2_key": "<key>" }
    Le front fait ensuite PATCH /playlists/{id} avec la cover_video_url.
    """
    from app.services.r2 import get_r2_client, is_configured

    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 storage not configured",
        )

    _VIDEO_MIME = {
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mov": "video/quicktime",
        "m4v": "video/x-m4v",
    }
    _VIDEO_MAX_BYTES = 25 * 1024 * 1024  # 25 Mo — identique au legacy

    # ── Extension ─────────────────────────────────────────────────────────────
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _VIDEO_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format non supporté ({ext or 'inconnu'}). Utilise mp4, webm ou mov.",
        )

    # ── Lecture + validation taille ───────────────────────────────────────────
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fichier vide",
        )
    if len(data) > _VIDEO_MAX_BYTES:
        mb = len(data) / 1024 / 1024
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Fichier trop lourd ({mb:.1f} Mo). Limite : 25 Mo.",
        )

    mime = _VIDEO_MIME[ext]

    # ── Clé R2 : PLAYLISTS/<userId>/<uuid>-<nom>.<ext> ────────────────────────
    uid = _uuid_module.uuid4().hex
    safe_uid = re.sub(r"[^a-zA-Z0-9_-]", "_", userId or "guest")[:60] or "guest"
    safe_name = re.sub(r"[^a-z0-9_-]", "_", (name or "cover").lower())[:40] or "cover"
    r2_key = f"PLAYLISTS/{safe_uid}/{uid}-{safe_name}.{ext}"

    # ── Upload R2 (boto3 sync → executor) ────────────────────────────────────
    client = get_r2_client()
    bucket = settings.R2_BUCKET

    def _sync_put() -> None:
        client.put_object(
            Bucket=bucket,
            Key=r2_key,
            Body=data,
            ContentType=mime,
        )

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _sync_put)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload R2 échoué : {type(exc).__name__}: {str(exc)[:200]}",
        )

    return {"ok": True, "cover_url": f"/watt/stream/{r2_key}", "r2_key": r2_key}


# ──────────────────────────────────────────────────────────────────────────────
# Proxy images R2 — même principe que /watt/stream/{key} pour l'audio.
# Évite CORS/CSP lorsque l'image est chargée via <img src="/watt/images/…">.
# Cache 24h côté browser (les images R2 sont immuables par UUID dans la clé).
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/images/{key:path}")
async def serve_image(key: str):
    """
    Proxy une image R2 par sa clé (ex. 'images/avatar/abc123.webp').

    ⚠️ Gate dur (fin binarité D2) : l'ORIGINAL d'une image vendable
    (préfixe `images/originals/`) n'est JAMAIS servi par ce proxy public.
    Il passe exclusivement par GET /images/{id}/download, qui vérifie la
    possession (UnlockedPrompt ou artiste) avant tout accès R2. Sans ce
    gate, cette route — enregistrée AVANT images.stream_image_preview dans
    main.py, donc prioritaire — servait n'importe quelle clé, y compris
    les originaux gatés. 404 indistinct (anti-énumération), miroir du gate
    de stream_image_preview (routers/images.py).
    """
    if key.startswith("images/originals/"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
        )

    from app.services.r2 import get_r2_client, is_configured

    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 storage not configured",
        )

    client = get_r2_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="R2 client unavailable",
        )

    try:
        obj = client.get_object(Bucket=settings.R2_BUCKET, Key=key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image non trouvée : {type(exc).__name__}",
        )

    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    mime = _IMAGE_MIME.get(ext, "image/jpeg")

    def _iter_chunks():
        try:
            for chunk in obj["Body"].iter_chunks(chunk_size=65536):
                yield chunk
        finally:
            try:
                obj["Body"].close()
            except Exception:
                pass

    headers: dict[str, str] = {"Cache-Control": "public, max-age=86400"}
    if obj.get("ContentLength"):
        headers["Content-Length"] = str(obj["ContentLength"])

    return StreamingResponse(_iter_chunks(), media_type=mime, headers=headers)


# ──────────────────────────────────────────────────────────────────────────────
# Upload audio — port des anciens endpoints Flask /api/watt/upload
# et /api/watt/upload-voice.
#
# /watt/upload       → upload d'un fichier audio de track (wav/mp3/m4a…)
#                       Retourne { url, key, mock }
# /watt/upload-voice → upload d'un sample voix (même pipeline R2, prefix différent)
#                       Retourne { sample_url, preview_url, url, key, mock }
#
# Les URLs retournées pointent vers /watt/stream/{key} (proxy same-origin).
# ──────────────────────────────────────────────────────────────────────────────

_AUDIO_MAX_BYTES = 50 * 1024 * 1024  # 50 Mo (tracks peuvent être lourdes)
_VOICE_MAX_BYTES = 20 * 1024 * 1024  # 20 Mo pour les samples voix
_AUDIO_EXTS = {"mp3", "wav", "m4a", "ogg", "flac", "aac", "webm"}
_AUDIO_MIME_UPLOAD = {
    "mp3":  "audio/mpeg",
    "wav":  "audio/wav",
    "m4a":  "audio/mp4",
    "ogg":  "audio/ogg",
    "flac": "audio/flac",
    "aac":  "audio/aac",
    "webm": "audio/webm",
}


def _slugify_name(name: str, max_len: int = 40) -> str:
    """Slugifie un nom pour l'utiliser dans une clé R2 (ASCII safe)."""
    s = unicodedata.normalize("NFD", name.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = _re_slug.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len] or "track"


async def _upload_audio_to_r2(
    file: UploadFile,
    name: str,
    r2_prefix: str,
    max_bytes: int,
) -> dict:
    """
    Logique commune d'upload audio vers R2.
    Retourne { url, key } ou lève HTTPException.
    """
    from app.services.r2 import get_r2_client, is_configured

    # Mode sans R2 (dev local) — renvoie un mock pour ne pas bloquer l'UI
    if not is_configured():
        return {"url": None, "key": f"{r2_prefix}/mock.wav", "mock": True}

    # Validation MIME
    ct = (file.content_type or "").lower()
    if not (ct.startswith("audio/") or ct in ("application/octet-stream", "video/webm")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le fichier doit être un fichier audio.",
        )

    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Fichier trop lourd ({len(data) // (1024*1024)} Mo) — max {max_bytes // (1024*1024)} Mo.",
        )

    filename = file.filename or "audio.wav"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
    if ext not in _AUDIO_EXTS:
        ext = "wav"
    mime = _AUDIO_MIME_UPLOAD.get(ext, "audio/wav")

    slug = _slugify_name(name)
    uid = _uuid_module.uuid4().hex[:12]
    r2_key = f"{r2_prefix}/{slug}-{uid}.{ext}"

    client = get_r2_client()
    bucket = settings.R2_BUCKET

    def _sync_put() -> None:
        client.put_object(Bucket=bucket, Key=r2_key, Body=data, ContentType=mime)

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _sync_put)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload R2 échoué : {type(exc).__name__}: {str(exc)[:200]}",
        )

    stream_url = f"/watt/stream/{r2_key}"
    return {"url": stream_url, "key": r2_key, "mock": False}


@router.post("/upload")
async def upload_audio(
    file: UploadFile = File(...),
    name: str = Form(default="track"),
    userId: str = Form(default=""),
):
    """
    Upload d'un fichier audio de track vers R2.
    Remplace Flask /api/watt/upload.
    Retourne { url, key, mock }.
    """
    result = await _upload_audio_to_r2(file, name, r2_prefix="tracks", max_bytes=_AUDIO_MAX_BYTES)
    return result


@router.post("/upload-voice")
async def upload_voice_sample(
    file: UploadFile = File(...),
    name: str = Form(default="voice"),
    userId: str = Form(default=""),
):
    """
    Upload d'un sample voix vers R2.
    Remplace Flask /api/watt/upload-voice.
    Retourne { sample_url, preview_url, url, key, mock }.
    preview_url = null (génération 30s non implémentée — à faire avec FFmpeg).
    """
    result = await _upload_audio_to_r2(file, name, r2_prefix="voices", max_bytes=_VOICE_MAX_BYTES)
    return {
        **result,
        "sample_url":  result["url"],
        "preview_url": None,  # TODO: générer clip 30s via FFmpeg
    }
