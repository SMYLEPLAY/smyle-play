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

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.database import get_db
from app.models.adn import Adn
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.models.user_follow import UserFollow


router = APIRouter(prefix="/watt", tags=["watt-compat"])


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
    "hit-mix": {
        "label": "HIT MIX",
        "folder": "HIT MIX",
        "r2_folder": "HIT MIX",
        "theme": "hit-mix",
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


def _track_to_flask_dict(track: Track, artist: Optional[User] = None) -> dict:
    """
    Convertit un Track FastAPI vers la forme attendue par le JS Flask.

    Flask track.to_dict() :
      {id, name, genre, streamUrl, r2Key, plays, uploadedAt, date}
    """
    public_id = track.legacy_id or str(track.id)
    uploaded_ms = int(track.created_at.timestamp() * 1000) if track.created_at else 0
    date_fr = track.created_at.strftime("%-d %b") if track.created_at else ""

    out = {
        "id":         public_id,
        "name":       track.title,
        "genre":      "",  # pas de genre par track dans le modèle FastAPI — vide pour compat
        "streamUrl":  track.audio_url or "",
        "r2Key":      track.r2_key or "",
        "plays":      track.plays or 0,
        "uploadedAt": uploaded_ms,
        "date":       date_fr,
    }
    if artist is not None:
        out["artistName"] = artist.artist_name or ""
        out["artistSlug"] = _derive_artist_slug(artist)
    return out


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
            "id":       t.legacy_id or str(t.id),
            "file":     (t.r2_key or "").split("/", 1)[-1] if t.r2_key else "",
            "name":     t.title,
            "duration": t.duration_seconds,
            "url":      t.audio_url or "",
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
            "created_at":     user.created_at.isoformat() if user.created_at else None,
        })
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
        .limit(50)
    )
    tracks = (await db.execute(stmt_tracks)).scalars().all()
    total_plays = sum(t.plays or 0 for t in tracks)

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
        (Adn.artist_id == target.id) & (Adn.is_published == True)  # noqa: E712
    )
    published_adn = (await db.execute(adn_stmt)).scalar_one_or_none()
    adn_payload: dict | None = None
    if published_adn is not None:
        teaser = (published_adn.description or "")[:240]
        adn_payload = {
            "id":              str(published_adn.id),
            "descriptionTeaser": teaser,
            "priceCredits":    published_adn.price_credits,
            "hasUsageGuide":   bool(published_adn.usage_guide),
            "hasExampleOutputs": bool(published_adn.example_outputs),
            "createdAt":       published_adn.created_at.isoformat() if published_adn.created_at else None,
        }

    # Prompts publiés de l'artiste (meta seulement — prompt_text/lyrics gated).
    # On ramène jusqu'à 50 items, suffisant pour tous les cas raisonnables
    # (au-delà, l'UI fera un "voir plus" via un endpoint paginé dédié).
    prompts_stmt = (
        select(Prompt)
        .where(
            (Prompt.artist_id == target.id)
            & (Prompt.is_published == True)  # noqa: E712
        )
        .order_by(desc(Prompt.created_at))
        .limit(50)
    )
    prompts_rows = (await db.execute(prompts_stmt)).scalars().all()
    prompts_payload = [
        {
            "id":           str(p.id),
            "title":        p.title,
            "description":  p.description or "",
            "priceCredits": p.price_credits,
            "hasLyrics":    bool(p.lyrics),
            # prompt_text omis volontairement — gated jusqu'à unlock
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
        "tracks":         [_track_to_flask_dict(t) for t in tracks],
        # Chantier "DNA unlock sur profil" — présents si l'artiste vend,
        # None / 0 / [] sinon. Le front cache la section correspondante
        # si vide. On ne renvoie JAMAIS prompt_text / lyrics en clair :
        # ces champs restent gated jusqu'à /unlocks/prompts/{id}.
        "adn":            adn_payload,
        "promptsForSale": prompts_for_sale,
        "prompts":        prompts_payload,
    }


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

    target: User | None = None
    for u in users:
        if _derive_artist_slug(u) == slug:
            target = u
            break

    if target is None:
        raise HTTPException(status_code=404, detail="Artiste introuvable")

    # Gatekeeping visibilité publique : seul soi-même peut voir son profil
    # tant qu'il n'est pas publié. Les autres reçoivent un 404 indistinguable
    # d'un slug inexistant (pas de fuite "ce compte existe mais est privé").
    is_self = viewer is not None and viewer.id == target.id
    if not target.profile_public and not is_self:
        raise HTTPException(status_code=404, detail="Artiste introuvable")

    payload = await build_artist_detail_payload(db, target, slug, viewer)
    return {"artist": payload}


@router.get("/tracks-recent")
async def tracks_recent(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Équivalent de `GET /api/tracks/recent`.
    Renvoie {'tracks': [...]} — les 12 derniers sons tous artistes confondus.
    """
    stmt = (
        select(Track, User)
        .join(User, User.id == Track.artist_id)
        .order_by(desc(Track.created_at))
        .limit(12)
    )
    rows = (await db.execute(stmt)).all()
    return {"tracks": [_track_to_flask_dict(t, a) for t, a in rows]}


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
    await db.commit()
    await db.refresh(track)
    return {"ok": True, "plays": int(track.plays or 0)}


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
        .where(Adn.is_published == True)  # noqa: E712
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

    target: User | None = None
    for u in users:
        if _derive_artist_slug(u) == slug:
            target = u
            break

    if target is None:
        raise HTTPException(status_code=404, detail="Artiste introuvable")

    # ADN
    adn_stmt = select(Adn).where(
        (Adn.artist_id == target.id) & (Adn.is_published == True)  # noqa: E712
    )
    adn = (await db.execute(adn_stmt)).scalar_one_or_none()
    if adn is None:
        raise HTTPException(status_code=404, detail="DNA Playlist non publiée")

    # Prompts publics de l'artiste
    prompts_stmt = (
        select(Prompt)
        .where(
            (Prompt.artist_id == target.id)
            & (Prompt.is_published == True)  # noqa: E712
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
        }
    }
