"""
Phase 9.4 — Service métier découverte (lecture pure, zéro mutation).

Trois groupes :
  - Public catalog : artistes, prompts, ADN publiés
  - Effective price : prix avec perk pour un user donné
  - Library : contenu possédé par un user

Aucune transaction, aucun lock, aucun side-effect. Le router peut commit
ou pas, ça ne change rien (uniquement des SELECT).

Filtre publié uniquement (is_published=True) systématique sur tous les
endpoints catalog. Indistinguable d'un 404 quand l'objet existe mais
n'est pas publié → anti-énumération.

Aggregat artist : un artiste apparaît dans le listing public ssi :
  - artist_name IS NOT NULL (proxy "profil prêt")
  - ET il a au moins 1 ADN OU 1 prompt publié
"""
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adn import Adn
from app.models.owned_adn import OwnedAdn
from app.models.owned_playlist_adn import OwnedPlaylistAdn
from app.models.playlist import Playlist
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.models.voice import Voice


# -----------------------------------------------------------------------------
# Helper interne : carte artiste (dict, sera mappé par Pydantic from_attributes)
# -----------------------------------------------------------------------------

def _artist_card(user: User) -> dict:
    """Retourne le dict artist card depuis une row User."""
    from app.core.slug import derive_artist_slug
    return {
        "id": user.id,
        "artist_name": user.artist_name,
        "slug": derive_artist_slug(user),
        "brand_color": user.brand_color,
        "avatar_url": user.avatar_url,
    }


# -----------------------------------------------------------------------------
# Artistes publics
# -----------------------------------------------------------------------------

def _has_published_content_subquery(user_id_col):
    """
    EXISTS clause : True si le user a au moins 1 ADN ou 1 prompt publié.
    Utilisée comme filtre WHERE et comme JOIN (pas le même cas selon les
    callers, donc on retourne juste l'EXISTS).
    """
    adn_exists = (
        select(Adn.id)
        .where(
            Adn.artist_id == user_id_col,
            Adn.is_published.is_(True),
            Adn.is_deleted.is_(False),
        )
        .exists()
    )
    prompt_exists = (
        select(Prompt.id)
        .where(
            Prompt.artist_id == user_id_col,
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
        )
        .exists()
    )
    return or_(adn_exists, prompt_exists)


async def list_public_artists(
    db: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[User], int]:
    """
    Liste les artistes "actifs" (profil explicitement publié + artist_name set
    + au moins 1 contenu publié).
    Tri : artist_name ASC pour stabilité (alphabétique → prévisible UX).

    Règle réseau (Chantier 1 bis) : un profil vierge ou non publié ne doit
    JAMAIS apparaître dans un listing public, même s'il a un artist_name et
    du contenu. L'activation passe par POST /watt/me/profile/publish.
    """
    base_filter = and_(
        User.artist_name.is_not(None),
        User.profile_public.is_(True),
        _has_published_content_subquery(User.id),
    )

    total = (await db.execute(
        select(func.count(User.id)).where(base_filter)
    )).scalar() or 0

    offset = (page - 1) * per_page
    items_q = (
        select(User)
        .where(base_filter)
        .order_by(User.artist_name.asc(), User.id.asc())
        .offset(offset)
        .limit(per_page)
    )
    items = list((await db.execute(items_q)).scalars().all())
    return items, int(total)


