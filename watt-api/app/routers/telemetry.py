"""
Télémétrie D0 — collecte privacy-first + funnel admin.

  POST /events         → ingestion batch (PUBLIC, auth optionnelle)
  GET  /admin/funnel   → funnel lisible (gated is_official OU is_admin)

Privacy-first : aucune PII stockée (pas d'IP, pas de user-agent). `session_id`
anonyme (client). `user_id` posé seulement si un Bearer valide est présent —
jamais accepté depuis le corps de la requête (anti-spoof).
Best-effort : la collecte ne bloque jamais ; en cas d'erreur on renvoie 202.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import ADMIN_FORBIDDEN_DETAIL, is_admin_user
from app.auth.jwt import decode_access_token, get_current_user
from app.core.ratelimit import limiter
from app.database import get_db
from app.models.analytics_event import AnalyticsEvent
from app.models.user import User
from app.services.analytics import ALLOWED_EVENTS, MAX_BATCH, MAX_STR, funnel_data
from app.services.users import get_user_by_email

router = APIRouter(tags=["telemetry"])


class EventIn(BaseModel):
    name: str
    path: str | None = None
    referrer: str | None = None
    props: dict | None = None


class EventsBatch(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    events: list[EventIn] = Field(default_factory=list)


async def _user_id_from_request(request: Request, db: AsyncSession):
    """Résout l'utilisateur depuis le Bearer SANS exiger l'auth (best-effort)."""
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    email = decode_access_token(token)
    if not email:
        return None
    try:
        user = await get_user_by_email(db, email)
        return user.id if user else None
    except Exception:
        return None


def _trunc(s: str | None) -> str | None:
    return s[:MAX_STR] if s else None


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("120/minute")
async def ingest_events(
    payload: EventsBatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = await _user_id_from_request(request, db)
    accepted = 0
    try:
        for ev in payload.events[:MAX_BATCH]:
            if ev.name not in ALLOWED_EVENTS:
                continue  # silencieux : on ignore les events hors whitelist
            db.add(AnalyticsEvent(
                session_id=payload.session_id[:64],
                user_id=user_id,
                name=ev.name,
                path=_trunc(ev.path),
                referrer=_trunc(ev.referrer),
                props=ev.props if isinstance(ev.props, dict) else None,
            ))
            accepted += 1
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        # Best-effort : on ne fait jamais échouer le client pour de la télémétrie.
        return {"accepted": 0}
    return {"accepted": accepted}


@router.get("/admin/funnel")
async def admin_funnel(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # K-01 : is_official OU is_admin (règle partagée).
    if not is_admin_user(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=ADMIN_FORBIDDEN_DETAIL)
    return await funnel_data(db, days)
