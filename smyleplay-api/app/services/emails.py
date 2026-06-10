"""
Emails transactionnels WATT — via l'API Resend (chantier hygiène revenu,
2026-06-10).

PRINCIPES (non négociables) :
  - 100 % best-effort : un email qui échoue ne casse JAMAIS l'action métier
    (achat, inscription…). Toute exception est avalée + loggée + Sentry.
  - Sans RESEND_API_KEY en env : module silencieusement désactivé.
  - Mode test Resend (tant que le domaine WATT n'est pas déposé/vérifié) :
    seuls les envois vers l'adresse du compte Resend passent ; les autres
    sont refusés par l'API → loggés, jamais levés.

3 emails branchés :
  - send_sale_email     → 💸 à l'artiste quand un de ses produits se vend
  - send_receipt_email  → reçu à l'acheteur après un achat
  - send_welcome_email  → bienvenue à l'inscription
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"

# Palette WATT (miroir de ui/core/tokens.css — un email ne charge pas de CSS
# externe, tout est inline).
_BG = "#070608"
_SURFACE = "#14101f"
_TEXT = "#e8e8f0"
_MUTED = "rgba(255,255,255,.66)"
_GOLD = "#ffd700"


def emails_enabled() -> bool:
    return bool(settings.RESEND_API_KEY)


def _layout(title: str, body_html: str) -> str:
    """Gabarit unique charte WATT : fond noir, éclair or, contenu carte."""
    return f"""\
<!DOCTYPE html>
<html lang="fr"><body style="margin:0;padding:0;background:{_BG};">
<div style="max-width:520px;margin:0 auto;padding:32px 20px;
            font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="text-align:center;padding-bottom:18px;">
    <span style="font-size:22px;">⚡</span>
    <span style="color:{_GOLD};font-weight:800;letter-spacing:.12em;
                 font-size:15px;vertical-align:middle;">WATT</span>
  </div>
  <div style="background:{_SURFACE};border:1px solid rgba(255,255,255,.10);
              border-radius:14px;padding:26px 24px;">
    <h1 style="margin:0 0 14px;font-size:18px;color:{_TEXT};">{title}</h1>
    {body_html}
  </div>
  <p style="text-align:center;color:{_MUTED};font-size:11px;margin-top:18px;">
    WATT — la marketplace des produits promptés.<br>
    Email transactionnel lié à ton compte.
  </p>
</div>
</body></html>"""


async def _send(to: str, subject: str, html: str) -> None:
    """Envoi bas niveau. Ne lève JAMAIS — best-effort intégral."""
    if not emails_enabled() or not to:
        return
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(
                _RESEND_URL,
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.EMAIL_FROM,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            if resp.status_code >= 400:
                # Cas attendu en mode test (destinataire ≠ compte Resend) :
                # on logge en INFO, pas en erreur — c'est un état normal
                # tant que le domaine n'est pas vérifié.
                logger.info(
                    "[emails] envoi refusé (%s) vers %s : %s",
                    resp.status_code, to, resp.text[:200],
                )
    except Exception:
        logger.warning("[emails] échec d'envoi vers %s", to, exc_info=True)
        try:
            import sentry_sdk
            sentry_sdk.capture_exception()
        except Exception:
            pass


# ── Les 3 emails ──────────────────────────────────────────────────────────

async def send_sale_email(
    to: str,
    *,
    item_title: str,
    amount: int,
    buyer_name: str | None = None,
) -> None:
    """💸 À l'artiste : un de ses produits vient de se vendre."""
    who = f"<strong style='color:{_TEXT};'>{buyer_name}</strong> a acheté" if buyer_name else "Quelqu'un a acheté"
    body = f"""\
    <p style="color:{_MUTED};font-size:14px;line-height:1.6;margin:0 0 16px;">
      {who} « <strong style="color:{_TEXT};">{item_title}</strong> ».
    </p>
    <p style="font-size:26px;font-weight:800;color:{_GOLD};margin:0 0 16px;">
      +{amount} Smyles
    </p>
    <p style="color:{_MUTED};font-size:13px;line-height:1.6;margin:0;">
      Le montant est déjà sur ton solde. Détail dans ton WATT BOARD →
      Analytique.
    </p>"""
    await _send(to, f"💸 Vendu ! « {item_title} » (+{amount} Smyles)", _layout("Tu viens de vendre", body))


