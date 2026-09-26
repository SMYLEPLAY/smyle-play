"""Brique 5 — achat de Smyles par carte (Stripe Checkout), Lot 3.

Stripe est SIMULÉ : aucun appel réseau, aucune vraie clé (valeurs de test
fabriquées ici). Couvre :
  - création de la session : interrupteur SHOW_ACHAT_SMYLES, clé absente,
    renonciation au droit de rétractation obligatoire (et horodatée), pack
    inconnu, mention de TVA configurable ;
  - webhook : signature exigée (fausse, absente, trop ancienne), crédit en
    `achetes` UNIQUEMENT à la réception de `checkout.session.completed`,
    idempotence (même événement rejoué, second événement de la même session),
    montant incohérent refusé et signalé ;
  - remboursement / litige : reprise dans `achetes`, jamais de solde négatif,
    manque signalé à l'admin, cumul remboursement partiel puis total, litige
    après remboursement sans double reprise.
"""
import hashlib
import hmac
import json
import time
import uuid

import pytest
from sqlalchemy import delete, select, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.models.achievement import Achievement, UserAchievement
from app.models.user import User
from app.services import stripe_payments
from app.services.credits import count_bucket_inconsistencies

SECRET_TEST = "whsec_" + "t" * 24          # fabriqué pour les tests, jamais une vraie clé
# Étape 2 : avec une clé de TEST, l'achat est réservé aux admins. Ces tests
# couvrent le parcours d'un client ordinaire : clé « réelle » FACTICE.
CLE_TEST = "sk_live_" + "x" * 24


@pytest.fixture(autouse=True)
def _stripe_simule(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", CLE_TEST)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET_TEST)
    appels = []

    async def _faux_stripe(path, data):
        appels.append((path, data))
        sid = "cs_test_" + uuid.uuid4().hex
        return {"id": sid, "url": f"https://checkout.stripe.com/c/pay/{sid}"}

    monkeypatch.setattr(stripe_payments, "_stripe_post", _faux_stripe)
    return appels


def _signer(corps: bytes, secret=SECRET_TEST, ts=None) -> str:
    ts = int(ts if ts is not None else time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + corps, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


async def _webhook(client, event: dict, **kw):
    corps = json.dumps(event).encode()
    return await client.post("/stripe/webhook", content=corps,
                             headers={"Stripe-Signature": _signer(corps, **kw),
                                      "Content-Type": "application/json"})


def _evt(etype, obj, eid=None):
    return {"id": eid or f"evt_{uuid.uuid4().hex}", "type": etype, "data": {"object": obj}}


async def _bk(uid):
    async with SessionLocal() as db:
        r = (await db.execute(text(
            "SELECT credits_balance b, smyles_achetes a, smyles_gagnes g, smyles_promo p "
            "FROM users WHERE id = :u"), {"u": uid})).first()
    return {"b": r.b, "a": r.a, "g": r.g, "p": r.p}


async def _preseed(uid, achetes=0):
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET credits_balance = :a, smyles_achetes = :a, "
                              "smyles_gagnes = 0, smyles_promo = 0 WHERE id = :u"), {"a": achetes, "u": uid})
        for ach in (await db.execute(select(Achievement))).scalars().all():
            db.add(UserAchievement(user_id=uid, achievement_id=ach.id))
        await db.commit()


async def _checkout(client, auth_headers, pack="pack_50"):
    r = await client.post("/credits/checkout", headers=auth_headers,
                          json={"pack_id": pack, "renonce_retractation": True})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _session_payee(sid, amount=3500, pi=None):
    return {"id": sid, "payment_status": "paid", "amount_total": amount, "currency": "eur",
            "payment_intent": pi or f"pi_{uuid.uuid4().hex}"}


async def _paiement(sid):
    async with SessionLocal() as db:
        return (await db.execute(text("SELECT * FROM stripe_payments WHERE session_id = :s"),
                                 {"s": sid})).first()


# ─── 1. Création de la session ─────────────────────────────────────────────────

async def test_checkout_exige_la_renonciation(client, auth_headers):
    r = await client.post("/credits/checkout", headers=auth_headers,
                          json={"pack_id": "pack_10", "renonce_retractation": False})
    assert r.status_code == 422 and "rétractation" in r.json()["detail"]


async def test_checkout_pack_inconnu(client, auth_headers):
    r = await client.post("/credits/checkout", headers=auth_headers,
                          json={"pack_id": "pack_999", "renonce_retractation": True})
    assert r.status_code == 422


