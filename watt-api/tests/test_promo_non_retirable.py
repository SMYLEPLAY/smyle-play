"""Fuite « Smyles offerts → argent réel » — Lot 3 (décision Tom 23/09).

La part d'une vente payée par l'acheteur en Smyles PROMO ne devient jamais
retirable : elle est créditée au bénéficiaire dans son bucket `promo` (sous-total
« gagnés — non retirables »), et tracée au ledger (`promo_paid`,
`promo_non_retirable`).

Couvre : vente payée 100 % en promo, 100 % en achetés, en mix ; la revente
(vendeur + artiste d'origine) ; l'invariant de somme ; le sous-total borné au
promo ; l'affichage créateur ; et un garde-fou statique : plus AUCUN chemin de
vente ne crédite `smyles_gagnes` en direct (tous passent par
`credit_sale_revenue`).
"""
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.prompt import Prompt
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import count_bucket_inconsistencies, promo_share
from app.services.resale import buy_resale_atomic, list_prompt_for_resale
from app.services.unlocks import unlock_prompt_atomic
from app.services.users import create_user

PRIX = 10   # vendeur standard : 80 % → 8 pour le vendeur, 2 de commission


async def _user(achetes=0, promo=0) -> uuid.UUID:
    async with SessionLocal() as db:
        uid = (await create_user(db, UserCreate(
            email=f"pytest-promo-{uuid.uuid4().hex[:10]}@smyleplay.example",
            password="12345678"))).id
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE users SET credits_balance = CAST(:a AS int) + CAST(:p AS int), smyles_achetes = :a, "
            "smyles_gagnes = 0, smyles_promo = :p, smyles_promo_gagnes = 0 WHERE id = :u"),
            {"a": achetes, "p": promo, "u": uid})
        # Trophées pré-acquis : aucun bonus ne pollue les soldes mesurés.
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()
    return uid


async def _prompt(artist, price=PRIX, **kw) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(artist_id=artist, title=f"P {uuid.uuid4().hex[:8]}", description="Tagline",
                   prompt_text="X" * 100, price_credits=price, is_published=True, **kw)
        db.add(p)
        await db.commit()
        return p.id


async def _bk(uid) -> dict:
    async with SessionLocal() as db:
        r = (await db.execute(text(
            "SELECT credits_balance b, smyles_achetes a, smyles_gagnes g, smyles_promo p, "
            "smyles_promo_gagnes pg FROM users WHERE id = :u"), {"u": uid})).first()
    return {"b": r.b, "a": r.a, "g": r.g, "p": r.p, "pg": r.pg}


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def _acheter(buyer, pid):
    async with SessionLocal() as db:
        r = await unlock_prompt_atomic(db, buyer_id=buyer, prompt_id=pid)
        await db.commit()
        return r.transaction.id


async def _tx(tid) -> Transaction:
    async with SessionLocal() as db:
        return await db.get(Transaction, tid)


async def _invariant_ok():
    async with SessionLocal() as db:
        return await count_bucket_inconsistencies(db) == 0


# ─── 1. Répartition ────────────────────────────────────────────────────────────

async def test_promo_share_arrondi_au_profit_du_promo():
    assert promo_share(8, 10, 10) == 8        # tout en promo → tout non retirable
    assert promo_share(8, 0, 10) == 0         # rien en promo → tout retirable
    assert promo_share(8, 3, 10) == 3         # 2,4 → 3 (jamais une miette de promo en retirable)
    assert promo_share(8, 1, 10) == 1         # 0,8 → 1
    assert promo_share(0, 5, 10) == 0
    for amount in range(0, 21):
        for pp in range(0, 21):
            part = promo_share(amount, pp, 20)
            assert 0 <= part <= min(amount, pp)
            assert part * 20 >= amount * pp   # au moins la part proportionnelle


@pytest.mark.parametrize(
    "achetes, promo, vendeur_gagnes, vendeur_promo",
    [
        (0, 50, 0, 8),     # 100 % promo : les 8 du vendeur sont NON retirables
        (50, 0, 8, 0),     # 100 % achetés : les 8 sont retirables (comme avant)
        (50, 3, 5, 3),     # mix : 3 promo payés → 3 non retirables (2,4 arrondi), 5 retirables
    ],
)
async def test_vente_directe_promo_achetes_mix(achetes, promo, vendeur_gagnes, vendeur_promo):
    artiste, acheteur = await _user(), await _user(achetes=achetes, promo=promo)
    pid = await _prompt(artiste)
    try:
        tid = await _acheter(acheteur, pid)
        a = await _bk(artiste)
        assert a["g"] == vendeur_gagnes and a["p"] == vendeur_promo and a["pg"] == vendeur_promo
        assert a["b"] == 8
        tx = await _tx(tid)
        assert tx.promo_paid == min(promo, PRIX)
        assert tx.promo_non_retirable == vendeur_promo
        # Conservation : l'acheteur a payé exactement le prix.
        b = await _bk(acheteur)
        assert b["b"] == achetes + promo - PRIX
        assert await _invariant_ok()
    finally:
        await _cleanup(artiste, acheteur)


