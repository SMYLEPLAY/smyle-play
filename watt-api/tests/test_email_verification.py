"""
Vérification d'email (Phase A — ouverture gratuite, 2026-09-11).

Couvre :
  - l'inscription crée un compte NON vérifié (email_verified = False) ;
  - le flux de confirmation : un jeton valide marque email_verified=True,
    à usage unique (le second échange est refusé) ;
  - le renvoi d'un email de vérification est anti-énumération (200 quel que
    soit le compte) et invalide le jeton précédent ;
  - le login n'est PAS bloqué par défaut (REQUIRE_EMAIL_VERIFIED=False) ;
  - le login EST bloqué quand REQUIRE_EMAIL_VERIFIED=True et l'email non
    vérifié, puis passe une fois l'email vérifié.

Même modèle que test_password_reset_flow.py : le service d'émission de jeton
est appelé directement (comme le fait l'endpoint), l'envoi d'email est
monkeypatché. Postgres requis (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import delete, select

import app.services.emails as emails_module
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.email_verification import issue_verification_token
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PASSWORD = "12345678"


@pytest.fixture
def sent_links(monkeypatch):
    """Capture les liens de vérification au lieu de les envoyer."""
    links: list[str] = []

    async def _fake(to: str, *, link: str) -> bool:
        links.append(link)
        return True

    monkeypatch.setattr(emails_module, "send_verification_email", _fake)
    return links


async def _make_user() -> dict:
    email = f"pytest-verif-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password=_PASSWORD))
        uid = user.id
    return {"id": uid, "email": email}


async def _cleanup(user_id) -> None:
    async with SessionLocal() as db:
        # email_verification_tokens : FK ON DELETE CASCADE → part avec l'user.
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _issue_token(user_id) -> str:
    async with SessionLocal() as db:
        user = (await db.execute(
            select(User).where(User.id == user_id)
        )).scalar_one()
        return await issue_verification_token(db, user)


async def _email_verified(user_id) -> bool:
    async with SessionLocal() as db:
        return (await db.execute(
            select(User.email_verified).where(User.id == user_id)
        )).scalar_one()


async def test_register_cree_un_compte_non_verifie(client):
    """POST /auth/register → 201, compte créé avec email_verified=False."""
    email = f"pytest-reg-{uuid.uuid4().hex[:12]}@smyleplay.example"
    uid = None
    try:
        r = await client.post("/auth/register", json={
            "email": email,
            "password": _PASSWORD,
            "accept_terms": True,
            "age_confirmed": True,
        })
        assert r.status_code == 201, r.text
        body = r.json()
        uid = body["id"]
        assert body["email_verified"] is False
    finally:
        if uid:
            await _cleanup(uid)


async def test_verify_email_happy_path(client):
    """Un jeton valide marque le compte comme vérifié."""
    user = await _make_user()
    try:
        assert await _email_verified(user["id"]) is False
        token = await _issue_token(user["id"])

        r = await client.post("/auth/verify-email", json={"token": token})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
        assert await _email_verified(user["id"]) is True
    finally:
        await _cleanup(user["id"])


async def test_verify_email_single_use(client):
    """Le jeton de vérification est à usage unique : le 2e échange est refusé."""
    user = await _make_user()
    try:
        token = await _issue_token(user["id"])

        first = await client.post("/auth/verify-email", json={"token": token})
        assert first.status_code == 200, first.text

        second = await client.post("/auth/verify-email", json={"token": token})
        assert second.status_code == 400, second.text
    finally:
        await _cleanup(user["id"])


async def test_verify_email_jeton_bidon_refuse(client):
    """Un jeton inventé ne passe pas (400)."""
    r = await client.post(
        "/auth/verify-email", json={"token": "jeton-de-test-xxxxxxxx"}
    )
    assert r.status_code == 400, r.text


async def test_resend_verification_anti_enumeration(client, sent_links):
    """Compte connu et inconnu : réponse strictement identique (200 ok)."""
    user = await _make_user()
    try:
        connu = await client.post(
            "/auth/resend-verification", json={"email": user["email"]}
        )
        inconnu = await client.post(
            "/auth/resend-verification",
            json={"email": f"inconnu-{uuid.uuid4().hex[:10]}@smyleplay.example"},
        )
        assert connu.status_code == inconnu.status_code == 200
        assert connu.json() == inconnu.json() == {"ok": True}
        # Un seul envoi : le compte connu (l'inconnu ne déclenche rien).
        assert len(sent_links) == 1, sent_links
        assert "#token=" in sent_links[0], sent_links
    finally:
        await _cleanup(user["id"])


async def test_resend_invalide_le_jeton_precedent(client, sent_links):
    """Un renvoi tue le jeton précédent (un seul lien vivant à la fois)."""
    user = await _make_user()
    try:
        old_token = await _issue_token(user["id"])
        # Renvoi → nouveau jeton, l'ancien devient mort.
        r = await client.post(
            "/auth/resend-verification", json={"email": user["email"]}
        )
        assert r.status_code == 200, r.text
        assert len(sent_links) == 1, sent_links
        new_token = sent_links[0].split("#token=", 1)[1]
        assert new_token != old_token

        dead = await client.post("/auth/verify-email", json={"token": old_token})
        assert dead.status_code == 400, dead.text

        alive = await client.post("/auth/verify-email", json={"token": new_token})
        assert alive.status_code == 200, alive.text
    finally:
        await _cleanup(user["id"])


async def test_resend_ne_renvoie_rien_si_deja_verifie(client, sent_links):
    """Compte déjà vérifié : réponse 200 mais aucun email émis."""
    user = await _make_user()
    try:
        token = await _issue_token(user["id"])
        assert (await client.post(
            "/auth/verify-email", json={"token": token}
        )).status_code == 200

        r = await client.post(
            "/auth/resend-verification", json={"email": user["email"]}
        )
        assert r.status_code == 200, r.text
        assert sent_links == []
    finally:
        await _cleanup(user["id"])


async def test_login_non_bloque_par_defaut(client):
    """Défaut REQUIRE_EMAIL_VERIFIED=False : un email non vérifié se connecte."""
    assert settings.REQUIRE_EMAIL_VERIFIED is False
    user = await _make_user()
    try:
        assert await _email_verified(user["id"]) is False
        r = await client.post(
            "/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()
    finally:
        await _cleanup(user["id"])


async def test_login_bloque_si_flag_actif_puis_passe_apres_verif(
    client, monkeypatch
):
    """REQUIRE_EMAIL_VERIFIED=True : login 403 tant que non vérifié, 200 après."""
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFIED", True)
    user = await _make_user()
    try:
        blocked = await client.post(
            "/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
        assert blocked.status_code == 403, blocked.text

        token = await _issue_token(user["id"])
        assert (await client.post(
            "/auth/verify-email", json={"token": token}
        )).status_code == 200

        ok = await client.post(
            "/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
        assert ok.status_code == 200, ok.text
    finally:
        await _cleanup(user["id"])
