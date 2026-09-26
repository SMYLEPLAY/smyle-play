"""Étape 2 — outils admin + sécurité du paiement.

Couvre :
  1. écran Pionniers : liste réservée à l'admin ;
  2. contenus retirés : journal du retrait (motif, état d'avant), liste,
     restauration par le SEUL chemin admin (la base refuse toute autre voie),
     motif obligatoire, état d'avant remis, journal de la restauration ;
  3. clé Stripe de TEST : achat réservé aux admins, Smyles marqués dans le
     registre et comptés à part dans les chiffres ;
  4. remboursement de Smyles déjà dépensés : compte bloqué pour l'achat par
     carte, signalé avec le manque, débloquable par l'admin avec motif ;
     aucun solde touché ;
  5. modération accessible aux administrateurs ; bouton « Signaler » sur les
     fiches ADN / ADN visuel / voix ; identifiants de migration ≤ 32 caractères.
"""
import hashlib
import hmac
import json
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import stripe_payments
from app.services.credits import count_bucket_inconsistencies
from app.services.moderation import takedown_content
from app.services.pioneer import award_pioneer
from app.services.users import create_user

SECRET_WH = "whsec_" + "e" * 24          # fabriqués pour les tests
CLE_DE_TEST = "sk_test_" + "e" * 24


async def _user(**flags) -> uuid.UUID:
    async with SessionLocal() as db:
        uid = (await create_user(db, UserCreate(
            email=f"pytest-e2-{uuid.uuid4().hex[:10]}@smyleplay.example", password="12345678"))).id
    if flags:
        sets = ", ".join(f"{k} = :{k}" for k in flags)
        async with SessionLocal() as db:
            await db.execute(text(f"UPDATE users SET {sets} WHERE id = :u"), {**flags, "u": uid})
            await db.commit()
    return uid


