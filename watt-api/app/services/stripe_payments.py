"""Brique 5 — achat de Smyles par carte (Stripe Checkout). Lot 3.

Principes (décisions Tom / coordinateur, 23/09) :
  - Stripe Checkout (page de paiement hébergée par Stripe : aucune donnée de
    carte ne transite ni n'est stockée chez nous) ;
  - packs existants 10 / 50 / 200 Smyles à 8 / 35 / 120 € (CREDIT_PACKS) ;
  - le CRÉDIT se fait UNIQUEMENT sur le webhook signé (jamais sur la page de
    retour), dans le bucket `achetes`, idempotent : une session Stripe ne
    crédite qu'une fois (clé d'idempotence du ledger), et chaque événement
    n'est traité qu'une fois (`stripe_events`) ;
  - remboursement / litige : on reprend ce qui reste en `achetes` ; si les
    Smyles ont déjà été dépensés, on ne passe JAMAIS un solde en négatif : le
    manque est noté (`shortfall`) et le compte est SIGNALÉ à l'admin ;
  - obligations légales : renonciation au droit de rétractation (case
    obligatoire, horodatée), CGV de vente de Smyles, mention de franchise de
    TVA configurable (MENTION_TVA_FRANCHISE).

Pas de SDK Stripe (pas de nouvelle dépendance) : deux appels HTTP (création
de session) via httpx, et la vérification de signature du webhook selon la
méthode documentée par Stripe (HMAC-SHA256 de « horodatage.corps »).
Les clés viennent UNIQUEMENT de l'environnement (settings).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.services.credits import get_pack_by_id, grant_credits_atomic

log = logging.getLogger(__name__)

STRIPE_API = "https://api.stripe.com/v1"
SIGNATURE_TOLERANCE_S = 300
TVA_MENTION = "TVA non applicable, art. 293 B du CGI"
CONSENT_TEXT = (
    "Je demande la fourniture immédiate du contenu numérique et je renonce "
    "à mon droit de rétractation."
)


class StripeUnavailable(Exception):
    """Achat par carte non configuré (clé absente) ou masqué."""


class StripeRequestError(Exception):
    """Requête d'achat invalide (pack inconnu, consentement absent)."""


class StripeSignatureError(Exception):
    """Webhook non authentifié (signature absente, fausse ou trop ancienne)."""


def is_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


# ── Appels Stripe (remplacés par un simulateur dans les tests) ──────────────

async def _stripe_post(path: str, data: dict) -> dict:
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{STRIPE_API}{path}",
            data=data,
            headers={"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"},
        )
    if r.status_code >= 400:
        # Jamais la clé dans les journaux : seulement le statut et le message Stripe.
        try:
            msg = r.json().get("error", {}).get("message")
        except Exception:  # noqa: BLE001
            msg = None
        log.warning("stripe.error", extra={"status": r.status_code, "message": msg})
        raise StripeUnavailable("Le paiement est momentanément indisponible.")
    return r.json()


# ── Création de la session de paiement ─────────────────────────────────────

async def create_checkout(
    db: AsyncSession,
    *,
    user_id: UUID,
    pack_id: str,
    consent: bool,
    base_url: str,
) -> dict:
    """Crée la session Stripe Checkout et renvoie son URL. Le caller commit.

    Rien n'est crédité ici : seul le webhook `checkout.session.completed`
    crédite. La renonciation au droit de rétractation est OBLIGATOIRE et
    horodatée (preuve)."""
    if not settings.launch_flags_dict()["achatSmyles"]:
        raise StripeUnavailable("L'achat de Smyles n'est pas encore ouvert.")
    if not is_configured():
        raise StripeUnavailable("Le paiement par carte n'est pas encore configuré.")
    pack = get_pack_by_id(pack_id)
    if pack is None:
        raise StripeRequestError("Pack inconnu.")
    if consent is not True:
        raise StripeRequestError(
            "Coche la case de renonciation au droit de rétractation pour continuer."
        )

    base = (base_url or "").rstrip("/")
    payment_id = uuid4()
    description = f"WATT — {pack['credits']} Smyles"
    if settings.MENTION_TVA_FRANCHISE:
        description += f" — {TVA_MENTION}"
    submit_msg = CONSENT_TEXT
    if settings.MENTION_TVA_FRANCHISE:
        submit_msg += f" {TVA_MENTION}."
    data = {
        "mode": "payment",
        "client_reference_id": str(user_id),
        "success_url": f"{base}/?achat=ok",
        "cancel_url": f"{base}/?achat=annule",
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(pack["price_eur_cents"]),
        "line_items[0][price_data][product_data][name]": f"{pack['credits']} Smyles",
        "payment_intent_data[description]": description,
        "payment_intent_data[metadata][payment_id]": str(payment_id),
        "metadata[payment_id]": str(payment_id),
        "metadata[pack_id]": pack["id"],
        "metadata[user_id]": str(user_id),
        "custom_text[submit][message]": submit_msg[:1200],
    }
    session = await _stripe_post("/checkout/sessions", data)
    await db.execute(
        text(
            "INSERT INTO stripe_payments (id, user_id, session_id, pack_id, credits, "
            "amount_cents, currency, status, consent_immediate_at) "
            "VALUES (:id, :u, :s, :p, :c, :a, 'eur', 'created', now())"
        ),
        {"id": payment_id, "u": user_id, "s": session["id"], "p": pack["id"],
         "c": pack["credits"], "a": pack["price_eur_cents"]},
    )
    return {"url": session["url"], "session_id": session["id"]}


