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

import html as _html
import logging

import httpx

from app.config import settings
from app.core.logging import masquer_email

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"

# Avertissement « emails désactivés » émis une seule fois par worker.
_averti_desactive = False

# Palette WATT (miroir de ui/core/tokens.css — un email ne charge pas de CSS
# externe, tout est inline).
_BG = "#070608"
_SURFACE = "#14101f"
_TEXT = "#e8e8f0"
_MUTED = "rgba(255,255,255,.66)"
_GOLD = "#ffd700"


def esc(value) -> str:
    """Lot A — échappe un texte saisi par un utilisateur (titre, nom, détail)
    avant de l'insérer dans le HTML d'un email : un titre « <a href=…> » ne
    doit jamais devenir un lien ou une mise en forme dans la boîte du
    destinataire."""
    return _html.escape("" if value is None else str(value), quote=True)


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


async def _send(to: str, subject: str, html: str, *, reply_to: str | None = None) -> bool:
    """
    Envoi bas niveau. Ne lève JAMAIS — best-effort intégral.

    Renvoie True seulement si Resend a accepté le message. B2 (2026-09-08) :
    avant, la fonction ne renvoyait rien et l'appelant ne pouvait pas savoir
    qu'un email n'était pas parti. Le mot de passe oublié en dépend.
    """
    if not to:
        return False
    if not emails_enabled():
        global _averti_desactive
        if not _averti_desactive:
            _averti_desactive = True
            logger.warning(
                "[emails] RESEND_API_KEY absente : aucun email n'est envoyé "
                "(bienvenue, vérification, mot de passe oublié, ventes)."
            )
        return False
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
                    # Lot D : les décisions de modération se contestent en
                    # répondant à l'email → la réponse part au contact.
                    **({"reply_to": [reply_to]} if reply_to else {}),
                },
            )
            if resp.status_code >= 400:
                # Refus de Resend (domaine non vérifié, quota, adresse
                # invalide…). Lot E : niveau WARNING (visible dans Railway),
                # adresse masquée. L'appelant reçoit False et décide s'il
                # faut alerter davantage (cf. reset MDP).
                logger.warning(
                    "[emails] envoi refusé par Resend (HTTP %s) vers %s, sujet « %s » : %s",
                    resp.status_code, masquer_email(to), subject[:80],
                    resp.text[:200],
                )
                return False
            logger.info("[emails] envoyé vers %s, sujet « %s »", masquer_email(to), subject[:80])
            return True
    except Exception:
        logger.warning(
            "[emails] échec d'envoi vers %s (Resend injoignable ?)",
            masquer_email(to), exc_info=True,
        )
        try:
            import sentry_sdk
            sentry_sdk.capture_exception()
        except Exception:
            pass
        return False


# ── Les 3 emails ──────────────────────────────────────────────────────────

