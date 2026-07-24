"""
D3 Confiance (07/07) — signalement de contenu (conformité DSA art. 16).

Routes :
  POST  /reports               → déposer un signalement (ANONYME AUTORISÉ,
                                 rate-limité ; accusé de réception dans la
                                 réponse + email best-effort si connu)
  GET   /admin/reports         → liste (admin = is_official), new en premier
  PATCH /admin/reports/{id}    → changer le statut (reviewed/actioned/rejected)

Notification : chaque nouveau signalement notifie le compte officiel (SYSTEM)
+ email best-effort à REPORT_NOTIFY_EMAIL si configuré (jamais d'adresse en
dur — repo public).
"""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import decode_access_token
from app.core.ratelimit import limiter
from app.database import get_db
from app.models.content_report import ContentReport, ReportReason, ReportStatus
from app.models.user import User

router = APIRouter(tags=["reports"])

_TARGET_TYPES = ("track", "prompt", "image", "profil", "playlist", "album")


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_type: Literal["track", "prompt", "image", "profil", "playlist", "album"]
    target_id: str = Field(min_length=1, max_length=64)
    reason: ReportReason
    detail: str | None = Field(default=None, max_length=2000)
    # Pour l'accusé de réception d'un signalement ANONYME (facultatif).
    reporter_email: EmailStr | None = None


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reporter_id: UUID | None = None
    reporter_email: str | None = None
    target_type: str
    target_id: str
    reason: ReportReason
    detail: str | None = None
    status: ReportStatus
    created_at: datetime
    resolved_at: datetime | None = None


class ReportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["reviewed", "actioned", "rejected"]


async def _optional_user(request: Request, db: AsyncSession) -> User | None:
    """Auth OPTIONNELLE : le DSA impose un mécanisme accessible à tous,
    y compris sans compte. On décode le Bearer si présent, sinon None."""
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    email = decode_access_token(auth[7:].strip())
    if not email:
        return None
    from app.services.users import get_user_by_email
    try:
        return await get_user_by_email(db, email)
    except Exception:
        return None