# ── Webhook ─────────────────────────────────────────────────────────────────

def verify_signature(payload: bytes, header: str | None, secret: str | None,
                     *, now: float | None = None) -> dict:
    """Vérifie l'en-tête `Stripe-Signature` (t=…,v1=…) et renvoie l'événement.

    Méthode Stripe : HMAC-SHA256(secret, f"{t}.{corps brut}") comparé à
    chaque v1 ; horodatage refusé au-delà de 5 minutes (anti-rejeu)."""
    if not secret:
        raise StripeUnavailable("Webhook Stripe non configuré.")
    if not header:
        raise StripeSignatureError("Signature absente.")
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        k, _, v = item.strip().partition("=")
        parts.setdefault(k, []).append(v)
    try:
        ts = int(parts.get("t", [""])[0])
    except ValueError:
        raise StripeSignatureError("Horodatage invalide.")
    if abs((now if now is not None else time.time()) - ts) > SIGNATURE_TOLERANCE_S:
        raise StripeSignatureError("Signature trop ancienne.")
    signed = f"{ts}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in parts.get("v1", [])):
        raise StripeSignatureError("Signature invalide.")
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:  # noqa: BLE001
        raise StripeSignatureError("Corps illisible.")


async def handle_event(db: AsyncSession, event: dict) -> str:
    """Traite un événement Stripe authentifié. Idempotent. Le caller commit.

    Renvoie un court statut (journal / tests)."""
    event_id = str(event.get("id") or "")
    etype = str(event.get("type") or "")
    if not event_id:
        return "ignore"
    first = (await db.execute(
        text(
            "INSERT INTO stripe_events (event_id, type) VALUES (:i, :t) "
            "ON CONFLICT (event_id) DO NOTHING RETURNING event_id"
        ),
        {"i": event_id, "t": etype[:64]},
    )).scalar_one_or_none()
    if first is None:
        return "deja_traite"

    obj = (event.get("data") or {}).get("object") or {}
    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return await _on_paid(db, obj)
    if etype == "charge.refunded":
        return await _on_recovery(
            db, event_id, obj.get("payment_intent"), int(obj.get("amount_refunded") or 0),
            statut="rembourse", motif="remboursement",
        )
    if etype == "charge.dispute.created":
        return await _on_recovery(
            db, event_id, obj.get("payment_intent"), int(obj.get("amount") or 0),
            statut="litige", motif="litige bancaire",
        )
    return "ignore"


async def _payment_by(db: AsyncSession, column: str, value: str):
    assert column in ("session_id", "payment_intent")
    return (await db.execute(
        text(f"SELECT * FROM stripe_payments WHERE {column} = :v FOR UPDATE"),  # noqa: S608
        {"v": value},
    )).first()


async def _on_paid(db: AsyncSession, session: dict) -> str:
    if session.get("payment_status") != "paid":
        return "en_attente"  # paiement différé : on attend async_payment_succeeded
    row = await _payment_by(db, "session_id", str(session.get("id") or ""))
    if row is None:
        log.warning("stripe.session_inconnue")
        return "session_inconnue"
    # Garde-fous : le montant payé doit être EXACTEMENT celui du pack.
    if int(session.get("amount_total") or -1) != int(row.amount_cents) or \
            str(session.get("currency") or "").lower() != row.currency:
        log.error("stripe.montant_incoherent", extra={"payment_id": str(row.id)})
        await db.execute(
            text("UPDATE stripe_payments SET status = 'montant_incoherent', flagged_at = now(), "
                 "updated_at = now() WHERE id = :i"), {"i": row.id})
        return "montant_incoherent"
    if row.user_id is None:
        return "compte_supprime"
    tx = await grant_credits_atomic(
        db,
        user_id=row.user_id,
        amount=int(row.credits),
        reason="achat_smyles_carte",
        tx_type=TransactionType.CREDIT_PURCHASE,        # → bucket `achetes`
        metadata={"stripe_session": row.session_id, "pack_id": row.pack_id,
                  "euro_cents": int(row.amount_cents)},
        idempotency_key=f"stripe_session:{row.session_id}",
    )
    await db.execute(
        text("UPDATE stripe_payments SET status = 'paye', payment_intent = :pi, "
             "credited_tx_id = :tx, updated_at = now() WHERE id = :i"),
        {"pi": session.get("payment_intent"), "tx": tx.id, "i": row.id},
    )
    return "credite"


