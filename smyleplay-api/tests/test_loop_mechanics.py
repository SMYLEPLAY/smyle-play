"""
Tests des mécaniques de la boucle d'engagement (2026-06-08).

Couvre parrainage, streak, packs (rareté par supply + stock-out) et la
rareté/supply des prompts. Deux familles :

  - Fonctions PURES (pas de DB) : barèmes et mappings de rareté. Rapides,
    déterministes.
  - Intégration (Postgres réel via SessionLocal, cf. conftest.py) : flux
    métier de bout en bout, modelés sur test_integration_unlock.py.

Comme test_integration_unlock, on pré-seed les UserAchievement pour qu'aucun
trophée ne pollue les assertions de solde (les trophées ont leurs tests
dédiés). Postgres requis (cf. conftest) ; en local : pytest -q.
"""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.prompt import Prompt
from app.models.referral import Referral, ReferralStatus
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user

from app.services.packs import (
    MYSTERY_PACK_PRICE,
    PackInsufficientCredits,
    PackPoolEmpty,
    open_mystery_pack_atomic,
    rarity_from_supply,
)
from app.services.referrals import (
    REFERRAL_REWARD_CREDITS,
    attach_referral_at_signup,
    maybe_reward_referral,
)
from app.services.streak import (
    DAILY_REWARD,
    MILESTONE_EVERY,
    MILESTONE_REWARD,
    claim_daily_checkin,
    reward_for_streak,
)
from app.services.marketplace import compute_rarity_tier
from app.services.unlocks import PromptNotPurchasable, unlock_prompt_atomic
from app.services.resale import (
    ResaleLinkedAccounts,
    ResaleSelfBuy,
    buy_resale_atomic,
    list_prompt_for_resale,
)


# =============================================================================
# Fonctions PURES — pas de DB
# =============================================================================

def test_reward_for_streak_bareme():
    # +1 chaque jour, +3 au 7e jour consécutif → semaine pleine = 9.
    week = [reward_for_streak(d) for d in range(1, 8)]
    assert week == [1, 1, 1, 1, 1, 1, 3]
    assert sum(week) == 9
    # 14 jours (2 cycles) = 18.
    assert sum(reward_for_streak(d) for d in range(1, 15)) == 18
    # Le palier tombe à chaque multiple de 7.
    assert reward_for_streak(MILESTONE_EVERY) == MILESTONE_REWARD
    assert reward_for_streak(MILESTONE_EVERY * 2) == MILESTONE_REWARD
    assert reward_for_streak(1) == DAILY_REWARD


def test_rarity_from_supply_mapping():
    assert rarity_from_supply(None) == "commun"      # illimité
    assert rarity_from_supply(1) == "legendaire"     # mythic 1/1
    assert rarity_from_supply(2) == "epique"
    assert rarity_from_supply(10) == "epique"
    assert rarity_from_supply(11) == "rare"
    assert rarity_from_supply(10000) == "rare"
    assert rarity_from_supply(10001) == "commun"     # open


def test_pyramid_cascade_pricing():
    # Pyramide ADN en cascade : cumul multiplicatif -30% (profil) puis -20%
    # (playlist). Décision Tom 2026-06-08.
    from app.services.credits import compute_effective_price
    assert compute_effective_price(50, False, False) == 50
    assert compute_effective_price(50, True, False) == 35    # -30% profil
    assert compute_effective_price(50, False, True) == 40    # -20% playlist
    assert compute_effective_price(50, True, True) == 28     # 50→35→28 (cumul)
    assert compute_effective_price(80, True, True) == 44     # 80→56→44 (-45%)
    # Rétro-compat : ancienne signature 2 arguments inchangée.
    assert compute_effective_price(10, True) == 7


def test_compute_rarity_tier_prompt():
    # Le tier "édition" partagé avec les ADN, appliqué aux prompts.
    assert compute_rarity_tier(None) == "unlimited"
    assert compute_rarity_tier(1) == "mythic"
    assert compute_rarity_tier(10) == "legendary"
    assert compute_rarity_tier(10000) == "limited"
    assert compute_rarity_tier(10001) == "open"


# =============================================================================
# Helpers intégration (modelés sur test_integration_unlock.py)
# =============================================================================

async def _make_user(initial_balance: int = 1000, artist_name: str | None = None) -> uuid.UUID:
    email = f"pytest-loop-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password="12345678"))
        user_id = user.id
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET credits_balance = :b, "
                "artist_name = COALESCE(:n, artist_name) WHERE id = :u"
            ),
            {"b": initial_balance, "n": artist_name, "u": user_id},
        )
        await db.commit()
    # Pré-seed tous les trophées → pas de bonus parasite sur les soldes.
    async with SessionLocal() as db:
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=user_id, achievement_id=ach.id))
        await db.commit()
    return user_id


