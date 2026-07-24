"""Modération DSA (Phase 3) — ban / unban / takedown via les endpoints admin.

Couvre le trou signalé à l'audit : capacité d'ACTION (pas seulement de réception).
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, update

from app.database import SessionLocal
from app.models.track import Track
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user


async def _mk_user(official: bool = False) -> dict:
    email = f"mod-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
        if official:
            await db.execute(
                update(User).where(User.id == uid).values(is_official=True)
            )
            await db.commit()
    return {"id": uid, "email": email, "password": "12345678"}


async def _token(client: AsyncClient, u: dict) -> str:
    r = await client.post("/auth/login",
                          json={"email": u["email"], "password": u["password"]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _cleanup(*uids):
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(Track).where(Track.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


@pytest.mark.asyncio
async def test_ban_blocks_login_and_access(client: AsyncClient):
    admin = await _mk_user(official=True)
    victim = await _mk_user()
    try:
        admin_tok = await _token(client, admin)
        victim_tok = await _token(client, victim)  # login OK avant ban
        h = {"Authorization": f"Bearer {admin_tok}"}

        # ban
        r = await client.post(f"/admin/users/{victim['id']}/ban",
                              json={"reason": "spam"}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        # le jeton existant du banni est désormais rejeté
        r = await client.get("/users/me",
                             headers={"Authorization": f"Bearer {victim_tok}"})
        assert r.status_code == 403, r.text

        # le banni ne peut plus se reconnecter
        r = await client.post("/auth/login",
                             json={"email": victim["email"], "password": victim["password"]})
        assert r.status_code == 403, r.text

        # unban → tout refonctionne
        r = await client.post(f"/admin/users/{victim['id']}/unban", headers=h)
        assert r.status_code == 200, r.text
        r = await client.post("/auth/login",
                             json={"email": victim["email"], "password": victim["password"]})
        assert r.status_code == 200, r.text
    finally:
        await _cleanup(admin["id"], victim["id"])


@pytest.mark.asyncio
async def test_non_admin_cannot_moderate(client: AsyncClient):
    lambda_user = await _mk_user()
    victim = await _mk_user()
    try:
        tok = await _token(client, lambda_user)
        h = {"Authorization": f"Bearer {tok}"}
        r = await client.post(f"/admin/users/{victim['id']}/ban",
                              json={"reason": "x"}, headers=h)
        assert r.status_code == 403, r.text
    finally:
        await _cleanup(lambda_user["id"], victim["id"])


@pytest.mark.asyncio
async def test_takedown_hides_reported_track(client: AsyncClient):
    admin = await _mk_user(official=True)
    owner = await _mk_user()
    track_id = uuid.uuid4()
    try:
        async with SessionLocal() as db:
            db.add(Track(id=track_id, artist_id=owner["id"], title="Bad", is_deleted=False))
            await db.commit()

        # un signalement anonyme sur ce track
        r = await client.post("/reports", json={
            "target_type": "track", "target_id": str(track_id),
            "reason": "contenu_illegal",
            "detail": "Contenu manifestement illégal.",
        })
        assert r.status_code == 201, r.text
        report_id = r.json()["id"]

        admin_tok = await _token(client, admin)
        h = {"Authorization": f"Bearer {admin_tok}"}
        r = await client.post(f"/admin/reports/{report_id}/takedown",
                              json={"ban_owner": False}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        # le track est bien masqué
        async with SessionLocal() as db:
            t = await db.get(Track, track_id)
            assert t.is_deleted is True
    finally:
        await _cleanup(admin["id"], owner["id"])
