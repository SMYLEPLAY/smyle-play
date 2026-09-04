"""F-03 (2026-09-02) — `funnel_data` avec la fenêtre `days` en paramètre lié.

Aucun test ne couvrait `services/analytics.funnel_data` : la réécriture des
requêtes (`interval '1 day' * :days` au lieu d'une interpolation f-string,
pour lever bandit B608) aurait pu casser `/telemetry/admin/funnel` sans que
personne ne le voie. Test « bout de chaîne » sur la vraie base : on insère un
événement récent et un événement vieux de 40 jours pour une session unique,
puis on vérifie que la fenêtre les inclut/exclut correctement.
"""
import uuid

from sqlalchemy import text

from app.database import SessionLocal
from app.services.analytics import funnel_data


async def _visitors(db, days: int) -> int:
    data = await funnel_data(db, days=days)
    assert data["window_days"] == days
    return data["funnel"][0]["count"]


async def test_funnel_fenetre_days_liee_en_parametre():
    session_recente = f"pytest-f03-{uuid.uuid4().hex}"
    session_ancienne = f"pytest-f03-{uuid.uuid4().hex}"
    async with SessionLocal() as db:
        try:
            avant_7 = await _visitors(db, 7)
            avant_365 = await _visitors(db, 365)

            await db.execute(
                text(
                    "INSERT INTO analytics_events (session_id, name, created_at) "
                    "VALUES (:recente, 'visit', now()), "
                    "(:ancienne, 'visit', now() - interval '40 days')"
                ),
                {"recente": session_recente, "ancienne": session_ancienne},
            )
            await db.commit()

            # 7 jours : seule la session récente entre dans la fenêtre.
            assert await _visitors(db, 7) == avant_7 + 1
            # 365 jours : les deux.
            assert await _visitors(db, 365) == avant_365 + 2

            # Bornes : days est ramené dans 1..365 (pas d'erreur SQL).
            assert (await funnel_data(db, days=0))["window_days"] == 1
            assert (await funnel_data(db, days=9999))["window_days"] == 365
        finally:
            await db.execute(
                text("DELETE FROM analytics_events WHERE session_id IN (:a, :b)"),
                {"a": session_recente, "b": session_ancienne},
            )
            await db.commit()


async def test_funnel_structure_complete():
    async with SessionLocal() as db:
        data = await funnel_data(db, days=30)

    assert [s["key"] for s in data["funnel"]] == [
        "visitors", "signups", "buyers", "returning",
    ]
    assert set(data["conversions"]) == {
        "visit_to_signup", "signup_to_purchase", "visit_to_purchase",
    }
    assert isinstance(data["by_event"], list)