async def test_non_retirables_se_depensent_mais_ne_se_retirent_pas():
    """Les gains non retirables sont dépensables ; le sous-total ne dépasse
    jamais le promo restant."""
    artiste, acheteur, autre = await _user(), await _user(promo=50), await _user()
    pid = await _prompt(artiste)
    pid2 = await _prompt(autre, price=5)
    try:
        await _acheter(acheteur, pid)
        assert (await _bk(artiste))["pg"] == 8
        await _acheter(artiste, pid2)            # l'artiste dépense 5 (promo en premier)
        a = await _bk(artiste)
        assert a["p"] == 3 and a["pg"] == 3 and a["g"] == 0
        assert await _invariant_ok()
    finally:
        await _cleanup(artiste, acheteur, autre)


# ─── 2. Revente ────────────────────────────────────────────────────────────────

async def test_revente_payee_en_promo_ni_vendeur_ni_artiste_ne_peuvent_retirer():
    artiste, revendeur = await _user(), await _user(achetes=100)
    acheteur = await _user(promo=200)
    pid = await _prompt(artiste, price=50)
    try:
        async with SessionLocal() as db:
            up = (await unlock_prompt_atomic(db, buyer_id=revendeur, prompt_id=pid)).unlocked_prompt.id
            await db.commit()
        async with SessionLocal() as db:
            await list_prompt_for_resale(db, owner_id=revendeur, prompt_id=pid, price=100)
            await db.commit()
        avant_art, avant_rev = await _bk(artiste), await _bk(revendeur)
        async with SessionLocal() as db:
            out = await buy_resale_atomic(db, buyer_id=acheteur, unlocked_prompt_id=up)
            await db.commit()
        apres_art, apres_rev = await _bk(artiste), await _bk(revendeur)
        # Tout payé en promo → rien de retirable de plus, ni pour l'un ni pour l'autre.
        assert apres_rev["g"] == avant_rev["g"]
        assert apres_art["g"] == avant_art["g"]
        assert apres_rev["p"] - avant_rev["p"] == out["seller_cut"]
        assert apres_art["p"] - avant_art["p"] == out["artist_royalty"]
        async with SessionLocal() as db:
            tx = (await db.execute(select(Transaction).where(
                Transaction.type == "resale", Transaction.buyer_id == acheteur))).scalar_one()
        assert tx.promo_paid == 100
        assert tx.promo_non_retirable == out["seller_cut"] + out["artist_royalty"]
        assert tx.metadata_json["promo"] == {"vendeur": out["seller_cut"], "artiste": out["artist_royalty"]}
        assert await _invariant_ok()
    finally:
        await _cleanup(artiste, revendeur, acheteur)


async def test_revente_mix_promo():
    artiste, revendeur = await _user(), await _user(achetes=100)
    acheteur = await _user(achetes=70, promo=30)
    pid = await _prompt(artiste, price=50)
    try:
        async with SessionLocal() as db:
            up = (await unlock_prompt_atomic(db, buyer_id=revendeur, prompt_id=pid)).unlocked_prompt.id
            await db.commit()
        async with SessionLocal() as db:
            await list_prompt_for_resale(db, owner_id=revendeur, prompt_id=pid, price=100)
            await db.commit()
        avant = await _bk(revendeur)
        async with SessionLocal() as db:
            out = await buy_resale_atomic(db, buyer_id=acheteur, unlocked_prompt_id=up)
            await db.commit()
        apres = await _bk(revendeur)
        vp = promo_share(out["seller_cut"], 30, 100)
        assert apres["p"] - avant["p"] == vp
        assert apres["g"] - avant["g"] == out["seller_cut"] - vp
        assert await _invariant_ok()
    finally:
        await _cleanup(artiste, revendeur, acheteur)


# ─── 3. Affichage créateur ─────────────────────────────────────────────────────

async def test_stats_createur_affichent_les_non_retirables(client):

    artiste, acheteur = await _user(), await _user(promo=50)
    pid = await _prompt(artiste)
    try:
        await _acheter(acheteur, pid)
        async with SessionLocal() as db:
            email = (await db.get(User, artiste)).email
        r = await client.post("/auth/login", json={"email": email, "password": "12345678"})
        tok = r.json()["access_token"]
        r = await client.get("/me/creator-stats", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["revenue_smyles"] == 8
        assert d["revenue_non_retirable_smyles"] == 8
        assert d["gagnes_non_retirables_detenus"] == 8
    finally:
        await _cleanup(artiste, acheteur)


# ─── 4. Garde-fou statique ─────────────────────────────────────────────────────

async def test_aucun_chemin_de_vente_ne_credite_gagnes_en_direct():
    """Toute part vendeur passe par credit_sale_revenue (qui isole le promo).
    Seul credits.py écrit `smyles_gagnes + …` ; le versement jackpot des packs
    (décision « jackpot retirable », #539) passe par credit_bucket."""
    services = Path(__file__).resolve().parents[1] / "app" / "services"
    fautifs = []
    for f in services.glob("*.py"):
        if f.name == "credits.py":
            continue
        if re.search(r"smyles_gagnes\s*=\s*smyles_gagnes\s*\+", f.read_text(encoding="utf-8")):
            fautifs.append(f.name)
    assert fautifs == [], fautifs
