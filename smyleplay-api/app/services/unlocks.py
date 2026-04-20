"""
Phase 9.3 — Services unlock atomic (PROMPT + ADN).

PATTERN ATOMIQUE (à respecter scrupuleusement, cf. credits.py docstring) :

    async with db.begin_nested():
        1. await _acquire_user_locks(db, [buyer_id, seller_id])
           → tri UUID croissant pour éviter deadlock buyer↔seller
        2. SELECT balance buyer (déjà locké, on la relit fraîche)
        3. Re-vérification métier (balance suffisante, etc.)
        4. INSERT Transaction (status=PENDING, type=UNLOCK)
        5. UPDATE buyer.credits_balance -= paid (UPDATE additif via SQL)
        6. UPDATE seller.credits_balance += artist_revenue
                  + credits_earned_total += artist_revenue
        7. INSERT objet métier (UnlockedPrompt | OwnedAdn)
           → IntegrityError ici = double-unlock concurrent → traduit en 409
        8. UPDATE Transaction (status=COMPLETED, completed_at=now)
    # caller (router) fait `await db.commit()`

INVARIANTS GARANTIS :
  - paid == artist_revenue + platform_fee (zéro crédit perdu)
  - paid >= 1 (jamais de transaction nulle)
  - buyer.balance ne devient jamais < 0 (CHECK constraint DB en filet)
  - Si quoi que ce soit raise dans le begin_nested : savepoint rollback,
    aucune balance touchée, aucune transaction créée, aucune Promesse non tenue
  - Si commit() échoue côté Postgres : tout rollback (atomicité ACID)

REFUS MÉTIER (traduits en HTTP par le router) :
  - SelfPurchaseForbidden : un artiste ne peut pas acheter son propre contenu
  - PromptNotPurchasable / AdnNotPurchasable : objet introuvable ou non publié
  - InsufficientCredits : balance trop basse
  - AlreadyUnlocked / AlreadyOwned : double-unlock (rattrapé par UNIQUE DB)
"""
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adn import Adn
from app.models.owned_adn import OwnedAdn
from app.models.prompt import Prompt
from app.models.transaction import (
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.models.unlocked_prompt import UnlockedPrompt
from app.services.credits import (
    _acquire_user_locks,
    compute_effective_price,
    compute_split,
)
from app.services.marketplace import user_owns_artist_adn


# -----------------------------------------------------------------------------
# Exceptions métier (router les traduit en HTTP 400/402/404/409)
# -----------------------------------------------------------------------------

class UnlockError(ValueError):
    """Base : erreur métier unlock."""


class SelfPurchaseForbidden(UnlockError):
    """Acheteur == artiste. → HTTP 400."""


class PromptNotPurchasable(UnlockError):
    """Prompt introuvable ou non publié. → HTTP 404."""


class AdnNotPurchasable(UnlockError):
    """ADN introuvable ou non publié. → HTTP 404."""


class InsufficientCredits(UnlockError):
    """
    Balance acheteur trop basse pour le prix effectif. → HTTP 402.
    Le détail expose `required` et `available` pour permettre à l'UI
    de proposer un pack adapté.
    """

    def __init__(self, required: int, available: int):
        super().__init__(
            f"Insufficient credits: need {required}, have {available}"
        )
        self.required = required
        self.available = available


class AlreadyUnlocked(UnlockError):
    """Buyer possède déjà ce prompt. → HTTP 409."""


class AlreadyOwned(UnlockError):
    """Buyer possède déjà cet ADN. → HTTP 409."""


# -----------------------------------------------------------------------------
# Result dataclass-like (retour des services, mappé en réponse par le router)
# -----------------------------------------------------------------------------

class _UnlockPromptResult:
    """Tuple structuré renvoyé par unlock_prompt_atomic."""

    __slots__ = (
        "unlocked_prompt",
        "transaction",
        "perk_applied",
        "base_price",
        "paid",
    )

    def __init__(
        self,
        unlocked_prompt: UnlockedPrompt,
        transaction: Transaction,
        perk_applied: bool,
        base_price: int,
        paid: int,
    ):
        self.unlocked_prompt = unlocked_prompt
        self.transaction = transaction
        self.perk_applied = perk_applied
        self.base_price = base_price
        self.paid = paid


class _UnlockAdnResult:
    __slots__ = ("owned_adn", "transaction", "paid")

    def __init__(
        self,
        owned_adn: OwnedAdn,
        transaction: Transaction,
        paid: int,
    ):
        self.owned_adn = owned_adn
        self.transaction = transaction
        self.paid = paid


# -----------------------------------------------------------------------------
# UNLOCK PROMPT
# -----------------------------------------------------------------------------

async def unlock_prompt_atomic(
    db: AsyncSession,
    *,
    buyer_id: UUID,
    prompt_id: UUID,
) -> _UnlockPromptResult:
    """
    Achète un prompt pour le compte de `buyer_id`.

    Étapes (toutes dans le savepoint, le caller commit en sortie) :
      1. SELECT prompt + artist_id (sans lock — info de routage)
      2. Refus self-purchase (early)
      3. Acquire locks ordonnés sur (buyer, artist)
      4. Détecte le perk (-30%) via OwnedAdn lookup
      5. Calcule effective_price + split
      6. SELECT balance buyer (lockée), check suffisance
      7. INSERT Transaction PENDING
      8. UPDATE buyer balance -= paid (via UPDATE additif SQL)
      9. UPDATE seller balance += artist_revenue + earned_total += artist_revenue
     10. INSERT UnlockedPrompt → IntegrityError attrapée → AlreadyUnlocked
     11. UPDATE Transaction COMPLETED
    """
    # 1. Prompt cible (sans lock, juste pour récupérer artist_id et price)
    prompt_row = (await db.execute(
        select(Prompt).where(Prompt.id == prompt_id)
    )).scalar_one_or_none()
    if prompt_row is None or not prompt_row.is_published:
        raise PromptNotPurchasable("Prompt not found or not published")

    artist_id = prompt_row.artist_id
    base_price = prompt_row.price_credits

    # 2. Self-purchase = refus avant tout lock (économise du travail DB)
    if buyer_id == artist_id:
        raise SelfPurchaseForbidden(
            "An artist cannot unlock their own prompt"
        )

    async with db.begin_nested():
        # 3. Locks ordonnés (tri UUID dans _acquire_user_locks)
        await _acquire_user_locks(db, [buyer_id, artist_id])

        # 4. Perk = buyer possède l'ADN de cet artiste ?
        perk_applied = await user_owns_artist_adn(
            db, user_id=buyer_id, artist_id=artist_id
        )

        # 5. Pricing entier
        paid = compute_effective_price(base_price, perk_applied)
        artist_revenue, platform_fee = compute_split(paid)
        # Sanity check (devrait être impossible vu compute_split garanti) :
        assert artist_revenue + platform_fee == paid

        # 6. Lecture balance buyer (déjà lockée par _acquire_user_locks)
        buyer_row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": buyer_id},
        )).first()
        if buyer_row is None:
            raise PromptNotPurchasable("Buyer not found")
        buyer_balance = int(buyer_row.credits_balance)
        if buyer_balance < paid:
            raise InsufficientCredits(required=paid, available=buyer_balance)

        # 7. Transaction PENDING
        tx = Transaction(
            type=TransactionType.UNLOCK,
            status=TransactionStatus.PENDING,
            buyer_id=buyer_id,
            seller_id=artist_id,
            credits_amount=paid,
            artist_revenue=artist_revenue,
            platform_fee=platform_fee,
            metadata_json={
                "prompt_id": str(prompt_id),
                "artist_id": str(artist_id),
                "base_price": base_price,
                "perk_applied": perk_applied,
            },
        )
        db.add(tx)
        await db.flush()

        # 8. Debit buyer (UPDATE additif → la CHECK >= 0 fait office de filet
        #    si jamais le check applicatif au-dessus était bypassé)
        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance - :paid "
                "WHERE id = :uid"
            ),
            {"paid": paid, "uid": buyer_id},
        )

        # 9. Credit seller (balance + earned_total)
        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance + :rev, "
                "    credits_earned_total = credits_earned_total + :rev "
                "WHERE id = :uid"
            ),
            {"rev": artist_revenue, "uid": artist_id},
        )

        # 10. Crée l'unlock — UNIQUE (current_owner_id, prompt_id) dédoublonne
        unlocked = UnlockedPrompt(
            current_owner_id=buyer_id,
            prompt_id=prompt_id,
            original_artist_id=artist_id,
        )
        db.add(unlocked)
        try:
            await db.flush()
        except IntegrityError as e:
            # Course critique : un unlock concurrent du même buyer/prompt
            # a déjà été commit. On laisse le savepoint rollback (raise
            # remonte au caller qui rollback la transaction outer) et on
            # remonte un message clair.
            raise AlreadyUnlocked(
                "You already own this prompt"
            ) from e

        # 11. Finalise la transaction
        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    # 12. Phase 9.6 — Hook achievements (HORS du savepoint principal).
    # Appelé après le COMPLETED pour que les counts soient à jour.
    # Le service utilise ses propres begin_nested → un grant qui foire
    # n'invalide pas l'unlock (l'user a quand même son contenu).
    # Import local pour éviter un import cycle services.unlocks ↔ services.achievements
    from app.models.achievement import AchievementAxis
    from app.services.achievements import check_and_grant_achievements
    await check_and_grant_achievements(
        db, user_id=buyer_id, axis=AchievementAxis.BUYER
    )
    await check_and_grant_achievements(
        db, user_id=artist_id, axis=AchievementAxis.ARTIST
    )

    return _UnlockPromptResult(
        unlocked_prompt=unlocked,
        transaction=tx,
        perk_applied=perk_applied,
        base_price=base_price,
        paid=paid,
    )