async def _admin(test_user):
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET is_admin = TRUE WHERE id = :u"), {"u": test_user["id"]})
        await db.commit()


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(Track).where(Track.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def _prompt(uid, published=True) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(artist_id=uid, title="Contenu signalé", description="Tagline",
                   prompt_text="X" * 100, price_credits=10, is_published=published)
        db.add(p)
        await db.commit()
        return p.id


# ─── 1. Pionniers ──────────────────────────────────────────────────────────────

async def test_liste_des_pionniers_reservee_admin(client, test_user, auth_headers):
    uid = await _user()
    await _prompt(uid)
    async with SessionLocal() as db:
        rang = await award_pioneer(db, uid, live=False)
        await db.commit()
    try:
        assert (await client.get("/admin/pioneer/liste", headers=auth_headers)).status_code == 403
        await _admin(test_user)
        r = await client.get("/admin/pioneer/liste", headers=auth_headers)
        assert r.status_code == 200
        mine = [p for p in r.json()["pionniers"] if p["user_id"] == str(uid)]
        assert mine and mine[0]["rang"] == rang and mine[0]["premiere_oeuvre"]
        assert "@" not in (mine[0]["pseudo"] or "")          # jamais d'email en clair
    finally:
        await _cleanup(uid)


# ─── 2. Contenus retirés : restauration ────────────────────────────────────────

async def test_retrait_journalise_puis_liste(client, test_user, auth_headers):
    await _admin(test_user)
    uid = await _user(artist_name="Auteur test")
    pid = await _prompt(uid)
    try:
        async with SessionLocal() as db:
            await takedown_content(db, "prompt", str(pid), "Plagiat manifeste", admin_id=test_user["id"])
            await db.commit()
        async with SessionLocal() as db:
            j = (await db.execute(text(
                "SELECT admin_id, motif, details FROM admin_journal WHERE action = 'retrait' AND cible_id = :c"),
                {"c": str(pid)})).first()
        assert j.admin_id == test_user["id"] and j.motif == "Plagiat manifeste"
        assert j.details == {"etait_publie": True}
        r = await client.get("/admin/contenus-retires", headers=auth_headers)
        mine = [c for c in r.json()["contenus"] if c["id"] == str(pid)]
        assert mine and mine[0]["motif"] == "Plagiat manifeste" and mine[0]["auteur"] == "Auteur test"
    finally:
        await _cleanup(uid)


async def test_la_base_refuse_toute_restauration_hors_chemin_admin():
    uid = await _user()
    pid = await _prompt(uid)
    try:
        async with SessionLocal() as db:
            await takedown_content(db, "prompt", str(pid), "test")
            await db.commit()
        with pytest.raises(DBAPIError):
            async with SessionLocal() as db:
                await db.execute(text("UPDATE prompts SET taken_down_at = NULL WHERE id = :i"), {"i": pid})
                await db.commit()
        async with SessionLocal() as db:
            assert (await db.get(Prompt, pid)).taken_down_at is not None
    finally:
        await _cleanup(uid)


async def test_restauration_admin_motif_obligatoire_et_etat_remis(client, test_user, auth_headers):
    uid = await _user()
    pid = await _prompt(uid)
    async with SessionLocal() as db:
        await takedown_content(db, "prompt", str(pid), "Erreur de modération")
        await db.commit()
    try:
        url = f"/admin/contenus-retires/prompt/{pid}/restaurer"
        assert (await client.post(url, headers=auth_headers, json={"reason": "ok ok"})).status_code == 403
        await _admin(test_user)
        assert (await client.post(url, headers=auth_headers, json={"reason": ""})).status_code == 422
        r = await client.post(url, headers=auth_headers, json={"reason": "Signalement abusif"})
        assert r.status_code == 200, r.text
        async with SessionLocal() as db:
            p = await db.get(Prompt, pid)
            assert p.taken_down_at is None and p.is_published is True
            j = (await db.execute(text(
                "SELECT admin_id, motif FROM admin_journal WHERE action = 'restauration' AND cible_id = :c"),
                {"c": str(pid)})).first()
        assert j.admin_id == test_user["id"] and j.motif == "Signalement abusif"
        # Déjà restauré → refus clair.
        assert (await client.post(url, headers=auth_headers, json={"reason": "encore"})).status_code == 422
        # Après une restauration, la garde reste active pour la suite.
        async with SessionLocal() as db:
            await takedown_content(db, "prompt", str(pid), "retrait 2")
            await db.commit()
        with pytest.raises(DBAPIError):
            async with SessionLocal() as db:
                await db.execute(text("UPDATE prompts SET taken_down_at = NULL WHERE id = :i"), {"i": pid})
                await db.commit()
    finally:
        await _cleanup(uid)


async def test_restauration_brouillon_reste_brouillon_et_morceau(client, test_user, auth_headers):
    await _admin(test_user)
    uid = await _user()
    brouillon = await _prompt(uid, published=False)
    async with SessionLocal() as db:
        t = Track(artist_id=uid, title="Morceau retiré")
        db.add(t)
        await db.commit()
        tid = t.id
        await takedown_content(db, "prompt", str(brouillon), "x")
        await takedown_content(db, "track", str(tid), "x")
        await db.commit()
    try:
        for typ, cid in (("prompt", brouillon), ("track", tid)):
            r = await client.post(f"/admin/contenus-retires/{typ}/{cid}/restaurer",
                                  headers=auth_headers, json={"reason": "restauration test"})
            assert r.status_code == 200, r.text
        async with SessionLocal() as db:
            assert (await db.get(Prompt, brouillon)).is_published is False   # état d'avant
            t = await db.get(Track, tid)
            assert t.is_deleted is False and t.taken_down_at is None
    finally:
        await _cleanup(uid)


async def test_retrait_ancien_sans_journal_revient_en_ligne(client, test_user, auth_headers):
    await _admin(test_user)
    uid = await _user()
    pid = await _prompt(uid)
    async with SessionLocal() as db:
        await db.execute(text("UPDATE prompts SET taken_down_at = now() WHERE id = :i"), {"i": pid})
        await db.commit()
    try:
        r = await client.get("/admin/contenus-retires", headers=auth_headers)
        mine = [c for c in r.json()["contenus"] if c["id"] == str(pid)]
        assert mine[0]["motif"] == "Motif non enregistré"
        r = await client.post(f"/admin/contenus-retires/prompt/{pid}/restaurer",
                              headers=auth_headers, json={"reason": "Retrait antérieur"})
        assert r.status_code == 200
        async with SessionLocal() as db:
            assert (await db.get(Prompt, pid)).is_published is True
    finally:
        await _cleanup(uid)


# ─── 3. Clé Stripe de TEST : réservé aux admins ────────────────────────────────

@pytest.fixture
def stripe_test(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", CLE_DE_TEST)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET_WH)

    async def _faux(path, data):
        sid = "cs_test_" + uuid.uuid4().hex
        return {"id": sid, "url": f"https://checkout.stripe.com/c/pay/{sid}"}

    monkeypatch.setattr(stripe_payments, "_stripe_post", _faux)


def _sig(corps: bytes) -> str:
    ts = int(time.time())
    return f"t={ts},v1=" + hmac.new(SECRET_WH.encode(), f"{ts}.".encode() + corps, hashlib.sha256).hexdigest()


async def _webhook(client, evt):
    corps = json.dumps(evt).encode()
    return await client.post("/stripe/webhook", content=corps, headers={"Stripe-Signature": _sig(corps)})


async def _preseed(uid, achetes=0):
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET credits_balance = :a, smyles_achetes = :a, "
                              "smyles_gagnes = 0, smyles_promo = 0 WHERE id = :u"), {"a": achetes, "u": uid})
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()


