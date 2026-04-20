"""
Phase 9.6 — Tests d'intégration du système achievements.

4 tests focalisés sur les invariants critiques :

  1. test_grant_artist_first_credit_grants_bonus
       Service de base : un user avec credits_earned_total=1 sur l'axis
       ARTIST déclenche le badge "Premier souffle" (reward=5).
       Vérifie : badge créé + balance += 5 + transaction BONUS.

  2. test_check_and_grant_idempotent
       Anti double-grant : appeler check_and_grant 2x consécutivement
       ne re-grant pas le badge (UNIQUE user_id+achievement_id).

  3. test_grant_zero_reward_no_bonus_transaction
       Badge "Curieux" (buyer_first_unlock, reward=0) : badge créé,
       MAIS aucune transaction BONUS (économie d'écriture pour les
       badges symboliques). Balance inchangée.

  4. test_get_achievements_catalog_endpoint
       Endpoint public GET /achievements retourne les 13 badges seedés.

Ces tests N'utilisent PAS les helpers de test_integration_unlock.py
(qui préseedent tous les badges pour neutraliser les hooks). Ici on veut
au contraire OBSERVER les grants → helpers locaux clean.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from app.database import SessionLocal
from app.main import app
from app.models.achievement import (
    Achievement,
    AchievementAxis,
    UserAchievement,
)
from app.models.transaction import Transaction, TransactionType
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.achievements import check_and_grant_achievements
from app.services.users import create_user


pytestmark = pytest.mark.asyncio(loop_scope="session")


# -----------------------------------------------------------------------------
# Helpers locaux — PAS de préseed, pour observer les grants réels
# -----------------------------------------------------------------------------

async def _make_user_clean(
    initial_balance: int = 0,
    earned_total: int = 0,
) -> uuid.UUID:
    """Crée un user, set ses balances, NE préseed AUCUN achievement."""
    email = f"pytest-ach-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password="12345678"))
        user_id = user.id
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET credits_balance = :b, "
                "credits_earned_total = :e WHERE id = :u"
            ),
            {"b": initial_balance, "e": earned_total, "u": user_id},
        )
        await db.commit()
    return user_id


async def _cleanup_user(user_id: uuid.UUID) -> None:
    """Cleanup complet — bypass trigger immutable transactions."""
    async with SessionLocal() as db:
        await db.execute(text("SET session_replication_role = 'replica'"))
        await db.execute(
            delete(Transaction).where(
                (Transaction.buyer_id == user_id)
                | (Transaction.seller_id == user_id)
            )
        )
        await db.execute(text("SET session_replication_role = 'origin'"))
        # CASCADE delete : user_achievements + unlocked_prompts partent avec
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _balance(user_id: uuid.UUID) -> int:
    async with SessionLocal() as db:
        row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :u"),
            {"u": user_id},
        )).first()
        return int(row.credits_balance)


async def _user_achievement_codes(user_id: uuid.UUID) -> set[str]:
    """Retourne le set des codes des achievements débloqués par user_id."""
    async with SessionLocal() as db:
        q = (
            select(Achievement.code)
            .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
            .where(UserAchievement.user_id == user_id)
        )
        rows = (await db.execute(q)).all()
        return {r.code for r in rows}


async def _bonus_transactions(user_id: uuid.UUID) -> list[Transaction]:
    async with SessionLocal() as db:
        q = select(Transaction).where(
            Transaction.buyer_id == user_id,
            Transaction.type == TransactionType.BONUS,
        )
        return list((await db.execute(q)).scalars().all())


# -----------------------------------------------------------------------------
# Test 1 — Grant ARTIST first_credit : badge + balance + transaction BONUS
# -----------------------------------------------------------------------------

async def test_grant_artist_first_credit_grants_bonus():
    """
    Un artist avec credits_earned_total=1 doit débloquer "Premier souffle"
    (axis=ARTIST, threshold=1, reward=5).

    Conservation :
      - 1 UserAchievement en DB
      - balance += 5
      - 1 transaction BONUS (credits_amount=5, metadata.code=artist_first_credit)
    """
    artist = await _make_user_clean(initial_balance=0, earned_total=1)
    try:
        async with SessionLocal() as db:
            grants = await check_and_grant_achievements(
                db, user_id=artist, axis=AchievementAxis.ARTIST
            )
            await db.commit()

        # Au moins 1 grant (artist_first_credit, threshold=1)
        assert len(grants) >= 1, "Aucun badge granté pour earned=1"

        codes = await _user_achievement_codes(artist)
        assert "artist_first_credit" in codes, (
            f"artist_first_credit absent des badges débloqués : {codes}"
        )

        # Balance = +5 (reward du badge)
        bal = await _balance(artist)
        assert bal == 5, f"Balance attendue 5 (reward), obtenue {bal}"

        # 1 transaction BONUS de 5 crédits
        bonuses = await _bonus_transactions(artist)
        assert len(bonuses) == 1, f"Attendu 1 BONUS, obtenu {len(bonuses)}"
        assert bonuses[0].credits_amount == 5
        assert bonuses[0].metadata_json is not None
        assert bonuses[0].metadata_json.get("achievement_code") == "artist_first_credit"
    finally:
        await _cleanup_user(artist)


# -----------------------------------------------------------------------------
# Test 2 — Idempotence
# -----------------------------------------------------------------------------

async def test_check_and_grant_idempotent():
    """
    Appeler check_and_grant 2x consécutivement avec le même progress ne
    re-grant rien. UNIQUE (user_id, achievement_id) protège.

    Vérifie : grants[0] >= 1, grants[1] == 0, balance reste à reward du 1er.
    """
    artist = await _make_user_clean(initial_balance=0, earned_total=1)
    try:
        async with SessionLocal() as db:
            grants1 = await check_and_grant_achievements(
                db, user_id=artist, axis=AchievementAxis.ARTIST
            )
            await db.commit()
        async with SessionLocal() as db:
            grants2 = await check_and_grant_achievements(
                db, user_id=artist, axis=AchievementAxis.ARTIST
            )
            await db.commit()

        assert len(grants1) >= 1, "1er appel n'a rien granté"
        assert len(grants2) == 0, (
            f"2ème appel a re-granté {len(grants2)} badges (devrait être 0)"
        )

        # Balance reste à 5 (pas de double-grant)
        bal = await _balance(artist)
        assert bal == 5, f"Balance corrompue par double-grant : {bal}"

        # Toujours 1 seule transaction BONUS
        bonuses = await _bonus_transactions(artist)
        assert len(bonuses) == 1
    finally:
        await _cleanup_user(artist)


# -----------------------------------------------------------------------------
# Test 3 — Reward=0 : badge créé MAIS pas de transaction BONUS
# -----------------------------------------------------------------------------

async def test_grant_zero_reward_no_bonus_transaction():
    """
    Le badge "Curieux" (buyer_first_unlock) a reward=0 → on crée bien le
    UserAchievement (pour l'audit/UI) mais on ne crée PAS de transaction
    BONUS et la balance reste inchangée.

    Setup : on injecte directement un UnlockedPrompt en DB pour amener
    progress sur l'axis BUYER à 1 sans passer par unlock_prompt_atomic
    (ce qui re-déclencherait les hooks et polluerait l'observation).
    """
    artist = await _make_user_clean(initial_balance=0, earned_total=0)
    buyer = await _make_user_clean(initial_balance=0, earned_total=0)

    # Créer un prompt + un UnlockedPrompt directement (sans appeler unlock_*)
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artist,
            title=f"Prompt {uuid.uuid4().hex[:6]}",
            description="t",
            prompt_text="X" * 100,
            price_credits=10,
            is_published=True,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        prompt_id = p.id

    async with SessionLocal() as db:
        up = UnlockedPrompt(
            current_owner_id=buyer,
            prompt_id=prompt_id,
            original_artist_id=artist,
        )
        db.add(up)
        await db.commit()

    try:
        async with SessionLocal() as db:
            grants = await check_and_grant_achievements(
                db, user_id=buyer, axis=AchievementAxis.BUYER
            )
            await db.commit()

        # Badge granté
        codes = await _user_achievement_codes(buyer)
        assert "buyer_first_unlock" in codes, (
            f"buyer_first_unlock manquant : {codes}"
        )

        # Balance INCHANGÉE (reward=0 sur ce badge)
        bal = await _balance(buyer)
        assert bal == 0, f"Balance modifiée alors que reward=0 : {bal}"

        # AUCUNE transaction BONUS (économie d'écriture)
        bonuses = await _bonus_transactions(buyer)
        # Filtrer le badge spécifique : on cherche zéro BONUS lié à first_unlock
        first_unlock_bonuses = [
            b for b in bonuses
            if b.metadata_json
            and b.metadata_json.get("achievement_code") == "buyer_first_unlock"
        ]
        assert len(first_unlock_bonuses) == 0, (
            "Une transaction BONUS a été créée pour un badge reward=0"
        )
    finally:
        # Cleanup explicite : UnlockedPrompt + Prompt (CASCADE part avec user)
        async with SessionLocal() as db:
            await db.execute(
                delete(UnlockedPrompt).where(
                    UnlockedPrompt.current_owner_id == buyer
                )
            )
            await db.execute(delete(Prompt).where(Prompt.id == prompt_id))
            await db.commit()
        await _cleanup_user(buyer)
        await _cleanup_user(artist)


# -----------------------------------------------------------------------------
# Test 4 — Endpoint catalog public
# -----------------------------------------------------------------------------

async def test_get_achievements_catalog_endpoint_returns_seeded_badges():
    """
    GET /achievements (public) doit retourner les 13 achievements seedés
    par la migration 0009. Vérifie aussi qu'au moins 1 badge de chaque axe
    est présent.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/achievements")

    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data and "total" in data
    assert data["total"] == 13, f"Attendu 13 badges seedés, obtenu {data['total']}"

    axes = {item["axis"] for item in data["items"]}
    # Les enum values sont sérialisées en string (lowercase)
    assert "buyer" in axes
    assert "fan" in axes
    assert "artist" in axes
