"""Lot L — paiement sûr avant l'ouverture au public (méga-audit du 26/10).

  - achat proposé seulement si clé + secret du webhook sont posés ;
  - clé restreinte de test (rk_test_) reconnue comme test ;
  - clé réelle : vente fermée tant que adresse + SIREN + médiateur manquent ;
  - majorité et email vérifié exigés pour acheter ;
  - preuve de renonciation (empreinte du texte, version des CGV) ;
  - événement Stripe prématuré (remboursement avant le crédit) NON consommé :
    le webhook répond en erreur et Stripe le rejoue ;
  - événement du mauvais mode (test / réel) ignoré ;
  - textes légaux selon l'ouverture réelle de la vente ;
  - vue admin de tous les paiements.
"""
import hashlib
import hmac
import json
import time
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.config import settings
from app.database import SessionLocal
from app.services import stripe_payments

SECRET = "whsec_" + "l" * 24
CLE_REELLE = "sk_live_" + "y" * 24


@pytest.fixture(autouse=True)
def _stripe(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", CLE_REELLE)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "EDITEUR_ADRESSE", "1 rue de l'Exemple, 75000 Paris")
    monkeypatch.setattr(settings, "EDITEUR_SIREN", "000 000 000")
    monkeypatch.setattr(settings, "EDITEUR_MEDIATEUR", "Médiateur de test")
    monkeypatch.setattr(settings, "ACHAT_EXIGE_EMAIL_VERIFIE", False)
    appels = []

    async def _faux(path, data):
        appels.append((path, data))
        sid = "cs_test_" + uuid.uuid4().hex
        return {"id": sid, "url": f"https://checkout.stripe.com/c/pay/{sid}"}

    monkeypatch.setattr(stripe_payments, "_stripe_post", _faux)
    return appels


def _signer(corps: bytes) -> str:
    ts = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + corps, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


async def _webhook(client, event: dict):
    corps = json.dumps(event).encode()
    return await client.post("/stripe/webhook", content=corps, headers={
        "Stripe-Signature": _signer(corps), "Content-Type": "application/json"})


async def _checkout(client, auth_headers, **extra):
    body = {"pack_id": "pack_100", "renonce_retractation": True, "majeur": True}
    body.update(extra)
    return await client.post("/credits/checkout", headers=auth_headers, json=body)


# ── Configuration et garde-fous ─────────────────────────────────────────────

def test_secret_du_webhook_obligatoire(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    assert stripe_payments.is_configured() is False


def test_cle_restreinte_de_test_reconnue(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "rk_test_" + "z" * 20)
    assert stripe_payments.is_test_mode() is True
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "rk_live_" + "z" * 20)
    assert stripe_payments.is_test_mode() is False


@pytest.mark.parametrize("manque", ["EDITEUR_ADRESSE", "EDITEUR_SIREN", "EDITEUR_MEDIATEUR"])
async def test_vente_fermee_sans_identite_complete(client, auth_headers, monkeypatch, manque):
    monkeypatch.setattr(settings, manque, "")
    assert stripe_payments.vente_ouverte_au_public() is False
    r = await _checkout(client, auth_headers)
    assert r.status_code == 503


async def test_majorite_exigee(client, auth_headers):
    r = await _checkout(client, auth_headers, majeur=False)
    assert r.status_code == 422 and "18 ans" in r.json()["detail"]


async def test_email_verifie_exige(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "ACHAT_EXIGE_EMAIL_VERIFIE", True)
    r = await _checkout(client, auth_headers)
    assert r.status_code == 422 and "email" in r.json()["detail"]


async def test_session_carte_francais_email_et_preuve(client, auth_headers, test_user, _stripe):
    r = await _checkout(client, auth_headers)
    assert r.status_code == 200, r.text
    _, data = _stripe[-1]
    assert data["payment_method_types[0]"] == "card" and data["locale"] == "fr"
    assert data["customer_email"] == test_user["email"]
    async with SessionLocal() as db:
        row = (await db.execute(text(
            "SELECT consent_text_sha256, cgu_version, majeur_declare FROM stripe_payments "
            "WHERE session_id = :s"), {"s": r.json()["session_id"]})).first()
    from app.core.legal import CGU_VERSION

    attendu = hashlib.sha256(data["custom_text[submit][message]"].encode()).hexdigest()
    assert row.consent_text_sha256 == attendu
    assert row.cgu_version == CGU_VERSION and row.majeur_declare is True


# ── Webhook : événements prématurés et mode ─────────────────────────────────

async def test_remboursement_premature_est_rejoue(client):
    evt = {"id": f"evt_{uuid.uuid4().hex}", "type": "charge.refunded",
           "data": {"object": {"payment_intent": f"pi_{uuid.uuid4().hex}", "amount_refunded": 800}}}
    r = await _webhook(client, evt)
    assert r.status_code == 503
    async with SessionLocal() as db:
        vu = (await db.execute(text("SELECT 1 FROM stripe_events WHERE event_id = :i"),
                               {"i": evt["id"]})).first()
    assert vu is None  # non consommé : Stripe le renverra


async def test_session_inconnue_est_rejouee(client):
    evt = {"id": f"evt_{uuid.uuid4().hex}", "type": "checkout.session.completed",
           "data": {"object": {"id": f"cs_{uuid.uuid4().hex}", "payment_status": "paid",
                               "amount_total": 800, "currency": "eur"}}}
    r = await _webhook(client, evt)
    assert r.status_code == 503


async def test_evenement_du_mauvais_mode_ignore(client):
    # Clé réelle → un événement « livemode: false » (test) n'est jamais appliqué.
    evt = {"id": f"evt_{uuid.uuid4().hex}", "type": "checkout.session.completed", "livemode": False,
           "data": {"object": {"id": f"cs_{uuid.uuid4().hex}", "payment_status": "paid"}}}
    r = await _webhook(client, evt)
    assert r.status_code == 200 and r.json()["statut"] == "mode_incoherent"


# ── Textes légaux et admin ──────────────────────────────────────────────────

async def test_textes_legaux_selon_la_vente(client, monkeypatch):
    r = await client.get("/legal")
    assert "{{EDITEUR_MEDIATEUR}}" not in r.text and "Médiateur de test" in r.text
    assert "L'achat de Smyles sera ouvert prochainement" not in r.text
    assert "000 000 000" in r.text
    monkeypatch.setattr(settings, "SHOW_ACHAT_SMYLES", False)
    r = await client.get("/legal")
    assert "L'achat de Smyles sera ouvert prochainement" in r.text
    assert "Médiateur de test" not in r.text
    assert "SI_VENTE" not in r.text and "SI_SANS_VENTE" not in r.text


async def test_paiements_admin_reserve(client, auth_headers):
    r = await client.get("/admin/paiements", headers=auth_headers)
    assert r.status_code in (401, 403)


async def test_paiements_tous_totaux():
    async with SessionLocal() as db:
        out = await stripe_payments.paiements_tous(db)
    assert set(out["totaux"]) >= {"paiementsReussis", "eurosEncaisses", "enAttenteDepuisPlusDUneHeure"}


async def test_confirmation_achat_envoyee_apres_credit(client, auth_headers, monkeypatch):
    envois = []

    async def _faux_email(to, **kw):
        envois.append((to, kw))
        return True

    import app.services.emails as emails_mod

    monkeypatch.setattr(emails_mod, "send_confirmation_achat_smyles", _faux_email)
    r = await _checkout(client, auth_headers)
    sid = r.json()["session_id"]
    evt = {"id": f"evt_{uuid.uuid4().hex}", "type": "checkout.session.completed", "livemode": True,
           "data": {"object": {"id": sid, "payment_status": "paid", "amount_total": 800,
                               "currency": "eur", "payment_intent": f"pi_{uuid.uuid4().hex}"}}}
    r = await _webhook(client, evt)
    assert r.status_code == 200 and r.json()["statut"] == "credite"
    assert len(envois) == 1
    to, kw = envois[0]
    assert kw["smyles"] == 100 and kw["euros_cents"] == 800 and kw["consentement_le"] is not None