async def _make_prompt(artist_id: uuid.UUID, price: int = 10, max_supply: int | None = None) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artist_id,
            title=f"Prompt {uuid.uuid4().hex[:8]}",
            description="Tagline",
            prompt_text="X" * 100,
            price_credits=price,
            is_published=True,
            max_supply=max_supply,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _balance(uid: uuid.UUID) -> int:
    async with SessionLocal() as db:
        row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :u"), {"u": uid}
        )).first()
        return int(row.credits_balance)


async def _cleanup_users(*uids: uuid.UUID) -> None:
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


# =============================================================================
# Parrainage
# =============================================================================

async def test_resale_blocked_between_referral_linked_accounts():
    """
    Anti wash-trading (H0.4) : un parrain et son filleul ne peuvent pas se
    revendre un prompt entre eux (sinon farm de royalties / gonflage de rareté
    entre comptes complices). buy_resale_atomic doit lever ResaleLinkedAccounts
    et ne RIEN débiter.
    """
    artist = await _make_user(initial_balance=0, artist_name="WashArtist")
    seller = await _make_user(initial_balance=1000)
    buyer = await _make_user(initial_balance=1000)
    prompt = await _make_prompt(artist, price=10)

    # Le seller acquiert le prompt puis le met en revente.
    async with SessionLocal() as db:
        await unlock_prompt_atomic(db, buyer_id=seller, prompt_id=prompt)
        await db.commit()
    async with SessionLocal() as db:
        up = await list_prompt_for_resale(
            db, owner_id=seller, prompt_id=prompt, price=20
        )
        up_id = up.id
        await db.commit()

    # Lien de parrainage seller (parrain) → buyer (filleul).
    async with SessionLocal() as db:
        db.add(Referral(
            referrer_id=seller, referred_id=buyer,
            status=ReferralStatus.PENDING, reward_credits=10,
        ))
        await db.commit()

    buyer_balance_before = await _balance(buyer)
    try:
        async with SessionLocal() as db:
            with pytest.raises(ResaleLinkedAccounts):
                await buy_resale_atomic(
                    db, buyer_id=buyer, unlocked_prompt_id=up_id
                )
            await db.rollback()
        # Aucun débit : le blocage précède toute mutation de solde.
        assert await _balance(buyer) == buyer_balance_before
    finally:
        await _cleanup_users(artist, seller, buyer)


async def test_referral_reward_on_first_action_and_idempotent():
    referrer = await _make_user(initial_balance=100)
    referred = await _make_user(initial_balance=100)
    try:
        # Récupère le code du parrain.
        async with SessionLocal() as db:
            code = (await db.get(User, referrer)).referral_code
            referred_user = await db.get(User, referred)
            link = await attach_referral_at_signup(db, referred_user, code)
            assert link is not None
            await db.commit()

        # 1ère action du filleul → récompense versée aux DEUX.
        async with SessionLocal() as db:
            rewarded = await maybe_reward_referral(db, referred)
            await db.commit()
        assert rewarded is True
        assert await _balance(referrer) == 100 + REFERRAL_REWARD_CREDITS
        assert await _balance(referred) == 100 + REFERRAL_REWARD_CREDITS

        # Idempotent : 2e déclenchement ne reverse rien.
        async with SessionLocal() as db:
            again = await maybe_reward_referral(db, referred)
            await db.commit()
        assert again is False
        assert await _balance(referrer) == 100 + REFERRAL_REWARD_CREDITS

        async with SessionLocal() as db:
            ref = (await db.execute(
                select(Referral).where(Referral.referred_id == referred)
            )).scalar_one()
            assert ref.status == ReferralStatus.REWARDED
    finally:
        await _cleanup_users(referrer, referred)


async def test_referral_no_self_referral():
    u = await _make_user()
    try:
        async with SessionLocal() as db:
            user = await db.get(User, u)
            link = await attach_referral_at_signup(db, user, user.referral_code)
            assert link is None  # auto-parrainage refusé
    finally:
        await _cleanup_users(u)