async def get_public_artist_profile(
    db: AsyncSession, artist_id: UUID
) -> dict | None:
    """
    Retourne un dict prêt pour ArtistPublicProfile, ou None si l'artiste
    n'a pas de contenu publié (404).

    Règle réseau : un profil doit être explicitement publié
    (profile_public=True) pour apparaître ici. Sinon None → 404 publique,
    indistinguable d'un artiste inexistant.
    """
    user = await db.get(User, artist_id)
    if user is None or user.artist_name is None or not user.profile_public:
        return None

    has_adn_q = select(
        exists().where(
            Adn.artist_id == artist_id,
            Adn.is_published.is_(True),
            Adn.is_deleted.is_(False),
        )
    )
    has_adn = bool((await db.execute(has_adn_q)).scalar())

    # C4 (séparation son/image) — "prompts_published_count" compte les
    # recettes audio publiées de l'artiste ; les images ne gonflent pas
    # ce compteur (elles ont leur propre surface).
    prompts_count_q = select(func.count(Prompt.id)).where(
        Prompt.artist_id == artist_id,
        Prompt.is_published.is_(True),
        Prompt.is_deleted.is_(False),
        Prompt.product_type != "image",
    )
    prompts_count = int((await db.execute(prompts_count_q)).scalar() or 0)

    if not has_adn and prompts_count == 0:
        return None  # Artiste sans contenu publié → invisible publiquement

    return {
        "id": user.id,
        "artist_name": user.artist_name,
        "bio": user.bio,
        "universe_description": user.universe_description,
        "brand_color": user.brand_color,
        "avatar_url": user.avatar_url,
        "has_adn": has_adn,
        "prompts_published_count": prompts_count,
    }


# -----------------------------------------------------------------------------
# Prompts publics
# -----------------------------------------------------------------------------

