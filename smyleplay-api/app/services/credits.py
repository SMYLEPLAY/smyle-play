"""
Services crédits — Phase 8 (grant atomique) + Phase 9 (helpers marketplace).

Pattern d'atomicité (à respecter dans tous les services qui mutent les balances):

    async with db.begin_nested():
        # 1. Lock toutes les rows users impactées via _acquire_user_locks
        #    (ordre déterministe trié pour éviter deadlock)
        # 2. Lectures + checks métier
        # 3. INSERT Transaction (status=PENDING)
        # 4. UPDATE balances (additif via SQL pour éviter races)
        # 5. INSERT objets métier (UnlockedPrompt, OwnedAdn, etc.)
        # 6. UPDATE Transaction (status=COMPLETED, completed_at=now)
    # Le caller (endpoint) est responsable du `await db.commit()` final.
    # Si un raise survient dans le begin_nested, le savepoint rollback;
    # si le commit() outer échoue, tout est rollback côté Postgres.
"""
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import (
    Transaction,
    TransactionStatus,
    TransactionType,
)


# -----------------------------------------------------------------------------
# Packs (source of truth)
# -----------------------------------------------------------------------------

CREDIT_PACKS: list[dict] = [
    {"id": "pack_10", "credits": 10, "price_eur_cents": 800},
    {"id": "pack_50", "credits": 50, "price_eur_cents": 3500},
    {"id": "pack_200", "credits": 200, "price_eur_cents": 12000},
]


def get_pack_by_id(pack_id: str) -> dict | None:
    return next((p for p in CREDIT_PACKS if p["id"] == pack_id), None)


# -----------------------------------------------------------------------------
# Phase 9 — Helpers marketplace (arithmétique entière + locks ordonnés)
# -----------------------------------------------------------------------------

# Pourcentage de revenu artiste sur un unlock (primary market). Le reste va
# à la plateforme. Pour les reventes P2P (Phase 10), la fonction de split
# prendra des paramètres différents (30% artiste / 20% plateforme / 50%
# vendeur) — d'où le param `artist_pct`.
PRIMARY_MARKET_ARTIST_PCT = 80

# Coefficient du perk -30% pour les détenteurs d'ADN (sur le prix d'un
# prompt du même artiste). Multiplicatif entier : prix * 7 // 10.
PERK_NUMERATOR = 7
PERK_DENOMINATOR = 10


