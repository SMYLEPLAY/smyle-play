"""
Sécurité images (2026-07-30) — re-clé des originaux à clé DEVINABLE.

Deux volets :
  1. Détection PURE de la « clé devinable » (uid original == uid aperçu) — sans
     R2 ni DB : _is_guessable_original / _uid_of_key / _ext_of_key.
  2. Gate admin : POST /admin/migrate-image-originals sans compte officiel →
     401 (anonyme) / 403 (connecté non-officiel).

REQUIRES (volet 2 seulement) : Postgres réel via DATABASE_URL (cf. conftest.py).
"""
import uuid

import pytest

from app.routers.reports import (
    _ext_of_key,
    _is_guessable_original,
    _uid_of_key,
)


# ── Volet 1 : détection pure (aucune I/O) ──────────────────────────────────

def test_uid_of_key():
    assert _uid_of_key("images/originals/abc123.png") == "abc123"
    assert _uid_of_key("images/previews/abc123.jpg") == "abc123"
    assert _uid_of_key("abc123") == "abc123"  # pas de dossier / extension
    assert _uid_of_key(None) is None
    assert _uid_of_key("") is None


def test_ext_of_key():
    assert _ext_of_key("images/originals/abc.png") == "png"
    assert _ext_of_key("images/originals/abc.WEBP") == "webp"  # normalisé
    assert _ext_of_key("images/originals/abc") == "jpg"  # défaut
    assert _ext_of_key(None) == "jpg"


def test_guessable_when_uids_equal():
    # Même uid entre original et aperçu → clé DEVINABLE → à migrer.
    uid = uuid.uuid4().hex
    assert _is_guessable_original(
        f"images/originals/{uid}.png", f"images/previews/{uid}.jpg"
    ) is True


def test_not_guessable_when_uids_differ():
    # uid original ALÉATOIRE séparé → déjà sûr → skip.
    assert _is_guessable_original(
        f"images/originals/{uuid.uuid4().hex}.png",
        f"images/previews/{uuid.uuid4().hex}.jpg",
    ) is False


def test_not_guessable_when_key_missing():
    uid = uuid.uuid4().hex
    assert _is_guessable_original(None, f"images/previews/{uid}.jpg") is False
    assert _is_guessable_original(f"images/originals/{uid}.png", None) is False
    assert _is_guessable_original(None, None) is False


# ── Volet 2 : gate admin (nécessite Postgres) ──────────────────────────────

from sqlalchemy import delete  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402
from app.services.users import create_user  # noqa: E402


async def _mk_user() -> tuple:
    email = f"pytest-migimg-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        u = await create_user(db, UserCreate(email=email, password="12345678"))
        return u.id, email


async def _login(client, email):
    r = await client.post("/auth/login",
                          json={"email": email, "password": "12345678"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _cleanup(user_ids):
    async with SessionLocal() as db:
        if user_ids:
            await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_migrate_requires_auth(client):
    # Sans Bearer → 401 (endpoint authentifié).
    r = await client.post("/admin/migrate-image-originals")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio(loop_scope="session")
async def test_migrate_requires_official(client):
    # Connecté mais non-officiel → 403.
    uid, email = await _mk_user()
    try:
        headers = await _login(client, email)
        r = await client.post("/admin/migrate-image-originals", headers=headers)
        assert r.status_code == 403, r.text
    finally:
        await _cleanup([uid])