BODY = {"pack_id": "pack_10", "renonce_retractation": True}


async def test_cle_de_test_achat_reserve_aux_admins(client, test_user, auth_headers, stripe_test):
    await _preseed(test_user["id"])
    r = await client.post("/credits/checkout", headers=auth_headers, json=BODY)
    assert r.status_code == 503                                    # client ordinaire
    d = (await client.get("/credits/packs", headers=auth_headers)).json()
    assert d["paiement_carte"] is False and "bientôt" in d["message"]
    d = (await client.get("/credits/packs")).json()                # visiteur
    assert d["paiement_carte"] is False
    await _admin(test_user)
    assert (await client.get("/credits/packs", headers=auth_headers)).json()["paiement_carte"] is True
    r = await client.post("/credits/checkout", headers=auth_headers, json=BODY)
    assert r.status_code == 200, r.text


async def test_smyles_de_test_marques_et_comptes_a_part(client, test_user, auth_headers, stripe_test):
    await _admin(test_user)
    await _preseed(test_user["id"])
    async with SessionLocal() as db:
        from app.services.beta_dashboard import beta_dashboard_data
        avant = (await beta_dashboard_data(db))["masse_smyles"]["crees"]
    sid = (await client.post("/credits/checkout", headers=auth_headers, json=BODY)).json()["session_id"]
    async with SessionLocal() as db:
        assert (await db.execute(text("SELECT mode_test FROM stripe_payments WHERE session_id = :s"),
                                 {"s": sid})).scalar_one() is True
    evt = {"id": f"evt_{uuid.uuid4().hex}", "type": "checkout.session.completed",
           "data": {"object": {"id": sid, "payment_status": "paid", "amount_total": 800,
                               "currency": "eur", "payment_intent": f"pi_{uuid.uuid4().hex}"}}}
    assert (await _webhook(client, evt)).json()["statut"] == "credite"
    async with SessionLocal() as db:
        meta = (await db.execute(text(
            "SELECT metadata_json FROM transactions WHERE idempotency_key = :k"),
            {"k": f"stripe_session:{sid}"})).scalar_one()
        apres = (await beta_dashboard_data(db))["masse_smyles"]["crees"]
    assert meta["stripe_test"] is True
    assert apres["achats_carte_de_test"] == avant["achats_carte_de_test"] + 10
    assert apres["achats_de_packs"] == avant["achats_de_packs"]    # pas un vrai achat


# ─── 4. Remboursement de Smyles déjà dépensés : blocage + déblocage ────────────

