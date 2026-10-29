"""Brique 5 — achat de Smyles par carte (Stripe Checkout). Lot 3.

Principes (décisions Tom / coordinateur, 23/09) :
  - Stripe Checkout (page de paiement hébergée par Stripe : aucune donnée de
    carte ne transite ni n'est stockée chez nous) ;
  - packs 100 / 500 / 2000 Smyles à 8 / 35 / 130 € (CREDIT_PACKS) ;
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


class AchatCarteBloque(Exception):
    """Compte bloqué pour les achats par carte (remboursement / litige alors
    que les Smyles étaient déjà dépensés). → 403."""


class CompteNonBloque(Exception):
    """Déblocage demandé pour un compte qui n'est pas bloqué."""


def is_configured() -> bool:
    """Lot L : la clé secrète NE SUFFIT PAS. Sans le secret du webhook, Stripe
    débiterait le client mais aucun crédit n'arriverait jamais (webhook
    refusé). Les deux sont exigés pour proposer l'achat."""
    return bool(settings.STRIPE_SECRET_KEY) and bool(settings.STRIPE_WEBHOOK_SECRET)


def is_test_mode() -> bool:
    """Clé Stripe de TEST (sk_test_…) : aucun vrai argent. Étape 2 : sur le
    vrai site, l'achat en mode test est RÉSERVÉ aux admins (sinon n'importe qui
    obtiendrait des Smyles avec une carte de test), et les Smyles ainsi
    crédités sont marqués dans le registre et exclus des chiffres."""
    # Lot L : « _test_ » couvre aussi les clés restreintes (rk_test_…), qui
    # étaient prises pour des clés réelles avec l'ancien test (sk_test_).
    return "_test_" in str(settings.STRIPE_SECRET_KEY or "")


class EditeurIncomplet(Exception):
    """Identité légale du vendeur incomplète : l'achat réel reste fermé."""


def editeur_complet() -> bool:
    """Lot L — garde-fou légal : pas de vente réelle à des consommateurs sans
    adresse, SIREN et médiateur de la consommation (LCEN 6-III, L111-1,
    L612-1). Ces trois valeurs viennent de l'environnement (Railway)."""
    return all(str(v or "").strip() for v in (
        settings.EDITEUR_ADRESSE, settings.EDITEUR_SIREN, settings.EDITEUR_MEDIATEUR))


def vente_ouverte_au_public() -> bool:
    """Lot L — l'achat RÉEL de Smyles est-il ouvert à tous ? (drapeau,
    clés Stripe live + webhook, identité légale complète). Sert aux textes
    légaux, qui changent selon cet état."""
    return (bool(settings.launch_flags_dict()["achatSmyles"]) and is_configured()
            and not is_test_mode() and editeur_complet())


def achat_carte_ouvert_pour(user) -> bool:
    """L'achat par carte est-il proposé à ce compte (None = visiteur) ?"""
    if not settings.launch_flags_dict()["achatSmyles"] or not is_configured():
        return False
    if is_test_mode():
        from app.auth.dependencies import is_admin_user

        return user is not None and is_admin_user(user)
    # Lot L : clé réelle → identité légale complète obligatoire.
    return editeur_complet()


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
    user,
    pack_id: str,
    consent: bool,
    base_url: str,
    majeur: bool = False,
) -> dict:
    """Crée la session Stripe Checkout et renvoie son URL. Le caller commit.

    Rien n'est crédité ici : seul le webhook `checkout.session.completed`
    crédite. La renonciation au droit de rétractation est OBLIGATOIRE et
    horodatée (preuve)."""
    user_id = user.id
    if not settings.launch_flags_dict()["achatSmyles"]:
        raise StripeUnavailable("L'achat de Smyles n'est pas encore ouvert.")
    if not is_configured():
        raise StripeUnavailable("Le paiement par carte n'est pas encore configuré.")
    if not achat_carte_ouvert_pour(user):
        # Clé de test sur le vrai site : réservé aux admins.
        raise StripeUnavailable("L'achat par carte n'est pas encore ouvert.")
    if getattr(user, "achat_carte_bloque_at", None) is not None:
        raise AchatCarteBloque(
            "L'achat par carte est suspendu sur ton compte. Contacte-nous pour le rétablir."
        )
    pack = get_pack_by_id(pack_id)
    if pack is None:
        raise StripeRequestError("Pack inconnu.")
    if consent is not True:
        raise StripeRequestError(
            "Coche la case de renonciation au droit de rétractation pour continuer."
        )
    # Lot L — achat par carte réservé aux majeurs (décision de prudence en
    # attendant l'avis du juriste ; ACHAT_MAJEUR_REQUIS=false pour lever).
    if settings.ACHAT_MAJEUR_REQUIS and majeur is not True:
        raise StripeRequestError(
            "L'achat par carte est réservé aux personnes majeures : coche la case « J'ai 18 ans ou plus »."
        )
    # Lot L — email vérifié pour acheter (pas pour se connecter) : la
    # confirmation d'achat doit arriver dans une boîte réelle.
    if settings.ACHAT_EXIGE_EMAIL_VERIFIE and not getattr(user, "email_verified", False):
        raise StripeRequestError(
            "Confirme d'abord ton adresse email (lien reçu à l'inscription) pour acheter des Smyles."
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
        # Lot L : carte uniquement (pas de paiement différé type SEPA, plus
        # risqué au lancement), page en français, reçu à l'email du compte.
        "payment_method_types[0]": "card",
        "locale": "fr",
    }
    if getattr(user, "email", None):
        data["customer_email"] = str(user.email)
    session = await _stripe_post("/checkout/sessions", data)
    await db.execute(
        text(
            "INSERT INTO stripe_payments (id, user_id, session_id, pack_id, credits, "
            "amount_cents, currency, status, consent_immediate_at, mode_test, "
            "consent_text_sha256, cgu_version, majeur_declare) "
            "VALUES (:id, :u, :s, :p, :c, :a, 'eur', 'created', now(), :t, :h, :v, :m)"
        ),
        {"id": payment_id, "u": user_id, "s": session["id"], "p": pack["id"],
         "c": pack["credits"], "a": pack["price_eur_cents"], "t": is_test_mode(),
         # Lot L — preuve de renonciation : empreinte du texte affiché et
         # version des CGV en vigueur au moment de l'achat.
         "h": hashlib.sha256(submit_msg.encode("utf-8")).hexdigest(),
         "v": _cgu_version(), "m": bool(majeur)},
    )
    return {"url": session["url"], "session_id": session["id"]}


