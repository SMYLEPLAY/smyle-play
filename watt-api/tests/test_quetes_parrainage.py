"""Étape 3 — quêtes de parrainage (FEATURE_QUETES_PARRAINAGE).

  - flag OFF (défaut) : POST /referrals/quetes → 404, rien n'est versé ;
  - un filleul compte s'il est ACTIF (définition unique) ET validé par le
    parrainage de base (status 'rewarded' → plafonds quotidien/IP conservés) ;
  - palier 3 → +10 Smyles en bucket PROMO (non retirable), invariant de somme ;
  - idempotent par (parrain, palier) : rappel, double appel simultané ;
  - plafond global sur 24 h : le palier attend, rien n'est perdu ;
  - badge Ambassadeur au palier 25.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import quetes_parrainage as qp
from app.services.users import create_user


@pytest.fixture
def quetes_on(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_QUETES_PARRAINAGE", True)
    monkeypatch.setattr(settings, "QUETES_PARRAINAGE_PALIERS", [(3, 10), (10, 50), (25, 150)])
    monkeypatch.setattr(settings, "QUETES_PARRAINAGE_PALIER_AMBASSADEUR", 25)
    monkeypatch.setattr(settings, "QUETES_PARRAINAGE_PLAFOND_24H", 10**9)


async def _user() -> uuid.UUID:
    email = f"pytest-qp-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET email_verified = TRUE WHERE id = :u"), {"u": uid})
        await db.commit()
    return uid


async def _filleul(parrain, *, actif=True, statut="rewarded", cible=None) -> uuid.UUID:
    f = await _user()
    async with SessionLocal() as db:
        await db.execute(text(
            "INSERT INTO referrals (id, referrer_id, referred_id, status, reward_credits, rewarded_at) "
            "VALUES (:i, :p, :f, :s, 10, :r)"),
            {"i": uuid.uuid4(), "p": parrain, "f": f, "s": statut,
             "r": datetime.now(timezone.utc) if statut == "rewarded" else None})
        if actif:  # action réelle récente : suivre un créateur
            await db.execute(text(
                "INSERT INTO user_follows (id, follower_id, followee_id) VALUES (:i, :f, :t)"),
                {"i": uuid.uuid4(), "f": f, "t": cible or parrain})
        await db.commit()
    return f


async def _buckets(uid):
    async with SessionLocal() as db:
        r = (await db.execute(text(
            "SELECT smyles_achetes a, smyles_gagnes g, smyles_promo p, credits_balance b "
            "FROM users WHERE id = :u"), {"u": uid})).first()
    return {"a": r.a, "g": r.g, "p": r.p, "b": r.b}


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(text("DELETE FROM user_follows WHERE follower_id = :u OR followee_id = :u"), {"u": uid})
            await db.execute(text("DELETE FROM referrals WHERE referrer_id = :u OR referred_id = :u"), {"u": uid})
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


def test_defauts_config():
    from app.config import Settings
    s = Settings()
    assert s.FEATURE_QUETES_PARRAINAGE is False
    # Décision Tom du 9/10/2026 (redénomination ×10) : 30 / 100 / 250 Smyles.
    assert [tuple(p) for p in s.QUETES_PARRAINAGE_PALIERS] == [(3, 30), (10, 100), (25, 250)]
    assert s.QUETES_PARRAINAGE_PALIER_AMBASSADEUR == 25
    assert s.QUETES_PARRAINAGE_PLAFOND_24H == 30000


async def test_flag_off_404(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_QUETES_PARRAINAGE", False)
    r = await client.post("/referrals/quetes", headers=auth_headers)
    assert r.status_code == 404


async def test_seuls_les_filleuls_actifs_et_valides_comptent(quetes_on):
    parrain = await _user()
    fs = [await _filleul(parrain) for _ in range(2)]
    fs.append(await _filleul(parrain, actif=False))          # inactif
    fs.append(await _filleul(parrain, statut="pending"))     # pas encore validé
    try:
        async with SessionLocal() as db:
            assert await qp.compter_filleuls_actifs(db, parrain) == 2
            res = await qp.verifier_et_verser_quetes(db, parrain)
            await db.commit()
        assert res["filleuls_actifs"] == 2
        assert res["nouveaux_versements"] == []
        assert res["prochain"] == {"seuil": 3, "smyles": 10, "manquants": 1}
    finally:
        await _cleanup(*fs, parrain)


async def test_palier_3_verse_10_promo_une_seule_fois(client, test_user, auth_headers, quetes_on):
    parrain = test_user["id"]
    fs = [await _filleul(parrain) for _ in range(3)]
    try:
        avant = await _buckets(parrain)
        r = await client.post("/referrals/quetes", headers=auth_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nouveaux_versements"] == [{"seuil": 3, "smyles": 10}]
        assert d["paliers"][0] == {"seuil": 3, "smyles": 10, "atteint": True, "verse": True}
        apres = await _buckets(parrain)
        assert apres["p"] - avant["p"] == 10          # bucket PROMO
        assert apres["g"] == avant["g"]               # jamais retirable
        assert apres["a"] + apres["g"] + apres["p"] == apres["b"]

        # Rappel : aucun second versement.
        r = await client.post("/referrals/quetes", headers=auth_headers)
        assert r.json()["nouveaux_versements"] == []
        assert (await _buckets(parrain))["p"] == apres["p"]

        async with SessionLocal() as db:
            n = (await db.execute(text(
                "SELECT count(*) FROM transactions WHERE idempotency_key = :k AND type = 'bonus'"),
                {"k": qp.cle(parrain, 3)})).scalar_one()
        assert n == 1
    finally:
        await _cleanup(*fs)


async def test_double_appel_simultane_un_seul_versement(quetes_on):
    parrain = await _user()
    fs = [await _filleul(parrain) for _ in range(3)]
    try:
        async def _un():
            async with SessionLocal() as db:
                res = await qp.verifier_et_verser_quetes(db, parrain)
                await db.commit()
                return res

        avant = (await _buckets(parrain))["p"]
        a, b = await asyncio.gather(_un(), _un())
        assert len(a["nouveaux_versements"]) + len(b["nouveaux_versements"]) == 1
        assert (await _buckets(parrain))["p"] - avant == 10
    finally:
        await _cleanup(*fs, parrain)


async def test_plafond_global_24h(quetes_on, monkeypatch):
    parrain = await _user()
    fs = [await _filleul(parrain) for _ in range(3)]
    try:
        avant = (await _buckets(parrain))["p"]
        async with SessionLocal() as db:
            deja = await qp._verse_24h(db)
        monkeypatch.setattr(settings, "QUETES_PARRAINAGE_PLAFOND_24H", deja + 5)
        async with SessionLocal() as db:
            res = await qp.verifier_et_verser_quetes(db, parrain)
            await db.commit()
        assert res["nouveaux_versements"] == []            # plafond : attend
        assert (await _buckets(parrain))["p"] == avant
        monkeypatch.setattr(settings, "QUETES_PARRAINAGE_PLAFOND_24H", 10**9)
        async with SessionLocal() as db:
            res = await qp.verifier_et_verser_quetes(db, parrain)
            await db.commit()
        assert res["nouveaux_versements"] == [{"seuil": 3, "smyles": 10}]  # rien de perdu
    finally:
        await _cleanup(*fs, parrain)


async def test_badge_ambassadeur(quetes_on, monkeypatch):
    # Paliers réduits pour le test : l'ambassadeur au 2e palier (4 filleuls).
    monkeypatch.setattr(settings, "QUETES_PARRAINAGE_PALIERS", [(2, 10), (4, 150)])
    monkeypatch.setattr(settings, "QUETES_PARRAINAGE_PALIER_AMBASSADEUR", 4)
    parrain = await _user()
    fs = [await _filleul(parrain) for _ in range(4)]
    try:
        avant = (await _buckets(parrain))["p"]
        async with SessionLocal() as db:
            res = await qp.verifier_et_verser_quetes(db, parrain)
            await db.commit()
        assert [v["seuil"] for v in res["nouveaux_versements"]] == [2, 4]
        assert res["ambassadeur"] is True and res["prochain"] is None
        assert (await _buckets(parrain))["p"] - avant == 160
        async with SessionLocal() as db:
            assert (await qp.progression_quetes(db, parrain))["ambassadeur"] is True
    finally:
        await _cleanup(*fs, parrain)
