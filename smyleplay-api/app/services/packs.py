"""
Service packs aléatoires — "mystery pack" (mécanique 3).

Le sink de la boucle d'expérience client : l'utilisateur dépense un prix fixe
de Smyles pour tirer UN prompt au hasard parmi le pool éligible. Rend les
Smyles désirables (gagnés via parrainage + streak) et fait circuler la valeur
vers les artistes.

Économie :
  - Prix FIXE de 8 Smyles par tirage (≈5,6 €), volontairement modéré (cf.
    [[project_engagement_loop_economy]]). À affiner avec le prix moyen réel.
  - Les 8 Smyles ne sont PAS brûlés : ils sont transférés à l'artiste du
    prompt tiré (split 80/20 comme un unlock normal) → la valeur circule,
    les créateurs sont récompensés, la plateforme prend sa part.

Réutilise toute la machinerie existante (UnlockedPrompt, Transaction type
UNLOCK avec metadata source=mystery_pack, compute_split, locks ordonnés).
Aucune nouvelle table : pas de migration.

Le pool exclut : les prompts non publiés / supprimés / non pack_eligible,
les prompts de l'acheteur lui-même, et ceux qu'il possède déjà. Si le pool
est vide → erreur claire (rien débité).
"""
import random
from uuid import UUID

from sqlalchemy import and_, exists, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.unlocked_prompt import UnlockedPrompt
from app.services.credits import _acquire_user_locks, compute_split

# Prix fixe d'un tirage (Smyles). Modéré au lancement, à affiner avec les
# données réelles (prix moyen des prompts pack_eligible).
MYSTERY_PACK_PRICE = 8

# Raretés (mécanique 3) — classées selon le PRIX du prompt, tirage PONDÉRÉ.
# L'upside du gacha : on peut décrocher un son cher à prix cassé, mais c'est
# rare (poids faible) → la valeur moyenne d'un tirage reste sous le prix du
# pack, donc la plateforme ne saigne jamais et pas d'arbitrage de revente.
# "max" inclusif ; le dernier tier capte tout le haut.
RARITY_TIERS = [
    {"name": "commun",     "min": 0,  "max": 5,            "weight": 70},
    {"name": "rare",       "min": 6,  "max": 15,           "weight": 22},
    {"name": "epique",     "min": 16, "max": 40,           "weight": 6},
    {"name": "legendaire", "min": 41, "max": 10**9,        "weight": 2},
]


def rarity_for_price(price: int) -> str:
    """Rareté d'un prompt d'après son prix (Smyles)."""
    for tier in RARITY_TIERS:
        if tier["min"] <= price <= tier["max"]:
            return tier["name"]
    return "commun"


def _roll_tier() -> dict:
    """Tire un tier au hasard, pondéré par les poids."""
    total = sum(t["weight"] for t in RARITY_TIERS)
    r = random.random() * total
    acc = 0
    for tier in RARITY_TIERS:
        acc += tier["weight"]
        if r <= acc:
            return tier
    return RARITY_TIERS[0]


class PackError(ValueError):
    """Erreur métier d'ouverture de pack (pool vide, solde insuffisant…)."""


class PackPoolEmpty(PackError):
    pass


class PackInsufficientCredits(PackError):
    def __init__(self, required: int, available: int):
        self.required = required
        self.available = available
        super().__init__("Insufficient credits for pack")


def _eligible_pool_query(buyer_id: UUID):
    """Sous-requête : prompts tirables pour ce buyer."""
    owned = (
        select(UnlockedPrompt.id)
        .where(
            UnlockedPrompt.current_owner_id == buyer_id,
            UnlockedPrompt.prompt_id == Prompt.id,
        )
    )
    return select(Prompt).where(
        and_(
            Prompt.is_published.is_(True),
            Prompt.is_deleted.is_(False),
            Prompt.pack_eligible.is_(True),
            Prompt.artist_id != buyer_id,
            ~exists(owned),
        )
    )


async def count_pack_pool(db: AsyncSession, buyer_id: UUID) -> int:
    """Nombre de prompts encore tirables pour ce buyer (pour l'UI)."""
    q = _eligible_pool_query(buyer_id).with_only_columns(func.count()).order_by(None)
    return int((await db.execute(q)).scalar() or 0)


