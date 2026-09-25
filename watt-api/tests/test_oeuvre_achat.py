"""Achat de l'Œuvre entière (1 son + 1 image) — Lot 3, décision Tom 23/09.

Prix = prix du son + prix de l'image − 10 %, un seul achat atomique ; la remise
est répartie au prorata sur chaque moitié, puis chaque moitié suit son circuit
normal (barème, Pionnier, trésorerie, part vendeur, promo non retirable).
Moitié déjà possédée → l'autre au prix plein. Son en écoute libre → pas
d'achat groupé.
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
from app.models.track import Track
from app.models.transaction import Transaction
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.credits import compute_split, count_bucket_inconsistencies
from app.services.links import link_image_to_track
from app.services.oeuvre_c4_purchase import (
    OeuvreNotBundlable,
    buy_oeuvre_atomic,
    oeuvre_bundle_price,
)
from app.services.treasury import treasury_balance
from app.services.unlocks import AlreadyUnlocked, InsufficientCredits, unlock_prompt_atomic
from app.services.users import create_user

P_SON, P_IMG = 30, 40          # total 70 → Œuvre 63 (remise 7 : 3 son / 4 image)


async def _user(achetes=0, promo=0, public=False) -> uuid.UUID:
    async with SessionLocal() as db:
        uid = (await create_user(db, UserCreate(
            email=f"pytest-oa-{uuid.uuid4().hex[:10]}@smyleplay.example", password="12345678"))).id
    async with SessionLocal() as db:
        await db.execute(text(
            "UPDATE users SET credits_balance = CAST(:a AS int) + CAST(:p AS int), "
            "smyles_achetes = :a, smyles_gagnes = 0, smyles_promo = :p, "
            "profile_public = :pub, artist_name = 'Créatrice' WHERE id = :u"),
            {"a": achetes, "p": promo, "pub": public, "u": uid})
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()
    return uid


async def _oeuvre(artist, *, avec_recette=True) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Renvoie (id de l'Œuvre = id de l'image, id de la recette)."""
    async with SessionLocal() as db:
        rec = None
        if avec_recette:
            rec = Prompt(artist_id=artist, title="Son de l'œuvre", description="Tagline",
                         prompt_text="X" * 100, price_credits=P_SON, is_published=True)
            db.add(rec)
            await db.flush()
        trk = Track(artist_id=artist, title="Son de l'œuvre", prompt_id=rec.id if rec else None)
        img = Prompt(artist_id=artist, title="Image de l'œuvre", description="Tagline",
                     prompt_text="un néon", price_credits=P_IMG, is_published=True,
                     product_type="image", image_platform="chatgpt", image_model_version="gpt-4o")
        db.add_all([trk, img])
        await db.flush()
        await link_image_to_track(db, owner_id=artist, track_id=trk.id, image_id=img.id)
        await db.commit()
        return img.id, (rec.id if rec else None)


async def _bk(uid) -> dict:
    async with SessionLocal() as db:
        r = (await db.execute(text(
            "SELECT credits_balance b, smyles_achetes a, smyles_gagnes g, smyles_promo p "
            "FROM users WHERE id = :u"), {"u": uid})).first()
    return {"b": r.b, "a": r.a, "g": r.g, "p": r.p}


async def _acheter(buyer, oid):
    async with SessionLocal() as db:
        out = await buy_oeuvre_atomic(db, buyer_id=buyer, oeuvre_id=oid)
        await db.commit()
    return out


