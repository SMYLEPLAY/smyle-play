"""
Service marché secondaire — revente de prompts avec royalties (2026-06-08).

Modèle validé Tom : TRANSFERT de propriété (le vendeur perd l'accès, comme une
carte) + split **30% artiste d'origine (royaltie) / 20% plateforme / 50%
vendeur**. La rareté/édition limitée reste réelle : revendre ne duplique pas,
ça transfère le seul exemplaire.

Flux :
  - list_prompt_for_resale   : le propriétaire fixe un prix de revente.
  - unlist_prompt_for_resale : retire de la vente.
  - buy_resale_atomic        : un acheteur paie → split 3 parts + transfert
                               current_owner_id + resale_price repasse à NULL.
  - get_resale_market        : listings publics du marché secondaire.

Atomicité : begin_nested + locks ordonnés (buyer, seller, artiste d'origine),
même pattern que unlock_*_atomic. Le caller commit.
"""
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.unlocked_prompt import UnlockedPrompt
from app.services.credits import _acquire_user_locks

# Split de revente (en %). La part vendeur = le reste (absorbe l'arrondi).
RESALE_ARTIST_PCT = 30
RESALE_PLATFORM_PCT = 20
# vendeur = 100 - 30 - 20 = 50%

# Bornes de prix de revente (cohérentes avec les prix de prompt).
RESALE_PRICE_MIN = 1
RESALE_PRICE_MAX = 100000


class ResaleError(ValueError):
    """Erreur métier de revente (→ HTTP 400/409 par le router)."""


class ResaleNotOwned(ResaleError):
    pass


class ResaleNotListed(ResaleError):
    pass


class ResaleSelfBuy(ResaleError):
    pass


class ResaleAlreadyOwned(ResaleError):
    pass


class ResaleLinkedAccounts(ResaleError):
    """Revente entre comptes liés par parrainage — bloquée (anti wash-trading)."""
    pass


class ResaleInsufficientCredits(ResaleError):
    def __init__(self, required: int, available: int):
        self.required = required
        self.available = available
        super().__init__("Insufficient credits for resale")


# -----------------------------------------------------------------------------
# Mise en vente / retrait
# -----------------------------------------------------------------------------

async def list_prompt_for_resale(
    db: AsyncSession, *, owner_id: UUID, prompt_id: UUID, price: int
) -> UnlockedPrompt:
    """Met en vente le prompt possédé par owner_id au prix donné. Caller commit."""
    if price < RESALE_PRICE_MIN or price > RESALE_PRICE_MAX:
        raise ResaleError(f"Prix de revente hors bornes ({RESALE_PRICE_MIN}-{RESALE_PRICE_MAX})")
    up = (await db.execute(
        select(UnlockedPrompt).where(
            UnlockedPrompt.current_owner_id == owner_id,
            UnlockedPrompt.prompt_id == prompt_id,
        )
    )).scalar_one_or_none()
    if up is None:
        raise ResaleNotOwned("Tu ne possèdes pas ce prompt")
    up.resale_price = int(price)
    await db.flush()
    return up


async def unlist_prompt_for_resale(
    db: AsyncSession, *, owner_id: UUID, prompt_id: UUID
) -> None:
    """Retire le prompt de la vente. Caller commit."""
    up = (await db.execute(
        select(UnlockedPrompt).where(
            UnlockedPrompt.current_owner_id == owner_id,
            UnlockedPrompt.prompt_id == prompt_id,
        )
    )).scalar_one_or_none()
    if up is None:
        raise ResaleNotOwned("Tu ne possèdes pas ce prompt")
    up.resale_price = None
    await db.flush()


# -----------------------------------------------------------------------------
# Achat d'une revente (le cœur)
# -----------------------------------------------------------------------------

