"""
S-03 sécurité (2026-09-02) — `audio_url` du snapshot de prompt dans les
offres d'échange (audit A §B2 étape 5).

`GET /trades/offers/me` renvoie, pour chaque prompt, l'audio du track lié
(« écouter avant d'accepter »). Cette valeur part dans un `src="…"` côté
front : une audio_url historique non conforme (guillemet, `javascript:`)
n'est plus renvoyée (None) ; une URL légitime (`/watt/stream/…`) l'est
toujours. Postgres requis (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import delete

from app.config import settings
from app.database import SessionLocal
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_user() -> uuid.UUID:
    email = f"pytest-snap-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password="12345678"))
        return user.id


async def _seed_prompt_with_track(artist_id: uuid.UUID, audio_url: str) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Prompt(
            artist_id=artist_id,
            title=f"Prompt {uuid.uuid4().hex[:8]}",
            description="Tagline",
            prompt_text="X" * 100,
            price_credits=10,
            is_published=True,
        )
        db.add(p)
        await db.flush()
        # Track lié (audio_url insérée DIRECTEMENT en base : simule une
        # ligne historique antérieure au validateur de TrackCreate).
        db.add(Track(
            title="Son piégé", artist_id=artist_id,
            audio_url=audio_url, prompt_id=p.id,
        ))
        await db.commit()
        return p.id


async def _cleanup(sender_id: uuid.UUID, receiver_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(Track).where(Track.artist_id == sender_id))
        await db.execute(delete(Prompt).where(Prompt.artist_id == sender_id))
        await db.execute(delete(User).where(User.id == receiver_id))
        await db.commit()


async def _offer_snapshot(client, auth_headers, receiver_id, prompt_id) -> dict:
    r = await client.post(
        "/trades/offers",
        json={"receiver_id": str(receiver_id), "offered_prompt_id": str(prompt_id)},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    offer_id = r.json()["id"]
    r = await client.get("/trades/offers/me", headers=auth_headers)
    assert r.status_code == 200, r.text
    mine = [o for o in r.json() if o["id"] == offer_id]
    assert len(mine) == 1
    return mine[0]["offered_prompt"]


async def test_prompt_snap_audio_url_sanitized(client, test_user, auth_headers, monkeypatch):
    # S-08 (2026-09-02) : le routeur /trades est désormais gaté par le
    # drapeau "troc" du MODE LANCEMENT (404 quand masqué, ce qui est le
    # défaut). Ce test porte sur l'assainissement de `audio_url` dans le
    # snapshot de prompt, pas sur le drapeau : on rallume l'item le temps
    # du test (`launch_flags_dict()` est relu à CHAQUE requête).
    monkeypatch.setattr(settings, "SHOW_TROC", True)

    receiver = await _make_user()
    try:
        prompt_id = await _seed_prompt_with_track(test_user["id"], 'x" onerror="1')
        snap = await _offer_snapshot(client, auth_headers, receiver, prompt_id)
        assert snap is not None
        assert snap["audio_url"] is None
    finally:
        await _cleanup(test_user["id"], receiver)


async def test_prompt_snap_audio_url_legit_kept(client, test_user, auth_headers, monkeypatch):
    # S-08 (2026-09-02) : le routeur /trades est désormais gaté par le
    # drapeau "troc" du MODE LANCEMENT (404 quand masqué, ce qui est le
    # défaut). Ce test porte sur l'assainissement de `audio_url` dans le
    # snapshot de prompt, pas sur le drapeau : on rallume l'item le temps
    # du test (`launch_flags_dict()` est relu à CHAQUE requête).
    monkeypatch.setattr(settings, "SHOW_TROC", True)

    receiver = await _make_user()
    try:
        legit = "/watt/stream/tracks/son-legitime-0123abcd4567.wav"
        prompt_id = await _seed_prompt_with_track(test_user["id"], legit)
        snap = await _offer_snapshot(client, auth_headers, receiver, prompt_id)
        assert snap["audio_url"] == legit
    finally:
        await _cleanup(test_user["id"], receiver)
