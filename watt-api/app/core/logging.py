"""
Logs applicatifs — Lot E (tenue en charge et exploitation, 2026-10-09).

Avant ce module, aucun gestionnaire n'était posé sur le logger racine :
Python n'affichait que les messages WARNING et au-dessus, sans date, et
tous les `logger.info(...)` de l'application (refus d'envoi d'email, etc.)
étaient PERDUS.

`configurer_logs()` (appelée par `create_app`, dans chaque worker) :
  • niveau INFO par défaut (variable d'environnement LOG_LEVEL pour changer) ;
  • une ligne JSON par message sur la sortie standard, avec l'heure (UTC, ISO
    8601), le niveau, le nom du module et le message. Railway lit ce format :
    le champ `level` donne la gravité affichée (sans lui, tout ce qui sort sur
    stderr apparaît en rouge « error ») ;
  • LOG_FORMAT=texte donne une ligne lisible (utile en local) ;
  • adresses email MASQUÉES dans tous les messages (`t***@gmail.com`), y
    compris les journaux d'accès d'uvicorn : un log n'est pas un endroit sûr
    pour des données personnelles.

Idempotente : un second appel ne double pas les lignes.
"""
from __future__ import annotations

import logging
import os
import re
import sys

_EMAIL = re.compile(
    r"(?P<premier>[A-Za-z0-9])[A-Za-z0-9._%+\-]*@(?P<domaine>[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
)

_DEJA_CONFIGURE = "_watt_logs_configures"


def masquer_email(email: object) -> str:
    """`tom.lecomte1@gmail.com` → `t***@gmail.com`. Tolère None / vide."""
    texte = "" if email is None else str(email).strip()
    if not texte:
        return "-"
    if "@" not in texte:
        return texte[:1] + "***"
    local, _, domaine = texte.rpartition("@")
    return f"{local[:1]}***@{domaine}"


def masquer_emails_dans(texte: str) -> str:
    """Masque toutes les adresses email présentes dans un texte libre."""
    if "@" not in texte:
        return texte
    return _EMAIL.sub(lambda m: f"{m.group('premier')}***@{m.group('domaine')}", texte)


class FiltreEmails(logging.Filter):
    """Filet de sécurité : réécrit le message d'un enregistrement de log pour
    y masquer les adresses email (arguments compris)."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — format cassé : on laisse passer tel quel
            return True
        masque = masquer_emails_dans(message)
        if masque != message:
            record.msg = masque
            record.args = None
        return True


def _formatter(format_: str) -> logging.Formatter:
    import structlog

    pre_chaine = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if format_ == "texte":
        rendu = structlog.dev.ConsoleRenderer(colors=False)
        finaux = [structlog.stdlib.ProcessorFormatter.remove_processors_meta, rendu]
    else:
        finaux = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ]
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=pre_chaine,
        processors=finaux,
    )


def configurer_logs(niveau: str | None = None, format_: str | None = None) -> None:
    """Pose le gestionnaire de logs de l'application (une seule fois)."""
    racine = logging.getLogger()
    niveau = (niveau or os.getenv("LOG_LEVEL") or "INFO").upper()
    format_ = (format_ or os.getenv("LOG_FORMAT") or "json").lower()

    if not getattr(racine, _DEJA_CONFIGURE, False):
        gestionnaire = logging.StreamHandler(sys.stdout)
        gestionnaire.setFormatter(_formatter(format_))
        gestionnaire.addFilter(FiltreEmails())
        racine.addHandler(gestionnaire)
        setattr(racine, _DEJA_CONFIGURE, True)
    racine.setLevel(niveau)

    # Journaux d'uvicorn : ils ont leurs propres gestionnaires (format
    # inchangé) ; on y ajoute seulement le masquage des emails.
    for nom in ("uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(nom)
        if not any(isinstance(f, FiltreEmails) for f in lg.filters):
            lg.addFilter(FiltreEmails())

    # Bibliothèques bavardes en INFO (une ligne par requête HTTP sortante).
    for bruyant in ("botocore", "boto3", "urllib3", "s3transfer", "httpx", "httpcore"):
        logging.getLogger(bruyant).setLevel(logging.WARNING)