async def buy_resale_atomic(
    db: AsyncSession, *, buyer_id: UUID, unlocked_prompt_id: UUID
) -> dict:
    """
    Achète un prompt en revente. Split 30/20/50, transfert de propriété.
    Le caller commit. Lève ResaleNotListed / ResaleSelfBuy / ResaleAlreadyOwned
    / ResaleInsufficientCredits.
    """
    # 1. Charge le listing (sans lock — routage).
    up = (await db.execute(
        select(UnlockedPrompt).where(UnlockedPrompt.id == unlocked_prompt_id)
    )).scalar_one_or_none()
    if up is None or up.resale_price is None:
        raise ResaleNotListed("Ce prompt n'est pas en vente")

    seller_id = up.current_owner_id
    original_artist_id = up.original_artist_id
    prompt_id = up.prompt_id
    price = int(up.resale_price)

    if buyer_id == seller_id:
        raise ResaleSelfBuy("Tu ne peux pas acheter ton propre prompt")

    # 1.b ANTI WASH-TRADING (H0.4) : interdit la revente entre comptes liés par
    # parrainage (parrain↔filleul, dans les deux sens). Empêche de blanchir/
    # farmer des royalties et de gonfler artificiellement la rareté en se
    # revendant entre comptes complices. Le self-buy est déjà bloqué au-dessus ;
    # ici on couvre les paires de comptes distincts mais liés.
    from app.models.referral import Referral
    linked = (await db.execute(
        select(Referral.id).where(
            or_(
                and_(Referral.referrer_id == buyer_id,
                     Referral.referred_id == seller_id),
                and_(Referral.referrer_id == seller_id,
                     Referral.referred_id == buyer_id),
            )
        ).limit(1)
    )).scalar_one_or_none()
    if linked is not None:
        raise ResaleLinkedAccounts(
            "Revente impossible entre comptes liés par parrainage."
        )

    # 2. L'acheteur ne possède-t-il pas déjà un exemplaire de ce prompt ?
    #    (la contrainte UNIQUE (current_owner_id, prompt_id) l'interdirait).
    already = (await db.execute(
        select(UnlockedPrompt.id).where(
            UnlockedPrompt.current_owner_id == buyer_id,
            UnlockedPrompt.prompt_id == prompt_id,
        )
    )).scalar_one_or_none()
    if already is not None:
        raise ResaleAlreadyOwned("Tu possèdes déjà ce prompt")

    async with db.begin_nested():
        # 3. Locks ordonnés (buyer, seller, artiste d'origine s'il existe).
        lock_ids = [buyer_id, seller_id]
        if original_artist_id is not None:
            lock_ids.append(original_artist_id)
        await _acquire_user_locks(db, lock_ids)

        # 4. Solde acheteur.
        buyer_row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": buyer_id},
        )).first()
        if buyer_row is None:
            raise ResaleError("Acheteur introuvable")
        balance = int(buyer_row.credits_balance)
        if balance < price:
            raise ResaleInsufficientCredits(required=price, available=balance)

        # 5. Split à 3. La part vendeur absorbe l'arrondi (reste).
        artist_royalty = (price * RESALE_ARTIST_PCT) // 100
        platform_fee = (price * RESALE_PLATFORM_PCT) // 100
        # Si l'artiste d'origine n'existe plus, sa royaltie va à la plateforme.
        if original_artist_id is None:
            platform_fee += artist_royalty
            artist_royalty = 0
        seller_cut = price - artist_royalty - platform_fee

        # 6. Transaction RESALE (artist_revenue + platform_fee <= credits_amount,
        #    la part vendeur n'y est pas stockée — cf. contrainte assouplie 0047).
        tx = Transaction(
            type=TransactionType.RESALE,
            status=TransactionStatus.PENDING,
            buyer_id=buyer_id,
            seller_id=seller_id,
            credits_amount=price,
            artist_revenue=artist_royalty,
            platform_fee=platform_fee,
            metadata_json={
                "source": "resale",
                "prompt_id": str(prompt_id),
                "original_artist_id": str(original_artist_id) if original_artist_id else None,
                "seller_cut": seller_cut,
            },
        )
        db.add(tx)
        await db.flush()

        # 7. Débite l'acheteur.
        await db.execute(
            text("UPDATE users SET credits_balance = credits_balance - :p WHERE id = :uid"),
            {"p": price, "uid": buyer_id},
        )
        # 8. Crédite le vendeur (balance + earned_total).
        await db.execute(
            text(
                "UPDATE users SET credits_balance = credits_balance + :c, "
                "credits_earned_total = credits_earned_total + :c WHERE id = :uid"
            ),
            {"c": seller_cut, "uid": seller_id},
        )
        # 9. Royaltie à l'artiste d'origine (si présent et > 0).
        if original_artist_id is not None and artist_royalty > 0:
            await db.execute(
                text(
                    "UPDATE users SET credits_balance = credits_balance + :r, "
                    "credits_earned_total = credits_earned_total + :r WHERE id = :uid"
                ),
                {"r": artist_royalty, "uid": original_artist_id},
            )

        # 10. TRANSFERT de propriété + retrait de la vente.
        up.current_owner_id = buyer_id
        up.resale_price = None
        try:
            await db.flush()
        except IntegrityError as e:
            raise ResaleAlreadyOwned("Conflit de propriété, réessaie") from e

        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    return {
        "prompt_id": prompt_id,
        "price_paid": price,
        "seller_cut": seller_cut,
        "artist_royalty": artist_royalty,
        "platform_fee": platform_fee,
        "new_balance": balance - price,
    }