async def _on_recovery(db: AsyncSession, event_id: str, payment_intent, amount_cents: int,
                       *, statut: str, motif: str) -> str:
    """Remboursement (cumulatif) ou litige : reprend les Smyles correspondants
    dans le bucket `achetes` restant, sans jamais passer un solde en négatif."""
    if not payment_intent:
        return "ignore"
    row = await _payment_by(db, "payment_intent", str(payment_intent))
    if row is None or row.credited_tx_id is None:
        return "paiement_inconnu"
    # Smyles à reprendre au total pour ce paiement : au prorata du montant
    # remboursé / contesté, arrondi au supérieur (en faveur de la plateforme).
    cible = min(int(row.credits),
                -(-int(row.credits) * max(0, amount_cents) // int(row.amount_cents)))
    deja = int(row.smyles_recovered) + int(row.shortfall)
    a_reprendre = max(0, cible - deja)
    repris = 0
    if a_reprendre > 0 and row.user_id is not None:
        achetes = int((await db.execute(
            text("SELECT smyles_achetes FROM users WHERE id = :u FOR UPDATE"),
            {"u": row.user_id},
        )).scalar_one())
        repris = min(a_reprendre, achetes)
        if repris > 0:
            await db.execute(
                text("UPDATE users SET smyles_achetes = smyles_achetes - :n, "
                     "credits_balance = credits_balance - :n WHERE id = :u"),
                {"n": repris, "u": row.user_id},
            )
            # Ledger : Smyles retirés de la circulation, sans bénéficiaire.
            db.add(Transaction(
                type=TransactionType.BURN,
                status=TransactionStatus.COMPLETED,
                buyer_id=row.user_id,
                credits_amount=repris,
                artist_revenue=0,
                platform_fee=0,
                idempotency_key=f"stripe_reprise:{event_id}",
                completed_at=datetime.now(timezone.utc),
                metadata_json={"source": "stripe_" + ("refund" if statut == "rembourse" else "dispute"),
                               "motif": motif, "stripe_payment_id": str(row.id),
                               "payment_intent": str(payment_intent)},
            ))
            await db.flush()
    manque = a_reprendre - repris
    await db.execute(
        text(
            "UPDATE stripe_payments SET status = :st, smyles_recovered = smyles_recovered + :r, "
            "shortfall = shortfall + :m, "
            "flagged_at = CASE WHEN :m > 0 THEN COALESCE(flagged_at, now()) ELSE flagged_at END, "
            "updated_at = now() WHERE id = :i"
        ),
        {"st": statut, "r": repris, "m": manque, "i": row.id},
    )
    if manque > 0:
        await _signaler_admin(db, row, manque, motif)
        return "signale"
    return "repris"


async def _signaler_admin(db: AsyncSession, row, manque: int, motif: str) -> None:
    """Notifie le compte de modération : Smyles déjà dépensés, non repris."""
    try:
        from app.models.notification import NotificationType
        from app.services.notifications import create_notification

        official = (await db.execute(
            text("SELECT id FROM users WHERE is_official = TRUE LIMIT 1")
        )).scalar_one_or_none()
        if official:
            await create_notification(
                db, user_id=official, type=NotificationType.SYSTEM,
                metadata={"text": (
                    f"⚠ Paiement {motif} : {manque} Smyles déjà dépensés n'ont pas pu "
                    f"être repris (compte {row.user_id}). À examiner : "
                    f"/admin/paiements/signales."
                )},
            )
    except Exception:  # noqa: BLE001
        log.warning("stripe.signalement_notif_echec", exc_info=True)


async def paiements_signales(db: AsyncSession, limit: int = 100) -> list[dict]:
    rows = (await db.execute(
        text(
            "SELECT p.id, p.user_id, u.artist_name, p.pack_id, p.credits, p.amount_cents, "
            "p.status, p.smyles_recovered, p.shortfall, p.flagged_at "
            "FROM stripe_payments p LEFT JOIN users u ON u.id = p.user_id "
            "WHERE p.flagged_at IS NOT NULL ORDER BY p.flagged_at DESC LIMIT :l"
        ),
        {"l": max(1, min(limit, 500))},
    )).all()
    return [
        {
            "paiement_id": str(r.id), "user_id": str(r.user_id) if r.user_id else None,
            "pseudo": r.artist_name, "pack": r.pack_id, "smyles": int(r.credits),
            "euros": round(int(r.amount_cents) / 100, 2), "statut": r.status,
            "smyles_repris": int(r.smyles_recovered), "smyles_non_repris": int(r.shortfall),
            "signale_le": r.flagged_at.isoformat() if r.flagged_at else None,
        }
        for r in rows
    ]
