"""Cas A — le versement « prix fort » d'un tirage rare/mythique en pack est
RETIRABLE : il atterrit dans le bucket smyles_gagnes (et non smyles_promo).

Décision Tom 2026-09-20 : ce top-up est du revenu créateur lié à la
consommation de son œuvre → retirable. On prouve ici :
  - Δsmyles_gagnes de l'artiste == PRIX PLEIN du prompt (part normale + top-up) ;
  - Δsmyles_promo == 0 (plus rien ne tombe en promo pour ce versement) ;
  - l'invariant de somme (achetes+gagnes+promo == credits_balance) tient après.
"""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import PRIMARY_MARKET_ARTIST_PCT, compute_split
from app.services.packs import MYSTERY_PACK_PRICE, open_mystery_pack_atomic
from app.services.users import create_user
from sqlalchemy import select


async def _make_user_consistent(balance: int, *, artist_name: str | None = None) -> uuid.UUID:
    """Crée un user avec des buckets COHÉRENTS (tout en achetés) = solde, et
    préseed tous les trophées pour éviter tout bonus parasite sur les soldes."""
    email = f"pytest-jackpot-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET credits_balance = :b, smyles_achetes = :b, "
                "smyles_gagnes = 0, smyles_promo = 0, "
                "artist_name = COALESCE(:n, artist_name) WHERE id = :u"
            ),
            {"b": balance, "n": artist_name, "u": uid},
        )
        # Préseed trophées → pas de grant BONUS parasite pendant le pack.
        achs = list((await db.execute(select(Achievement))).scalars().all())
        for ach in achs:
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()
    return uid


async def _make_prompt(artist_id: uuid.UUID, price: int, max_supply: int | None) -> uuid.UUID:
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


async def _buckets(uid: uuid.UUID) -> dict:
    async with SessionLocal() as db:
        r = (await db.execute(
            text(
                "SELECT smyles_achetes, smyles_gagnes, smyles_promo, credits_balance "
                "FROM users WHERE id = :u"
            ),
            {"u": uid},
        )).first()
    return {
        "achetes": int(r.smyles_achetes),
        "gagnes": int(r.smyles_gagnes),
        "promo": int(r.smyles_promo),
        "balance": int(r.credits_balance),
    }


async def _cleanup(*uids: uuid.UUID) -> None:
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def test_topup_jackpot_atterrit_en_gagnes_retirable():
    """Un son legendary (≤10 ex.) tiré en pack : l'artiste touche le PRIX PLEIN,
    ENTIÈREMENT en gagnes (retirable), rien en promo."""
    artist = await _make_user_consistent(0, artist_name="JackpotArtist")
    buyer = await _make_user_consistent(100)
    full_price = 80
    try:
        await _make_prompt(artist, price=full_price, max_supply=5)  # legendary

        before = await _buckets(artist)
        async with SessionLocal() as db:
            res = await open_mystery_pack_atomic(db, buyer)
            await db.commit()
        after = await _buckets(artist)

        # Le tirage porte bien sur le prompt de l'artiste (seul éligible).
        assert res["rarity"] == "epique"

        # Part normale (déjà en gagnes) + top-up (désormais en gagnes) = prix plein.
        normal_share = compute_split(MYSTERY_PACK_PRICE, PRIMARY_MARKET_ARTIST_PCT)[0]
        topup = full_price - normal_share
        assert topup > 0

        assert after["gagnes"] - before["gagnes"] == full_price   # 100 % retirable
        assert after["promo"] - before["promo"] == 0              # plus rien en promo
        assert after["balance"] - before["balance"] == full_price

        # Invariant de somme tenu (achetes + gagnes + promo == credits_balance).
        assert (
            after["achetes"] + after["gagnes"] + after["promo"] == after["balance"]
        )
    finally:
        await _cleanup(artist, buyer)
