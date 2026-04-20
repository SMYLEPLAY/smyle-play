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
from app.models.prompt import Prompt
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User


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
        .where(Adn.artist_id == user_id_col, Adn.is_published.is_(True))
        .exists()
    )
    prompt_exists = (
        select(Prompt.id)
        .where(Prompt.artist_id == user_id_col, Prompt.is_published.is_(True))
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
            Adn.artist_id == artist_id, Adn.is_published.is_(True)
        )
    )
    has_adn = bool((await db.execute(has_adn_q)).scalar())

    prompts_count_q = select(func.count(Prompt.id)).where(
        Prompt.artist_id == artist_id, Prompt.is_published.is_(True)
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
    base_filter = [Prompt.is_published.is_(True)]
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
        .where(Prompt.id == prompt_id, Prompt.is_published.is_(True))
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
    base_filter = [Adn.is_published.is_(True)]
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
        .where(Adn.id == adn_id, Adn.is_published.is_(True))
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
    items_q = (
        select(UnlockedPrompt, Prompt, User)
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
        }
        for up, p, u in rows
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
