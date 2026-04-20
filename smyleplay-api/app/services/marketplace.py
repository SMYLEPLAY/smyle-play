"""
Phase 9.2 — Service métier marketplace (catalogue artiste).

Règles encodées ici (et NON dans les routers) :
  - 1 ADN max par artiste : check applicatif PUIS rattrapage IntegrityError
    (course critique entre deux POST simultanés du même artiste)
  - Création prompt : impossible sans ADN existant (même non publié)
  - Lock contenu après 1ère vente (option b) :
      * Adn.description figé dès qu'un OwnedAdn existe pour cet ADN
      * Prompt.prompt_text figé dès qu'un UnlockedPrompt existe pour ce prompt
    Champs métadonnées (usage_guide, example_outputs, title, description,
    price_credits, is_published) restent toujours éditables.
  - last_updated_by_artist_at : MAJ uniquement quand un champ "contenu"
    (description/usage_guide/example_outputs) bouge sur l'ADN.
  - Aucune suppression : pas de DELETE, on désactive via is_published=False.
  - Toutes les exceptions métier remontent en ValueError → traduites
    en HTTP 400/409 par le router.

Pas de begin_nested ici : on ne touche pas aux balances, juste à des
tables "catalogue". Une transaction outer (commit/rollback géré par le
router) suffit.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adn import Adn
from app.models.owned_adn import OwnedAdn
from app.models.prompt import Prompt
from app.models.unlocked_prompt import UnlockedPrompt


# -----------------------------------------------------------------------------
# Exceptions métier (traduites en HTTP par le router)
# -----------------------------------------------------------------------------

class MarketplaceError(ValueError):
    """Base : erreur métier marketplace, → HTTP 400 par défaut."""


class AdnAlreadyExists(MarketplaceError):
    """L'artiste a déjà un ADN. → HTTP 409."""


class AdnNotFound(MarketplaceError):
    """L'artiste n'a pas encore d'ADN. → HTTP 404."""


class PromptNotFound(MarketplaceError):
    """Prompt introuvable ou non possédé par l'artiste. → HTTP 404."""


class ContentLockedAfterSale(MarketplaceError):
    """
    Tentative de modifier un champ "contenu" alors que l'objet a déjà été
    acheté par au moins un user. → HTTP 409.
    """


# -----------------------------------------------------------------------------
# ADN
# -----------------------------------------------------------------------------

async def create_adn(
    db: AsyncSession,
    *,
    artist_id: UUID,
    description: str,
    usage_guide: str | None,
    example_outputs: str | None,
    price_credits: int,
) -> Adn:
    """
    Crée l'ADN d'un artiste. 1 max par artiste.

    On fait un check applicatif pour avoir un message propre, MAIS on
    rattrape aussi IntegrityError au cas où deux requêtes concurrentes
    arrivent (la contrainte DB tranche).
    """
    existing = await db.execute(
        select(Adn.id).where(Adn.artist_id == artist_id)
    )
    if existing.first() is not None:
        raise AdnAlreadyExists("Artist already has an ADN")

    adn = Adn(
        artist_id=artist_id,
        description=description,
        usage_guide=usage_guide,
        example_outputs=example_outputs,
        price_credits=price_credits,
        is_published=False,
        last_updated_by_artist_at=func.now(),
    )
    db.add(adn)
    try:
        await db.flush()
    except IntegrityError as e:
        # Course critique : un POST concurrent a gagné. On annule proprement
        # côté caller (qui fera rollback) et on remonte un message clair.
        raise AdnAlreadyExists("Artist already has an ADN") from e
    return adn


async def get_adn_by_artist(
    db: AsyncSession, artist_id: UUID
) -> Adn | None:
    result = await db.execute(
        select(Adn).where(Adn.artist_id == artist_id)
    )
    return result.scalar_one_or_none()


async def user_owns_artist_adn(
    db: AsyncSession, *, user_id: UUID, artist_id: UUID
) -> bool:
    """
    True si `user_id` possède l'ADN de `artist_id` → éligible perk -30%
    sur les prompts de cet artiste.

    Lookup le plus chaud du domaine (appelé sur chaque unlock + chaque
    affichage prix marketplace) → on s'appuie sur les index existants
    (owned_adns.user_id + adns.artist_id), pas de jointure inutile.
    """
    result = await db.execute(
        select(OwnedAdn.adn_id)
        .join(Adn, Adn.id == OwnedAdn.adn_id)
        .where(OwnedAdn.user_id == user_id, Adn.artist_id == artist_id)
        .limit(1)
    )
    return result.first() is not None


async def _adn_has_been_sold(db: AsyncSession, adn_id: UUID) -> bool:
    """True si au moins un OwnedAdn existe pour cet ADN."""
    result = await db.execute(
        select(func.count(OwnedAdn.user_id)).where(OwnedAdn.adn_id == adn_id)
    )
    count = result.scalar() or 0
    return int(count) > 0


# Ensemble des champs ADN considérés comme "contenu" (lock après vente +
# trigger MAJ last_updated_by_artist_at). price_credits / is_published
# n'en font volontairement pas partie.
_ADN_CONTENT_FIELDS = ("description", "usage_guide", "example_outputs")


