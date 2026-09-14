"""
D3 Confiance (07/07) — tests du signalement DSA.

  1. test_report_anonymous : POST /reports SANS auth → 201 + accusé (id),
     reporter_id NULL, statut new.
  2. test_report_authenticated : POST avec Bearer → reporter_id rempli,
     reporter_email auto (celui du compte).
  3. test_admin_gate : GET /admin/reports par un non-admin → 403 ;
     PATCH statut par un non-admin → 403.
  4. test_is_admin_non_officiel_modere (N-02, 09/09) : un compte `is_admin`
     SANS `is_official` liste les signalements et en classe un — avant N-02,
     ces deux routes testaient encore `is_official` seul et Tom, admin par
     K-01, ne pouvait ni lister ni classer un signalement.

REQUIRES : Postgres réel via DATABASE_URL (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import delete, text, update

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.content_report import ContentReport
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user


async def _mk_user() -> tuple:
    email = f"pytest-report-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        return u.id, email


async def _login(client, email):
    r = await client.post("/auth/login",
                          json={"email": email, "password": "12345678"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _cleanup(user_ids, report_ids):
    async with SessionLocal() as db:
        if report_ids:
            await db.execute(delete(ContentReport).where(
                ContentReport.id.in_(report_ids)))
        if user_ids:
            await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


async def test_report_anonymous(client):
    rid = None
    try:
        r = await client.post("/reports", json={
            "target_type": "track",
            "target_id": str(uuid.uuid4()),
            "reason": "contenu_illegal",
            "detail": "Test signalement anonyme",
        })
        assert r.status_code == 201, r.text
        body = r.json()
        rid = body["id"]
        assert body["status"] == "new"
        assert body["reporter_id"] is None
    finally:
        await _cleanup([], [rid] if rid else [])


async def test_report_authenticated(client):
    uid, email = await _mk_user()
    rid = None
    try:
        headers = await _login(client, email)
        r = await client.post("/reports", headers=headers, json={
            "target_type": "image",
            "target_id": str(uuid.uuid4()),
            "reason": "contrefacon",
        })
        assert r.status_code == 201, r.text
        body = r.json()
        rid = body["id"]
        assert body["reporter_id"] == str(uid)
        assert body["reporter_email"] == email  # accusé auto pour un connecté
    finally:
        await _cleanup([uid], [rid] if rid else [])


async def test_admin_gate(client):
    uid, email = await _mk_user()
    try:
        headers = await _login(client, email)
        r = await client.get("/admin/reports", headers=headers)
        assert r.status_code == 403, r.text
        r2 = await client.patch(
            f"/admin/reports/{uuid.uuid4()}", headers=headers,
            json={"status": "reviewed"},
        )
        assert r2.status_code == 403, r2.text
    finally:
        await _cleanup([uid], [])


async def test_is_admin_non_officiel_modere(client):
    """N-02 : `is_admin` (sans `is_official`) suffit pour lister et classer."""
    uid, email = await _mk_user()
    rid = None
    try:
        async with SessionLocal() as db:
            await db.execute(update(User).where(User.id == uid)
                             .values(is_admin=True, is_official=False))
            await db.commit()
        headers = await _login(client, email)

        r = await client.post("/reports", json={
            "target_type": "track",
            "target_id": str(uuid.uuid4()),
            "reason": "contenu_illegal",
            "detail": "Signalement à classer par un admin non officiel",
        })
        assert r.status_code == 201, r.text
        rid = r.json()["id"]

        r = await client.get("/admin/reports?only_new=true", headers=headers)
        assert r.status_code == 200, r.text
        assert rid in {row["id"] for row in r.json()}

        r = await client.patch(f"/admin/reports/{rid}", headers=headers,
                               json={"status": "reviewed"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "reviewed"
        assert r.json()["resolved_at"] is not None
    finally:
        await _cleanup([uid], [rid] if rid else [])