@router.post("/reports", response_model=ReportRead,
             status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def create_report(
    payload: ReportCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ReportRead:
    """Dépose un signalement. Accusé de réception = la réponse 201 (id de
    suivi) + email best-effort si une adresse est connue (DSA art. 16)."""
    user = await _optional_user(request, db)

    report = ContentReport(
        reporter_id=user.id if user else None,
        reporter_email=(payload.reporter_email
                        or (user.email if user else None)),
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason=payload.reason,
        detail=payload.detail,
    )
    db.add(report)
    await db.flush()

    # Notif SYSTEM au compte officiel (modération) — best-effort.
    try:
        from app.models.notification import NotificationType
        from app.services.notifications import create_notification
        official = (await db.execute(
            select(User).where(User.is_official.is_(True)).limit(1)
        )).scalar_one_or_none()
        if official:
            await create_notification(
                db,
                user_id=official.id,
                type=NotificationType.SYSTEM,
                actor_id=user.id if user else None,
                target_type="report",
                target_id=report.id,
                metadata={
                    "text": f"⚑ Nouveau signalement ({payload.reason.value}) "
                            f"sur {payload.target_type}",
                },
            )
    except Exception:
        pass

    await db.commit()
    await db.refresh(report)

    # Emails best-effort APRÈS commit : modérateur + accusé de réception.
    try:
        import os
        from app.services.emails import _layout, _send
        notify = os.environ.get("REPORT_NOTIFY_EMAIL")
        if notify:
            await _send(
                notify,
                f"⚑ Signalement {payload.reason.value} — {payload.target_type}",
                _layout(
                    "Nouveau signalement",
                    (f"<p>Motif : <b>{payload.reason.value}</b> · cible : "
                     f"<b>{payload.target_type}</b> ({payload.target_id}).</p>"
                     f"<p>{(payload.detail or '')[:500]}</p>"
                     f"<p>Réf : {report.id}</p>"),
                ),
            )
        if report.reporter_email:
            await _send(
                report.reporter_email,
                "Accusé de réception de ton signalement",
                _layout(
                    "Signalement bien reçu",
                    (f"<p>Ton signalement a bien été enregistré "
                     f"(réf. {report.id}).</p>"
                     f"<p>Il sera examiné dans les meilleurs délais, "
                     f"conformément à notre procédure de modération.</p>"),
                ),
            )
    except Exception:
        pass

    return ReportRead.model_validate(report)


@router.get("/admin/reports", response_model=list[ReportRead])
async def list_reports(
    only_new: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReportRead]:
    if not current_user.is_official:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Réservé à l'administration")
    q = select(ContentReport)
    if only_new:
        q = q.where(ContentReport.status == ReportStatus.NEW)
    q = q.order_by(
        (ContentReport.status == ReportStatus.NEW).desc(),
        desc(ContentReport.created_at),
    ).limit(200)
    rows = (await db.execute(q)).scalars().all()
    return [ReportRead.model_validate(r) for r in rows]


@router.patch("/admin/reports/{report_id}", response_model=ReportRead)
async def patch_report(
    report_id: UUID,
    payload: ReportPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportRead:
    if not current_user.is_official:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Réservé à l'administration")
    report = (await db.execute(
        select(ContentReport).where(ContentReport.id == report_id)
    )).scalar_one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail="Signalement introuvable")
    report.status = ReportStatus(payload.status)
    report.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(report)
    return ReportRead.model_validate(report)


# ─────────────────────────────────────────────────────────────────────────
# Modération ACTIONNABLE (Phase 3 lancement, 2026-07-24)
# Le PATCH ci-dessus ne fait que changer un libellé. Le DSA exige une capacité
# d'ACTION : retirer le contenu signalé et/ou suspendre un compte. Ces routes
# le permettent, réservées au compte officiel (is_official).
# ─────────────────────────────────────────────────────────────────────────


class TakedownRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Suspendre aussi le compte auteur du contenu retiré.
    ban_owner: bool = False
    reason: str | None = Field(default=None, max_length=500)


class BanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


class ModerationResult(BaseModel):
    ok: bool
    detail: str


def _require_official(current_user: User) -> None:
    if not current_user.is_official:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Réservé à l'administration")


@router.post("/admin/reports/{report_id}/takedown",
             response_model=ModerationResult)
async def takedown_reported_content(
    report_id: UUID,
    payload: TakedownRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ModerationResult:
    """
    Retire le contenu ciblé par un signalement (le rend invisible sans
    supprimer la ligne = preuve conservée), passe le signalement à `actioned`,
    et suspend optionnellement le compte auteur.
    """
    _require_official(current_user)
    from app.services.moderation import ban_user, takedown_content

    report = (await db.execute(
        select(ContentReport).where(ContentReport.id == report_id)
    )).scalar_one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail="Signalement introuvable")

    result = await takedown_content(
        db, report.target_type, report.target_id, payload.reason
    )
    if not result["ok"]:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=result["detail"])

    if payload.ban_owner:
        owner_id = await _resolve_owner_id(db, report.target_type, report.target_id)
        if owner_id is not None:
            await ban_user(db, owner_id, payload.reason)

    report.status = ReportStatus.ACTIONED
    report.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return ModerationResult(ok=True, detail=result["detail"])


@router.post("/admin/users/{user_id}/ban", response_model=ModerationResult)
async def ban_account(
    user_id: UUID,
    payload: BanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ModerationResult:
    """Suspend un compte (login + accès authentifié bloqués)."""
    _require_official(current_user)
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Impossible de se suspendre soi-même.")
    from app.services.moderation import ban_user

    user = await ban_user(db, user_id, payload.reason)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Compte introuvable")
    await db.commit()
    return ModerationResult(ok=True, detail="Compte suspendu.")


@router.post("/admin/users/{user_id}/unban", response_model=ModerationResult)
async def unban_account(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ModerationResult:
    """Rétablit un compte suspendu."""
    _require_official(current_user)
    from app.services.moderation import unban_user

    user = await unban_user(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Compte introuvable")
    await db.commit()
    return ModerationResult(ok=True, detail="Compte rétabli.")


async def _resolve_owner_id(db: AsyncSession, target_type: str, target_id: str):
    """Retrouve le compte propriétaire d'un contenu (pour ban_owner)."""
    import uuid as _uuid

    from app.models.album import Album
    from app.models.playlist import Playlist
    from app.models.prompt import Prompt
    from app.models.track import Track

    ttype = (target_type or "").strip().lower()
    try:
        tid = _uuid.UUID(str(target_id))
    except (ValueError, TypeError):
        return None
    if ttype == "profil":
        return tid
    model = {
        "prompt": Prompt, "image": Prompt, "track": Track,
        "playlist": Playlist, "album": Album,
    }.get(ttype)
    if model is None:
        return None
    obj = (await db.execute(select(model).where(model.id == tid))).scalar_one_or_none()
    if obj is None:
        return None
    for attr in ("artist_id", "owner_id", "user_id", "creator_id"):
        if hasattr(obj, attr):
            return getattr(obj, attr)
    return None