def compute_effective_price(base_price: int, has_perk: bool) -> int:
    """
    Calcule le prix effectif d'un prompt après application éventuelle du
    perk -30% (détenteur d'ADN du même artiste).

    Arithmétique strictement entière. Arrondi inférieur (favorise l'acheteur,
    prévisible). Plancher à 1 pour empêcher tout prix nul ou négatif même
    sur cas pathologique (base_price=1).

    Exemples:
        compute_effective_price(3, False) == 3
        compute_effective_price(3, True)  == 2   # 3*7//10 = 2
        compute_effective_price(5, True)  == 3   # 5*7//10 = 3
        compute_effective_price(7, True)  == 4   # 7*7//10 = 4
        compute_effective_price(10, True) == 7   # 10*7//10 = 7
        compute_effective_price(50, True) == 35  # 50*7//10 = 35
    """
    if base_price <= 0:
        raise ValueError("base_price must be positive")
    if has_perk:
        return max(1, (base_price * PERK_NUMERATOR) // PERK_DENOMINATOR)
    return base_price


def compute_split(
    amount: int,
    artist_pct: int = PRIMARY_MARKET_ARTIST_PCT,
) -> tuple[int, int]:
    """
    Calcule le split (artist_revenue, platform_fee) en arithmétique entière.

    Garantit: artist_revenue + platform_fee == amount (pas de crédit perdu).
    L'artiste reçoit exactement `(amount * artist_pct) // 100`, la plateforme
    récupère le reste (donc absorbe les pertes d'arrondi).

    Pour Phase 10 (P2P resale), on appellera avec un artist_pct différent
    (30% artiste, 20% plateforme), et on passera la part vendeur en
    `amount - artist_revenue - platform_fee` côté caller.

    Exemples (artist_pct=80, primary market):
        compute_split(3)   == (2, 1)    # 3*80//100=2, reste=1
        compute_split(5)   == (4, 1)    # 5*80//100=4, reste=1
        compute_split(7)   == (5, 2)    # 7*80//100=5, reste=2
        compute_split(10)  == (8, 2)    # 10*80//100=8, reste=2
        compute_split(50)  == (40, 10)  # 50*80//100=40, reste=10
    """
    if amount <= 0:
        raise ValueError("amount must be positive")
    if not (0 <= artist_pct <= 100):
        raise ValueError("artist_pct must be in [0, 100]")
    artist_revenue = (amount * artist_pct) // 100
    platform_fee = amount - artist_revenue
    return artist_revenue, platform_fee


async def _acquire_user_locks(
    db: AsyncSession,
    user_ids: list[UUID],
) -> None:
    """
    Lock les lignes users dans l'ordre UUID croissant pour éviter les
    deadlocks lors d'opérations multi-user (ex: unlock prompt = buyer +
    seller, ou pack opening = buyer + N sellers en Phase 10).

    DOIT être appelé en première chose dans tout savepoint mutant des
    balances de plusieurs users.

    Si un id apparaît deux fois (ex: artiste = acheteur — refusé en amont),
    on dédoublonne pour éviter un double-lock inutile.
    """
    if not user_ids:
        return
    sorted_unique = sorted(set(user_ids))
    for uid in sorted_unique:
        await db.execute(
            text("SELECT id FROM users WHERE id = :uid FOR UPDATE"),
            {"uid": uid},
        )


# -----------------------------------------------------------------------------
# Atomic credit operations
# -----------------------------------------------------------------------------

async def grant_credits_atomic(
    db: AsyncSession,
    user_id: UUID,
    amount: int,
    reason: str | None = None,
    *,
    tx_type: TransactionType = TransactionType.GRANT,
    metadata: dict | None = None,
) -> Transaction:
    """
    Ajoute des crédits au user de manière atomique.

    Pattern:
      1. Savepoint (rollback propre si quoi que ce soit échoue)
      2. SELECT ... FOR UPDATE sur la row users (empêche races)
      3. INSERT transaction (status=pending)
      4. UPDATE users.credits_balance
      5. UPDATE transaction (status=completed, completed_at=now)

    Le caller est responsable du `await db.commit()` final.

    Args:
      tx_type   : type de la transaction. Default = GRANT (admin/seed).
                  Les achievements passent BONUS pour distinguer dans le ledger.
      metadata  : dict additionnel mergé dans metadata_json. Si fourni avec
                  reason, les deux sont conservés ({"reason": ..., **metadata}).
    """
    if amount <= 0:
        raise ValueError("Amount must be positive")

    async with db.begin_nested():
        # 1. Lock la row user (empêche grant concurrent sur le même user)
        result = await db.execute(
            text(
                "SELECT id, credits_balance "
                "FROM users WHERE id = :uid "
                "FOR UPDATE"
            ),
            {"uid": user_id},
        )
        row = result.first()
        if not row:
            raise ValueError(f"User {user_id} not found")

        # 2. Construire metadata_json (reason + metadata fusionnés)
        meta: dict = {}
        if reason:
            meta["reason"] = reason
        if metadata:
            meta.update(metadata)

        # 3. Créer la transaction en PENDING
        tx = Transaction(
            type=tx_type,
            status=TransactionStatus.PENDING,
            buyer_id=user_id,  # bénéficiaire du grant
            credits_amount=amount,
            metadata_json=meta or None,
        )
        db.add(tx)
        await db.flush()

        # 3. Créditer le user (update atomique additif)
        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance + :amount "
                "WHERE id = :uid"
            ),
            {"amount": amount, "uid": user_id},
        )

        # 4. Finaliser la transaction
        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    return tx


# -----------------------------------------------------------------------------
# Query helpers
# -----------------------------------------------------------------------------

async def get_user_transactions(
    db: AsyncSession,
    user_id: UUID,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Transaction], int]:
    """Retourne l'historique paginé des transactions (buyer OR seller)."""
    offset = (page - 1) * per_page

    count_q = select(func.count(Transaction.id)).where(
        or_(
            Transaction.buyer_id == user_id,
            Transaction.seller_id == user_id,
        )
    )
    total = (await db.execute(count_q)).scalar() or 0

    items_q = (
        select(Transaction)
        .where(
            or_(
                Transaction.buyer_id == user_id,
                Transaction.seller_id == user_id,
            )
        )
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    items = list((await db.execute(items_q)).scalars().all())
    return items, int(total)