async def open_mystery_pack_atomic(db: AsyncSession, buyer_id: UUID) -> dict:
    """
    Ouvre un pack : débite MYSTERY_PACK_PRICE, tire 1 prompt aléatoire,
    crédite l'artiste, crée l'UnlockedPrompt. Le caller commit.

    Retourne le prompt tiré + le nouveau solde. Lève PackPoolEmpty si rien à
    tirer, PackInsufficientCredits si solde trop bas.
    """
    price = MYSTERY_PACK_PRICE

    async with db.begin_nested():
        # 1. Lock le buyer (le seller sera locké après tirage).
        await _acquire_user_locks(db, [buyer_id])

        # 2. Vérifie le solde AVANT de tirer (évite un tirage gaspillé).
        buyer_row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": buyer_id},
        )).first()
        if buyer_row is None:
            raise PackError("Buyer not found")
        balance = int(buyer_row.credits_balance)
        if balance < price:
            raise PackInsufficientCredits(required=price, available=balance)

        # 3. Tire une rareté pondérée, puis un prompt au hasard DANS ce tier.
        #    Si le tier tiré est vide pour ce buyer, on retombe sur le pool
        #    global (garantit un résultat tant que le pool n'est pas vide).
        tier = _roll_tier()
        pick = (await db.execute(
            _eligible_pool_query(buyer_id)
            .where(Prompt.price_credits.between(tier["min"], tier["max"]))
            .order_by(func.random())
            .limit(1)
        )).scalar_one_or_none()
        if pick is None:
            pick = (await db.execute(
                _eligible_pool_query(buyer_id).order_by(func.random()).limit(1)
            )).scalar_one_or_none()
        if pick is None:
            raise PackPoolEmpty("Aucun prompt disponible dans le pool")

        # Rareté affichée = celle du PRIX réel du son tiré (pas du tier roulé,
        # car le fallback a pu donner un autre tier).
        rarity = rarity_for_price(pick.price_credits)
        artist_id = pick.artist_id
        # 4. Lock l'artiste tiré (en plus du buyer déjà locké).
        await _acquire_user_locks(db, [artist_id])

        artist_revenue, platform_fee = compute_split(price)

        # 5. Transaction (type UNLOCK, marquée source=mystery_pack).
        tx = Transaction(
            type=TransactionType.UNLOCK,
            status=TransactionStatus.PENDING,
            buyer_id=buyer_id,
            seller_id=artist_id,
            credits_amount=price,
            artist_revenue=artist_revenue,
            platform_fee=platform_fee,
            metadata_json={
                "source": "mystery_pack",
                "prompt_id": str(pick.id),
                "artist_id": str(artist_id),
            },
        )
        db.add(tx)
        await db.flush()

        # 6. Débite le buyer, crédite l'artiste.
        await db.execute(
            text("UPDATE users SET credits_balance = credits_balance - :p WHERE id = :uid"),
            {"p": price, "uid": buyer_id},
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

        # 7. Crée l'UnlockedPrompt (UNIQUE buyer+prompt dédoublonne).
        unlocked = UnlockedPrompt(
            current_owner_id=buyer_id,
            prompt_id=pick.id,
            original_artist_id=artist_id,
        )
        db.add(unlocked)
        try:
            await db.flush()
        except IntegrityError as e:
            # Course critique : déjà possédé entre le tirage et l'insert.
            # On laisse remonter pour rollback ; l'UI peut re-tenter.
            raise PackError("Tirage en conflit, réessaie") from e

        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    # Trophées packs (paliers 1/10/50/100 ouvertures). Hors savepoint principal,
    # le service achievements gère ses propres begin_nested. Le caller commit.
    from app.models.achievement import AchievementAxis
    from app.services.achievements import check_and_grant_achievements
    await check_and_grant_achievements(
        db, user_id=buyer_id, axis=AchievementAxis.COLLECTOR
    )

    new_balance = balance - price
    return {
        "prompt_id": pick.id,
        "title": pick.title,
        "artist_id": artist_id,
        "rarity": rarity,
        "price_paid": price,
        "new_balance": new_balance,
    }