async def test_manque_bloque_l_achat_carte_puis_deblocage_admin(client, test_user, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_" + "e" * 24)   # factice
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET_WH)

    async def _faux(path, data):
        sid = "cs_live_" + uuid.uuid4().hex
        return {"id": sid, "url": f"https://checkout.stripe.com/c/pay/{sid}"}

    monkeypatch.setattr(stripe_payments, "_stripe_post", _faux)
    uid = test_user["id"]
    await _preseed(uid)
    sid = (await client.post("/credits/checkout", headers=auth_headers, json=BODY)).json()["session_id"]
    pi = f"pi_{uuid.uuid4().hex}"
    await _webhook(client, {"id": f"evt_{uuid.uuid4().hex}", "type": "checkout.session.completed",
                            "data": {"object": {"id": sid, "payment_status": "paid", "amount_total": 800,
                                                "currency": "eur", "payment_intent": pi}}})
    # Il dépense tout (les 10 achetés passent en gagnés chez un tiers : simulé).
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET smyles_achetes = 0, smyles_gagnes = 10, "
                              "credits_balance = 10 WHERE id = :u"), {"u": uid})
        await db.commit()
    r = await _webhook(client, {"id": f"evt_{uuid.uuid4().hex}", "type": "charge.dispute.created",
                                "data": {"object": {"payment_intent": pi, "amount": 800}}})
    assert r.json()["statut"] == "signale"
    async with SessionLocal() as db:
        u = await db.get(User, uid)
        assert u.achat_carte_bloque_at is not None and "10 Smyles" in u.achat_carte_bloque_motif
        assert (u.smyles_gagnes, u.smyles_gagnes_bloque) == (10, 0)    # rien gelé, rien touché
    # Bloqué : plus d'achat par carte, message clair.
    r = await client.post("/credits/checkout", headers=auth_headers, json=BODY)
    assert r.status_code == 403 and "suspendu" in r.json()["detail"]
    assert "suspendu" in (await client.get("/credits/packs", headers=auth_headers)).json()["message"]
    # L'admin le voit et débloque (motif obligatoire, journalisé).
    await _admin(test_user)
    r = await client.get("/admin/achats-carte/bloques", headers=auth_headers)
    mine = [c for c in r.json()["comptes"] if c["user_id"] == str(uid)]
    assert mine and mine[0]["smyles_non_repris"] == 10
    url = f"/admin/achats-carte/{uid}/debloquer"
    assert (await client.post(url, headers=auth_headers, json={"reason": ""})).status_code == 422
    assert (await client.post(url, headers=auth_headers, json={"reason": "Remboursé à l'amiable"})).status_code == 200
    assert (await client.post(url, headers=auth_headers, json={"reason": "encore"})).status_code == 404
    async with SessionLocal() as db:
        u = await db.get(User, uid)
        assert u.achat_carte_bloque_at is None and u.credits_balance == 10
        j = (await db.execute(text(
            "SELECT motif FROM admin_journal WHERE action = 'deblocage_achat_carte' AND cible_id = :c"),
            {"c": str(uid)})).scalar_one()
        assert j == "Remboursé à l'amiable"
        assert await count_bucket_inconsistencies(db) == 0


# ─── 5. Divers ─────────────────────────────────────────────────────────────────

async def test_moderation_accessible_aux_administrateurs(client, test_user, auth_headers):
    assert (await client.get("/admin/reports", headers=auth_headers)).status_code == 403
    await _admin(test_user)
    assert (await client.get("/admin/reports", headers=auth_headers)).status_code == 200


async def test_bouton_signaler_sur_fiches_adn_et_voix():
    src = (Path(__file__).resolve().parents[2] / "artiste.js").read_text(encoding="utf-8")
    assert "{ 'adn-artist': 'adn', 'visual-adn': 'visual_adn', 'voix': 'voix' }" in src
    assert 'class="mp-report-btn" type="button" data-report-type="${_reportType}"' in src


async def test_identifiants_de_migration_32_caracteres_max():
    """alembic_version.version_num est un VARCHAR(32) : un identifiant plus
    long fait échouer la migration en production."""
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    trop_longs = []
    for f in versions.glob("*.py"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("revision = "):
                rev = line.split("=", 1)[1].strip().strip("\"'")
                if len(rev) > 32:
                    trop_longs.append(rev)
    assert trop_longs == []
