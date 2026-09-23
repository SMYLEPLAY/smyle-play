"""Activité par jour (Lot 2) — base des mesures « prêt à sortir ».

Une ligne `user_activity_days(user_id, day)` par compte et par jour où il a été
vu CONNECTÉ (toute requête authentifiée passe par `get_current_user`), plus un
drapeau `listened` quand il a écouté un son en étant connecté.

Contrainte : ne JAMAIS ralentir une requête.
  - un cache mémoire (par processus) retient les couples déjà écrits
    aujourd'hui → au plus UNE écriture par compte et par jour et par processus ;
  - l'écriture part dans une tâche de fond, avec sa propre session, HORS du
    chemin de la requête ; `INSERT … ON CONFLICT` la rend idempotente entre
    processus (plusieurs répliques Railway) ;
  - toute erreur est avalée et journalisée : la mesure ne casse rien.

Le cache est vidé au changement de jour (UTC) et borné en taille.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import text

log = logging.getLogger(__name__)

_MAX_CACHE = 200_000

_cache_day: date | None = None
_seen: set[tuple[UUID, bool]] = set()
_tasks: set[asyncio.Task] = set()


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _should_write(user_id: UUID, listened: bool) -> bool:
    global _cache_day
    today = _today()
    if _cache_day != today or len(_seen) > _MAX_CACHE:
        _seen.clear()
        _cache_day = today
    key = (user_id, listened)
    if key in _seen:
        return False
    _seen.add(key)
    return True


async def record_activity(user_id: UUID, *, listened: bool = False, day: date | None = None) -> None:
    """Écrit (ou complète) la ligne du jour. Idempotent. Ne lève jamais."""
    from app.database import SessionLocal

    try:
        async with SessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO user_activity_days (user_id, day, listened) "
                    "VALUES (:u, :d, :l) "
                    "ON CONFLICT (user_id, day) DO UPDATE "
                    "SET listened = user_activity_days.listened OR EXCLUDED.listened "
                    "WHERE EXCLUDED.listened AND NOT user_activity_days.listened"
                ),
                {"u": user_id, "d": day or _today(), "l": listened},
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — la mesure ne doit jamais casser une requête
        log.warning("activity.record_failed", exc_info=True)
        _seen.discard((user_id, listened))


def note_activity(user_id: UUID | None, *, listened: bool = False) -> None:
    """À appeler depuis une requête : programme l'écriture en tâche de fond si
    ce compte n'a pas encore été noté aujourd'hui (dans ce processus)."""
    if user_id is None or not _should_write(user_id, listened):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(record_activity(user_id, listened=listened))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def drain() -> None:
    """Attend les écritures en cours (tests, arrêt propre)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


def reset_cache() -> None:
    """Vide le cache (tests)."""
    _seen.clear()
