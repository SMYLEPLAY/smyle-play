"""Statut PIONNIER — commission plafonnee a 10 %, regle du TAUX LE PLUS
FAVORABLE (Brique 1).

  - un Pionnier ne paie jamais plus de 10 % ;
  - mais il ne perd pas un meilleur taux acquis par son palier (Mythique = 5 %) ;
  - et le taux Pionnier ne s'applique PAS a la revente (decision Tom) : celle-ci
    garde son split fixe royaltie 30 / plateforme 20 / vendeur 50.

L'ATTRIBUTION des 100 premiers createurs n'est pas testee ici : elle n'est pas
codee (Brique 2). Seul le marqueur et son effet sur le taux le sont.
"""
import uuid

import pytest
from sqlalchemy import delete, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.prompt import Prompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.resale import (
    RESALE_ARTIST_PCT,
    RESALE_PLATFORM_PCT,
    buy_resale_atomic,
    list_prompt_for_resale,
)
from app.services.tiers import (
    PIONEER_COMMISSION_PCT,
    artist_pct_for,
    commission_pct_for,
)
from app.services.unlocks import unlock_prompt_atomic
from app.services.users import create_user


# ---------------------------------------------------------------------------
# 1. Regle du taux le plus favorable (unitaire, exhaustif)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "tier, pionnier, commission_attendue",
    [
        ("standard", False, 20),
        ("standard", True, 10),   # le pionnier ameliore
        ("premium", False, 12),
        ("premium", True, 10),    # le pionnier ameliore
        ("mythique", False, 5),
        ("mythique", True, 5),    # le palier reste MEILLEUR -> on le garde
        (None, False, 20),        # palier inconnu -> standard (historique)
        (None, True, 10),
    ],
)
def test_taux_le_plus_favorable(tier, pionnier, commission_attendue):
    assert commission_pct_for(tier, pionnier) == commission_attendue
    assert artist_pct_for(tier, pionnier) == 100 - commission_attendue


def test_un_pionnier_ne_paie_jamais_plus_que_le_plafond():
    for tier in ("standard", "premium", "mythique", None, "inconnu"):
        assert commission_pct_for(tier, True) <= PIONEER_COMMISSION_PCT


def test_le_pionnier_ne_degrade_jamais_un_meilleur_taux():
    for tier in ("standard", "premium", "mythique", None, "inconnu"):
        assert commission_pct_for(tier, True) <= commission_pct_for(tier, False)


# ---------------------------------------------------------------------------
# Helpers d'integration
# ---------------------------------------------------------------------------

async def _user(balance: int, *, pionnier: bool = False, tier: str = "standard"):
    email = f"pytest-pio-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(
            text(
                "UPDATE users SET credits_balance = :b, smyles_achetes = :b, "
                "smyles_gagnes = 0, smyles_promo = 0, is_pioneer = :pio, "
                "tier = :tier WHERE id = :u"
            ),
            {"b": balance, "pio": pionnier, "tier": tier, "u": uid},
        )
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()
    return uid


async def _prompt(artist_id, price):
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


async def _gagnes(uid):
    async with SessionLocal() as db:
        r = (await db.execute(
            text("SELECT smyles_gagnes FROM users WHERE id = :u"), {"u": uid}
        )).first()
    return int(r.smyles_gagnes)


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.execute(
            text(
                "UPDATE users SET credits_balance = 0, smyles_achetes = 0, "
                "smyles_gagnes = 0, smyles_promo = 0 WHERE is_treasury = TRUE"
            )
        )
        await db.commit()


# ---------------------------------------------------------------------------
# 2. Effet reel sur une vente (marche primaire)
# ---------------------------------------------------------------------------

async def test_vente_dun_pionnier_commission_10_pct():
    """Vendeur standard PIONNIER : la plateforme prend 10 % (et non 20 %),
    le createur garde 90 %. Observable sur la part vendeur ET sur la ligne de
    ledger — independamment de la destination de la commission (autre PR)."""
    price = 100
    buyer, seller = await _user(1000), await _user(0, pionnier=True)
    try:
        pid = await _prompt(seller, price)
        g_av = await _gagnes(seller)
        async with SessionLocal() as db:
            res = await unlock_prompt_atomic(db, buyer_id=buyer, prompt_id=pid)
            await db.commit()
            commission = int(res.transaction.platform_fee)
            part_vendeur = int(res.transaction.artist_revenue)
        assert commission == 10                      # 10 %, pas 20 %
        assert part_vendeur == 90
        assert await _gagnes(seller) - g_av == 90    # la part vendeur est retirable
    finally:
        await _cleanup(buyer, seller)


async def test_vente_dun_mythique_pionnier_garde_5_pct():
    """Le pionnier ne DEGRADE pas un meilleur taux : Mythique reste a 5 %."""
    price = 100
    buyer = await _user(1000)
    seller = await _user(0, pionnier=True, tier="mythique")
    try:
        pid = await _prompt(seller, price)
        g_av = await _gagnes(seller)
        async with SessionLocal() as db:
            res = await unlock_prompt_atomic(db, buyer_id=buyer, prompt_id=pid)
            await db.commit()
            commission = int(res.transaction.platform_fee)
        assert commission == 5                       # 5 %, le palier reste meilleur
        assert await _gagnes(seller) - g_av == 95
    finally:
        await _cleanup(buyer, seller)


# ---------------------------------------------------------------------------
# 3. La revente N'EST PAS concernee par le taux Pionnier (decision Tom)
# ---------------------------------------------------------------------------

async def test_revente_ignore_le_taux_pionnier():
    """Le revendeur est Pionnier : la revente garde son split FIXE
    (royaltie 30 / plateforme 20 / vendeur 50). La commission encaissee doit
    rester 20 %, pas 10 %."""
    prix_initial, prix_revente = 50, 100
    artiste = await _user(0)                      # auteur d'origine
    revendeur = await _user(1000, pionnier=True)  # PIONNIER
    acheteur = await _user(1000)
    try:
        pid = await _prompt(artiste, prix_initial)
        # Le revendeur acquiert d'abord le prompt, puis le met en revente.
        async with SessionLocal() as db:
            res = await unlock_prompt_atomic(db, buyer_id=revendeur, prompt_id=pid)
            await db.commit()
            up_id = res.unlocked_prompt.id
        async with SessionLocal() as db:
            await list_prompt_for_resale(
                db, owner_id=revendeur, prompt_id=pid, price=prix_revente
            )
            await db.commit()

        async with SessionLocal() as db:
            out = await buy_resale_atomic(
                db, buyer_id=acheteur, unlocked_prompt_id=up_id
            )
            await db.commit()

        commission_revente = prix_revente * RESALE_PLATFORM_PCT // 100
        assert commission_revente == 20                      # 20 %, pas 10 %
        # Le revendeur est Pionnier : son taux 10 % ne doit PAS s'appliquer ici.
        assert int(out["platform_fee"]) == commission_revente
        # Le split de revente reste bien celui d'origine.
        assert (RESALE_ARTIST_PCT, RESALE_PLATFORM_PCT) == (30, 20)
    finally:
        await _cleanup(artiste, revendeur, acheteur)
