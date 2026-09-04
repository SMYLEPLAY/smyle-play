"""
S-10 sécurité (2026-09-02) — flux « mot de passe oublié » (audit A §M4 + §J6).

Deux problèmes fermés ici :
  1. Le lien envoyé par email était `…/reset?token=<secret>`. uvicorn tourne
     avec `--access-log` (railway.toml, Procfile) : chaque GET /reset?token=…
     écrivait le jeton — valable 60 minutes — dans les logs Railway, et le
     `Referer` d'une ressource tierce l'aurait fait fuiter aussi. Le jeton
     passe désormais en FRAGMENT (`#token=`), jamais transmis au serveur.
  2. L'origine du lien dérivait du seul en-tête Host (`request.base_url`) :
     un Host arbitraire laissé passer par l'edge empoisonnait le lien.
     `PUBLIC_BASE_URL` prend la main quand elle est posée.

§J6 : le flux n'avait AUCUN test. Ceux-ci couvrent le chemin nominal, l'usage
unique, l'anti-énumération d'emails, l'invalidation du lien précédent et la
révocation des JWT (token_version).

Le service d'envoi est monkeypatché pour capturer le lien (auth.py importe
`send_password_reset_email` à l'appel, donc patcher le module suffit).
Postgres requis (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import delete, text

import app.services.emails as emails_module
from app.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PASSWORD = "12345678"
_NEW_PASSWORD = "nouveau-mot-de-passe-1"


@pytest.fixture
def sent_links(monkeypatch):
    """Capture les liens de réinitialisation au lieu de les envoyer."""
    links: list[str] = []

    async def _fake(to: str, *, link: str) -> None:
        links.append(link)

    monkeypatch.setattr(emails_module, "send_password_reset_email", _fake)
    return links


async def _make_user() -> dict:
    email = f"pytest-reset-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password=_PASSWORD))
        uid = user.id
    return {"id": uid, "email": email}


async def _cleanup(user_id) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


def _token_of(link: str) -> str:
    """Extrait le jeton du fragment (forme canonique après S-10)."""
    assert "#token=" in link, link
    return link.split("#token=", 1)[1]


async def _forgot(client, email: str):
    r = await client.post("/auth/forgot-password", json={"email": email})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    return r


async def test_forgot_password_link_uses_fragment(client, sent_links):
    """Le jeton est en fragment : jamais dans l'URL envoyée au serveur."""
    user = await _make_user()
    try:
        await _forgot(client, user["email"])
        assert len(sent_links) == 1, sent_links
        link = sent_links[0]
        assert "#token=" in link, link
        assert "?token=" not in link, link
        # Le chemin reste /reset, la partie avant le # ne porte aucun secret.
        before_fragment = link.split("#", 1)[0]
        assert before_fragment.endswith("/reset"), link
        assert _token_of(link)
    finally:
        await _cleanup(user["id"])


async def test_forgot_password_honore_public_base_url(client, sent_links, monkeypatch):
    """PUBLIC_BASE_URL prend la main sur l'en-tête Host (anti-empoisonnement)."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://watt.example/")
    user = await _make_user()
    try:
        await _forgot(client, user["email"])
        assert sent_links[0].startswith("https://watt.example/reset#token="), sent_links
    finally:
        await _cleanup(user["id"])


async def test_reset_password_happy_path(client, sent_links):
    """Chemin nominal : le nouveau mot de passe fonctionne, l'ancien non."""
    user = await _make_user()
    try:
        await _forgot(client, user["email"])
        token = _token_of(sent_links[0])

        r = await client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": _NEW_PASSWORD},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

        ok = await client.post(
            "/auth/login", json={"email": user["email"], "password": _NEW_PASSWORD}
        )
        assert ok.status_code == 200, ok.text

        ko = await client.post(
            "/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
        assert ko.status_code == 401, ko.text
    finally:
        await _cleanup(user["id"])


async def test_reset_token_single_use(client, sent_links):
    """Le jeton est à usage unique : le second échange est refusé."""
    user = await _make_user()
    try:
        await _forgot(client, user["email"])
        token = _token_of(sent_links[0])

        first = await client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": _NEW_PASSWORD},
        )
        assert first.status_code == 200, first.text

        second = await client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "encore-un-autre-mdp-9"},
        )
        assert second.status_code == 400, second.text

        # Le mot de passe reste celui posé par le premier échange.
        ok = await client.post(
            "/auth/login", json={"email": user["email"], "password": _NEW_PASSWORD}
        )
        assert ok.status_code == 200, ok.text
    finally:
        await _cleanup(user["id"])


async def test_forgot_password_unknown_email_still_ok(client, sent_links):
    """Anti-énumération : email inconnu → 200 {"ok": true}, aucun envoi."""
    r = await client.post(
        "/auth/forgot-password",
        json={"email": f"inconnu-{uuid.uuid4().hex[:10]}@smyleplay.example"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert sent_links == []


async def test_second_forgot_invalide_le_premier_lien(client, sent_links):
    """Un seul lien vivant à la fois : le second `forgot` tue le premier."""
    user = await _make_user()
    try:
        await _forgot(client, user["email"])
        await _forgot(client, user["email"])
        assert len(sent_links) == 2, sent_links
        old_token, new_token = (_token_of(link) for link in sent_links)
        assert old_token != new_token

        dead = await client.post(
            "/auth/reset-password",
            json={"token": old_token, "new_password": _NEW_PASSWORD},
        )
        assert dead.status_code == 400, dead.text

        alive = await client.post(
            "/auth/reset-password",
            json={"token": new_token, "new_password": _NEW_PASSWORD},
        )
        assert alive.status_code == 200, alive.text
    finally:
        await _cleanup(user["id"])


async def test_reset_bumpe_token_version_et_revoque_les_jwt(client, sent_links):
    """Les sessions ouvertes avant le reset sont révoquées (token_version)."""
    user = await _make_user()
    try:
        login = await client.post(
            "/auth/login", json={"email": user["email"], "password": _PASSWORD}
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        before = await client.get("/users/me", headers=headers)
        assert before.status_code == 200, before.text

        async with SessionLocal() as db:
            tv_before = (await db.execute(
                text("SELECT COALESCE(token_version, 0) FROM users WHERE id = :u"),
                {"u": user["id"]},
            )).scalar_one()

        await _forgot(client, user["email"])
        token = _token_of(sent_links[0])
        r = await client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": _NEW_PASSWORD},
        )
        assert r.status_code == 200, r.text

        async with SessionLocal() as db:
            tv_after = (await db.execute(
                text("SELECT COALESCE(token_version, 0) FROM users WHERE id = :u"),
                {"u": user["id"]},
            )).scalar_one()
        assert tv_after == tv_before + 1

        after = await client.get("/users/me", headers=headers)
        assert after.status_code == 401, after.text
    finally:
        await _cleanup(user["id"])


async def test_reset_password_jeton_bidon_refuse(client):
    """Un jeton inventé ne passe pas (et ne révèle rien de plus qu'un 400)."""
    r = await client.post(
        "/auth/reset-password",
        json={"token": "pas-un-vrai-jeton", "new_password": _NEW_PASSWORD},
    )
    assert r.status_code == 400, r.text


async def test_reset_html_lit_le_fragment_puis_purge_lurl():
    """Garde-fou front : reset.html lit location.hash et purge l'URL."""
    from pathlib import Path

    html = (Path(__file__).resolve().parents[2] / "reset.html").read_text(
        encoding="utf-8"
    )
    assert "location.hash" in html
    assert "history.replaceState" in html
    # Le fallback ?token= reste (emails partis avant le déploiement).
    assert "location.search" in html
