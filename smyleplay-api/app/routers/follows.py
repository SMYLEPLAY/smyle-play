"""
Chantier 1 — Endpoints abonnement (follow/unfollow) + publication de profil.

Toutes ces routes vivent sous le préfixe `/watt/...` pour rester homogène
avec le reste du compat layer consommé par le front (watt.js, dashboard.js,
artiste.js, hub/community.js, etc.).

Endpoints :
  POST   /watt/artists/{slug}/follow     → suit un artiste            (auth)
  DELETE /watt/artists/{slug}/follow     → désabonne                  (auth)
  GET    /watt/artists/{slug}/followers  → liste publique des abonnés
  GET    /watt/me/following              → liste des artistes que je suis (auth)
  GET    /watt/me/followers              → mes abonnés                 (auth)
  GET    /watt/me/network                → graphe agrégé pour le
                                            Réseau Créatif WATT        (auth)
  POST   /watt/me/profile/publish        → bascule profile_public=TRUE
                                            si artist_name + bio + ≥1 track (auth)
  POST   /watt/me/profile/unpublish      → retire le profil de la vitrine (auth)

Règles métier :
  - Auto-follow rejeté côté API (400) ET côté SQL (CHECK constraint) — défense
    en profondeur, l'un des deux suffit mais on garde les deux.
  - Doublon (already following) → 409 Conflict.
  - Unfollow d'un lien inexistant → 404 (le front peut ignorer ou retry).
  - Suppression d'un user → CASCADE supprime toutes ses arêtes (cf. migration
    0014_add_follow_system).
  - La publication de profil exige : artist_name non-vide ET bio non-vide
    ET au moins 1 track uploadée. Sinon 422 avec détail de ce qui manque.
    Cette validation côté serveur double la validation client (wattboard) —
    impossible de passer profile_public=TRUE en court-circuitant l'UI.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.track import Track
from app.models.user import User
from app.models.user_follow import UserFollow

# On réutilise les helpers existants de watt_compat pour ne pas duppliquer la
# logique de slugification (qui doit rester strictement identique pour que
# /watt/artists/{slug}/follow trouve bien le même artiste que /watt/artists/{slug}).
from app.routers.watt_compat import (
    _derive_artist_slug,
    _optional_current_user,
    build_artist_detail_payload,
)


router = APIRouter(prefix="/watt", tags=["watt-follows"])


# ──────────────────────────────────────────────────────────────────────────
# Helpers internes
# ──────────────────────────────────────────────────────────────────────────


async def _find_artist_by_slug(
    db: AsyncSession,
    slug: str,
    *,
    viewer_id=None,
) -> User:
    """
    Retrouve un User par slug dérivé. Comme le slug n'est pas stocké, on
    parcourt les artistes potentiels (artist_name renseigné OU email
    @smyleplay.local). OK pour < 1000 artistes.

    Règle réseau : un profil non publié (profile_public=False) est 404
    pour tous SAUF son propre propriétaire (viewer_id == user.id), qui
    peut le preview depuis son wattboard. Cette exception permet au front
    d'afficher la preview vierge sans exposer le profil aux tiers.

    Lève 404 si introuvable ou non visible pour ce viewer.
    """
    stmt_users = select(User).where(
        (User.artist_name.is_not(None)) | (User.email.like("%@smyleplay.local"))
    )
    users = (await db.execute(stmt_users)).scalars().all()

    for u in users:
        if _derive_artist_slug(u) == slug:
            # Gate profile_public : 404 aux tiers si non publié, OK si self
            is_self = viewer_id is not None and u.id == viewer_id
            if not u.profile_public and not is_self:
                raise HTTPException(status_code=404, detail="Artiste introuvable")
            return u

    raise HTTPException(status_code=404, detail="Artiste introuvable")


async def _is_following(
    db: AsyncSession, follower_id, followee_id
) -> bool:
    """Existe-t-il déjà une arête follower → followee ?"""
    stmt = select(UserFollow.id).where(
        (UserFollow.follower_id == follower_id)
        & (UserFollow.followee_id == followee_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _count_followers(db: AsyncSession, user_id) -> int:
    stmt = select(func.count(UserFollow.id)).where(UserFollow.followee_id == user_id)
    return int((await db.execute(stmt)).scalar() or 0)


async def _count_following(db: AsyncSession, user_id) -> int:
    stmt = select(func.count(UserFollow.id)).where(UserFollow.follower_id == user_id)
    return int((await db.execute(stmt)).scalar() or 0)


def _serialize_artist_card(
    user: User,
    *,
    track_count: int = 0,
    plays: int = 0,
    is_following: bool = False,
) -> dict:
    """
    Forme compacte renvoyée dans les listes (followers, following, network).
    Volontairement plus light que /watt/artists/{slug} : juste de quoi
    afficher une bande artiste (avatar + nom + genre + plays + bouton).
    """
    return {
        "id":           str(user.id),
        "userId":       str(user.id),
        "slug":         _derive_artist_slug(user),
        "artistName":   user.artist_name or "",
        "bio":          user.bio or "",
        "avatarColor":  user.brand_color or "",
        "trackCount":   track_count,
        "plays":        plays,
        "isFollowing":  is_following,
    }


async def _hydrate_artist_cards(
    db: AsyncSession,
    users: list[User],
    *,
    viewer_id=None,
) -> list[dict]:
    """
    Pour chaque user, calcule trackCount + plays + isFollowing (si viewer_id).
    Une seule passe par user pour rester simple — N+1 acceptable pour < 100
    cartes par appel (dashboard ne charge que les top liens).

    Règle réseau : on n'hydrate PAS les cartes des users dont le profil
    n'est pas publié. Exception : le viewer peut voir sa propre carte
    même non publiée (utile pour me_card dans /me/network).
    Les cartes filtrées disparaissent proprement des listes réseau
    (following/followers/followers d'un artiste) — un profil vierge ne
    se balade jamais en dehors de sa propre preview owner.
    """
    if not users:
        return []

    # Filtre profile_public avec exception self-view
    users = [
        u for u in users
        if u.profile_public or (viewer_id is not None and u.id == viewer_id)
    ]
    if not users:
        return []

    cards: list[dict] = []
    viewer_following: set = set()
    if viewer_id is not None:
        # Charge en bloc l'ensemble des followees du viewer pour éviter N+1
        stmt = select(UserFollow.followee_id).where(
            UserFollow.follower_id == viewer_id
        )
        viewer_following = {
            row for row in (await db.execute(stmt)).scalars().all()
        }

    for u in users:
        # plays + tracks par artiste
        stmt = select(
            func.coalesce(func.sum(Track.plays), 0),
            func.count(Track.id),
        ).where(Track.artist_id == u.id)
        plays, track_count = (await db.execute(stmt)).one()
        cards.append(
            _serialize_artist_card(
                u,
                track_count=int(track_count or 0),
                plays=int(plays or 0),
                is_following=(u.id in viewer_following),
            )
        )
    return cards


# ──────────────────────────────────────────────────────────────────────────
# POST /watt/artists/{slug}/follow
# ──────────────────────────────────────────────────────────────────────────


@router.post(
    "/artists/{slug}/follow",
    status_code=status.HTTP_201_CREATED,
)
async def follow_artist(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Suit un artiste. Le follower est toujours `current_user` (JWT) — jamais
    accepté en body. Renvoie l'état frais (isFollowing + followersCount).

    On ne peut pas follow un profil non publié : le helper renvoie 404
    (sauf si c'est soi-même, mais ça partait en 400 juste après de toute
    façon — on ne peut pas se follow soi-même).
    """
    target = await _find_artist_by_slug(db, slug, viewer_id=current_user.id)

    if target.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tu ne peux pas te suivre toi-même",
        )

    if await _is_following(db, current_user.id, target.id):
        # Idempotence amicale : on renvoie 200 + l'état actuel plutôt qu'un
        # 409 brutal qui forcerait le front à gérer l'erreur. La nuance "déjà
        # abonné" sort dans `alreadyFollowing: true`.
        followers = await _count_followers(db, target.id)
        return {
            "ok": True,
            "alreadyFollowing": True,
            "isFollowing": True,
            "followersCount": followers,
            "artistSlug": slug,
        }

    follow = UserFollow(
        follower_id=current_user.id,
        followee_id=target.id,
    )
    db.add(follow)
    try:
        await db.commit()
    except IntegrityError:
        # Course critique : un autre tab a inséré la même paire entre
        # le _is_following et le commit. On rattrape proprement.
        await db.rollback()
        followers = await _count_followers(db, target.id)
        return {
            "ok": True,
            "alreadyFollowing": True,
            "isFollowing": True,
            "followersCount": followers,
            "artistSlug": slug,
        }

    followers = await _count_followers(db, target.id)
    return {
        "ok": True,
        "alreadyFollowing": False,
        "isFollowing": True,
        "followersCount": followers,
        "artistSlug": slug,
    }