async def send_sale_email(
    to: str,
    *,
    item_title: str,
    amount: int,
    buyer_name: str | None = None,
) -> None:
    """💸 À l'artiste : un de ses produits vient de se vendre."""
    who = f"<strong style='color:{_TEXT};'>{esc(buyer_name)}</strong> a acheté" if buyer_name else "Quelqu'un a acheté"
    body = f"""\
    <p style="color:{_MUTED};font-size:14px;line-height:1.6;margin:0 0 16px;">
      {who} « <strong style="color:{_TEXT};">{esc(item_title)}</strong> ».
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
                   border-bottom:1px solid rgba(255,255,255,.08);">{esc(item_title)}</td>
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
            elif item_kind == "visual_adn":
                artist = (seller.artist_name if seller else None) or "l'artiste"
                title = f"ADN visuel de {artist}"
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


async def send_password_reset_email(to: str, *, link: str) -> bool:
    """
    Lien de réinitialisation de mot de passe (jeton 60 min, usage unique).

    Renvoie True si Resend a accepté l'envoi, False sinon (module désactivé
    faute de RESEND_API_KEY, ou destinataire refusé tant que le domaine WATT
    n'est pas vérifié). L'appelant DOIT traiter False comme un incident
    d'exploitation : sans email, le testeur est enfermé dehors.
    """
    body = f"""\
    <p style="color:{_MUTED};font-size:14px;line-height:1.7;margin:0 0 18px;">
      Quelqu'un (toi, normalement) a demandé à réinitialiser le mot de passe
      de ton compte WATT. Ce lien est valable <strong style="color:{_TEXT};">60
      minutes</strong> et ne fonctionne qu'une fois :
    </p>
    <p style="text-align:center;margin:0 0 18px;">
      <a href="{link}" style="display:inline-block;background:{_GOLD};
         color:#070608;font-weight:800;padding:12px 28px;border-radius:999px;
         text-decoration:none;font-size:14px;">Choisir un nouveau mot de passe</a>
    </p>
    <p style="color:{_MUTED};font-size:12px;line-height:1.6;margin:0;">
      Si tu n'es pas à l'origine de cette demande, ignore simplement cet
      email — ton mot de passe actuel reste valable.
    </p>"""
    delivered = await _send(
        to, "Réinitialise ton mot de passe WATT",
        _layout("Mot de passe oublié ?", body),
    )
    if not delivered:
        # Bruyant exprès : c'est le seul email dont l'absence bloque un
        # utilisateur. Ni le lien ni le jeton ne sont journalisés.
        logger.error(
            "[emails] lien de réinitialisation NON ENVOYÉ à %s "
            "(emails_enabled=%s). Secours bêta : "
            "cd watt-api && python tools/reset_link.py <email>",
            masquer_email(to), emails_enabled(),
        )
    return delivered


async def send_verification_email(to: str, *, link: str) -> bool:
    """
    Lien de vérification d'email (jeton usage unique, 48 h). Phase A.

    Renvoie True si Resend a accepté l'envoi, False sinon (module désactivé
    faute de RESEND_API_KEY, ou destinataire refusé tant que le domaine WATT
    n'est pas vérifié). Best-effort : l'inscription n'échoue jamais si l'envoi
    ne part pas, et la vérification n'est pas bloquante par défaut
    (REQUIRE_EMAIL_VERIFIED=False) — un envoi manqué n'enferme personne dehors.

    Texte sobre : aucune promesse au-delà de « confirme ton adresse ».
    """
    body = f"""\
    <p style="color:{_MUTED};font-size:14px;line-height:1.7;margin:0 0 18px;">
      Confirme ton adresse email pour sécuriser ton compte WATT. Ce lien est
      valable <strong style="color:{_TEXT};">48 heures</strong> et ne
      fonctionne qu'une fois :
    </p>
    <p style="text-align:center;margin:0 0 18px;">
      <a href="{link}" style="display:inline-block;background:{_GOLD};
         color:#070608;font-weight:800;padding:12px 28px;border-radius:999px;
         text-decoration:none;font-size:14px;">Confirmer mon adresse</a>
    </p>
    <p style="color:{_MUTED};font-size:12px;line-height:1.6;margin:0;">
      Si tu n'es pas à l'origine de cette inscription, ignore simplement cet
      email.
    </p>"""
    return await _send(
        to, "Confirme ton adresse email WATT",
        _layout("Vérifie ton email", body),
    )


async def send_welcome_email(to: str, *, name: str | None = None) -> None:
    """Bienvenue à l'inscription."""
    hello = f"Bienvenue {esc(name)} ⚡" if name else "Bienvenue ⚡"
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


# ── Lot D — décisions de modération (DSA art. 16, 17 et 20) ────────────────

_LIBELLES_CIBLE = {
    "track": "un son", "prompt": "une recette", "image": "une image",
    "profil": "un profil", "playlist": "une playlist", "album": "un album",
    "adn": "un ADN musical", "visual_adn": "un ADN visuel", "voix": "une voix",
}


def libelle_cible(target_type: str | None) -> str:
    return _LIBELLES_CIBLE.get((target_type or "").strip().lower(), "un contenu")


def _paragraphe(texte_html: str) -> str:
    return (f'<p style="color:{_MUTED};font-size:14px;line-height:1.7;margin:0 0 14px;">'
            f"{texte_html}</p>")


def _bloc_recours() -> str:
    from app.core.legal import CONTACT_EMAIL

    return _paragraphe(
        "<strong style=\"color:" + _TEXT + ";\">Contester cette décision</strong> : "
        "réponds simplement à cet email, ou écris à "
        f'<a href="mailto:{esc(CONTACT_EMAIL)}" style="color:{_GOLD};">{esc(CONTACT_EMAIL)}</a> '
        "en expliquant pourquoi. Ta demande sera réexaminée par une personne, "
        "gratuitement. Tu peux aussi saisir le juge compétent."
    )


