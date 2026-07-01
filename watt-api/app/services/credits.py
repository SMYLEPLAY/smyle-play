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

# 2026-05-13 — Taux moyen crédit ↔ euro pour affichage ordre d'idée
# (utilisé côté UI pour montrer l'équivalent euro à côté des prix crédits).
# Valeur = pack_50 médian = 35€/50 = 0.70€/crédit.
EUR_PER_CREDIT: float = 0.70


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

# Coefficient du perk -30% pour les détenteurs d'ADN artiste (sur prompt).
PERK_NUMERATOR = 7
PERK_DENOMINATOR = 10

# Coefficient du perk -20% pour les détenteurs d'ADN Playlist (sur ADN Track).
PLAYLIST_PERK_NUMERATOR = 8
PLAYLIST_PERK_DENOMINATOR = 10

# Coefficient du perk « œuvre complète » (C5) : -15% sur le BUNDLE des deux
# ADN de collection (ADN Playlist + ADN Album) achetés ensemble.
OEUVRE_PACK_NUMERATOR = 85
OEUVRE_PACK_DENOMINATOR = 100


def compute_effective_price(
    base_price: int,
    has_perk: bool,
    has_playlist_perk: bool = False,
) -> int:
    """
    Prix effectif après application de la PYRAMIDE ADN en CASCADE (cumul
    multiplicatif, décision Tom 2026-06-08) :
      - has_perk          : détenteur de l'ADN profil de l'artiste → -30%
      - has_playlist_perk : détenteur de l'ADN d'une playlist contenant ce
                            son → -20%
    Les deux se CUMULENT (appliqués l'un après l'autre) : -30% puis -20%
    = -44% effectif. Arithmétique entière, arrondi inférieur (favorise
    l'acheteur), plancher à 1.

    Rétro-compatible : has_playlist_perk absent → comportement identique à
    l'ancienne signature (base, has_perk).

    Exemples:
        compute_effective_price(3, False)          == 3
        compute_effective_price(50, True)          == 35   # -30%
        compute_effective_price(50, False, True)   == 40   # -20%
        compute_effective_price(50, True, True)    == 28   # -30% puis -20%
        compute_effective_price(80, True, True)    == 44   # 80→56→44
    """
    if base_price <= 0:
        raise ValueError("base_price must be positive")
    price = base_price
    if has_perk:
        price = max(1, (price * PERK_NUMERATOR) // PERK_DENOMINATOR)
    if has_playlist_perk:
        price = max(1, (price * PLAYLIST_PERK_NUMERATOR) // PLAYLIST_PERK_DENOMINATOR)
    return price


def compute_oeuvre_pack_price(face_prices: list[int], has_artist_perk: bool) -> int:
    """
    Prix du pack « œuvre complète » (C5) — bundle des ADN de collection des
    deux faces (ADN Playlist + ADN Album) d'une même œuvre.

    Cascade des perks (⚠️ plafond, décision plan binarité) :
      1. Chaque face reçoit le perk ARTISTE -30% si `has_artist_perk` (détenteur
         de l'ADN profil/visuel de l'artiste) — via compute_effective_price
         (plancher 1 par face).
      2. Le pack applique -15% sur la SOMME des faces.

    Le perk -20% « ADN collection » n'est PAS appliqué ici par construction :
    l'acheteur ne possède pas encore les ADN de collection (il les acquiert via
    ce pack). C'est un perk AVAL, sur les achats À L'UNITÉ futurs (ADN Track /
    prompt image). La cascade -30% × -20% × -15% ne peut donc jamais frapper un
    même montant — le plafond est STRUCTUREL, pas seulement arithmétique.

    Plancher : >= nombre de faces (>= 1 Smyle par face), le pack ne tombe jamais
    à 0. Arithmétique entière, arrondi inférieur (favorise l'acheteur).

    Exemples (2 faces) :
        compute_oeuvre_pack_price([40, 35], False) == 63   # (40+35)*85//100
        compute_oeuvre_pack_price([40, 35], True)  == 44   # (28+24)=52 → *85//100
        compute_oeuvre_pack_price([1, 1], True)    == 2    # plancher = nb faces
    """
    if not face_prices:
        raise ValueError("face_prices must be non-empty")
    subtotal = sum(
        compute_effective_price(int(p), has_artist_perk) for p in face_prices
    )
    packed = (subtotal * OEUVRE_PACK_NUMERATOR) // OEUVRE_PACK_DENOMINATOR
    return max(len(face_prices), packed)


def compute_adn_price_with_playlist_perk(base_price: int, has_perk: bool) -> int:
    """
    Prix d'un ADN Track après perk -20% (détenteur de l'ADN Playlist qui
    contient ce track). Distinct du perk -30% sur les prompts.

    Exemples:
        compute_adn_price_with_playlist_perk(10, True) == 8   # 10*8//10
        compute_adn_price_with_playlist_perk(50, True) == 40  # 50*8//10
    """
    if base_price <= 0:
        raise ValueError("base_price must be positive")
    if has_perk:
        return max(1, (base_price * PLAYLIST_PERK_NUMERATOR) // PLAYLIST_PERK_DENOMINATOR)
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


async def artist_pct_for_user(db: AsyncSession, user_id: UUID) -> int:
    """Part artiste (%) selon le PALIER du vendeur (C6).

    Lit `users.tier` et renvoie 80 / 88 / 95 (commission 20 / 12 / 5).
    Tout palier inconnu / NULL (comptes pré-migration 0069) retombe sur
    Standard (80%) = comportement historique. À appeler DANS la section
    lockée d'un flux de vente, juste avant `compute_split`.
    """
    from app.services.tiers import artist_pct_for_tier  # import local: pas de cycle

    row = (await db.execute(
        text("SELECT tier FROM users WHERE id = :uid"),
        {"uid": user_id},
    )).first()
    tier = row.tier if row is not None else None
    return artist_pct_for_tier(tier)


# -----------------------------------------------------------------------------
# A1 — sous-soldes par catégorie de Smyle (achetés / gagnés / promo).
# Helpers centralisés : tout crédit/débit DOIT passer par eux (câblage en A1.3)
# pour que l'invariant `somme buckets == credits_balance` vive à UN seul endroit.
# À utiliser DANS un savepoint déjà locké (_acquire_user_locks) par le caller.
# -----------------------------------------------------------------------------

# Whitelist stricte nom logique → colonne SQL (anti-injection).
_BUCKET_COLUMNS = {
    "achetes": "smyles_achetes",
    "gagnes": "smyles_gagnes",
    "promo": "smyles_promo",
}

# Ordre de dépense par défaut : on consomme d'abord le promo (expirable, non
# encaissable), puis les achetés, puis les gagnés (encaissables, à préserver).
_SPEND_PRIORITY = ("promo", "achetes", "gagnes")

# A1.3 — routage type de transaction → bucket pour les CRÉDITS via
# grant_credits_atomic. credit_purchase = acheté ; bonus/grant (bienvenue,
# parrainage, streak, trophée, Saison 0) = promo ; earning = gagné ; refund =
# acheté (conservateur, non encaissable). Défaut prudent = acheté.
_TXTYPE_BUCKET = {
    TransactionType.CREDIT_PURCHASE: "achetes",
    TransactionType.BONUS: "promo",
    TransactionType.GRANT: "promo",
    TransactionType.EARNING: "gagnes",
    TransactionType.REFUND: "achetes",
}


async def credit_bucket(
    db: AsyncSession,
    user_id: UUID,
    amount: int,
    *,
    bucket: str,
) -> None:
    """Ajoute `amount` Smyles au bucket donné + au solde total (atomique en SQL).

    `bucket` ∈ {'achetes', 'gagnes', 'promo'}. Maintient l'invariant
    somme == credits_balance.
    """
    if amount <= 0:
        raise ValueError("amount must be positive")
    col = _BUCKET_COLUMNS.get(bucket)
    if col is None:
        raise ValueError(f"unknown bucket: {bucket!r}")
    await db.execute(
        text(
            f"UPDATE users SET {col} = {col} + :a, "  # noqa: S608 (col whitelisté)
            "credits_balance = credits_balance + :a WHERE id = :uid"
        ),
        {"a": amount, "uid": user_id},
    )


async def debit_with_priority(
    db: AsyncSession,
    user_id: UUID,
    amount: int,
) -> dict[str, int]:
    """Débite `amount` Smyles en consommant promo → achetés → gagnés.

    Renvoie la ventilation effectivement débitée par bucket. Lève ValueError si
    le solde total est insuffisant (le check métier reste de la responsabilité
    du caller ; ici garde-fou défensif). Maintient somme == credits_balance.
    """
    if amount <= 0:
        raise ValueError("amount must be positive")
    row = (await db.execute(
        text(
            "SELECT smyles_promo, smyles_achetes, smyles_gagnes "
            "FROM users WHERE id = :uid FOR UPDATE"
        ),
        {"uid": user_id},
    )).first()
    if row is None:
        raise ValueError("user not found")
    available = {
        "promo": int(row.smyles_promo),
        "achetes": int(row.smyles_achetes),
        "gagnes": int(row.smyles_gagnes),
    }
    if amount > sum(available.values()):
        raise ValueError("insufficient smyles for debit")

    taken = {"promo": 0, "achetes": 0, "gagnes": 0}
    remaining = amount
    for b in _SPEND_PRIORITY:
        if remaining <= 0:
            break
        t = min(remaining, available[b])
        taken[b] = t
        remaining -= t

    await db.execute(
        text(
            "UPDATE users SET "
            "smyles_promo = smyles_promo - :p, "
            "smyles_achetes = smyles_achetes - :a, "
            "smyles_gagnes = smyles_gagnes - :g, "
            "credits_balance = credits_balance - :tot WHERE id = :uid"
        ),
        {
            "p": taken["promo"],
            "a": taken["achetes"],
            "g": taken["gagnes"],
            "tot": amount,
            "uid": user_id,
        },
    )
    return taken


# -----------------------------------------------------------------------------
# A1.2 — vérification de cohérence (mode shadow). Lecture seule.
# Invariant cible : smyles_achetes + smyles_gagnes + smyles_promo == credits_balance.
# Tant que tous les chemins crédit/débit ne sont pas branchés (A1.3), des comptes
# peuvent être incohérents (ex: crédit non encore routé vers un bucket) — d'où le
# mode shadow : on MESURE l'écart sans s'appuyer sur les buckets. Le CHECK DB
# d'invariant ne sera posé qu'en A1.4, une fois ce compteur stabilisé à 0.
# -----------------------------------------------------------------------------

async def user_bucket_consistent(db: AsyncSession, user_id: UUID) -> bool:
    """True si, pour cet utilisateur, somme(buckets) == credits_balance."""
    row = (await db.execute(
        text(
            "SELECT (smyles_achetes + smyles_gagnes + smyles_promo = credits_balance) "
            "AS ok FROM users WHERE id = :uid"
        ),
        {"uid": user_id},
    )).first()
    return bool(row.ok) if row is not None else False


async def count_bucket_inconsistencies(db: AsyncSession) -> int:
    """Nombre d'utilisateurs où somme(buckets) != credits_balance (shadow A1.2).
    Doit tendre vers 0 quand tous les chemins crédit/débit passent par les helpers."""
    row = (await db.execute(
        text(
            "SELECT count(*) AS n FROM users "
            "WHERE smyles_achetes + smyles_gagnes + smyles_promo <> credits_balance"
        )
    )).first()
    return int(row.n)


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

        # 3. Créditer le user (update atomique additif) — A1.3 : on route vers
        # le bon bucket selon le type de transaction (credit_bucket met aussi à
        # jour credits_balance, donc somme(buckets) == credits_balance).
        await credit_bucket(
            db, user_id, amount, bucket=_TXTYPE_BUCKET.get(tx_type, "achetes")
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
