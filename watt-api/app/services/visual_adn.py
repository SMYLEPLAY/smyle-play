"""
Service métier ADN Visuel artiste (signature visuelle).

Calque STRICT du domaine ADN musical :
  - CRUD : mirror des fonctions ADN de marketplace.py
      (create_adn / get_adn_by_artist / update_adn / delete_adn)
  - Achat atomique : mirror de unlock_adn_atomic (services/unlocks.py)

Règles encodées ici (PAS dans le router) :
  - 1 ADN visuel max par artiste : check applicatif PUIS rattrapage
    IntegrityError (course critique).
  - Lock description après 1ère vente (option b) : VisualAdn.description
    figé dès qu'un OwnedVisualAdn existe. usage_guide / example_outputs /
    price / style / palette restent éditables.
  - last_updated_by_artist_at : MAJ uniquement quand un champ "contenu"
    (description / usage_guide / example_outputs) bouge.
  - Soft-delete : is_deleted=True (les acheteurs gardent leur accès).

Le perk -30% que CET ADN visuel débloque (sur les IMAGES de l'artiste) est
appliqué côté unlock_prompt_atomic (services/unlocks.py), pas ici.
"""
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.owned_visual_adn import OwnedVisualAdn
from app.models.transaction import (
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.models.visual_adn import VisualAdn


# -----------------------------------------------------------------------------
# Exceptions métier (traduites en HTTP par le router) — mirror marketplace.py
# -----------------------------------------------------------------------------

class VisualAdnError(ValueError):
    """Base : erreur métier ADN visuel → HTTP 400 par défaut."""


class VisualAdnAlreadyExists(VisualAdnError):
    """L'artiste a déjà un ADN visuel. → HTTP 409."""


class VisualAdnNotFound(VisualAdnError):
    """L'artiste n'a pas encore d'ADN visuel. → HTTP 404."""


class VisualAdnContentLocked(VisualAdnError):
    """description verrouillée après 1ère vente. → HTTP 409."""


# -----------------------------------------------------------------------------
# CRUD (mirror des fonctions ADN de marketplace.py)
# -----------------------------------------------------------------------------

async def create_visual_adn(
    db: AsyncSession,
    *,
    artist_id: UUID,
    description: str,
    usage_guide: str | None,
    example_outputs: str | None,
    price_credits: int,
    ai_reference: str | None = None,
    max_supply: int | None = None,
    style: str | None = None,
    palette: str | None = None,
    adn_reserve_credits: int | None = None,
) -> VisualAdn:
    """Crée l'ADN visuel d'un artiste. 1 max par artiste."""
    existing = await db.execute(
        select(VisualAdn.id).where(VisualAdn.artist_id == artist_id)
    )
    if existing.first() is not None:
        raise VisualAdnAlreadyExists("Artist already has a visual ADN")

    visual_adn = VisualAdn(
        artist_id=artist_id,
        description=description,
        usage_guide=usage_guide,
        example_outputs=example_outputs,
        price_credits=price_credits,
        ai_reference=ai_reference,
        max_supply=max_supply,
        style=style,
        palette=palette,
        adn_reserve_credits=adn_reserve_credits,
        is_published=False,
        last_updated_by_artist_at=func.now(),
    )
    db.add(visual_adn)
    try:
        await db.flush()
    except IntegrityError as e:
        raise VisualAdnAlreadyExists(
            "Artist already has a visual ADN"
        ) from e
    return visual_adn


async def get_visual_adn_by_artist(
    db: AsyncSession, artist_id: UUID
) -> VisualAdn | None:
    result = await db.execute(
        select(VisualAdn).where(
            VisualAdn.artist_id == artist_id,
            VisualAdn.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def user_owns_artist_visual_adn(
    db: AsyncSession, *, user_id: UUID, artist_id: UUID
) -> bool:
    """
    True si `user_id` possède l'ADN visuel de `artist_id` → éligible perk
    -30% sur les IMAGES (product_type='image') de cet artiste.

    Mirror de marketplace.user_owns_artist_adn (qui cible les prompts).
    """
    result = await db.execute(
        select(OwnedVisualAdn.visual_adn_id)
        .join(VisualAdn, VisualAdn.id == OwnedVisualAdn.visual_adn_id)
        .where(
            OwnedVisualAdn.user_id == user_id,
            VisualAdn.artist_id == artist_id,
        )
        .limit(1)
    )
    return result.first() is not None


async def _visual_adn_has_been_sold(
    db: AsyncSession, visual_adn_id: UUID
) -> bool:
    """True si au moins un OwnedVisualAdn existe pour cet ADN visuel."""
    result = await db.execute(
        select(func.count(OwnedVisualAdn.user_id)).where(
            OwnedVisualAdn.visual_adn_id == visual_adn_id
        )
    )
    return int(result.scalar() or 0) > 0


_VISUAL_ADN_CONTENT_FIELDS = ("description", "usage_guide", "example_outputs")


async def update_visual_adn(
    db: AsyncSession,
    *,
    artist_id: UUID,
    payload: dict,
) -> VisualAdn:
    """
    PATCH partiel sur l'ADN visuel de l'artiste.

    Lock après vente (option b) : `description` figé dès qu'un OwnedVisualAdn
    existe. Le reste (usage_guide, example_outputs, price, style, palette,
    publication) reste éditable.
    """
    visual_adn = await get_visual_adn_by_artist(db, artist_id)
    if visual_adn is None:
        raise VisualAdnNotFound("Artist has no visual ADN yet")

    if not payload:
        return visual_adn

    if (
        "description" in payload
        and payload["description"] != visual_adn.description
    ):
        if await _visual_adn_has_been_sold(db, visual_adn.id):
            raise VisualAdnContentLocked(
                "Visual ADN description is locked after the first sale "
                "(usage_guide / example_outputs / price / style / palette "
                "remain editable)"
            )

    content_changed = False
    for field, value in payload.items():
        if getattr(visual_adn, field) != value:
            setattr(visual_adn, field, value)
            if field in _VISUAL_ADN_CONTENT_FIELDS:
                content_changed = True

    if content_changed:
        visual_adn.last_updated_by_artist_at = func.now()

    await db.flush()
    return visual_adn


async def delete_visual_adn(db: AsyncSession, artist_id: UUID) -> None:
    """
    Soft-delete de l'ADN visuel de l'artiste.
    Les acheteurs (OwnedVisualAdn) conservent leur accès en library.
    """
    visual_adn = await get_visual_adn_by_artist(db, artist_id)
    if visual_adn is None:
        raise VisualAdnNotFound("Visual ADN introuvable ou déjà supprimé")
    visual_adn.is_deleted = True
    visual_adn.is_published = False
    await db.flush()


# -----------------------------------------------------------------------------
# Achat atomique — mirror de unlock_adn_atomic (services/unlocks.py)
# -----------------------------------------------------------------------------

class _UnlockVisualAdnResult:
    __slots__ = ("owned_visual_adn", "transaction", "paid")

    def __init__(self, owned_visual_adn, transaction, paid: int):
        self.owned_visual_adn = owned_visual_adn
        self.transaction = transaction
        self.paid = paid


async def unlock_visual_adn_atomic(
    db: AsyncSession,
    *,
    buyer_id: UUID,
    visual_adn_id: UUID,
) -> _UnlockVisualAdnResult:
    """
    Achète un ADN visuel. Calque STRICT de unlock_adn_atomic.

    Pas de perk applicable à l'achat de l'ADN lui-même. Une fois acheté,
    débloque le perk -30% sur toutes les IMAGES de cet artiste
    (appliqué dans unlock_prompt_atomic).

    Idempotent (UNIQUE PK), stock-out via max_supply, parrainage géré côté
    router (best-effort, comme l'ADN musical).
    """
    # Imports locaux : mirror du style de unlock_adn_atomic + évite tout
    # cycle d'import avec services.unlocks (exceptions partagées).
    from app.services.credits import (
        _acquire_user_locks,
        artist_pct_for_user,
        compute_split,
    )
    from app.services.unlocks import (
        AdnNotPurchasable,
        AlreadyOwned,
        InsufficientCredits,
        SelfPurchaseForbidden,
    )

    visual_adn_row = (await db.execute(
        select(VisualAdn).where(VisualAdn.id == visual_adn_id)
    )).scalar_one_or_none()
    if visual_adn_row is None or not visual_adn_row.is_published:
        raise AdnNotPurchasable("Visual ADN not found or not published")

    # Stock-out : édition limitée épuisée.
    if visual_adn_row.max_supply is not None:
        sold_count = (await db.execute(
            select(func.count(OwnedVisualAdn.visual_adn_id)).where(
                OwnedVisualAdn.visual_adn_id == visual_adn_id
            )
        )).scalar_one()
        if int(sold_count) >= int(visual_adn_row.max_supply):
            raise AdnNotPurchasable(
                f"Visual ADN sold out "
                f"({sold_count}/{visual_adn_row.max_supply})"
            )

    artist_id = visual_adn_row.artist_id
    paid = int(visual_adn_row.price_credits)

    if buyer_id == artist_id:
        raise SelfPurchaseForbidden(
            "An artist cannot unlock their own visual ADN"
        )

    async with db.begin_nested():
        await _acquire_user_locks(db, [buyer_id, artist_id])

        # K-07 (2026-09-04, tâche B-M8) : commission au PALIER du vendeur
        # (80/88/95), comme unlock_prompt_atomic. Avant, compute_split était
        # appelé sans palier → 20 % en dur sur ce flux, alors que la page
        # Offres promet 12 % / 5 %. Standard = 80 % = comportement historique.
        # Lu DANS la section lockée (le vendeur est déjà verrouillé).
        artist_pct = await artist_pct_for_user(db, artist_id)
        artist_revenue, platform_fee = compute_split(paid, artist_pct)
        assert artist_revenue + platform_fee == paid

        buyer_row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": buyer_id},
        )).first()
        if buyer_row is None:
            raise AdnNotPurchasable("Buyer not found")
        buyer_balance = int(buyer_row.credits_balance)
        if buyer_balance < paid:
            raise InsufficientCredits(
                required=paid, available=buyer_balance
            )

        tx = Transaction(
            type=TransactionType.UNLOCK,
            status=TransactionStatus.PENDING,
            buyer_id=buyer_id,
            seller_id=artist_id,
            credits_amount=paid,
            artist_revenue=artist_revenue,
            platform_fee=platform_fee,
            metadata_json={
                "visual_adn_id": str(visual_adn_id),
                "artist_id": str(artist_id),
                "base_price": paid,
            },
        )
        db.add(tx)
        await db.flush()

        await db.execute(
            text(
                "UPDATE users "
                "SET smyles_promo = GREATEST(0, smyles_promo - :paid), "
                "    smyles_achetes = GREATEST(0, smyles_achetes - GREATEST(0, :paid - smyles_promo)), "
                "    smyles_gagnes = GREATEST(0, smyles_gagnes - GREATEST(0, :paid - smyles_promo - smyles_achetes)), "
                "    credits_balance = credits_balance - :paid "
                "WHERE id = :uid"
            ),
            {"paid": paid, "uid": buyer_id},
        )
        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance + :rev, "
                "    smyles_gagnes = smyles_gagnes + :rev, "
                "    credits_earned_total = credits_earned_total + :rev "
                "WHERE id = :uid"
            ),
            {"rev": artist_revenue, "uid": artist_id},
        )

        owned = OwnedVisualAdn(
            user_id=buyer_id, visual_adn_id=visual_adn_id
        )
        db.add(owned)
        try:
            await db.flush()
        except IntegrityError as e:
            raise AlreadyOwned("You already own this visual ADN") from e

        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    # Hook achievements (HORS du savepoint principal) — mirror unlock_adn.
    from app.models.achievement import AchievementAxis
    from app.services.achievements import check_and_grant_achievements
    await check_and_grant_achievements(
        db, user_id=buyer_id, axis=AchievementAxis.FAN
    )
    await check_and_grant_achievements(
        db, user_id=artist_id, axis=AchievementAxis.ARTIST
    )

    return _UnlockVisualAdnResult(
        owned_visual_adn=owned, transaction=tx, paid=paid
    )
