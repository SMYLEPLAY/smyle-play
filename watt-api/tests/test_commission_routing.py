"""Routage de la commission vers la tresorerie societe (Brique 1).

Couvre les trois choses qui peuvent casser :
  1. flag OFF (defaut) -> comportement STRICTEMENT inchange (rien n'est encaisse) ;
  2. flag ON -> la commission atterrit sur la tresorerie, dans le bucket NON
     retirable `achetes`, `gagnes` reste a 0, et la conservation tient
     (debit acheteur == part vendeur + commission) ;
  3. CONCURRENCE -> la tresorerie est une ligne chaude touchee par chaque vente.
     Des ventes simultanees (vendeurs differents, et croisees A<->B) doivent
     toutes aboutir sans deadlock.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import compute_split
from app.services.tiers import artist_pct_for_tier
from app.services.treasury import treasury_balance, treasury_user_id
from app.services.unlocks import unlock_prompt_atomic
from app.services.users import create_user


async def _user(balance: int) -> uuid.UUID:
    """User seede de facon COHERENTE avec l'invariant A1.4 (tout en achetes),
    trophees preseedes pour qu'aucun bonus ne pollue les soldes."""
    email = f"pytest-comm-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET credits_balance = :b, smyles_achetes = :b, "
                "smyles_gagnes = 0, smyles_promo = 0 WHERE id = :u"
            ),
            {"b": balance, "u": uid},
        )
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()
    return uid


async def _prompt(artist_id: uuid.UUID, price: int) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artist_id,
            title=f"P {uuid.uuid4().hex[:8]}",
            description="Tagline",
            prompt_text="X" * 100,
            price_credits=price,
            is_published=True,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _bk(uid: uuid.UUID) -> dict:
    async with SessionLocal() as db:
        r = (await db.execute(
            text(
                "SELECT credits_balance b, smyles_achetes a, smyles_gagnes g, "
                "smyles_promo p FROM users WHERE id = :u"
            ),
            {"u": uid},
        )).first()
    return {"b": int(r.b), "a": int(r.a), "g": int(r.g), "p": int(r.p)}


async def _reset_treasury() -> None:
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET credits_balance = 0, smyles_achetes = 0, "
                "smyles_gagnes = 0, smyles_promo = 0 WHERE is_treasury = TRUE"
            )
        )
        await db.commit()


async def _cleanup(*uids: uuid.UUID) -> None:
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()
    await _reset_treasury()


async def test_flag_off_rien_nest_encaisse(monkeypatch):
    """Defaut : la commission reste tracee au ledger et n'est creditee a
    personne — comportement d'avant la Brique 1, bit pour bit."""
    monkeypatch.setattr(settings, "FEATURE_MARKET_SMYLES", False)
    buyer, seller = await _user(1000), await _user(0)
    try:
        pid = await _prompt(seller, 50)
        async with SessionLocal() as db:
            avant = await treasury_balance(db)
            await unlock_prompt_atomic(db, buyer_id=buyer, prompt_id=pid)
            await db.commit()
        async with SessionLocal() as db:
            apres = await treasury_balance(db)
        assert apres == avant  # tresorerie intacte
    finally:
        await _cleanup(buyer, seller)


async def test_flag_on_commission_encaissee_en_achetes(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_MARKET_SMYLES", True)
    price = 50
    buyer, seller = await _user(1000), await _user(0)
    try:
        pid = await _prompt(seller, price)
        b_av, s_av = await _bk(buyer), await _bk(seller)
        async with SessionLocal() as db:
            t_av = await treasury_balance(db)
            await unlock_prompt_atomic(db, buyer_id=buyer, prompt_id=pid)
            await db.commit()
        b_ap, s_ap = await _bk(buyer), await _bk(seller)
        async with SessionLocal() as db:
            t_ap = await treasury_balance(db)

        part_vendeur, commission = compute_split(price, artist_pct_for_tier("standard"))
        assert commission > 0

        # Debit acheteur = prix ; part vendeur en GAGNES (retirable).
        assert b_av["b"] - b_ap["b"] == price
        assert s_ap["g"] - s_av["g"] == part_vendeur
        # Commission sur la tresorerie, en ACHETES (non retirable), jamais gagnes.
        assert t_ap["total"] - t_av["total"] == commission
        assert t_ap["achetes"] - t_av["achetes"] == commission
        assert t_ap["gagnes"] == 0
        # Conservation : ce que paie l'acheteur = vendeur + commission.
        assert price == part_vendeur + commission
        # Invariant A1.4 sur les trois comptes.
        for x in (b_ap, s_ap):
            assert x["a"] + x["g"] + x["p"] == x["b"]
        assert t_ap["achetes"] + t_ap["gagnes"] + t_ap["promo"] == t_ap["total"]
    finally:
        await _cleanup(buyer, seller)


async def test_concurrence_ventes_simultanees_sans_deadlock(monkeypatch):
    """LE test qui compte : la tresorerie est verrouillee par CHAQUE vente.
    6 ventes simultanees (vendeurs ET acheteurs distincts) doivent toutes
    aboutir — pas de deadlock, et la tresorerie encaisse la somme exacte."""
    monkeypatch.setattr(settings, "FEATURE_MARKET_SMYLES", True)
    price, n = 50, 6
    pairs = []
    for _ in range(n):
        b, s = await _user(1000), await _user(0)
        pairs.append((b, s, await _prompt(s, price)))
    try:
        async with SessionLocal() as db:
            t_av = await treasury_balance(db)

        async def vente(buyer, pid):
            async with SessionLocal() as db:
                await unlock_prompt_atomic(db, buyer_id=buyer, prompt_id=pid)
                await db.commit()
            return "ok"

        res = await asyncio.wait_for(
            asyncio.gather(*(vente(b, pid) for b, _, pid in pairs)),
            timeout=60,
        )
        assert res == ["ok"] * n  # aucune vente perdue, aucun deadlock

        async with SessionLocal() as db:
            t_ap = await treasury_balance(db)
        commission = compute_split(price, artist_pct_for_tier("standard"))[1]
        assert t_ap["total"] - t_av["total"] == commission * n
        assert t_ap["gagnes"] == 0
    finally:
        await _cleanup(*[u for b, s, _ in pairs for u in (b, s)])


async def test_concurrence_ventes_croisees_sans_deadlock(monkeypatch):
    """Scenario classique de deadlock : A achete a B pendant que B achete a A.
    Avec la tresorerie en plus, l'ordre de verrouillage doit tenir."""
    monkeypatch.setattr(settings, "FEATURE_MARKET_SMYLES", True)
    a, b = await _user(1000), await _user(1000)
    try:
        pa, pb = await _prompt(a, 50), await _prompt(b, 50)

        async def vente(buyer, pid):
            async with SessionLocal() as db:
                await unlock_prompt_atomic(db, buyer_id=buyer, prompt_id=pid)
                await db.commit()
            return "ok"

        res = await asyncio.wait_for(
            asyncio.gather(vente(a, pb), vente(b, pa)), timeout=60
        )
        assert res == ["ok", "ok"]
    finally:
        await _cleanup(a, b)