async def test_referral_daily_cap(monkeypatch):
    # Anti-abus : au-delà du plafond glissant 24h, plus de récompense.
    import app.services.referrals as ref_mod
    monkeypatch.setattr(ref_mod, "REFERRAL_DAILY_CAP", 1)

    referrer = await _make_user(initial_balance=100)
    a = await _make_user(initial_balance=0)
    b = await _make_user(initial_balance=0)
    try:
        async with SessionLocal() as db:
            code = (await db.get(User, referrer)).referral_code

        # Filleul A : attaché puis récompensé (1 récompensé sur 24h).
        async with SessionLocal() as db:
            await ref_mod.attach_referral_at_signup(db, await db.get(User, a), code)
            await db.commit()
        async with SessionLocal() as db:
            assert await ref_mod.maybe_reward_referral(db, a) is True
            await db.commit()
        bal_after_a = await _balance(referrer)  # 100 + 10

        # Filleul B : attaché puis tenté → PLAFONNÉ (cap=1, déjà 1 récompensé).
        async with SessionLocal() as db:
            await ref_mod.attach_referral_at_signup(db, await db.get(User, b), code)
            await db.commit()
        async with SessionLocal() as db:
            assert await ref_mod.maybe_reward_referral(db, b) is False
            await db.commit()
        # Le solde du parrain n'a PAS bougé après le plafonnement.
        assert await _balance(referrer) == bal_after_a
    finally:
        await _cleanup_users(referrer, a, b)


# =============================================================================
# Streak
# =============================================================================

async def test_streak_first_claim_and_same_day_idempotent():
    u = await _make_user(initial_balance=0)
    try:
        async with SessionLocal() as db:
            r1 = await claim_daily_checkin(db, u)
            await db.commit()
        assert r1["claimed"] is True
        assert r1["streak_count"] == 1
        assert r1["reward_granted"] == DAILY_REWARD
        assert await _balance(u) == DAILY_REWARD

        # Même jour → no-op.
        async with SessionLocal() as db:
            r2 = await claim_daily_checkin(db, u)
            await db.commit()
        assert r2["claimed"] is False
        assert await _balance(u) == DAILY_REWARD
    finally:
        await _cleanup_users(u)


async def test_streak_milestone_day7():
    u = await _make_user(initial_balance=0)
    try:
        # Simule 6 jours consécutifs déjà faits, dernier = hier.
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE users SET streak_count = 6, "
                    "last_checkin_date = (CURRENT_DATE - INTERVAL '1 day') "
                    "WHERE id = :u"
                ),
                {"u": u},
            )
            await db.commit()
        async with SessionLocal() as db:
            r = await claim_daily_checkin(db, u)
            await db.commit()
        assert r["streak_count"] == 7
        assert r["reward_granted"] == MILESTONE_REWARD  # palier 7 → +3
        assert r["is_milestone"] is True
        assert await _balance(u) == MILESTONE_REWARD
    finally:
        await _cleanup_users(u)


# =============================================================================
# Packs — rareté par supply + stock-out
# =============================================================================

async def test_pack_open_debits_and_grants_unlimited_is_commun():
    artist = await _make_user(initial_balance=0, artist_name="PackArtist")
    buyer = await _make_user(initial_balance=100)
    try:
        await _make_prompt(artist, price=80, max_supply=None)  # illimité
        async with SessionLocal() as db:
            res = await open_mystery_pack_atomic(db, buyer)
            await db.commit()
        assert res["price_paid"] == MYSTERY_PACK_PRICE
        assert res["rarity"] == "commun"  # supply illimité → commun (pas legendaire)
        assert await _balance(buyer) == 100 - MYSTERY_PACK_PRICE
        # Le son tiré est bien dans la bibliothèque du buyer.
        async with SessionLocal() as db:
            owned = (await db.execute(
                select(func.count(UnlockedPrompt.id)).where(
                    UnlockedPrompt.current_owner_id == buyer
                )
            )).scalar()
            assert int(owned) == 1
    finally:
        await _cleanup_users(artist, buyer)


async def test_pack_insufficient_credits():
    artist = await _make_user(initial_balance=0, artist_name="PoorArtist")
    buyer = await _make_user(initial_balance=MYSTERY_PACK_PRICE - 1)
    try:
        await _make_prompt(artist, price=10, max_supply=None)
        with pytest.raises(PackInsufficientCredits):
            async with SessionLocal() as db:
                await open_mystery_pack_atomic(db, buyer)
                await db.commit()
    finally:
        await _cleanup_users(artist, buyer)


async def test_pack_pool_empty_when_only_own_prompts():
    artist = await _make_user(initial_balance=100, artist_name="LonelyArtist")
    try:
        await _make_prompt(artist, price=10, max_supply=None)
        # L'artiste ne peut pas tirer son propre prompt → pool vide.
        with pytest.raises(PackPoolEmpty):
            async with SessionLocal() as db:
                await open_mystery_pack_atomic(db, artist)
                await db.commit()
    finally:
        await _cleanup_users(artist)


