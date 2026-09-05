"""
S-06 sécurité (2026-09-02) — course « double vente » sur la revente P2P
(audit A §M3).

Avant : le listing était lu sans verrou et transféré par un UPDATE
inconditionnel. Deux acheteurs simultanés sur le même exemplaire payaient
tous les deux (vendeur crédité 2×), le second dépossédait le premier.
Désormais : listing verrouillé (FOR UPDATE) dans le savepoint avant les
verrous users, re-validation, transfert conditionnel (rowcount == 1).

Le test lance deux `POST /resale/{id}/buy` en parallèle avec
`asyncio.gather` sur le client ASGI (pool asyncpg partagé : les deux
requêtes s'entrelacent réellement et se sérialisent sur le verrou de ligne).
Postgres requis (cf. conftest.py).
"""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, func, select, text

from app.config import settings
from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.prompt import Prompt
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.resale import list_prompt_for_resale
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PASSWORD = "12345678"


async def _make_user(initial_balance: int, artist_name: str | None = None) -> dict:
    email = f"pytest-race-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password=_PASSWORD))
        user_id = user.id
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET credits_balance = :b, smyles_achetes = :b, "
                "smyles_promo = 0, smyles_gagnes = 0, "
                "artist_name = COALESCE(:n, artist_name) WHERE id = :u"
            ),
            {"b": initial_balance, "n": artist_name, "u": user_id},
        )
        # Pré-seed des trophées → aucun bonus parasite sur les soldes.
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=user_id, achievement_id=ach.id))
        await db.commit()
    return {"id": user_id, "email": email}


async def _login(client, email: str) -> dict:
    r = await client.post("/auth/login", json={"email": email, "password": _PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


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


async def _seed_listing(artist_id, seller_id, price: int) -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artist_id,
            title=f"Prompt race {uuid.uuid4().hex[:8]}",
            description="Tagline",
            prompt_text="X" * 100,
            price_credits=8,
            is_published=True,
        )
        db.add(p)
        await db.flush()
        up = UnlockedPrompt(
            current_owner_id=seller_id, prompt_id=p.id, original_artist_id=artist_id,
        )
        db.add(up)
        await db.commit()
        await db.refresh(up)
        prompt_id, up_id = p.id, up.id
    async with SessionLocal() as db:
        await list_prompt_for_resale(db, owner_id=seller_id, prompt_id=prompt_id, price=price)
        await db.commit()
    return prompt_id, up_id


async def test_two_buyers_same_listing_only_one_wins(client, monkeypatch):
    # S-08 (2026-09-02) : le routeur /resale est désormais gaté par le
    # drapeau "resale" du MODE LANCEMENT (404 quand masqué, ce qui est le
    # défaut). Ce test porte sur la course « double vente », pas sur le
    # drapeau : on rallume l'item le temps du test (`launch_flags_dict()`
    # est relu à CHAQUE requête).
    monkeypatch.setattr(settings, "SHOW_RESALE", True)

    price = 10
    artist = await _make_user(0, artist_name="RaceArtist")
    seller = await _make_user(0)
    buyer_a = await _make_user(50)
    buyer_b = await _make_user(50)
    try:
        prompt_id, up_id = await _seed_listing(artist["id"], seller["id"], price)
        headers_a = await _login(client, buyer_a["email"])
        headers_b = await _login(client, buyer_b["email"])

        ra, rb = await asyncio.gather(
            client.post(f"/resale/{up_id}/buy", headers=headers_a),
            client.post(f"/resale/{up_id}/buy", headers=headers_b),
        )
        statuses = sorted([ra.status_code, rb.status_code])
        assert statuses[0] == 200, (ra.text, rb.text)
        assert statuses[1] in (404, 409), (ra.text, rb.text)

        winner, loser = (buyer_a, buyer_b) if ra.status_code == 200 else (buyer_b, buyer_a)
        win_resp = ra if ra.status_code == 200 else rb
        seller_cut = win_resp.json()["seller_cut"]
        artist_royalty = win_resp.json()["artist_royalty"]
        assert seller_cut + artist_royalty + win_resp.json()["platform_fee"] == price

        # Propriété transférée UNE fois, au gagnant ; listing retiré.
        async with SessionLocal() as db:
            up = await db.get(UnlockedPrompt, up_id)
            assert up.current_owner_id == winner["id"]
            assert up.resale_price is None
            n_copies = (await db.execute(
                select(func.count(UnlockedPrompt.id)).where(UnlockedPrompt.prompt_id == prompt_id)
            )).scalar()
            assert n_copies == 1  # aucune duplication d'exemplaire
            n_tx = (await db.execute(
                select(func.count(Transaction.id)).where(
                    Transaction.type == TransactionType.RESALE,
                    Transaction.status == TransactionStatus.COMPLETED,
                    Transaction.seller_id == seller["id"],
                )
            )).scalar()
            assert n_tx == 1  # une seule vente enregistrée au ledger

        # Soldes : gagnant débité, perdant intact, vendeur crédité UNE fois.
        assert await _balance(winner["id"]) == 50 - price
        assert await _balance(loser["id"]) == 50
        assert await _balance(seller["id"]) == seller_cut
        assert await _balance(artist["id"]) == artist_royalty

        # Le perdant réessaie : le listing n'existe plus → 404, solde intact.
        loser_headers = headers_b if winner is buyer_a else headers_a
        r_again = await client.post(f"/resale/{up_id}/buy", headers=loser_headers)
        assert r_again.status_code == 404, r_again.text
        assert await _balance(loser["id"]) == 50
    finally:
        await _cleanup_users(artist["id"], seller["id"], buyer_a["id"], buyer_b["id"])


async def test_resale_price_changed_between_display_and_buy_is_refused(client, monkeypatch):
    """Re-validation sous verrou : si le prix change (relisting) entre la
    pré-lecture et le savepoint, l'achat au prix affiché est refusé plutôt
    que facturé au nouveau prix. (Simulé par un relisting concurrent : le
    listing repasse à un autre prix pendant la course → l'un des deux achats
    au moins échoue, jamais de double crédit.)"""
    # S-08 : même gate que ci-dessus. Sans ce rallumage le test resterait
    # vert à vide (404 fait partie de ses statuts tolérés) sans jamais
    # exercer la re-validation sous verrou.
    monkeypatch.setattr(settings, "SHOW_RESALE", True)

    artist = await _make_user(0, artist_name="RaceArtist2")
    seller = await _make_user(0)
    buyer = await _make_user(100)
    try:
        prompt_id, up_id = await _seed_listing(artist["id"], seller["id"], 10)
        headers = await _login(client, buyer["email"])
        seller_headers = await _login(client, seller["email"])

        # Relisting (prix 30) et achat lancés en parallèle.
        r_relist, r_buy = await asyncio.gather(
            client.post(f"/resale/prompts/{prompt_id}/list", json={"price": 30},
                        headers=seller_headers),
            client.post(f"/resale/{up_id}/buy", headers=headers),
        )
        assert r_relist.status_code in (204, 404)
        assert r_buy.status_code in (200, 404), r_buy.text
        balance = await _balance(buyer["id"])
        if r_buy.status_code == 200:
            paid = r_buy.json()["price_paid"]
            assert paid in (10, 30)
            assert balance == 100 - paid
            assert await _balance(seller["id"]) == r_buy.json()["seller_cut"]
        else:
            assert balance == 100
            assert await _balance(seller["id"]) == 0
    finally:
        await _cleanup_users(artist["id"], seller["id"], buyer["id"])