# -----------------------------------------------------------------------------
# Marché (listings publics)
# -----------------------------------------------------------------------------

async def get_resale_market(
    db: AsyncSession,
    *,
    seller_id: UUID | None = None,
    prompt_id: UUID | None = None,
    limit: int = 50,
) -> list[dict]:
    """Listings du marché secondaire : prompts en vente + infos prompt +
    attribution du créateur d'origine (nom + slug → lien "créé par →").
    Si `seller_id` est fourni, on ne renvoie que les reventes de ce vendeur
    (section Revente d'un profil)."""
    from app.core.slug import derive_artist_slug
    from app.models.user import User

    q = (
        select(UnlockedPrompt, Prompt, User)
        .join(Prompt, Prompt.id == UnlockedPrompt.prompt_id)
        .outerjoin(User, User.id == UnlockedPrompt.original_artist_id)
        .where(
            UnlockedPrompt.resale_price.is_not(None),
            Prompt.is_deleted.is_(False),
        )
    )
    if seller_id is not None:
        q = q.where(UnlockedPrompt.current_owner_id == seller_id)
    if prompt_id is not None:
        q = q.where(UnlockedPrompt.prompt_id == prompt_id)
    q = q.order_by(UnlockedPrompt.resale_price.asc()).limit(limit)
    rows = (await db.execute(q)).all()
    return [
        {
            "unlocked_prompt_id": up.id,
            "prompt_id": up.prompt_id,
            "title": p.title,
            "resale_price": up.resale_price,
            "seller_id": up.current_owner_id,
            "original_artist_id": up.original_artist_id,
            "original_artist_name": (oa.artist_name if oa else None),
            "original_artist_slug": (derive_artist_slug(oa) if oa else None),
            "max_supply": p.max_supply,
            "edition_number": up.edition_number,
            # C4 ④ — nature du produit + aperçu pour rendre correctement une
            # revente d'IMAGE (le front affiche la vignette + label image au
            # lieu de la card audio). preview_r2_key est NON gaté (aperçu
            # public). On ne dévoile JAMAIS image_r2_key / la recette ici.
            "product_type": p.product_type,
            "preview_r2_key": (p.preview_r2_key if p.product_type == "image" else None),
        }
        for up, p, oa in rows
    ]


async def get_prompt_market(db: AsyncSession, prompt_id: UUID) -> dict | None:
    """Marché CANONIQUE d'un morceau (modèle StockX) : une seule fiche avec
    l'offre PRIMAIRE (créateur, si stock restant) + les offres SECONDAIRES
    (reventes). Évite les annonces dupliquées."""
    p = (await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id, Prompt.is_deleted.is_(False)
        )
    )).scalar_one_or_none()
    if p is None:
        return None
    sold = (await db.execute(
        select(func.count(UnlockedPrompt.id)).where(
            UnlockedPrompt.prompt_id == prompt_id
        )
    )).scalar() or 0
    # max_supply None = illimité → toujours dispo en primaire, pas de rareté.
    if p.max_supply is None:
        supply_left = None
        primary_available = True
    else:
        supply_left = max(0, int(p.max_supply) - int(sold))
        primary_available = supply_left > 0
    secondary = await get_resale_market(db, prompt_id=prompt_id)
    return {
        "prompt_id": str(prompt_id),
        "title": p.title,
        "primary_price": p.price_credits,
        "max_supply": p.max_supply,
        "sold": int(sold),
        "supply_left": supply_left,
        "primary_available": primary_available,
        "is_limited": p.max_supply is not None,
        "secondary": secondary,
        "secondary_from": (secondary[0]["resale_price"] if secondary else None),
    }
