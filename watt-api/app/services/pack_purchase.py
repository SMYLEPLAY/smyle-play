"""
Achat PACK (Phase 2 Beats) — déblocage groupé recette + beat en une seule
transaction atomique, au prix pack (track.pack_price_credits).

Réutilise le pattern atomique de unlock_prompt_atomic (locks ordonnés, débit
buyer / crédit artiste, mint UnlockedPrompt). Les deux produits appartiennent
à l'artiste du morceau. Mint les deux exemplaires (avec #X/N si édition
limitée) et retire un beat exclusif de la vente après l'achat.
"""
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.models.track import Track
from app.models.transaction import (
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.models.unlocked_prompt import UnlockedPrompt
from app.services.credits import _acquire_user_locks, compute_split
from app.services.unlocks import (
    AlreadyUnlocked,
    InsufficientCredits,
    SelfPurchaseForbidden,
    UnlockError,
)


class PackNotPurchasable(UnlockError):
    """Pas d'offre pack valide sur ce morceau, ou un produit indisponible."""


async def buy_pack_atomic(
    db: AsyncSession,
    *,
    buyer_id: UUID,
    track_id: UUID,
) -> dict:
    # 1. Morceau + offre pack (les 3 conditions : recette + beat + prix pack).
    track = (await db.execute(
        select(Track).where(
            Track.id == track_id,
            Track.is_deleted.is_(False),
        )
    )).scalar_one_or_none()
    if (
        track is None
        or track.prompt_id is None
        or track.beat_id is None
        or track.pack_price_credits is None
    ):
        raise PackNotPurchasable("Aucune offre pack sur ce morceau")

    # 2. Les deux produits vendables.
    products = (await db.execute(
        select(Prompt).where(Prompt.id.in_([track.prompt_id, track.beat_id]))
    )).scalars().all()
    by_id = {p.id: p for p in products}
    recipe = by_id.get(track.prompt_id)
    beat = by_id.get(track.beat_id)
    if recipe is None or beat is None:
        raise PackNotPurchasable("Un produit du pack est introuvable")
    if (
        recipe.is_deleted or beat.is_deleted
        or not recipe.is_published or not beat.is_published
    ):
        raise PackNotPurchasable("Un produit du pack n'est plus disponible")

    artist_id = track.artist_id
    price = int(track.pack_price_credits)
    if buyer_id == artist_id:
        raise SelfPurchaseForbidden("Un artiste ne peut pas acheter son propre pack")

    async with db.begin_nested():
        # Locks ordonnés (buyer + artiste) — sérialise les achats concurrents.
        await _acquire_user_locks(db, [buyer_id, artist_id])

        # Stock-out par produit (édition limitée épuisée).
        for p in (recipe, beat):
            if p.max_supply is not None:
                sold = (await db.execute(
                    select(func.count(UnlockedPrompt.id)).where(
                        UnlockedPrompt.prompt_id == p.id
                    )
                )).scalar_one()
                if int(sold) >= int(p.max_supply):
                    raise PackNotPurchasable("Un produit du pack est épuisé")

        # Balance buyer (lockée).
        buyer_row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": buyer_id},
        )).first()
        if buyer_row is None:
            raise PackNotPurchasable("Buyer not found")
        buyer_balance = int(buyer_row.credits_balance)
        if buyer_balance < price:
            raise InsufficientCredits(required=price, available=buyer_balance)

        artist_revenue, platform_fee = compute_split(price)

        tx = Transaction(
            type=TransactionType.UNLOCK,
            status=TransactionStatus.PENDING,
            buyer_id=buyer_id,
            seller_id=artist_id,
            credits_amount=price,
            artist_revenue=artist_revenue,
            platform_fee=platform_fee,
            metadata_json={
                "source": "pack",
                "track_id": str(track_id),
                "recipe_id": str(recipe.id),
                "beat_id": str(beat.id),
            },
        )
        db.add(tx)
        await db.flush()

        await db.execute(
            text(
                "UPDATE users SET smyles_promo = GREATEST(0, smyles_promo - :p), "
                "smyles_achetes = GREATEST(0, smyles_achetes - GREATEST(0, :p - smyles_promo)), "
                "smyles_gagnes = GREATEST(0, smyles_gagnes - GREATEST(0, :p - smyles_promo - smyles_achetes)), "
                "credits_balance = credits_balance - :p "
                "WHERE id = :uid"
            ),
            {"p": price, "uid": buyer_id},
        )
        await db.execute(
            text(
                "UPDATE users SET credits_balance = credits_balance + :r, "
                "smyles_gagnes = smyles_gagnes + :r, "
                "credits_earned_total = credits_earned_total + :r WHERE id = :uid"
            ),
            {"r": artist_revenue, "uid": artist_id},
        )

        # Mint les DEUX exemplaires (avec #X/N si édition limitée).
        for p in (recipe, beat):
            edition_number = None
            if p.max_supply is not None:
                minted = (await db.execute(
                    select(func.count(UnlockedPrompt.id)).where(
                        UnlockedPrompt.prompt_id == p.id
                    )
                )).scalar_one()
                edition_number = int(minted) + 1
            unlocked = UnlockedPrompt(
                current_owner_id=buyer_id,
                prompt_id=p.id,
                original_artist_id=artist_id,
                edition_number=edition_number,
            )
            db.add(unlocked)
            try:
                await db.flush()
            except IntegrityError as e:
                raise AlreadyUnlocked(
                    "Tu possèdes déjà un élément de ce pack"
                ) from e
            # Beat exclusif → retiré de la vente après l'achat.
            if (
                getattr(p, "product_type", "recipe") == "beat"
                and getattr(p, "license_type", None) == "exclusive"
            ):
                p.is_published = False
                await db.flush()

        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    # Hook achievements (hors savepoint, best-effort — ne casse pas l'achat).
    try:
        from app.models.achievement import AchievementAxis
        from app.services.achievements import check_and_grant_achievements
        await check_and_grant_achievements(
            db, user_id=buyer_id, axis=AchievementAxis.BUYER
        )
    except Exception:
        pass

    nb = (await db.execute(
        text("SELECT credits_balance FROM users WHERE id = :uid"),
        {"uid": buyer_id},
    )).first()
    return {
        "price_paid": price,
        "recipe_id": recipe.id,
        "beat_id": beat.id,
        "new_balance": int(nb.credits_balance) if nb else None,
    }
