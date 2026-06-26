"""Journal de téléchargements (H0.5+) — le helper enregistre bien un événement."""
import uuid

import pytest
from sqlalchemy import delete, select

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.download_event import DownloadEvent
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.downloads import log_download
from app.services.users import create_user


async def test_log_download_records_event():
    email = f"pytest-dl-{uuid.uuid4().hex[:10]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = u.id
    pid = uuid.uuid4()
    try:
        async with SessionLocal() as db:
            await log_download(db, user_id=uid, product_id=pid, kind="audio")
        async with SessionLocal() as db:
            rows = (await db.execute(
                select(DownloadEvent).where(DownloadEvent.user_id == uid)
            )).scalars().all()
        assert len(rows) == 1, f"attendu 1 événement, reçu {len(rows)}"
        assert rows[0].kind == "audio"
        assert rows[0].product_id == pid
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(DownloadEvent).where(DownloadEvent.user_id == uid))
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