async def test_pack_topup_full_price_for_legendary():
    # Un son legendary (2–10 ex.) tiré en pack → l'artiste touche le PRIX PLEIN.
    artist = await _make_user(initial_balance=0, artist_name="RareArtist")
    buyer = await _make_user(initial_balance=100)
    try:
        await _make_prompt(artist, price=80, max_supply=5)  # legendary
        async with SessionLocal() as db:
            res = await open_mystery_pack_atomic(db, buyer)
            await db.commit()
        assert res["rarity"] == "epique"
        assert await _balance(artist) == 80                 # prix plein, pas 6
        assert await _balance(buyer) == 100 - MYSTERY_PACK_PRICE
    finally:
        await _cleanup_users(artist, buyer)


async def test_pack_no_topup_for_limited_tier():
    # Un son "limited" (11–10 000 ex.) NE déclenche PAS le top-up (garde-fou).
    artist = await _make_user(initial_balance=0, artist_name="LimArtist")
    buyer = await _make_user(initial_balance=100)
    try:
        await _make_prompt(artist, price=80, max_supply=50)  # limited (>10)
        async with SessionLocal() as db:
            res = await open_mystery_pack_atomic(db, buyer)
            await db.commit()
        assert res["rarity"] == "rare"
        assert await _balance(artist) == 6                  # juste la part des 8
    finally:
        await _cleanup_users(artist, buyer)


# =============================================================================
# Stock-out édition limitée (achat direct prompt)
# =============================================================================

async def _make_owned_prompt(owner_id, prompt_id, artist_id):
    async with SessionLocal() as db:
        up = UnlockedPrompt(
            current_owner_id=owner_id,
            prompt_id=prompt_id,
            original_artist_id=artist_id,
        )
        db.add(up)
        await db.commit()
        await db.refresh(up)
        return up.id


async def test_resale_transfer_and_split():
    # Revente : transfert de propriété + split 30% artiste / 20% plateforme / 50% vendeur.
    artist = await _make_user(initial_balance=0, artist_name="OrigArtist")
    seller = await _make_user(initial_balance=0)
    buyer = await _make_user(initial_balance=200)
    try:
        prompt_id = await _make_prompt(artist, price=80, max_supply=None)
        up_id = await _make_owned_prompt(seller, prompt_id, artist)

        # Le vendeur met en vente à 100.
        async with SessionLocal() as db:
            await list_prompt_for_resale(db, owner_id=seller, prompt_id=prompt_id, price=100)
            await db.commit()

        # L'acheteur achète.
        async with SessionLocal() as db:
            res = await buy_resale_atomic(db, buyer_id=buyer, unlocked_prompt_id=up_id)
            await db.commit()

        # Split : 30 / 20 / 50.
        assert res["artist_royalty"] == 30
        assert res["platform_fee"] == 20
        assert res["seller_cut"] == 50
        # Soldes.
        assert await _balance(buyer) == 200 - 100
        assert await _balance(seller) == 50
        assert await _balance(artist) == 30
        # Propriété TRANSFÉRÉE à l'acheteur, retirée de la vente.
        async with SessionLocal() as db:
            up2 = await db.get(UnlockedPrompt, up_id)
            assert up2.current_owner_id == buyer
            assert up2.resale_price is None
    finally:
        await _cleanup_users(artist, seller, buyer)


async def test_resale_self_buy_refused():
    artist = await _make_user(initial_balance=0, artist_name="A")
    seller = await _make_user(initial_balance=100)
    try:
        prompt_id = await _make_prompt(artist, price=10, max_supply=None)
        up_id = await _make_owned_prompt(seller, prompt_id, artist)
        async with SessionLocal() as db:
            await list_prompt_for_resale(db, owner_id=seller, prompt_id=prompt_id, price=20)
            await db.commit()
        with pytest.raises(ResaleSelfBuy):
            async with SessionLocal() as db:
                await buy_resale_atomic(db, buyer_id=seller, unlocked_prompt_id=up_id)
                await db.commit()
    finally:
        await _cleanup_users(artist, seller)


async def test_prompt_stockout_limited_edition():
    artist = await _make_user(initial_balance=0, artist_name="LimitedArtist")
    buyer1 = await _make_user(initial_balance=100)
    buyer2 = await _make_user(initial_balance=100)
    try:
        prompt_id = await _make_prompt(artist, price=10, max_supply=1)  # 1/1
        # 1er acheteur : OK.
        async with SessionLocal() as db:
            await unlock_prompt_atomic(db, buyer_id=buyer1, prompt_id=prompt_id)
            await db.commit()
        # 2e acheteur : épuisé → refus.
        with pytest.raises(PromptNotPurchasable):
            async with SessionLocal() as db:
                await unlock_prompt_atomic(db, buyer_id=buyer2, prompt_id=prompt_id)
                await db.commit()
    finally:
        await _cleanup_users(artist, buyer1, buyer2)
