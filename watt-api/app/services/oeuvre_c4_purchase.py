"""Achat d'une ŒUVRE entière (1 son + 1 image) — Lot 3, décision Tom 23/09.

Règles actées :
  - prix = prix du son + prix de l'image − 10 % ;
  - UN SEUL achat atomique des deux moitiés (un savepoint, verrous pris une
    fois : trésorerie puis acheteur/créateur) ;
  - la remise est répartie AU PRORATA sur chaque moitié, puis chaque moitié
    suit son circuit normal (`unlock_prompt_atomic`) : barème du vendeur
    20/12/5, taux Pionnier au plus favorable, commission vers la trésorerie,
    part vendeur, part payée en Smyles offerts non retirable ;
  - si l'acheteur possède déjà une moitié : il achète l'autre au PRIX PLEIN,
    sans remise ;
  - pas d'achat groupé si la moitié son est en « écoute libre » (pas de
    recette) ;
  - même créateur (garanti par la liaison C4).

Définition du « prix » d'une moitié : son prix effectif pour CET acheteur,
c'est-à-dire exactement ce qu'il paierait en l'achetant seule (perks ADN
−30 % / playlist −20 % compris). La remise de l'Œuvre s'applique par-dessus.
(Point signalé au coordinateur : cumul perks + remise.)

Idempotence : la propriété (UNIQUE propriétaire/prompt) est vérifiée SOUS les
verrous ; un double clic achète au plus une fois (le second voit les moitiés
possédées → 409, ou n'achète que ce qui manque).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.models.track import Track
from app.models.unlocked_prompt import UnlockedPrompt
from app.services.credits import _acquire_user_locks
from app.services.treasury import begin_commission
from app.services.unlocks import (
    AlreadyUnlocked,
    InsufficientCredits,
    PromptNotPurchasable,
    SelfPurchaseForbidden,
    UnlockError,
    _effective_prompt_price,
    unlock_prompt_atomic,
)

OEUVRE_DISCOUNT_PCT = 10


class OeuvreIntrouvable(PromptNotPurchasable):
    """Œuvre introuvable / non publiée. → 404."""


class OeuvreNotBundlable(UnlockError):
    """Achat groupé impossible (son en écoute libre, beat). → 409."""


def oeuvre_bundle_price(p_son: int, p_image: int) -> tuple[int, int, int]:
    """(prix de l'Œuvre, remise imputée au son, remise imputée à l'image).

    Prix = somme − 10 % arrondi à l'entier INFÉRIEUR (au profit de
    l'acheteur). Remise répartie au prorata des prix ; l'arrondi va à l'image.
    """
    total = p_son + p_image
    prix = total * (100 - OEUVRE_DISCOUNT_PCT) // 100
    remise = total - prix
    r_son = remise * p_son // total if total else 0
    return prix, r_son, remise - r_son


async def _resolve(db: AsyncSession, oeuvre_id: UUID) -> tuple[Prompt, Prompt | None]:
    """Image + recette sonore de l'Œuvre (publiées, non supprimées/retirées)."""
    img = (await db.execute(
        select(Prompt).where(
            Prompt.id == oeuvre_id,
            Prompt.product_type == "image",
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            Prompt.taken_down_at.is_(None),
        )
    )).scalar_one_or_none()
    if img is None:
        raise OeuvreIntrouvable("Œuvre introuvable.")
    recipe_id = img.linked_prompt_id
    if recipe_id is None and img.linked_track_id is not None:
        recipe_id = (await db.execute(
            select(Track.prompt_id).where(
                Track.id == img.linked_track_id, Track.is_deleted.is_(False)
            )
        )).scalar_one_or_none()
    recipe = None
    if recipe_id is not None:
        recipe = (await db.execute(
            select(Prompt).where(
                Prompt.id == recipe_id,
                Prompt.is_published.is_(True),
                Prompt.is_deleted.is_(False),
                Prompt.taken_down_at.is_(None),
                Prompt.product_type.in_(("recipe", "beat")),
            )
        )).scalar_one_or_none()
    return img, recipe