async def list_public_prompts(
    db: AsyncSession,
    *,
    artist_id: UUID | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """
    Liste les prompts publiés, optionnellement filtrés par artiste.
    Tri : created_at DESC (les plus récents en premier).

    Retourne des dicts {prompt fields + artist sub-dict} prêts pour
    PromptPublicCard, sans le champ prompt_text (gated).
    """
    # C4 (séparation son/image) — ce catalogue public alimente les surfaces de
    # recettes audio ; les images (product_type='image') ont leur propre
    # surface (/images) et ne doivent jamais y figurer.
    base_filter = [
        Prompt.is_published.is_(True),
        Prompt.is_deleted.is_(False),
        Prompt.product_type != "image",
    ]
    if artist_id is not None:
        base_filter.append(Prompt.artist_id == artist_id)

    total = (await db.execute(
        select(func.count(Prompt.id)).where(*base_filter)
    )).scalar() or 0

    offset = (page - 1) * per_page
    items_q = (
        select(Prompt, User)
        .join(User, User.id == Prompt.artist_id)
        .where(*base_filter)
        .order_by(Prompt.created_at.desc(), Prompt.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).all()
    items = [
        {
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "price_credits": p.price_credits,
            "created_at": p.created_at,
            "artist": _artist_card(u),
        }
        for p, u in rows
    ]
    return items, int(total)


async def get_public_prompt(
    db: AsyncSession, prompt_id: UUID
) -> dict | None:
    """Retourne le détail public d'un prompt (sans prompt_text), ou None."""
    q = (
        select(Prompt, User)
        .join(User, User.id == Prompt.artist_id)
        .where(
            Prompt.id == prompt_id,
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            # C4 (séparation son/image) — cette fiche dessert une recette audio.
            # Un id d'image ne doit pas y résoudre (les images ont leur propre
            # fiche via /images). On renvoie donc None (=> 404) pour un id image.
            Prompt.product_type != "image",
        )
    )
    row = (await db.execute(q)).first()
    if row is None:
        return None
    p, u = row
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "price_credits": p.price_credits,
        "created_at": p.created_at,
        "artist": _artist_card(u),
        # Métadonnées teaser (avant achat) — PAS le prompt_text ni les paroles.
        "platform": p.prompt_platform,
        "model_version": p.prompt_model_version,
        "has_lyrics": bool(p.lyrics),
    }


# -----------------------------------------------------------------------------
# ADN publics
# -----------------------------------------------------------------------------

async def list_public_adns(
    db: AsyncSession,
    *,
    artist_id: UUID | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """Liste les ADN publiés (sans example_outputs). Tri : created_at DESC."""
    base_filter = [Adn.is_published.is_(True), Adn.is_deleted.is_(False)]
    if artist_id is not None:
        base_filter.append(Adn.artist_id == artist_id)

    total = (await db.execute(
        select(func.count(Adn.id)).where(*base_filter)
    )).scalar() or 0

    offset = (page - 1) * per_page
    items_q = (
        select(Adn, User)
        .join(User, User.id == Adn.artist_id)
        .where(*base_filter)
        .order_by(Adn.created_at.desc(), Adn.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).all()
    items = [
        {
            "id": a.id,
            "description": a.description,
            "usage_guide": a.usage_guide,
            "price_credits": a.price_credits,
            "artist": _artist_card(u),
        }
        for a, u in rows
    ]
    return items, int(total)


async def get_public_adn(db: AsyncSession, adn_id: UUID) -> dict | None:
    q = (
        select(Adn, User)
        .join(User, User.id == Adn.artist_id)
        .where(Adn.id == adn_id, Adn.is_published.is_(True), Adn.is_deleted.is_(False))
    )
    row = (await db.execute(q)).first()
    if row is None:
        return None
    a, u = row
    return {
        "id": a.id,
        "description": a.description,
        "usage_guide": a.usage_guide,
        "price_credits": a.price_credits,
        "artist": _artist_card(u),
    }


# -----------------------------------------------------------------------------
# Library : prompts débloqués par le user
# -----------------------------------------------------------------------------

async def list_user_library_prompts(
    db: AsyncSession,
    *,
    user_id: UUID,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """
    Liste les prompts débloqués par `user_id`, tri unlocked_at DESC.

    On utilise current_owner_id (= user_id) pour la possession actuelle —
    important pour Phase 10 (transferts P2P : si un user a vendu un
    UnlockedPrompt, il ne doit plus l'avoir dans sa library).

    On JOIN sur prompts (CASCADE garanti existence) puis sur users via
    prompts.artist_id (et non original_artist_id) parce que prompts.artist_id
    est non-nullable, alors qu'original_artist_id peut être NULL si l'artiste
    a été supprimé (SET NULL).
    """
    base_filter = UnlockedPrompt.current_owner_id == user_id

    total = (await db.execute(
        select(func.count(UnlockedPrompt.id)).where(base_filter)
    )).scalar() or 0

    offset = (page - 1) * per_page

    # P1-B8 (2026-05-11) — Jointure track lié au prompt pour exposer l'audio.
    # Un prompt peut avoir 0, 1 ou plusieurs tracks (tracks.prompt_id, ondelete SET NULL).
    # On prend le PLUS RÉCENT via deux scalar_subquery corrélées (audio_url + cover_url).
    # NULL si aucun track lié → frontend masque le player.
    audio_url_subq = (
        select(Track.audio_url)
        .where(Track.prompt_id == Prompt.id, Track.is_deleted.is_(False))
        .order_by(Track.created_at.desc())
        .limit(1)
        .correlate(Prompt)
        .scalar_subquery()
    )
    cover_url_subq = (
        select(Track.cover_url)
        .where(Track.prompt_id == Prompt.id, Track.is_deleted.is_(False))
        .order_by(Track.created_at.desc())
        .limit(1)
        .correlate(Prompt)
        .scalar_subquery()
    )

    # Couleur du track lié — repère visuel cohérent avec la marketplace.
    track_color_subq = (
        select(Track.color)
        .where(Track.prompt_id == Prompt.id, Track.is_deleted.is_(False))
        .order_by(Track.created_at.desc())
        .limit(1)
        .correlate(Prompt)
        .scalar_subquery()
    )

    items_q = (
        select(
            UnlockedPrompt,
            Prompt,
            User,
            audio_url_subq.label("audio_url"),
            cover_url_subq.label("cover_url"),
            track_color_subq.label("track_color"),
        )
        .join(Prompt, Prompt.id == UnlockedPrompt.prompt_id)
        .join(User, User.id == Prompt.artist_id)
        .where(base_filter)
        .order_by(UnlockedPrompt.unlocked_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).all()
    items = [
        {
            "unlocked_id": up.id,
            "unlocked_at": up.unlocked_at,
            "prompt_id": p.id,
            "title": p.title,
            "description": p.description,
            "prompt_text": p.prompt_text,  # ← gated content, OK car possédé
            "lyrics": p.lyrics,  # ← gated content, null si instrumental
            "price_credits": p.price_credits,
            "created_at": p.created_at,
            "artist": _artist_card(u),
            # C4 ④ — champs IMAGE exposés UNIQUEMENT pour les images possédées
            # (item possédé → recette autorisée, comme prompt_text). audio_url /
            # cover_url restent NULL (pas de Track), c'est normal. Pour l'audio
            # ces clés sont None et le front continue d'afficher la card audio.
            "preview_r2_key": (p.preview_r2_key if p.product_type == "image" else None),
            "image_platform": (p.image_platform if p.product_type == "image" else None),
            "image_model_version": (p.image_model_version if p.product_type == "image" else None),
            "image_settings": (p.image_settings if p.product_type == "image" else None),
            "negative_prompt": (p.negative_prompt if p.product_type == "image" else None),
            # Sprint 1 PR3 — réglages génération (P1-F4) exposés ici
            # car library = possession. Weirdness + style_influence sont
            # GATED ailleurs (retirés du payload public watt_compat).
            "prompt_platform": p.prompt_platform,
            "prompt_model_version": p.prompt_model_version,
            "prompt_weirdness": p.prompt_weirdness,
            "prompt_style_influence": p.prompt_style_influence,
            "prompt_vocal_gender": p.prompt_vocal_gender,
            # P1-B8 — audio + cover du track lié (ou None si pas de track).
            "audio_url": audio_url,
            "cover_url": cover_url,
            # Couleur du track lié — repère visuel cohérent avec la marketplace.
            "track_color": track_color,
            # Marché secondaire — prix de revente courant (None = pas en vente).
            "resale_price": up.resale_price,
            # #X/N — numéro d'exemplaire possédé + taille de l'édition.
            # edition_number NULL = tirage illimité (pas de badge #X/N).
            "edition_number": up.edition_number,
            "max_supply": p.max_supply,
            # Beats : 'recipe' | 'beat'. Le front affiche un bouton Télécharger
            # sur les beats possédés (download gaté /beats/{id}/download).
            "product_type": p.product_type,
            "license_type": p.license_type,
        }
        for up, p, u, audio_url, cover_url, track_color in rows
    ]
    return items, int(total)


# -----------------------------------------------------------------------------
# Library : ADN possédés par le user
# -----------------------------------------------------------------------------

async def list_user_library_adns(
    db: AsyncSession,
    *,
    user_id: UUID,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """
    Liste les ADN possédés par `user_id`, tri owned_at DESC.

    Contrairement à UnlockedPrompt, OwnedAdn n'est pas transférable
    (Phase 9 et au-delà — l'ADN reste rattaché au user qui l'a acheté).
    """
    base_filter = OwnedAdn.user_id == user_id

    total = (await db.execute(
        select(func.count(OwnedAdn.user_id)).where(base_filter)
    )).scalar() or 0

    offset = (page - 1) * per_page
    items_q = (
        select(OwnedAdn, Adn, User)
        .join(Adn, Adn.id == OwnedAdn.adn_id)
        .join(User, User.id == Adn.artist_id)
        .where(base_filter)
        .order_by(OwnedAdn.owned_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).all()
    items = [
        {
            "adn_id": a.id,
            "owned_at": oa.owned_at,
            "description": a.description,
            "usage_guide": a.usage_guide,
            "example_outputs": a.example_outputs,  # ← gated, OK car possédé
            "price_credits": a.price_credits,
            "artist": _artist_card(u),
        }
        for oa, a, u in rows
    ]
    return items, int(total)


async def list_user_library_playlist_adns(
    db: AsyncSession,
    *,
    user_id: UUID,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """
    Liste les ADN Playlist achetés par user_id, tri owned_at DESC.
    seed_prompt est exposé ici car l'utilisateur a payé.
    """
    base_filter = OwnedPlaylistAdn.user_id == user_id

    total = (await db.execute(
        select(func.count(OwnedPlaylistAdn.playlist_id)).where(base_filter)
    )).scalar() or 0

    offset = (page - 1) * per_page
    items_q = (
        select(OwnedPlaylistAdn, Playlist, User)
        .join(Playlist, Playlist.id == OwnedPlaylistAdn.playlist_id)
        .join(User, User.id == Playlist.owner_id)
        .where(base_filter)
        .order_by(OwnedPlaylistAdn.owned_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).all()
    items = [
        {
            "playlist_id": str(pl.id),
            "owned_at": opa.owned_at,
            "title": pl.title,
            "color": pl.color,
            "seed_prompt": pl.seed_prompt,
            "adn_price": pl.adn_price,
            "owner": _artist_card(u),
        }
        for opa, pl, u in rows
    ]
    return items, int(total)


# -----------------------------------------------------------------------------
# Catalog public — Voix (is_published=True, is_deleted=False)
# -----------------------------------------------------------------------------

async def list_public_voices(
    db: AsyncSession,
    *,
    artist_id: UUID | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """
    Liste les voix publiées visible dans le catalogue public.
    `sample_url` (full) n'est PAS retourné — seulement `preview_url` (30s).
    """
    base_filter = [
        Voice.is_published.is_(True),
        Voice.is_deleted.is_(False),
    ]
    if artist_id is not None:
        base_filter.append(Voice.artist_id == artist_id)

    total = (await db.execute(
        select(func.count(Voice.id)).where(*base_filter)
    )).scalar() or 0

    offset = (page - 1) * per_page
    items_q = (
        select(Voice, User)
        .join(User, User.id == Voice.artist_id)
        .where(*base_filter)
        .order_by(Voice.created_at.desc(), Voice.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).all()
    items = [
        {
            "id": v.id,
            "name": v.name,
            "style": v.style,
            "genres": v.genres or [],
            "license": v.license,
            "price_credits": v.price_credits,
            "preview_url": v.preview_url,
            "artist": _artist_card(u),
        }
        for v, u in rows
    ]
    return items, int(total)


# -----------------------------------------------------------------------------
# Catalog public — Playlists ADN en vente (adn_for_sale=True, public)
# -----------------------------------------------------------------------------

async def list_public_playlists_adn(
    db: AsyncSession,
    *,
    artist_id: UUID | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """
    Liste les playlists publiques dont l'ADN est en vente.
    Filtres : visibility='public' ET adn_for_sale=True ET adn_price IS NOT NULL.
    """
    base_filter = [
        Playlist.visibility == "public",
        Playlist.adn_for_sale.is_(True),
        Playlist.adn_price.is_not(None),
    ]
    if artist_id is not None:
        base_filter.append(Playlist.owner_id == artist_id)

    total = (await db.execute(
        select(func.count(Playlist.id)).where(*base_filter)
    )).scalar() or 0

    offset = (page - 1) * per_page
    items_q = (
        select(Playlist, User)
        .join(User, User.id == Playlist.owner_id)
        .where(*base_filter)
        .order_by(Playlist.created_at.desc(), Playlist.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).all()
    items = [
        {
            "id": pl.id,
            "title": pl.title,
            "color": pl.color,
            "adn_price": pl.adn_price,
            "owner": _artist_card(u),
        }
        for pl, u in rows
    ]
    return items, int(total)