async def send_decision_auteur(
    to: str | None,
    *,
    nature: str,
    target_type: str | None = None,
    titre: str | None = None,
    motif: str,
    reference: str | None = None,
) -> bool:
    """Informe l'auteur d'un retrait de contenu (`nature="retrait"`) ou le
    titulaire d'un compte suspendu (`nature="suspension"`) : motif, référence
    et voie de recours (DSA art. 17). Best-effort, ne lève jamais."""
    from app.core.legal import CONTACT_EMAIL

    if not to or str(to).endswith("@deleted.watt"):
        return False
    try:
        if nature == "suspension":
            sujet = "Ton compte WATT est suspendu"
            titre_h = "Compte suspendu"
            intro = ("Ton compte WATT a été suspendu par la modération. Pendant la "
                     "suspension, tu ne peux plus te connecter et tes contenus ne "
                     "sont plus visibles ni en vente. Ceux qui les ont déjà achetés "
                     "gardent leur accès.")
        else:
            quoi = libelle_cible(target_type)
            nom = f" « {esc(titre)} »" if titre else ""
            sujet = "Un de tes contenus a été retiré de WATT"
            titre_h = "Contenu retiré"
            intro = (f"La modération a retiré {esc(quoi)}{nom} de la vitrine. "
                     "Il n'est plus visible ni en vente ; ceux qui l'ont déjà "
                     "acheté gardent leur accès.")
        corps = (
            _paragraphe(intro)
            + _paragraphe(f"<strong style=\"color:{_TEXT};\">Motif</strong> : {esc(motif)}")
            + (_paragraphe(f"Référence : {esc(reference)}") if reference else "")
            + _bloc_recours()
        )
        return await _send(to, sujet, _layout(titre_h, corps), reply_to=CONTACT_EMAIL)
    except Exception:  # noqa: BLE001
        logger.warning("[emails] décision de modération (auteur) : échec", exc_info=True)
        return False


async def send_levee_suspension(to: str | None) -> bool:
    """Informe le titulaire que sa suspension est levée."""
    if not to or str(to).endswith("@deleted.watt"):
        return False
    try:
        corps = _paragraphe("La suspension de ton compte WATT est levée : tu peux "
                            "te reconnecter, et tes contenus sont de nouveau visibles.")
        return await _send(to, "Ton compte WATT est rétabli", _layout("Compte rétabli", corps))
    except Exception:  # noqa: BLE001
        logger.warning("[emails] levée de suspension : échec", exc_info=True)
        return False


async def send_decision_signaleur(
    to: str | None,
    *,
    decision: str,
    target_type: str | None = None,
    titre: str | None = None,
    reference: str | None = None,
) -> bool:
    """Informe la personne qui a signalé de la décision prise (DSA art. 16 §5) :
    `decision` = "retire" (contenu retiré / compte suspendu) ou "rejete"."""
    from app.core.legal import CONTACT_EMAIL

    if not to or str(to).endswith("@deleted.watt"):
        return False
    try:
        quoi = libelle_cible(target_type)
        nom = f" « {esc(titre)} »" if titre else ""
        if decision == "retire":
            verdict = (f"Après examen, la modération a retiré {esc(quoi)}{nom} que tu "
                       "avais signalé. Merci pour ton signalement.")
        else:
            verdict = (f"Après examen, la modération a estimé que {esc(quoi)}{nom} que "
                       "tu avais signalé ne contrevient pas à nos règles : il reste en "
                       "ligne.")
        corps = (
            _paragraphe(verdict)
            + (_paragraphe(f"Référence du signalement : {esc(reference)}") if reference else "")
            + _paragraphe("Si tu n'es pas d'accord, réponds à cet email ou écris à "
                          f'<a href="mailto:{esc(CONTACT_EMAIL)}" style="color:{_GOLD};">'
                          f"{esc(CONTACT_EMAIL)}</a>.")
        )
        return await _send(to, "Suite donnée à ton signalement",
                           _layout("Ton signalement a été traité", corps),
                           reply_to=CONTACT_EMAIL)
    except Exception:  # noqa: BLE001
        logger.warning("[emails] décision de modération (signaleur) : échec", exc_info=True)
        return False