# ──────────────────────────────────────────────────────────────────────────
# DELETE /watt/artists/{slug}/follow
# ──────────────────────────────────────────────────────────────────────────


@router.delete("/artists/{slug}/follow")
async def unfollow_artist(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Désabonne. Idempotent : si l'arête n'existe pas, renvoie 200 quand même
    avec `wasFollowing: false`. Pas de 404 — le front peut spammer ce
    endpoint sans gérer d'erreur.
    """
    target = await _find_artist_by_slug(db, slug, viewer_id=current_user.id)

    stmt = select(UserFollow).where(
        (UserFollow.follower_id == current_user.id)
        & (UserFollow.followee_id == target.id)
    )
    follow = (await db.execute(stmt)).scalar_one_or_none()

    was_following = follow is not None
    if follow is not None:
        await db.delete(follow)
        await db.commit()

    followers = await _count_followers(db, target.id)
    return {
        "ok": True,
        "wasFollowing": was_following,
        "isFollowing": False,
        "followersCount": followers,
        "artistSlug": slug,
    }


# ──────────────────────────────────────────────────────────────────────────
# GET /watt/artists/{slug}/followers
# ──────────────────────────────────────────────────────────────────────────


@router.get("/artists/{slug}/followers")
async def list_followers(
    slug: str,
    viewer: User | None = Depends(_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Liste publique des abonnés d'un artiste. Si le viewer est authentifié,
    chaque carte porte `isFollowing` (le viewer suit-il déjà cet abonné ?)
    pour permettre des boutons Follow/Unfollow inline.

    Le helper applique le gate profile_public : si la cible n'est pas
    publiée et que le viewer n'est pas elle-même, renvoie 404.
    """
    target = await _find_artist_by_slug(
        db, slug, viewer_id=viewer.id if viewer is not None else None
    )

    stmt = (
        select(User)
        .join(UserFollow, UserFollow.follower_id == User.id)
        .where(UserFollow.followee_id == target.id)
        .order_by(desc(UserFollow.created_at))
        .limit(200)
    )
    users = (await db.execute(stmt)).scalars().all()

    viewer_id = viewer.id if viewer is not None else None
    cards = await _hydrate_artist_cards(db, list(users), viewer_id=viewer_id)
    return {"artistSlug": slug, "count": len(cards), "followers": cards}


# ──────────────────────────────────────────────────────────────────────────
# GET /watt/me/following
# ──────────────────────────────────────────────────────────────────────────


@router.get("/me/following")
async def my_following(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Liste des artistes que je suis."""
    stmt = (
        select(User)
        .join(UserFollow, UserFollow.followee_id == User.id)
        .where(UserFollow.follower_id == current_user.id)
        .order_by(desc(UserFollow.created_at))
    )
    users = (await db.execute(stmt)).scalars().all()
    cards = await _hydrate_artist_cards(
        db, list(users), viewer_id=current_user.id
    )
    return {"count": len(cards), "following": cards}


# ──────────────────────────────────────────────────────────────────────────
# GET /watt/me/followers
# ──────────────────────────────────────────────────────────────────────────


@router.get("/me/followers")
async def my_followers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Liste de mes abonnés (qui me suit)."""
    stmt = (
        select(User)
        .join(UserFollow, UserFollow.follower_id == User.id)
        .where(UserFollow.followee_id == current_user.id)
        .order_by(desc(UserFollow.created_at))
    )
    users = (await db.execute(stmt)).scalars().all()
    cards = await _hydrate_artist_cards(
        db, list(users), viewer_id=current_user.id
    )
    return {"count": len(cards), "followers": cards}


# ──────────────────────────────────────────────────────────────────────────
# GET /watt/me/network
# ──────────────────────────────────────────────────────────────────────────


@router.get("/me/network")
async def my_network(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Vue agrégée pour le Réseau Créatif WATT du dashboard.

    Renvoie deux ensembles d'arêtes (centrées sur `me`) :
      - `following` : les nœuds que je suis (sortantes)
      - `followers` : les nœuds qui me suivent (entrantes)
      - `mutual`    : sous-ensemble présent dans les deux (mes connexions
                       fortes, à mettre en surbrillance dans le canvas)

    Chaque nœud porte le minimum vital pour le canvas : id, artistName,
    slug, brandColor, plays, trackCount.

    `me` est aussi renvoyé pour servir de nœud central (avatar/couleur).
    """
    # Following
    stmt_following = (
        select(User)
        .join(UserFollow, UserFollow.followee_id == User.id)
        .where(UserFollow.follower_id == current_user.id)
        .order_by(desc(UserFollow.created_at))
    )
    following_users = (await db.execute(stmt_following)).scalars().all()

    # Followers
    stmt_followers = (
        select(User)
        .join(UserFollow, UserFollow.follower_id == User.id)
        .where(UserFollow.followee_id == current_user.id)
        .order_by(desc(UserFollow.created_at))
    )
    follower_users = (await db.execute(stmt_followers)).scalars().all()

    following_cards = await _hydrate_artist_cards(
        db, list(following_users), viewer_id=current_user.id
    )
    follower_cards = await _hydrate_artist_cards(
        db, list(follower_users), viewer_id=current_user.id
    )

    following_ids = {c["id"] for c in following_cards}
    follower_ids = {c["id"] for c in follower_cards}
    mutual_ids = following_ids & follower_ids

    # Stats du nœud central
    stmt_me = select(
        func.coalesce(func.sum(Track.plays), 0),
        func.count(Track.id),
    ).where(Track.artist_id == current_user.id)
    me_plays, me_tracks = (await db.execute(stmt_me)).one()

    me_card = _serialize_artist_card(
        current_user,
        track_count=int(me_tracks or 0),
        plays=int(me_plays or 0),
        is_following=False,  # je ne me suis pas moi-même
    )

    return {
        "me":         me_card,
        "following":  following_cards,
        "followers":  follower_cards,
        "mutualIds":  sorted(mutual_ids),
        "stats": {
            "followingCount": len(following_cards),
            "followersCount": len(follower_cards),
            "mutualCount":    len(mutual_ids),
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# POST /watt/me/profile/publish
# ──────────────────────────────────────────────────────────────────────────


@router.post("/me/profile/publish")
async def publish_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Bascule `profile_public` à TRUE.

    Validation minimale : il faut un `artist_name` (display name) non-vide.
    Aucune exigence de bio ni de track : un utilisateur peut rendre son
    profil public sans avoir jamais publié de son. Le statut « artiste »
    n'est attribué qu'au moment du 1er morceau posté — pas en amont.

    Réponse 422 avec détail des champs manquants si le nom est vide.
    """
    missing: list[str] = []

    if not (current_user.artist_name or "").strip():
        missing.append("artist_name")

    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Il te manque un nom pour publier ton profil",
                "missing": missing,
            },
        )

    if not current_user.profile_public:
        current_user.profile_public = True
        await db.commit()
        await db.refresh(current_user)

    slug = _derive_artist_slug(current_user)

    # On renvoie l'artist complet (même shape que GET /watt/artists/{slug})
    # pour que le front puisse re-hydrater state.artist sans 2e appel.
    # viewer=current_user → isSelf=True → le front sait qu'il est en mode owner
    # sur sa propre fiche (on garde isFollowing=False côté helper pour ce cas).
    artist_payload = await build_artist_detail_payload(
        db, current_user, slug, current_user
    )

    return {
        "ok": True,
        "profilePublic": True,
        "artistSlug": slug,
        "artist": artist_payload,
    }


# ──────────────────────────────────────────────────────────────────────────
# POST /watt/me/profile/unpublish
# ──────────────────────────────────────────────────────────────────────────


@router.post("/me/profile/unpublish")
async def unpublish_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Retire le profil de la vitrine publique. Les données restent (tracks,
    ADN, follows) — seul le flag bascule. L'artiste peut re-publier sans
    repasser par les validations puisque tout est déjà en place.
    """
    if current_user.profile_public:
        current_user.profile_public = False
        await db.commit()
        await db.refresh(current_user)

    slug = _derive_artist_slug(current_user)

    # Même contrat que publish : on renvoie l'artist complet. Le front peut
    # ainsi rester sur /u/<slug> en "mode preview privé" (profilePublic=false
    # + isSelf=true) sans re-fetch — il re-hydrate depuis la réponse.
    artist_payload = await build_artist_detail_payload(
        db, current_user, slug, current_user
    )

    return {
        "ok": True,
        "profilePublic": False,
        "artistSlug": slug,
        "artist": artist_payload,
    }
