"""
D3 Confiance (07/07) — tests du signalement DSA.

  1. test_report_anonymous : POST /reports SANS auth → 201 + accusé (id),
     reporter_id NULL, statut new.
  2. test_report_authenticated : POST avec Bearer → reporter_id rempli,
     reporter_email auto (celui du compte).
  3. test_admin_gate : GET /admin/reports par un non-admin → 403 ;
     PATCH statut par un non-admin → 403.

REQUIRES : Postgres réel via DATABASE_URL (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import delete, text

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