def _cgu_version() -> str:
    from app.core.legal import CGU_VERSION

    return CGU_VERSION


# ── Webhook ─────────────────────────────────────────────────────────────────

class EvenementARejouer(Exception):
    """Lot L — l'événement est arrivé trop tôt (remboursement avant le crédit,
    session pas encore connue) : on ne le consomme PAS, le webhook répond en
    erreur et Stripe le renvoie plus tard (jusqu'à 3 jours)."""

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
    # Lot L — un événement du mauvais mode (test reçu par le site réel, ou
    # l'inverse) n'est jamais appliqué.
    if "livemode" in event and bool(event["livemode"]) == is_test_mode():
        log.error("stripe.mode_incoherent", extra={"event_id": event_id})
        return "mode_incoherent"
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
        statut = await _on_paid(db, obj)
    elif etype == "charge.refunded":
        statut = await _on_recovery(
            db, event_id, obj.get("payment_intent"), int(obj.get("amount_refunded") or 0),
            statut="rembourse", motif="remboursement",
        )
    elif etype == "charge.dispute.created":
        statut = await _on_recovery(
            db, event_id, obj.get("payment_intent"), int(obj.get("amount") or 0),
            statut="litige", motif="litige bancaire",
        )
    else:
        return "ignore"
    if statut in ("session_inconnue", "paiement_inconnu"):
        # Lot L : AVANT, l'événement était marqué « traité » et jamais rejoué
        # (un remboursement arrivé avant le crédit laissait les Smyles à
        # l'acheteur). Désormais : erreur visible + rejeu par Stripe.
        log.error("stripe.evenement_premature", extra={"event_id": event_id, "statut": statut})
        raise EvenementARejouer(statut)
    return statut


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
                  "euro_cents": int(row.amount_cents),
                  # Étape 2 : Smyles obtenus avec une carte de TEST (aucun
                  # vrai argent) — distingués et exclus des chiffres.
                  **({"stripe_test": True} if row.mode_test else {})},
        idempotency_key=f"stripe_session:{row.session_id}",
        # Lot I : carte de TEST = aucun euro réel → Smyles « promo » (non
        # retirables, et qui ne deviennent jamais « gagnés » chez un vendeur).
        bucket="promo" if row.mode_test else None,
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
        # Étape 2 (partie prudente de la règle, non destructive) : le compte
        # est BLOQUÉ pour les achats par carte et signalé avec le manque. Les
        # `gagnes` ne sont PAS gelés : décision de Tom, au cas par cas.
        if row.user_id is not None:
            motif_blocage = (f"{motif.capitalize()} : {manque} Smyles déjà dépensés "
                             f"n'ont pas pu être repris (paiement de {int(row.amount_cents) / 100:.2f} €).")
            await db.execute(
                text("UPDATE users SET achat_carte_bloque_at = COALESCE(achat_carte_bloque_at, now()), "
                     "achat_carte_bloque_motif = :m WHERE id = :u"),
                {"m": motif_blocage, "u": row.user_id},
            )
            from app.services.moderation import journaliser

            await journaliser(db, admin_id=None, action="blocage_achat_carte", cible_type="compte",
                              cible_id=str(row.user_id), motif=motif_blocage,
                              details={"paiement_id": str(row.id), "manque": manque})
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