# -----------------------------------------------------------------------------
# UNLOCK ADN
# -----------------------------------------------------------------------------

async def unlock_adn_atomic(
    db: AsyncSession,
    *,
    buyer_id: UUID,
    adn_id: UUID,
) -> _UnlockAdnResult:
    """
    Achète un ADN. Pas de perk applicable (le perk s'applique aux PROMPTS
    pour les détenteurs d'ADN, pas dans l'autre sens). Donc paid = price brut.

    Même squelette que unlock_prompt mais simplifié (pas de calcul perk).
    """
    adn_row = (await db.execute(
        select(Adn).where(Adn.id == adn_id)
    )).scalar_one_or_none()
    if adn_row is None or not adn_row.is_published:
        raise AdnNotPurchasable("ADN not found or not published")

    artist_id = adn_row.artist_id
    paid = adn_row.price_credits

    if buyer_id == artist_id:
        raise SelfPurchaseForbidden(
            "An artist cannot unlock their own ADN"
        )

    async with db.begin_nested():
        await _acquire_user_locks(db, [buyer_id, artist_id])

        artist_revenue, platform_fee = compute_split(paid)
        assert artist_revenue + platform_fee == paid

        buyer_row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": buyer_id},
        )).first()
        if buyer_row is None:
            raise AdnNotPurchasable("Buyer not found")
        buyer_balance = int(buyer_row.credits_balance)
        if buyer_balance < paid:
            raise InsufficientCredits(required=paid, available=buyer_balance)

        tx = Transaction(
            type=TransactionType.UNLOCK,
            status=TransactionStatus.PENDING,
            buyer_id=buyer_id,
            seller_id=artist_id,
            credits_amount=paid,
            artist_revenue=artist_revenue,
            platform_fee=platform_fee,
            metadata_json={
                "adn_id": str(adn_id),
                "artist_id": str(artist_id),
                # Pas de base_price/perk_applied : pas de perk sur ADN
            },
        )
        db.add(tx)
        await db.flush()

        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance - :paid "
                "WHERE id = :uid"
            ),
            {"paid": paid, "uid": buyer_id},
        )
        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance + :rev, "
                "    credits_earned_total = credits_earned_total + :rev "
                "WHERE id = :uid"
            ),
            {"rev": artist_revenue, "uid": artist_id},
        )

        owned = OwnedAdn(user_id=buyer_id, adn_id=adn_id)
        db.add(owned)
        try:
            await db.flush()
        except IntegrityError as e:
            raise AlreadyOwned("You already own this ADN") from e

        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    # Phase 9.6 — Hook achievements (HORS du savepoint principal).
    # FAN axis pour le buyer (collection ADN), ARTIST pour le seller (gains).
    from app.models.achievement import AchievementAxis
    from app.services.achievements import check_and_grant_achievements
    await check_and_grant_achievements(
        db, user_id=buyer_id, axis=AchievementAxis.FAN
    )
    await check_and_grant_achievements(
        db, user_id=artist_id, axis=AchievementAxis.ARTIST
    )

    return _UnlockAdnResult(owned_adn=owned, transaction=tx, paid=paid)
