"""
Génère un lien de réinitialisation de mot de passe SANS passer par l'email.

POURQUOI (ticket B2, bêta interne 2026-09-08)
─────────────────────────────────────────────
Tant que le domaine WATT n'est pas déposé et vérifié chez Resend, aucun email
transactionnel ne part vers un testeur : sans RESEND_API_KEY le module email
est désactivé, et avec une clé mais sans domaine vérifié Resend n'accepte que
l'adresse du propriétaire du compte. Résultat : un testeur qui perd son mot de
passe perd son compte, le jeton n'existant qu'en empreinte SHA-256 en base.

Cet outil produit le MÊME jeton que `POST /auth/forgot-password` (même
fonction : app/services/password_reset.py — 32 bytes urlsafe, empreinte
SHA-256, 60 minutes, usage unique, invalidation du lien précédent) et affiche
le lien pour que Tom le transmette au testeur par le canal de son choix.

DANGER — LIRE AVANT D'UTILISER
──────────────────────────────
Ce script donne à son porteur le pouvoir de prendre la main sur N'IMPORTE
QUEL compte : un lien émis ici permet de changer le mot de passe sans rien
connaître de l'ancien. Il n'a donc AUCUNE route HTTP (un endpoint de
réinitialisation administrative serait une porte dérobée), il s'exécute
uniquement sur la machine d'ops de Tom, contre la base pointée par
`watt-api/.env`, et chaque émission laisse une trace dans le journal
applicatif (logger `app.services.password_reset`, niveau WARNING).

Dispositif de BÊTA INTERNE : à retirer au profit de l'envoi automatique dès
que le domaine sera configuré chez Resend.

USAGE
─────
    cd watt-api
    python tools/reset_link.py testeur@example.com
    python tools/reset_link.py testeur@example.com --base-url https://watt.market

L'origine du lien vient de `--base-url`, sinon de PUBLIC_BASE_URL. Sans l'un
ni l'autre le script refuse d'agir : un lien pointant sur le mauvais hôte est
un jeton brûlé pour rien.

Le lien n'est affiché QU'UNE FOIS (seule l'empreinte reste en base) : si tu le
perds, relance la commande — le lien précédent est alors invalidé.

Sortie : 0 si un lien a été émis, 1 sinon (compte inconnu, supprimé, banni,
ou base d'origine manquante).
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import socket
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.services.password_reset import (  # noqa: E402
    RESET_TOKEN_TTL_MINUTES,
    ResetLinkRefused,
    issue_reset_link_for_email,
)


async def emit_link(email: str, base_url: str) -> int:
    async with SessionLocal() as db:
        try:
            user, link = await issue_reset_link_for_email(
                db, email, base_url=base_url
            )
        except ResetLinkRefused as exc:
            print(f"REFUSÉ : {exc}", file=sys.stderr)
            return 1

    # Trace opérateur, en plus de celle du service. Ni jeton ni lien.
    logging.getLogger("watt.tools.reset_link").warning(
        "[reset-secours] émis par operateur=%s@%s pour user_id=%s email=%s",
        getpass.getuser(), socket.gethostname(), user.id, user.email,
    )

    print("")
    print("  Lien de réinitialisation — À USAGE UNIQUE, AFFICHÉ UNE SEULE FOIS")
    print(f"  Compte  : {user.email}  (id={user.id})")
    print(f"  Validité: {RESET_TOKEN_TTL_MINUTES} minutes")
    print("")
    print(f"  {link}")
    print("")
    print("  Transmets-le au testeur par un canal direct (message privé).")
    print("  Il n'est plus récupérable : seule son empreinte est en base.")
    print("  Émettre un nouveau lien invalide celui-ci.")
    print("")
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ap = argparse.ArgumentParser(
        description=(
            "Lien de réinitialisation de mot de passe hors email "
            "(secours bêta interne — outil local, jamais exposé en HTTP)."
        ),
    )
    ap.add_argument("email", help="Email du compte à dépanner.")
    ap.add_argument(
        "--base-url",
        default=None,
        help="Origine du lien (ex. https://watt.market). "
             "Défaut : variable d'environnement PUBLIC_BASE_URL.",
    )
    args = ap.parse_args()

    base_url = (args.base_url or os.getenv("PUBLIC_BASE_URL") or "").strip()
    if not base_url:
        ap.error(
            "origine du lien inconnue : passe --base-url https://<hôte> "
            "ou pose PUBLIC_BASE_URL."
        )
    return asyncio.run(emit_link(args.email, base_url))


if __name__ == "__main__":
    raise SystemExit(main())