async def comptes_bloques(db: AsyncSession) -> list[dict]:
    """Comptes bloqués pour l'achat par carte, avec le manque total non repris."""
    rows = (await db.execute(text(
        "SELECT u.id, u.artist_name, u.achat_carte_bloque_at, u.achat_carte_bloque_motif, "
        "COALESCE((SELECT sum(p.shortfall) FROM stripe_payments p WHERE p.user_id = u.id), 0) AS manque, "
        "u.smyles_gagnes, u.credits_balance "
        "FROM users u WHERE u.achat_carte_bloque_at IS NOT NULL "
        "ORDER BY u.achat_carte_bloque_at DESC"
    ))).all()
    return [
        {
            "user_id": str(r.id),
            "pseudo": r.artist_name or "(sans pseudo)",
            "bloque_le": r.achat_carte_bloque_at.isoformat() if r.achat_carte_bloque_at else None,
            "motif": r.achat_carte_bloque_motif,
            "smyles_non_repris": int(r.manque),
            "solde_actuel": int(r.credits_balance),
            "dont_gagnes": int(r.smyles_gagnes),
        }
        for r in rows
    ]


async def debloquer_achat_carte(db: AsyncSession, *, admin_id: UUID, user_id: UUID, motif: str) -> None:
    """Rétablit l'achat par carte (motif obligatoire, journalisé). Ne touche à
    aucun solde. Le caller commit."""
    res = await db.execute(
        text("UPDATE users SET achat_carte_bloque_at = NULL, achat_carte_bloque_motif = NULL "
             "WHERE id = :u AND achat_carte_bloque_at IS NOT NULL RETURNING id"),
        {"u": user_id},
    )
    if res.first() is None:
        raise CompteNonBloque("Ce compte n'est pas bloqué.")
    from app.services.moderation import journaliser

    await journaliser(db, admin_id=admin_id, action="deblocage_achat_carte", cible_type="compte",
                      cible_id=str(user_id), motif=motif)


# ── Lot L : vue admin de TOUS les paiements, et confirmation d'achat ─────────

async def paiements_tous(db: AsyncSession, limit: int = 200) -> dict:
    """Tous les paiements par carte (les plus récents d'abord) et les totaux.

    « En attente depuis plus d'une heure » = session créée, jamais créditée :
    soit le client a abandonné (normal), soit le crédit a échoué (à vérifier
    dans le tableau de bord Stripe si le paiement y apparaît « réussi »)."""
    rows = (await db.execute(text(
        "SELECT p.id, p.user_id, u.artist_name, p.pack_id, p.credits, p.amount_cents, "
        "p.status, p.mode_test, p.created_at, p.smyles_recovered, p.shortfall "
        "FROM stripe_payments p LEFT JOIN users u ON u.id = p.user_id "
        "ORDER BY p.created_at DESC LIMIT :l"), {"l": max(1, min(limit, 1000))})).all()
    tot = (await db.execute(text(
        "SELECT "
        " count(*) FILTER (WHERE status = 'paye' AND NOT mode_test) AS nb_payes, "
        " COALESCE(sum(amount_cents) FILTER (WHERE status = 'paye' AND NOT mode_test), 0) AS euros_payes, "
        " count(*) FILTER (WHERE status = 'rembourse' AND NOT mode_test) AS nb_rembourses, "
        " count(*) FILTER (WHERE status = 'litige' AND NOT mode_test) AS nb_litiges, "
        " count(*) FILTER (WHERE status = 'created' AND created_at < now() - interval '1 hour') "
        "   AS nb_en_attente "
        "FROM stripe_payments"))).first()
    return {
        "totaux": {
            "paiementsReussis": int(tot.nb_payes),
            "eurosEncaisses": round(int(tot.euros_payes) / 100, 2),
            "rembourses": int(tot.nb_rembourses),
            "litiges": int(tot.nb_litiges),
            "enAttenteDepuisPlusDUneHeure": int(tot.nb_en_attente),
        },
        "paiements": [
            {
                "paiementId": str(r.id), "pseudo": r.artist_name, "pack": r.pack_id,
                "smyles": int(r.credits), "euros": round(int(r.amount_cents) / 100, 2),
                "statut": r.status, "test": bool(r.mode_test),
                "le": r.created_at.isoformat() if r.created_at else None,
                "smylesRepris": int(r.smyles_recovered), "smylesNonRepris": int(r.shortfall),
            }
            for r in rows
        ],
    }


async def infos_confirmation(db: AsyncSession, session_id: str) -> dict | None:
    """Données de l'email de confirmation d'un pack crédité (Lot L, L221-13)."""
    r = (await db.execute(text(
        "SELECT p.credits, p.amount_cents, p.consent_immediate_at, p.cgu_version, p.id, "
        "p.mode_test, u.email FROM stripe_payments p JOIN users u ON u.id = p.user_id "
        "WHERE p.session_id = :s AND p.status = 'paye'"), {"s": session_id})).first()
    if r is None or not r.email:
        return None
    return {
        "email": r.email, "smyles": int(r.credits), "euros_cents": int(r.amount_cents),
        "consentement_le": r.consent_immediate_at, "cgu_version": r.cgu_version,
        "paiement_id": str(r.id), "test": bool(r.mode_test),
    }