async def test_checkout_masque_ou_sans_cle(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", False)
    body = {"pack_id": "pack_10", "renonce_retractation": True}
    assert (await client.post("/credits/checkout", headers=auth_headers, json=body)).status_code == 503
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    assert (await client.post("/credits/checkout", headers=auth_headers, json=body)).status_code == 503


async def test_checkout_cree_la_session_sans_crediter(client, test_user, auth_headers, _stripe_simule):
    await _preseed(test_user["id"])
    sid = await _checkout(client, auth_headers, "pack_50")
    path, data = _stripe_simule[-1]
    assert path == "/checkout/sessions"
    assert data["line_items[0][price_data][unit_amount]"] == "3500"
    assert data["mode"] == "payment" and data["success_url"].endswith("/?achat=ok")
    assert "TVA" not in data["payment_intent_data[description]"]
    row = await _paiement(sid)
    assert row.credits == 50 and row.amount_cents == 3500 and row.consent_immediate_at is not None
    assert (await _bk(test_user["id"]))["b"] == 0          # rien crédité avant le webhook


async def test_mention_tva_configurable(client, test_user, auth_headers, _stripe_simule, monkeypatch):
    monkeypatch.setattr(settings, "MENTION_TVA_FRANCHISE", True)
    await _checkout(client, auth_headers, "pack_10")
    _, data = _stripe_simule[-1]
    assert "TVA non applicable, art. 293 B du CGI" in data["payment_intent_data[description]"]
    assert "293 B" in data["custom_text[submit][message]"]
    r = await client.get("/credits/packs")
    assert r.json()["mention_tva"] == "TVA non applicable, art. 293 B du CGI"


# ─── 2. Webhook : crédit ───────────────────────────────────────────────────────

async def test_webhook_signature_exigee(client):
    evt = _evt("checkout.session.completed", {"id": "cs_x"})
    corps = json.dumps(evt).encode()
    r = await client.post("/stripe/webhook", content=corps)
    assert r.status_code == 400                                    # absente
    r = await client.post("/stripe/webhook", content=corps,
                          headers={"Stripe-Signature": _signer(corps, secret="whsec_faux")})
    assert r.status_code == 400                                    # fausse
    r = await _webhook(client, evt, ts=time.time() - 3600)
    assert r.status_code == 400                                    # trop ancienne (rejeu)


async def test_webhook_non_configure(client, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    r = await client.post("/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "t=1,v1=x"})
    assert r.status_code == 503


async def test_credit_en_achetes_idempotent(client, test_user, auth_headers):
    uid = test_user["id"]
    await _preseed(uid)
    sid = await _checkout(client, auth_headers, "pack_50")
    evt = _evt("checkout.session.completed", _session_payee(sid))
    r = await _webhook(client, evt)
    assert r.status_code == 200 and r.json()["statut"] == "credite"
    assert await _bk(uid) == {"b": 50, "a": 50, "g": 0, "p": 0}   # bucket `achetes`
    # Même événement rejoué → rien.
    assert (await _webhook(client, evt)).json()["statut"] == "deja_traite"
    # Autre événement, même session (ex. async_payment_succeeded) → pas de double crédit.
    evt2 = _evt("checkout.session.async_payment_succeeded", _session_payee(sid))
    assert (await _webhook(client, evt2)).status_code == 200
    assert (await _bk(uid))["b"] == 50
    async with SessionLocal() as db:
        n = (await db.execute(text(
            "SELECT count(*) FROM transactions WHERE idempotency_key = :k"),
            {"k": f"stripe_session:{sid}"})).scalar_one()
        assert n == 1
        assert await count_bucket_inconsistencies(db) == 0


async def test_paiement_non_confirme_ne_credite_pas(client, test_user, auth_headers):
    await _preseed(test_user["id"])
    sid = await _checkout(client, auth_headers, "pack_10")
    obj = _session_payee(sid, amount=800)
    obj["payment_status"] = "unpaid"
    assert (await _webhook(client, _evt("checkout.session.completed", obj))).json()["statut"] == "en_attente"
    assert (await _bk(test_user["id"]))["b"] == 0


async def test_montant_incoherent_refuse_et_signale(client, test_user, auth_headers):
    await _preseed(test_user["id"])
    sid = await _checkout(client, auth_headers, "pack_200")
    r = await _webhook(client, _evt("checkout.session.completed", _session_payee(sid, amount=800)))
    assert r.json()["statut"] == "montant_incoherent"
    assert (await _bk(test_user["id"]))["b"] == 0
    assert (await _paiement(sid)).flagged_at is not None


# ─── 3. Remboursement / litige ─────────────────────────────────────────────────

async def _paye(client, uid, auth_headers, pack="pack_50", amount=3500):
    sid = await _checkout(client, auth_headers, pack)
    pi = f"pi_{uuid.uuid4().hex}"
    await _webhook(client, _evt("checkout.session.completed", _session_payee(sid, amount, pi)))
    return sid, pi


async def test_remboursement_reprend_les_achetes(client, test_user, auth_headers):
    uid = test_user["id"]
    await _preseed(uid)
    sid, pi = await _paye(client, uid, auth_headers)
    r = await _webhook(client, _evt("charge.refunded", {"payment_intent": pi, "amount_refunded": 3500}))
    assert r.json()["statut"] == "repris"
    assert await _bk(uid) == {"b": 0, "a": 0, "g": 0, "p": 0}
    row = await _paiement(sid)
    assert row.smyles_recovered == 50 and row.shortfall == 0 and row.flagged_at is None


async def test_remboursement_partiel_puis_total_cumulatif(client, test_user, auth_headers):
    uid = test_user["id"]
    await _preseed(uid)
    sid, pi = await _paye(client, uid, auth_headers)
    await _webhook(client, _evt("charge.refunded", {"payment_intent": pi, "amount_refunded": 700}))
    assert (await _bk(uid))["a"] == 40                    # 50 × 700/3500 = 10 repris
    await _webhook(client, _evt("charge.refunded", {"payment_intent": pi, "amount_refunded": 3500}))
    assert (await _bk(uid))["a"] == 0                     # cumul : 50 au total, pas 60
    assert (await _paiement(sid)).smyles_recovered == 50


async def test_smyles_deja_depenses_jamais_de_solde_negatif(client, test_user, auth_headers):
    """Achète 50, en dépense 45 (restent 5 en achetés) puis rembourse : on reprend
    5, les 45 manquants sont signalés, aucun solde ne passe sous zéro."""
    uid = test_user["id"]
    await _preseed(uid)
    sid, pi = await _paye(client, uid, auth_headers)
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET smyles_achetes = 5, smyles_gagnes = 3, "
                              "credits_balance = 8 WHERE id = :u"), {"u": uid})
        await db.commit()
    r = await _webhook(client, _evt("charge.refunded", {"payment_intent": pi, "amount_refunded": 3500}))
    assert r.json()["statut"] == "signale"
    b = await _bk(uid)
    assert b == {"b": 3, "a": 0, "g": 3, "p": 0}          # gagnés intacts, rien de négatif
    row = await _paiement(sid)
    assert row.smyles_recovered == 5 and row.shortfall == 45 and row.flagged_at is not None
    # Litige ensuite sur le même paiement : rien de plus à reprendre.
    r = await _webhook(client, _evt("charge.dispute.created", {"payment_intent": pi, "amount": 3500}))
    row = await _paiement(sid)
    assert row.smyles_recovered + row.shortfall == 50
    async with SessionLocal() as db:
        assert await count_bucket_inconsistencies(db) == 0


async def test_liste_admin_des_paiements_signales(client, test_user, auth_headers):
    uid = test_user["id"]
    await _preseed(uid)
    sid, pi = await _paye(client, uid, auth_headers, "pack_10", 800)
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET smyles_achetes = 0, smyles_gagnes = 10, "
                              "credits_balance = 10 WHERE id = :u"), {"u": uid})
        await db.commit()
    await _webhook(client, _evt("charge.dispute.created", {"payment_intent": pi, "amount": 800}))
    assert (await client.get("/admin/paiements/signales", headers=auth_headers)).status_code == 403
    async with SessionLocal() as db:
        await db.execute(text("UPDATE users SET is_admin = TRUE WHERE id = :u"), {"u": uid})
        await db.commit()
    r = await client.get("/admin/paiements/signales", headers=auth_headers)
    assert r.status_code == 200
    mine = [p for p in r.json()["paiements"] if p["user_id"] == str(uid)]
    assert mine and mine[0]["smyles_non_repris"] == 10


async def test_aucune_cle_dans_les_reponses(client, test_user, auth_headers):
    await _preseed(test_user["id"])
    r = await client.post("/credits/checkout", headers=auth_headers,
                          json={"pack_id": "pack_10", "renonce_retractation": True})
    assert CLE_TEST not in r.text and SECRET_TEST not in r.text