async def oeuvre_offer(db: AsyncSession, *, oeuvre_id: UUID, buyer_id: UUID | None) -> dict | None:
    """Ce que la page /o/{id} affiche pour le bouton « Acheter l'Œuvre ».

    Visiteur anonyme : prix public (somme des prix affichés − 10 %).
    Acheteur connecté : prix réel pour lui (perks compris), ou prix plein de
    la moitié manquante s'il en possède déjà une. None si pas d'achat groupé.
    """
    try:
        img, recipe = await _resolve(db, oeuvre_id)
    except OeuvreIntrouvable:
        return None
    if recipe is None or recipe.product_type == "beat":
        return None
    if buyer_id is None:
        prix, _, _ = oeuvre_bundle_price(recipe.price_credits, img.price_credits)
        return {"priceCredits": prix, "fullPriceCredits": recipe.price_credits + img.price_credits,
                "discountPct": OEUVRE_DISCOUNT_PCT, "mode": "oeuvre"}
    if buyer_id == img.artist_id:
        return None
    owned = set((await db.execute(
        select(UnlockedPrompt.prompt_id).where(
            UnlockedPrompt.current_owner_id == buyer_id,
            UnlockedPrompt.prompt_id.in_([img.id, recipe.id]),
        )
    )).scalars().all())
    if len(owned) == 2:
        return {"priceCredits": None, "mode": "possedee"}
    p_son, _, _ = await _effective_prompt_price(db, buyer_id=buyer_id, prompt_row=recipe)
    p_img, _, _ = await _effective_prompt_price(db, buyer_id=buyer_id, prompt_row=img)
    if owned:
        manquante = p_img if recipe.id in owned else p_son
        return {"priceCredits": manquante, "discountPct": 0, "mode": "moitie_manquante"}
    prix, _, _ = oeuvre_bundle_price(p_son, p_img)
    return {"priceCredits": prix, "fullPriceCredits": p_son + p_img,
            "discountPct": OEUVRE_DISCOUNT_PCT, "mode": "oeuvre"}


async def buy_oeuvre_atomic(db: AsyncSession, *, buyer_id: UUID, oeuvre_id: UUID) -> dict:
    """Achète l'Œuvre (ou la moitié manquante). Le caller commit.

    Lève : OeuvreIntrouvable (404), OeuvreNotBundlable (409), SelfPurchaseForbidden (400),
    AlreadyUnlocked (409 : les deux moitiés déjà possédées),
    InsufficientCredits (402), PromptNotPurchasable (stock épuisé, 404).
    """
    img, recipe = await _resolve(db, oeuvre_id)
    if recipe is None:
        raise OeuvreNotBundlable(
            "Le son de cette œuvre est en écoute libre : seule l'image s'achète."
        )
    if recipe.product_type == "beat":
        # Signalé : un beat (licence, exclusivité) n'entre pas dans l'achat
        # groupé tant que la règle n'est pas décidée.
        raise OeuvreNotBundlable("L'achat groupé n'est pas proposé pour un beat.")
    artist_id = img.artist_id
    if buyer_id == artist_id:
        raise SelfPurchaseForbidden("Tu ne peux pas acheter ta propre œuvre.")

    async with db.begin_nested():
        treasury_id = await begin_commission(db)
        await _acquire_user_locks(db, [buyer_id, artist_id])

        owned = set((await db.execute(
            select(UnlockedPrompt.prompt_id).where(
                UnlockedPrompt.current_owner_id == buyer_id,
                UnlockedPrompt.prompt_id.in_([img.id, recipe.id]),
            )
        )).scalars().all())
        if len(owned) == 2:
            raise AlreadyUnlocked("Tu possèdes déjà cette œuvre.")

        if owned:
            # Une moitié déjà possédée → l'autre au PRIX PLEIN, sans remise.
            manquante = img if recipe.id in owned else recipe
            r = await unlock_prompt_atomic(
                db, buyer_id=buyer_id, prompt_id=manquante.id,
                _oeuvre={"treasury_id": treasury_id, "discount": 0, "oeuvre_id": img.id},
            )
            achats = [r]
            mode = "moitie_manquante"
            remise = 0
        else:
            p_son, _, _ = await _effective_prompt_price(db, buyer_id=buyer_id, prompt_row=recipe)
            p_img, _, _ = await _effective_prompt_price(db, buyer_id=buyer_id, prompt_row=img)
            prix, r_son, r_img = oeuvre_bundle_price(p_son, p_img)
            balance = int((await db.execute(
                text("SELECT credits_balance FROM users WHERE id = :u"), {"u": buyer_id}
            )).scalar_one())
            if balance < prix:
                raise InsufficientCredits(required=prix, available=balance)
            achats = [
                await unlock_prompt_atomic(
                    db, buyer_id=buyer_id, prompt_id=recipe.id,
                    _oeuvre={"treasury_id": treasury_id, "discount": r_son, "oeuvre_id": img.id},
                ),
                await unlock_prompt_atomic(
                    db, buyer_id=buyer_id, prompt_id=img.id,
                    _oeuvre={"treasury_id": treasury_id, "discount": r_img, "oeuvre_id": img.id},
                ),
            ]
            mode = "oeuvre"
            remise = r_son + r_img

    # Trophées (hors savepoint), une fois pour l'achat.
    from app.models.achievement import AchievementAxis
    from app.services.achievements import check_and_grant_achievements

    await check_and_grant_achievements(db, user_id=buyer_id, axis=AchievementAxis.BUYER)
    await check_and_grant_achievements(db, user_id=artist_id, axis=AchievementAxis.ARTIST)
    await check_and_grant_achievements(db, user_id=artist_id, axis=AchievementAxis.IMAGE_SELLER)

    return {
        "mode": mode,
        "paid": sum(a.paid for a in achats),
        "remise": remise,
        "achats": [
            {"prompt_id": str(a.unlocked_prompt.prompt_id), "paid": a.paid,
             "transaction_id": str(a.transaction.id)}
            for a in achats
        ],
    }