async def send_receipt_email(
    to: str,
    *,
    item_title: str,
    amount: int,
) -> None:
    """Reçu à l'acheteur : récapitulatif de l'achat."""
    body = f"""\
    <p style="color:{_MUTED};font-size:14px;line-height:1.6;margin:0 0 16px;">
      Ton achat est confirmé :
    </p>
    <table style="width:100%;border-collapse:collapse;margin:0 0 16px;">
      <tr>
        <td style="color:{_TEXT};font-size:14px;padding:8px 0;
                   border-bottom:1px solid rgba(255,255,255,.08);">{item_title}</td>
        <td style="color:{_GOLD};font-size:14px;font-weight:700;text-align:right;
                   border-bottom:1px solid rgba(255,255,255,.08);">−{amount} Smyles</td>
      </tr>
    </table>
    <p style="color:{_MUTED};font-size:13px;line-height:1.6;margin:0;">
      Ton exemplaire (fichier + recette) est disponible dans ta Bibliothèque.
      Ce reçu fait foi de ton achat.
    </p>"""
    await _send(to, f"Reçu — « {item_title} »", _layout("Merci pour ton achat ⚡", body))


async def send_purchase_emails(
    db,
    *,
    buyer,
    seller_id,
    amount: int,
    item_title: str | None = None,
    item_kind: str = "prompt",
) -> None:
    """
    Orchestrateur achat : 💸 au vendeur + reçu à l'acheteur.

    Best-effort intégral (ne lève jamais) — à appeler APRÈS le commit de
    l'achat, jamais avant. `buyer` = User courant (email + artist_name).
    `item_title` None → résolu depuis la DB selon `item_kind`
    ('prompt' | 'voice' | 'adn').
    """
    if not emails_enabled():
        return
    try:
        from sqlalchemy import select

        from app.models.user import User as _User

        seller = None
        if seller_id is not None:
            seller = (await db.execute(
                select(_User).where(_User.id == seller_id)
            )).scalar_one_or_none()

        title = (item_title or "").strip()
        if not title:
            if item_kind == "adn":
                artist = (seller.artist_name if seller else None) or "l'artiste"
                title = f"ADN musical de {artist}"
            else:
                title = "ta création" if item_kind == "prompt" else "une voix"

        buyer_name = getattr(buyer, "artist_name", None) or "Un artiste"
        if seller is not None and seller.email:
            await send_sale_email(
                seller.email,
                item_title=title, amount=amount, buyer_name=buyer_name,
            )
        if getattr(buyer, "email", None):
            await send_receipt_email(
                buyer.email, item_title=title, amount=amount,
            )
    except Exception:
        logger.warning("[emails] send_purchase_emails a échoué", exc_info=True)


async def send_welcome_email(to: str, *, name: str | None = None) -> None:
    """Bienvenue à l'inscription."""
    hello = f"Bienvenue {name} ⚡" if name else "Bienvenue ⚡"
    body = f"""\
    <p style="color:{_MUTED};font-size:14px;line-height:1.7;margin:0 0 14px;">
      Ton compte WATT est prêt. Ici, chaque son est généré par IA et chaque
      création porte sa <strong style="color:{_TEXT};">recette</strong> — le
      prompt exact qui l'a fait naître.
    </p>
    <p style="color:{_MUTED};font-size:14px;line-height:1.7;margin:0;">
      Pour commencer : crée ton profil, publie ta première création depuis le
      WATT BOARD, ou explore la marketplace et collectionne des exemplaires
      numérotés #X/N.
    </p>"""
    await _send(to, "Bienvenue sur WATT ⚡", _layout(hello, body))
