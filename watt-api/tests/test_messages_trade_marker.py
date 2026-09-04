"""
S-03 sécurité (2026-09-02) — marqueur d'échange `__TRADE_OFFER__<uuid>` dans
la messagerie (audit A §B3).

Le client poste ce marqueur via l'endpoint générique
`POST /messages/threads/{id}/send` ; le front le rend comme une carte
cliquable. Sans contrôle serveur, `__TRADE_OFFER__');alert(1)//` devenait un
XSS stocké chez l'interlocuteur. Règle : suffixe = UUID d'une offre existante,
envoyée par l'expéditeur du message au destinataire du fil ; stockage
canonique. Postgres requis (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models.message import Message
from app.models.trade import TradeOffer
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_MARK = "__TRADE_OFFER__"


async def _make_user() -> uuid.UUID:
    email = f"pytest-msg-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password="12345678"))
        return user.id


async def _cleanup_users(*uids: uuid.UUID) -> None:
    # Threads / messages / offres / notifications sont en ON DELETE CASCADE.
    async with SessionLocal() as db:
        for uid in uids:
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


async def _open_thread(client, auth_headers, other_id: uuid.UUID) -> str:
    r = await client.post(f"/messages/threads/{other_id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _seed_offer(sender_id: uuid.UUID, receiver_id: uuid.UUID) -> uuid.UUID:
    async with SessionLocal() as db:
        offer = TradeOffer(sender_id=sender_id, receiver_id=receiver_id,
                           credit_supplement=0, message="test")
        db.add(offer)
        await db.commit()
        await db.refresh(offer)
        return offer.id


async def test_trade_marker_with_non_uuid_is_rejected(client, test_user, auth_headers):
    other = await _make_user()
    try:
        tid = await _open_thread(client, auth_headers, other)
        for payload in (
            _MARK + "');alert(1)//",
            _MARK,
            _MARK + "not-a-uuid",
            _MARK + str(uuid.uuid4()) + "');alert(1)//",
        ):
            r = await client.post(f"/messages/threads/{tid}/send",
                                  json={"content": payload}, headers=auth_headers)
            assert r.status_code == 400, (payload, r.text)
        # Un UUID bien formé mais sans offre en base → 400 aussi.
        r = await client.post(f"/messages/threads/{tid}/send",
                              json={"content": _MARK + str(uuid.uuid4())},
                              headers=auth_headers)
        assert r.status_code == 400, r.text
        # Rien n'a été stocké.
        async with SessionLocal() as db:
            n = (await db.execute(
                select(Message).where(Message.thread_id == uuid.UUID(tid))
            )).scalars().all()
            assert n == []
    finally:
        await _cleanup_users(other)


async def test_trade_marker_for_foreign_offer_is_rejected(client, test_user, auth_headers):
    other = await _make_user()
    third = await _make_user()
    try:
        tid = await _open_thread(client, auth_headers, other)
        # Offre dont l'expéditeur n'est PAS le current user (other → me).
        foreign = await _seed_offer(other, test_user["id"])
        r = await client.post(f"/messages/threads/{tid}/send",
                              json={"content": f"{_MARK}{foreign}"}, headers=auth_headers)
        assert r.status_code == 400, r.text
        # Offre envoyée par moi mais à un AUTRE destinataire que celui du fil.
        elsewhere = await _seed_offer(test_user["id"], third)
        r = await client.post(f"/messages/threads/{tid}/send",
                              json={"content": f"{_MARK}{elsewhere}"}, headers=auth_headers)
        assert r.status_code == 400, r.text
    finally:
        await _cleanup_users(other, third)


async def test_trade_marker_valid_is_stored_canonical(client, test_user, auth_headers):
    other = await _make_user()
    try:
        tid = await _open_thread(client, auth_headers, other)
        offer_id = await _seed_offer(test_user["id"], other)
        # UUID en majuscules + espaces : accepté, stocké sous forme canonique.
        raw = f"  {_MARK}{str(offer_id).upper()}  "
        r = await client.post(f"/messages/threads/{tid}/send",
                              json={"content": raw}, headers=auth_headers)
        assert r.status_code == 201, r.text
        assert r.json()["content"] == f"{_MARK}{offer_id}"
        async with SessionLocal() as db:
            stored = (await db.execute(
                select(Message.content).where(Message.thread_id == uuid.UUID(tid))
            )).scalars().all()
            assert stored == [f"{_MARK}{offer_id}"]
        # Un message texte ordinaire passe toujours (pas de faux positif).
        r = await client.post(f"/messages/threads/{tid}/send",
                              json={"content": "Salut ! Ça te dit un échange ?\nÀ +"},
                              headers=auth_headers)
        assert r.status_code == 201, r.text
        # Caractère de contrôle (hors \n \t) → 422 (schéma MessageCreate).
        r = await client.post(f"/messages/threads/{tid}/send",
                              json={"content": "hello\u0001world"}, headers=auth_headers)
        assert r.status_code == 422, r.text
    finally:
        await _cleanup_users(other)
