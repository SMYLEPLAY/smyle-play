"""
Télémétrie D0 — collecte privacy-first + funnel admin.

  POST /events         → ingestion batch (PUBLIC, auth optionnelle)
  GET  /admin/funnel   → funnel lisible (gated is_official OU is_admin)

B3 (2026-09-08) : le funnel ne compte plus les événements `signup` /
`purchase` — que le front n'émet nulle part, ce qui le rendait
structurellement vide. Les marches « Inscrits » et « 1er achat » sont
désormais lues dans `users` et `transactions` ; « Visiteurs » et
« Reviennent » restent télémétriques et sont étiquetées comme telles.
Le tableau d'activité de la bêta est `GET /admin/beta` (routers/admin.py).

Privacy-first : aucune PII stockée (pas d'IP, pas de user-agent). `session_id`
anonyme (client). Lot D : aucun événement n'est plus rattaché à un compte
(`user_id` toujours NULL, garanti en base par ck_analytics_events_sans_compte) —
la mesure annoncée comme anonyme l'est réellement. Conservation : 13 mois
(purge automatique, cf. services/analytics.py).
Best-effort : la collecte ne bloque jamais ; en cas d'erreur on renvoie 202.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import ADMIN_FORBIDDEN_DETAIL, is_admin_user
from app.auth.jwt import get_current_user
from app.core.ratelimit import limiter
from app.database import get_db
from app.models.analytics_event import AnalyticsEvent
from app.models.user import User
from app.services.analytics import ALLOWED_EVENTS, MAX_BATCH, MAX_STR, funnel_data

router = APIRouter(tags=["telemetry"])


class EventIn(BaseModel):
    name: str
    path: str | None = None
    referrer: str | None = None
    props: dict | None = None


class EventsBatch(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    events: list[EventIn] = Field(default_factory=list)


def _trunc(s: str | None) -> str | None:
    return s[:MAX_STR] if s else None


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("120/minute")
async def ingest_events(
    payload: EventsBatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    accepted = 0
    try:
        for ev in payload.events[:MAX_BATCH]:
            if ev.name not in ALLOWED_EVENTS:
                continue  # silencieux : on ignore les events hors whitelist
            db.add(AnalyticsEvent(
                session_id=payload.session_id[:64],
                user_id=None,  # Lot D : mesure sans compte
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


@router.post("/admin/mesure/purge")
async def admin_purge_mesure(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lot D — purge manuelle des données de mesure de plus de 13 mois (la
    même purge tourne seule au démarrage puis toutes les 24 h)."""
    if not is_admin_user(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=ADMIN_FORBIDDEN_DETAIL)
    from app.services.analytics import purger_mesure_ancienne

    n = await purger_mesure_ancienne(db)
    await db.commit()
    return {"supprimes": n}


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
