"""Fonction de rétractation en ligne (art. L221-21 et D221-5 du Code de la
consommation, en vigueur depuis le 19 juin 2026).

  POST /retractation             (public, connecté ou non) → déclaration
  GET  /admin/retractations      (admin)                   → déclarations reçues

Parcours exigé par le texte : un lien « Renoncer au contrat ici » (pied de
page de toutes les pages) ouvre la page /retractation ; le consommateur y
remplit sa déclaration (nom et prénom, achat visé, email pour l'accusé de
réception), puis la valide avec le bouton « Confirmer la rétractation ».
Nous lui envoyons aussitôt un accusé de réception sur support durable
(email) qui reprend la déclaration, avec la date et l'heure.

La déclaration est TOUJOURS enregistrée, même quand le droit de rétractation
ne s'applique plus (Smyles livrés après renonciation, achat entre
particuliers) : c'est l'équipe qui l'examine et répond.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.core.ratelimit import LIMIT_RETRACTATION, limiter
from app.database import get_db
from app.models.user import User

log = logging.getLogger(__name__)
router = APIRouter(tags=["rétractation"])

_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _optional_user(
    token: str | None = Depends(_optional_oauth2),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    # Sert uniquement à RATTACHER la déclaration au compte (aide au
    # traitement), jamais à autoriser quoi que ce soit : la rétractation est
    # ouverte à tous, sans compte et sans condition d'acceptation des CGU.
    from app.auth.jwt import resolve_optional_user

    return await resolve_optional_user(db, token)


class RetractationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nom_prenom: str = Field(min_length=2, max_length=120)
    contrat: str = Field(min_length=3, max_length=500)
    email: EmailStr
    message: str | None = Field(default=None, max_length=2000)

    @field_validator("message")
    @classmethod
    def _vide_vers_none(cls, v: str | None) -> str | None:
        return v or None


def _texte_date(dt: datetime) -> str:
    # Base des fuseaux parfois absente du conteneur : jamais d'erreur, on
    # retombe alors sur l'heure UTC (en le disant).
    try:
        local, fuseau = dt.astimezone(ZoneInfo("Europe/Paris")), "heure de Paris"
    except Exception:  # noqa: BLE001
        local, fuseau = dt.astimezone(timezone.utc), "UTC"
    return local.strftime("%d/%m/%Y à %H:%M:%S") + f" ({fuseau})"


async def _prevenir_equipe(db: AsyncSession, **infos) -> None:
    """Email au contact WATT + notification au compte officiel. Best-effort."""
    try:
        from app.core.legal import CONTACT_EMAIL
        from app.services.emails import send_alerte_retractation

        await send_alerte_retractation(CONTACT_EMAIL, **infos)
    except Exception:  # noqa: BLE001
        log.warning("retractation.alerte_email_echec", exc_info=True)
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
                    f"⚠ Rétractation reçue de {infos['nom_prenom']} "
                    f"({infos['email_client']}). À traiter : /admin/retractations."
                )},
            )
    except Exception:  # noqa: BLE001
        log.warning("retractation.alerte_notif_echec", exc_info=True)


@router.post("/retractation", status_code=status.HTTP_201_CREATED)
@limiter.limit(LIMIT_RETRACTATION)
async def declarer_retractation(
    payload: RetractationIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(_optional_user),
) -> dict:
    ref = uuid4()
    recue_le = datetime.now(timezone.utc)
    email = str(payload.email).strip().lower()
    await db.execute(
        text(
            "INSERT INTO retractations "
            "(id, user_id, nom_prenom, contrat, email, message, created_at) "
            "VALUES (:id, :uid, :nom, :contrat, :email, :msg, :at)"
        ),
        {
            "id": ref, "uid": user.id if user else None,
            "nom": payload.nom_prenom, "contrat": payload.contrat,
            "email": email, "msg": payload.message, "at": recue_le,
        },
    )
    # La déclaration est gardée même si l'envoi d'email échoue ensuite.
    await db.commit()

    recue_le_texte = _texte_date(recue_le)
    reference = str(ref)[:8].upper()
    from app.services.emails import send_accuse_retractation

    ar_envoye = await send_accuse_retractation(
        email, nom_prenom=payload.nom_prenom, contrat=payload.contrat,
        message=payload.message, recue_le_texte=recue_le_texte,
        reference=reference,
    )
    if ar_envoye:
        await db.execute(
            text("UPDATE retractations SET ar_envoye = TRUE WHERE id = :id"),
            {"id": ref},
        )
    await _prevenir_equipe(
        db, nom_prenom=payload.nom_prenom, contrat=payload.contrat,
        email_client=email, message=payload.message,
        recue_le_texte=recue_le_texte, reference=reference,
    )
    await db.commit()

    return {
        "reference": reference,
        "nom_prenom": payload.nom_prenom,
        "contrat": payload.contrat,
        "email": email,
        "message": payload.message,
        "recue_le": recue_le.isoformat(),
        "recue_le_texte": recue_le_texte,
        "accuse_envoye": ar_envoye,
    }


@router.get("/admin/retractations")
async def lister_retractations(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT id, user_id, nom_prenom, contrat, email, message, statut, "
        "ar_envoye, created_at FROM retractations "
        "ORDER BY created_at DESC LIMIT 200"
    ))).all()
    return [
        {
            "reference": str(r.id)[:8].upper(),
            "id": str(r.id),
            "user_id": str(r.user_id) if r.user_id else None,
            "nom_prenom": r.nom_prenom,
            "contrat": r.contrat,
            "email": r.email,
            "message": r.message,
            "statut": r.statut,
            "accuse_envoye": bool(r.ar_envoye),
            "recue_le": r.created_at.isoformat() if r.created_at else None,
            "recue_le_texte": _texte_date(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]


async def purger_retractations_anciennes(db: AsyncSession) -> int:
    """Supprime les déclarations reçues il y a plus de RETRACTATIONS_RETENTION_ANS
    ans. Ne commit pas. Renvoie le nombre supprimé."""
    from app.core.legal import RETRACTATIONS_RETENTION_ANS

    res = await db.execute(text(
        "DELETE FROM retractations "
        "WHERE created_at < now() - make_interval(years => :a)"),
        {"a": RETRACTATIONS_RETENTION_ANS})
    return int(res.rowcount or 0)
