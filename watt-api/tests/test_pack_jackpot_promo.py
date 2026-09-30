"""Pricing v2 (30/09, option A) — le versement « prix fort » d'un tirage
rare/mythique en pack est NON RETIRABLE : il atterrit dans le bucket
smyles_promo (annule le « cas A », #539).

Ce top-up est financé par la plateforme, pas par un acheteur : il n'est adossé
à aucun argent réel. On prouve ici :
  - Δsmyles_gagnes de l'artiste == SA PART NORMALE de la vente (payée par
    l'acheteur avec des Smyles achetés → retirable) ;
  - Δsmyles_promo == le TOP-UP (prix plein − part normale), non retirable ;
  - la ligne de ledger reste de type BONUS, avec une clé d'idempotence ;
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


async def test_topup_jackpot_atterrit_en_promo_non_retirable():
    """Un son legendary (≤10 ex.) tiré en pack : l'artiste touche toujours le
    PRIX PLEIN, mais le top-up plateforme est en promo (non retirable)."""
    artist = await _make_user_consistent(0, artist_name="JackpotArtist")
    buyer = await _make_user_consistent(100)
    full_price = 80
    try:
        pid = await _make_prompt(artist, price=full_price, max_supply=5)  # legendary

        before = await _buckets(artist)
        async with SessionLocal() as db:
            res = await open_mystery_pack_atomic(db, buyer)
            await db.commit()
        after = await _buckets(artist)

        # Le tirage porte bien sur le prompt de l'artiste (seul éligible).
        assert res["rarity"] == "epique"

        normal_share = compute_split(MYSTERY_PACK_PRICE, PRIMARY_MARKET_ARTIST_PCT)[0]
        topup = full_price - normal_share
        assert topup > 0

        assert after["gagnes"] - before["gagnes"] == normal_share  # part payée par l'acheteur
        assert after["promo"] - before["promo"] == topup           # top-up NON retirable
        assert after["balance"] - before["balance"] == full_price  # prix plein inchangé

        # Invariant de somme tenu (achetes + gagnes + promo == credits_balance).
        assert (
            after["achetes"] + after["gagnes"] + after["promo"] == after["balance"]
        )

        # Ledger : ligne BONUS conservée, idempotente (clé liée au tirage).
        async with SessionLocal() as db:
            row = (await db.execute(
                text(
                    "SELECT type, credits_amount, idempotency_key, "
                    "metadata_json->>'bucket' AS bucket FROM transactions "
                    "WHERE buyer_id = :a AND metadata_json->>'reason' = 'pack_limited_topup' "
                    "AND metadata_json->>'prompt_id' = :p"
                ),
                {"a": artist, "p": str(pid)},
            )).first()
        assert row is not None
        assert row.type == "bonus"
        assert int(row.credits_amount) == topup
        assert row.idempotency_key and row.idempotency_key.startswith("pack_topup:")
        assert row.bucket == "promo"
    finally:
        await _cleanup(artist, buyer)
