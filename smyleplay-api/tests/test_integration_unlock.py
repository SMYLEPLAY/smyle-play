"""
Phase 9.5 — Tests d'intégration pour le système financier.

4 tests critiques (cf. handoff Phase 9.5) :

  1. test_deadlock_crossed_unlocks
       Deux unlocks croisés (A achète prompt-de-B, B achète prompt-de-A)
       lancés en parallèle. _acquire_user_locks tri les UUID croissant
       → pas de deadlock possible. Les deux doivent réussir < 10s.

  2. test_double_unlock_race
       Même buyer, même prompt, deux unlocks simultanés. Une coroutine
       réussit (ok), l'autre est refusée par UNIQUE constraint en
       AlreadyUnlocked. Vérifie : 1 seule UnlockedPrompt en DB,
       1 seule transaction COMPLETED, balances cohérentes.

  3. test_perk_race_consistency
       Buyer achète ADN et prompt du même artiste simultanément. Le perk
       s'applique selon l'ordre de commit, mais paid doit TOUJOURS être
       cohérent avec perk_applied. Vérifie : possession des deux + CHECK
       strict UNLOCK (artist_revenue + platform_fee = credits_amount).

  4. test_credit_conservation
       Pour un unlock isolé : Δbuyer = paid, Δartist = artist_revenue,
       paid - artist_revenue = platform_fee. Vérifie aussi que
       credits_earned_total artist += artist_revenue.

REQUIRES :
  - Postgres réel via DATABASE_URL (cf. conftest.py)
  - pytest-asyncio avec event_loop scope=session (déjà dans conftest)
  - Migration 0010 appliquée (sinon le filet DB CHECK strict UNLOCK est
    absent, mais les tests passent quand même via les checks applicatifs)

Ces tests utilisent VRAIMENT plusieurs sessions DB en parallèle pour
exercer la concurrence Postgres réelle (lockings, isolation). Si on
mockait, les tests seraient fictifs. C'est pour ça qu'on a besoin d'un
event_loop scope="session" partagé (déjà configuré dans conftest.py).

Ces tests peuvent prendre 1-3s chacun (locks + commits réels). Si CI
devient trop lent → @pytest.mark.slow.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, select, text

# Force TOUS les tests de ce fichier à partager le MÊME event loop (session).
# Sans ça, pytest-asyncio crée un loop par test, mais SessionLocal/asyncpg
# garde des connexions bound au loop précédent → "another operation is in
# progress". Cf. pytest.ini : asyncio_default_fixture_loop_scope=session
# couvre les fixtures, ce marker couvre les tests eux-mêmes.
pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.adn import Adn
from app.models.prompt import Prompt
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import compute_effective_price, compute_split
from app.services.unlocks import (
    UnlockError,
    unlock_adn_atomic,
    unlock_prompt_atomic,
)
from app.services.users import create_user


# =============================================================================
# Helpers
# =============================================================================

async def _make_user(
    initial_balance: int = 1000,
    artist_name: str | None = None,
) -> uuid.UUID:
    """
    Crée un user avec un solde et (optionnel) un nom d'artiste.

    create_user() commit en interne (cf. pattern conftest.py). On bump
    ensuite le balance/artist_name via un UPDATE séparé.
    """
    email = f"pytest-int-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(
            db, UserCreate(email=email, password="12345678")
        )
        user_id = user.id

    # Patch balance + artist_name si nécessaire
    if initial_balance != 10 or artist_name is not None:
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE users "
                    "SET credits_balance = :b, "
                    "    artist_name = COALESCE(:n, artist_name) "
                    "WHERE id = :u"
                ),
                {"b": initial_balance, "n": artist_name, "u": user_id},
            )
            await db.commit()

    # Phase 9.6 — Préseed TOUS les UserAchievement pour ce user.
    # Les hooks check_and_grant_achievements dans unlock_*_atomic ne
    # déclencheront donc aucun nouveau grant (tous déjà débloqués).
    # Sans ça, les assertions financières seraient polluées par les
    # bonuses (ex: artist gagne 8 + bonus 5 = 13 au lieu de 8).
    # Les achievements ont leurs propres tests unitaires dédiés.
    async with SessionLocal() as db:
        achs = list((await db.execute(select(Achievement))).scalars().all())
        for ach in achs:
            db.add(UserAchievement(user_id=user_id, achievement_id=ach.id))
        await db.commit()

    return user_id


async def _make_published_prompt(
    artist_id: uuid.UUID, price: int = 10
) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artist_id,
            title=f"Prompt {uuid.uuid4().hex[:8]}",
            description="Tagline",
            prompt_text="X" * 100,
            price_credits=price,
            is_published=True,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _make_published_adn(
    artist_id: uuid.UUID, price: int = 50
) -> uuid.UUID:
    async with SessionLocal() as db:
        a = Adn(
            artist_id=artist_id,
            description="X" * 250,
            usage_guide="how to",
            example_outputs="examples premium",
            price_credits=price,
            is_published=True,
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return a.id


async def _balance(uid: uuid.UUID) -> int:
    async with SessionLocal() as db:
        row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :u"),
            {"u": uid},
        )).first()
        return int(row.credits_balance)


async def _earned(uid: uuid.UUID) -> int:
    async with SessionLocal() as db:
        row = (await db.execute(
            text("SELECT credits_earned_total FROM users WHERE id = :u"),
            {"u": uid},
        )).first()
        return int(row.credits_earned_total)


async def _cleanup(*user_ids: uuid.UUID) -> None:
    """
    CASCADE delete les users → prompts/adns/owned/unlocked partent avec.
    Mais transactions.buyer_id/seller_id sont SET NULL → on nettoie aussi
    les transactions liées pour ne pas pourrir la table de tests.

    En prod, un trigger interdit DELETE FROM transactions (ledger immuable).
    En tests on bypass via `session_replication_role = 'replica'` qui
    désactive TOUS les triggers user-defined sur la session courante.
    Requiert que le rôle DB soit superuser (cas de smyleplay/dev).
    """
    if not user_ids:
        return
    ids = list(user_ids)
    async with SessionLocal() as db:
        # Bypass du trigger "Transactions cannot be deleted" pour cleanup test
        await db.execute(text("SET session_replication_role = 'replica'"))
        await db.execute(
            delete(Transaction).where(
                (Transaction.buyer_id.in_(ids))
                | (Transaction.seller_id.in_(ids))
            )
        )
        await db.execute(text("SET session_replication_role = 'origin'"))
        await db.execute(delete(User).where(User.id.in_(ids)))
        await db.commit()


async def _do_unlock_prompt(buyer_id: uuid.UUID, prompt_id: uuid.UUID):
    """
    Ouvre une session indépendante (vraie concurrence) et unlock un prompt.
    Retourne ('ok', result) ou ('err', exception_class_name, str).
    """
    async with SessionLocal() as db:
        try:
            r = await unlock_prompt_atomic(
                db, buyer_id=buyer_id, prompt_id=prompt_id
            )
            await db.commit()
            return ("ok", r)
        except UnlockError as e:
            await db.rollback()
            return ("err", type(e).__name__, str(e))
        except Exception as e:  # pragma: no cover — diagnostic uniquement
            await db.rollback()
            return ("crash", type(e).__name__, str(e))


async def _do_unlock_adn(buyer_id: uuid.UUID, adn_id: uuid.UUID):
    async with SessionLocal() as db:
        try:
            r = await unlock_adn_atomic(
                db, buyer_id=buyer_id, adn_id=adn_id
            )
            await db.commit()
            return ("ok", r)
        except UnlockError as e:
            await db.rollback()
            return ("err", type(e).__name__, str(e))
        except Exception as e:  # pragma: no cover
            await db.rollback()
            return ("crash", type(e).__name__, str(e))


# =============================================================================
# Test 1 — Deadlock : deux unlocks croisés
# =============================================================================

@pytest.mark.asyncio(loop_scope="session")
async def test_deadlock_crossed_unlocks():
    """
    Artist A achète prompt-de-B en parallèle de Artist B qui achète
    prompt-de-A. Sans tri UUID des locks dans _acquire_user_locks, ça
    deadlock systématiquement (chacun lock son propre id puis attend
    l'autre). Avec tri, les deux locks visent le même id en premier →
    sérialisation propre, pas de deadlock.

    Critère de succès : asyncio.gather() retourne en < 10s, deux 'ok'.
    Si un timeout déclenche → deadlock indétecté, fail immédiat.
    """
    artist_a = await _make_user(initial_balance=1000, artist_name="A")
    artist_b = await _make_user(initial_balance=1000, artist_name="B")
    prompt_of_a = await _make_published_prompt(artist_a, price=10)
    prompt_of_b = await _make_published_prompt(artist_b, price=10)

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                _do_unlock_prompt(artist_a, prompt_of_b),  # A buys B
                _do_unlock_prompt(artist_b, prompt_of_a),  # B buys A
            ),
            timeout=10.0,
        )
        assert all(r[0] == "ok" for r in results), (
            f"Deadlock test : pas tous OK : {results}"
        )
    finally:
        await _cleanup(artist_a, artist_b)


# =============================================================================
# Test 2 — Race : double-unlock simultané sur le même (buyer, prompt)
# =============================================================================

@pytest.mark.asyncio(loop_scope="session")
async def test_double_unlock_race():
    """
    Même buyer, même prompt, deux unlocks parallèles.

    Invariants après race :
      - exactement 1 succès, 1 AlreadyUnlocked (UNIQUE constraint DB)
      - exactement 1 row UnlockedPrompt en DB
      - exactement 1 transaction UNLOCK COMPLETED en DB
      - balance buyer débitée d'un seul `paid` (pas double)
      - balance seller créditée d'un seul `artist_revenue`
    """
    artist = await _make_user(initial_balance=0, artist_name="Solo")
    buyer = await _make_user(initial_balance=1000)
    prompt = await _make_published_prompt(artist, price=10)

    bal_buyer_before = await _balance(buyer)
    bal_artist_before = await _balance(artist)

    try:
        results = await asyncio.gather(
            _do_unlock_prompt(buyer, prompt),
            _do_unlock_prompt(buyer, prompt),
        )
        oks = [r for r in results if r[0] == "ok"]
        errs = [r for r in results if r[0] == "err"]
        crashes = [r for r in results if r[0] == "crash"]

        assert not crashes, f"Crash inattendu : {crashes}"
        assert len(oks) == 1 and len(errs) == 1, (
            f"Race anormale : oks={len(oks)} errs={len(errs)} "
            f"detail={results}"
        )
        assert errs[0][1] == "AlreadyUnlocked", (
            f"Erreur attendue AlreadyUnlocked, reçu : {errs[0]}"
        )

        # Compte des rows DB
        async with SessionLocal() as db:
            n_unlocked = (await db.execute(
                text(
                    "SELECT COUNT(*) FROM unlocked_prompts "
                    "WHERE current_owner_id = :u AND prompt_id = :p"
                ),
                {"u": buyer, "p": prompt},
            )).scalar()
            assert n_unlocked == 1, (
                f"Race a créé {n_unlocked} unlocks (attendu 1)"
            )

            n_tx = (await db.execute(
                text(
                    "SELECT COUNT(*) FROM transactions "
                    "WHERE buyer_id = :u AND type = 'unlock' "
                    "  AND status = 'completed'"
                ),
                {"u": buyer},
            )).scalar()
            assert n_tx == 1, (
                f"Race a créé {n_tx} tx COMPLETED (attendu 1)"
            )

        bal_buyer_after = await _balance(buyer)
        bal_artist_after = await _balance(artist)
        # paid = 10 (no perk), split 80/20 → artist=8, fee=2
        assert bal_buyer_before - bal_buyer_after == 10
        assert bal_artist_after - bal_artist_before == 8
    finally:
        await _cleanup(artist, buyer)


# =============================================================================
# Test 3 — Perk-in-race : ADN + prompt simultanés
# =============================================================================

@pytest.mark.asyncio(loop_scope="session")
async def test_perk_race_consistency():
    """
    Buyer achète ADN et prompt du même artiste simultanément. Selon
    l'ordre de commit (non-déterministe), le perk peut s'appliquer ou
    pas — mais paid DOIT toujours être cohérent avec perk_applied.

    Invariants vérifiés à la fin (peu importe qui commit en premier) :
      - les deux opérations réussissent
      - paid_prompt == compute_effective_price(base_price, perk_applied)
        → ⇔ pas d'incohérence : paid réduit ssi perk applied
      - tx.artist_revenue + tx.platform_fee == tx.credits_amount
        (CHECK strict UNLOCK garanti par migration 0010)
      - buyer possède l'ADN ET le prompt en DB
    """
    artist = await _make_user(initial_balance=0, artist_name="ArtistX")
    buyer = await _make_user(initial_balance=1000)
    prompt = await _make_published_prompt(artist, price=10)
    adn = await _make_published_adn(artist, price=50)

    try:
        results = await asyncio.gather(
            _do_unlock_adn(buyer, adn),
            _do_unlock_prompt(buyer, prompt),
        )
        adn_res, prompt_res = results
        assert adn_res[0] == "ok", f"ADN unlock a échoué : {adn_res}"
        assert prompt_res[0] == "ok", f"Prompt unlock a échoué : {prompt_res}"

        prompt_unlock = prompt_res[1]

        # 1. Cohérence paid <-> perk_applied
        expected_paid = compute_effective_price(
            prompt_unlock.base_price, prompt_unlock.perk_applied
        )
        assert prompt_unlock.paid == expected_paid, (
            f"Incohérence perk : paid={prompt_unlock.paid}, "
            f"perk_applied={prompt_unlock.perk_applied}, "
            f"base_price={prompt_unlock.base_price}, "
            f"attendu={expected_paid}"
        )

        # 2. CHECK strict UNLOCK (= au lieu de <=)
        tx = prompt_unlock.transaction
        assert tx.artist_revenue + tx.platform_fee == tx.credits_amount, (
            f"Split CHECK strict cassé : "
            f"artist={tx.artist_revenue} + fee={tx.platform_fee} "
            f"!= amount={tx.credits_amount}"
        )

        # 3. Possession effective des deux objets
        async with SessionLocal() as db:
            owns_adn = (await db.execute(
                text(
                    "SELECT 1 FROM owned_adns "
                    "WHERE user_id = :u AND adn_id = :a"
                ),
                {"u": buyer, "a": adn},
            )).first()
            owns_prompt = (await db.execute(
                text(
                    "SELECT 1 FROM unlocked_prompts "
                    "WHERE current_owner_id = :u AND prompt_id = :p"
                ),
                {"u": buyer, "p": prompt},
            )).first()
            assert owns_adn is not None, "Buyer doit posséder l'ADN"
            assert owns_prompt is not None, "Buyer doit posséder le prompt"
    finally:
        await _cleanup(artist, buyer)


# =============================================================================
# Test 4 — Conservation des crédits
# =============================================================================

@pytest.mark.asyncio(loop_scope="session")
async def test_credit_conservation():
    """
    Pour un unlock isolé (séquentiel, pas de race), conservation stricte :
      Δbuyer == paid
      Δartist == artist_revenue
      Δearned_artist == artist_revenue
      paid == artist_revenue + platform_fee
      ⇒ Δbuyer == Δartist + platform_fee  (zéro crédit créé/détruit)

    Si on cassait cette invariance, c'est tout le système financier qui
    est miné.
    """
    artist = await _make_user(initial_balance=0, artist_name="ArtistC")
    buyer = await _make_user(initial_balance=1000)
    prompt = await _make_published_prompt(artist, price=10)

    bal_buyer_b = await _balance(buyer)
    bal_artist_b = await _balance(artist)
    earned_artist_b = await _earned(artist)

    try:
        result = await _do_unlock_prompt(buyer, prompt)
        assert result[0] == "ok", f"Unlock a échoué : {result}"
        unlock = result[1]

        bal_buyer_a = await _balance(buyer)
        bal_artist_a = await _balance(artist)
        earned_artist_a = await _earned(artist)

        delta_buyer = bal_buyer_b - bal_buyer_a
        delta_artist = bal_artist_a - bal_artist_b
        delta_earned = earned_artist_a - earned_artist_b

        artist_revenue_expected, platform_fee_expected = compute_split(
            unlock.paid
        )

        assert delta_buyer == unlock.paid, (
            f"Buyer débité de {delta_buyer}, attendu {unlock.paid}"
        )
        assert delta_artist == artist_revenue_expected, (
            f"Artist crédité de {delta_artist}, "
            f"attendu {artist_revenue_expected}"
        )
        assert delta_earned == artist_revenue_expected, (
            f"earned_total artist += {delta_earned}, "
            f"attendu {artist_revenue_expected}"
        )
        # Conservation comptable : ce que perd buyer = ce que gagne
        # artist + ce que prend la plateforme. Aucun crédit créé/détruit.
        assert delta_buyer == delta_artist + platform_fee_expected, (
            f"Conservation cassée : "
            f"Δbuyer={delta_buyer}, Δartist={delta_artist}, "
            f"platform_fee={platform_fee_expected}"
        )
    finally:
        await _cleanup(artist, buyer)