async def update_adn(
    db: AsyncSession,
    *,
    artist_id: UUID,
    payload: dict,
) -> Adn:
    """
    PATCH partiel sur l'ADN de l'artiste.

    Lock après vente (option b) : si l'ADN a déjà été acheté ET que
    `description` est dans le payload, on raise ContentLockedAfterSale.
    Le reste (usage_guide, example_outputs, price, publication) reste
    éditable même après vente.

    Raison : usage_guide et example_outputs sont du "tooling" pour aider
    l'acheteur, on autorise leur enrichissement. Seul le coeur sémantique
    (description) est figé.
    """
    adn = await get_adn_by_artist(db, artist_id)
    if adn is None:
        raise AdnNotFound("Artist has no ADN yet")

    if not payload:
        return adn  # PATCH vide = no-op explicite, on ne touche pas updated_at

    # Lock check : `description` uniquement (option b stricte)
    if "description" in payload and payload["description"] != adn.description:
        if await _adn_has_been_sold(db, adn.id):
            raise ContentLockedAfterSale(
                "ADN description is locked after the first sale "
                "(usage_guide / example_outputs / price remain editable)"
            )

    # Détection MAJ contenu pour last_updated_by_artist_at
    content_changed = False
    for field, value in payload.items():
        current = getattr(adn, field)
        if current != value:
            setattr(adn, field, value)
            if field in _ADN_CONTENT_FIELDS:
                content_changed = True

    if content_changed:
        adn.last_updated_by_artist_at = func.now()

    await db.flush()
    return adn


# -----------------------------------------------------------------------------
# Prompt
# -----------------------------------------------------------------------------

async def create_prompt(
    db: AsyncSession,
    *,
    artist_id: UUID,
    title: str,
    description: str | None,
    prompt_text: str,
    price_credits: int,
) -> Prompt:
    """
    Crée un prompt. Pré-requis : l'artiste a un ADN (même non publié).

    Pourquoi : un prompt est une "déclinaison" de l'ADN de l'artiste —
    sans ADN il n'y a pas d'identité créative à laquelle rattacher
    le prompt. Côté UX, c'est aussi un garde-fou contre les artistes qui
    publieraient en vrac sans avoir construit leur signature d'abord.
    """
    adn = await get_adn_by_artist(db, artist_id)
    if adn is None:
        raise AdnNotFound(
            "Artist must create an ADN before publishing prompts"
        )

    prompt = Prompt(
        artist_id=artist_id,
        title=title,
        description=description,
        prompt_text=prompt_text,
        price_credits=price_credits,
        is_published=False,
        # pack_eligible : default DB = True, on ne touche pas en Phase 9
    )
    db.add(prompt)
    await db.flush()
    return prompt


async def get_prompt_for_artist(
    db: AsyncSession, *, artist_id: UUID, prompt_id: UUID
) -> Prompt | None:
    """
    Récupère un prompt SI il appartient à l'artiste fourni.
    Renvoie None si introuvable OU si appartient à un autre artiste
    (404 indistingable, anti-énumération).
    """
    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.artist_id == artist_id,
        )
    )
    return result.scalar_one_or_none()


async def list_prompts_for_artist(
    db: AsyncSession,
    *,
    artist_id: UUID,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Prompt], int]:
    """Liste paginée des prompts de l'artiste (publiés + drafts)."""
    offset = (page - 1) * per_page

    count_q = select(func.count(Prompt.id)).where(
        Prompt.artist_id == artist_id
    )
    total = (await db.execute(count_q)).scalar() or 0

    items_q = (
        select(Prompt)
        .where(Prompt.artist_id == artist_id)
        .order_by(Prompt.created_at.desc(), Prompt.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    items = list((await db.execute(items_q)).scalars().all())
    return items, int(total)


async def _prompt_has_been_sold(db: AsyncSession, prompt_id: UUID) -> bool:
    """True si au moins un UnlockedPrompt existe pour ce prompt."""
    result = await db.execute(
        select(func.count(UnlockedPrompt.id)).where(
            UnlockedPrompt.prompt_id == prompt_id
        )
    )
    count = result.scalar() or 0
    return int(count) > 0


async def update_prompt(
    db: AsyncSession,
    *,
    artist_id: UUID,
    prompt_id: UUID,
    payload: dict,
) -> Prompt:
    """
    PATCH prompt.

    Lock après vente (option b stricte) : `prompt_text` figé dès qu'un
    UnlockedPrompt existe. Le reste (title / description / prix /
    publication) reste éditable.
    """
    prompt = await get_prompt_for_artist(
        db, artist_id=artist_id, prompt_id=prompt_id
    )
    if prompt is None:
        raise PromptNotFound("Prompt not found")

    if not payload:
        return prompt

    if "prompt_text" in payload and payload["prompt_text"] != prompt.prompt_text:
        if await _prompt_has_been_sold(db, prompt.id):
            raise ContentLockedAfterSale(
                "Prompt text is locked after the first sale "
                "(title / description / price remain editable)"
            )

    for field, value in payload.items():
        if getattr(prompt, field) != value:
            setattr(prompt, field, value)

    await db.flush()
    return prompt