async def _possede(buyer, *pids) -> int:
    async with SessionLocal() as db:
        return int((await db.execute(select(UnlockedPrompt.id).where(
            UnlockedPrompt.current_owner_id == buyer,
            UnlockedPrompt.prompt_id.in_(list(pids))))).all().__len__())


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(text("UPDATE prompts SET linked_prompt_id = NULL, linked_track_id = NULL "
                                  "WHERE artist_id = :u"), {"u": uid})
            await db.execute(delete(Track).where(Track.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.execute(text("UPDATE users SET credits_balance = 0, smyles_achetes = 0, "
                              "smyles_gagnes = 0, smyles_promo = 0 WHERE is_treasury = TRUE"))
        await db.commit()


# ─── 1. Prix ───────────────────────────────────────────────────────────────────

async def test_prix_moins_dix_pourcent_reparti_au_prorata():
    assert oeuvre_bundle_price(30, 40) == (63, 3, 4)
    assert oeuvre_bundle_price(3, 3) == (5, 0, 1)        # arrondi au profit de l'acheteur
    for ps in range(3, 60, 7):
        for pi in range(3, 60, 11):
            prix, rs, ri = oeuvre_bundle_price(ps, pi)
            assert prix + rs + ri == ps + pi                # conservation
            assert rs <= ps and ri <= pi


# ─── 2. Achat groupé ───────────────────────────────────────────────────────────

async def test_achat_de_l_oeuvre_entiere_atomique(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_MARKET_SMYLES", True)
    artiste, acheteur = await _user(public=True), await _user(achetes=100)
    oid, rec = await _oeuvre(artiste)
    try:
        async with SessionLocal() as db:
            tresor_avant = (await treasury_balance(db))["total"]
        out = await _acheter(acheteur, oid)
        assert out["mode"] == "oeuvre" and out["paid"] == 63 and out["remise"] == 7
        assert await _possede(acheteur, oid, rec) == 2
        # Chaque moitié : sa ligne de ledger, sa remise, son split (vendeur standard 80 %).
        async with SessionLocal() as db:
            txs = (await db.execute(select(Transaction).where(
                Transaction.buyer_id == acheteur, Transaction.type == "unlock"))).scalars().all()
            tresor_apres = (await treasury_balance(db))["total"]
        paid = sorted(t.credits_amount for t in txs)
        assert paid == [27, 36]                             # 30−3 et 40−4
        for t in txs:
            assert t.metadata_json["oeuvre_id"] == str(oid)
            assert (t.artist_revenue, t.platform_fee) == compute_split(t.credits_amount, 80)
        rev = sum(t.artist_revenue for t in txs)
        com = sum(t.platform_fee for t in txs)
        assert (await _bk(acheteur))["b"] == 100 - 63
        assert (await _bk(artiste))["g"] == rev
        assert tresor_apres - tresor_avant == com           # commission → trésorerie
        assert rev + com == 63                              # conservation stricte
        async with SessionLocal() as db:
            assert await count_bucket_inconsistencies(db) == 0
    finally:
        await _cleanup(artiste, acheteur)


async def test_pionnier_taux_le_plus_favorable_sur_chaque_moitie(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_PIONEER", True)
    artiste, acheteur = await _user(public=True), await _user(achetes=100)
    async with SessionLocal() as db:
        libre = (await db.execute(text(
            "SELECT min(r) FROM generate_series(1,100) r "
            "WHERE NOT EXISTS (SELECT 1 FROM users WHERE pioneer_rank = r)"))).scalar_one()
        await db.execute(text("UPDATE users SET is_pioneer = TRUE, pioneer_rank = :r WHERE id = :u"),
                         {"r": libre, "u": artiste})
        await db.commit()
    oid, _ = await _oeuvre(artiste)
    try:
        await _acheter(acheteur, oid)
        async with SessionLocal() as db:
            txs = (await db.execute(select(Transaction).where(
                Transaction.buyer_id == acheteur, Transaction.type == "unlock"))).scalars().all()
        for t in txs:
            assert (t.artist_revenue, t.platform_fee) == compute_split(t.credits_amount, 90)
    finally:
        await _cleanup(artiste, acheteur)


async def test_moitie_deja_possedee_l_autre_au_prix_plein():
    artiste, acheteur = await _user(public=True), await _user(achetes=200)
    oid, rec = await _oeuvre(artiste)
    try:
        async with SessionLocal() as db:
            await unlock_prompt_atomic(db, buyer_id=acheteur, prompt_id=rec)   # le son, seul
            await db.commit()
        avant = (await _bk(acheteur))["b"]
        out = await _acheter(acheteur, oid)
        assert out["mode"] == "moitie_manquante" and out["remise"] == 0
        assert out["paid"] == P_IMG                          # prix plein, sans remise
        assert avant - (await _bk(acheteur))["b"] == P_IMG
        with pytest.raises(AlreadyUnlocked):
            await _acheter(acheteur, oid)                    # tout possédé → refus
    finally:
        await _cleanup(artiste, acheteur)


async def test_pas_d_achat_groupe_si_son_en_ecoute_libre(client):
    artiste, acheteur = await _user(public=True), await _user(achetes=100)
    oid, _ = await _oeuvre(artiste, avec_recette=False)
    try:
        with pytest.raises(OeuvreNotBundlable):
            await _acheter(acheteur, oid)
        assert (await _bk(acheteur))["b"] == 100
        r = await client.get(f"/watt/oeuvres/{oid}")
        assert r.status_code == 200 and r.json()["bundle"] is None
    finally:
        await _cleanup(artiste, acheteur)


async def test_solde_insuffisant_rien_ne_bouge():
    artiste, acheteur = await _user(public=True), await _user(achetes=62)   # 63 requis
    oid, rec = await _oeuvre(artiste)
    try:
        with pytest.raises(InsufficientCredits):
            await _acheter(acheteur, oid)
        assert (await _bk(acheteur))["b"] == 62
        assert await _possede(acheteur, oid, rec) == 0      # atomique : aucune moitié
    finally:
        await _cleanup(artiste, acheteur)


async def test_paye_en_promo_moities_non_retirables():
    artiste, acheteur = await _user(public=True), await _user(promo=100)
    oid, _ = await _oeuvre(artiste)
    try:
        await _acheter(acheteur, oid)
        a = await _bk(artiste)
        assert a["g"] == 0 and a["p"] > 0                    # rien de retirable
        async with SessionLocal() as db:
            txs = (await db.execute(select(Transaction).where(
                Transaction.buyer_id == acheteur, Transaction.type == "unlock"))).scalars().all()
        assert all(t.promo_paid == t.credits_amount for t in txs)
        assert sum(t.promo_non_retirable for t in txs) == a["p"]
    finally:
        await _cleanup(artiste, acheteur)


async def test_double_clic_concurrent_un_seul_achat():
    artiste, acheteur = await _user(public=True), await _user(achetes=500)
    oid, rec = await _oeuvre(artiste)
    try:
        res = await asyncio.wait_for(asyncio.gather(
            _acheter(acheteur, oid), _acheter(acheteur, oid), return_exceptions=True), timeout=60)
        ok = [r for r in res if not isinstance(r, Exception)]
        assert len(ok) == 1 and isinstance([r for r in res if isinstance(r, Exception)][0], AlreadyUnlocked)
        assert (await _bk(acheteur))["b"] == 500 - 63       # débité une seule fois
        assert await _possede(acheteur, oid, rec) == 2
    finally:
        await _cleanup(artiste, acheteur)


# ─── 3. API ────────────────────────────────────────────────────────────────────

async def test_api_offre_et_achat(client, test_user, auth_headers):
    artiste = await _user(public=True)
    oid, _ = await _oeuvre(artiste)
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET credits_balance = 100, smyles_achetes = 100, "
                              "smyles_gagnes = 0, smyles_promo = 0 WHERE id = :u"), {"u": test_user["id"]})
        await db.commit()
    try:
        d = (await client.get(f"/watt/oeuvres/{oid}")).json()
        assert d["bundle"] == {"priceCredits": 63, "fullPriceCredits": 70,
                               "discountPct": 10, "mode": "oeuvre"}
        r = await client.post(f"/watt/oeuvres/{oid}/acheter")
        assert r.status_code == 401
        r = await client.post(f"/watt/oeuvres/{oid}/acheter", headers=auth_headers)
        assert r.status_code == 201, r.text
        d = (await client.get(f"/watt/oeuvres/{oid}", headers=auth_headers)).json()
        assert d["bundle"]["mode"] == "possedee"
        r = await client.post(f"/watt/oeuvres/{oid}/acheter", headers=auth_headers)
        assert r.status_code == 409
    finally:
        await _cleanup(artiste)
