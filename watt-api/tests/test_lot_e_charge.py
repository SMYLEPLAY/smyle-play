"""
Lot E — tenue en charge et exploitation (2026-10-09).

  • R2 : appels hors boucle asyncio, client à délais courts, panne → 503
    (et non 404), audio servi par redirection 302 (lecture partielle iPhone).
  • Logs : niveau INFO horodaté, emails masqués, refus Resend journalisés.
  • Emails d'inscription en arrière-plan.
  • Images : plafond de 40 mégapixels.
  • Requêtes : plus de N+1 sur les conversations et les abonnés ; /watt/adns
    retirée.
  • Exploitation : redémarrage Railway, lock_timeout des migrations, Python
    3.11, sauvegarde des médias rouge si non configurée.
"""
from __future__ import annotations

import io
import logging
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, event, text

from app.config import settings
from app.database import SessionLocal, engine
from app.models.message import Message, MessageThread
from app.models.track import Track
from app.models.user import User
from app.models.user_follow import UserFollow
from app.schemas.user import UserCreate
from app.services.users import create_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

RACINE = Path(__file__).resolve().parents[2]
API = Path(__file__).resolve().parents[1]
_PWD = "12345678"


# ── outils ────────────────────────────────────────────────────────────────

async def _user(*, public: bool = True) -> dict:
    suffix = uuid.uuid4().hex[:10]
    email = f"pytest-lote-{suffix}@smyleplay.example"
    async with SessionLocal() as db:
        uid = (await create_user(db, UserCreate(email=email, password=_PWD))).id
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET profile_public = :p, artist_name = :n WHERE id = :u"),
            {"p": public, "n": f"LotE {suffix}", "u": uid},
        )
        await db.commit()
    return {"id": uid, "email": email}


async def _login(client, email: str) -> dict:
    r = await client.post("/auth/login", json={"email": email, "password": _PWD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _cleanup(*uids) -> None:
    async with SessionLocal() as db:
        from app.models.dna import DNA

        for uid in uids:
            await db.execute(delete(DNA).where(DNA.artist_id == uid))
            await db.execute(delete(Track).where(Track.artist_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()


@contextmanager
def _compteur_requetes():
    """Compte les requêtes SQL émises (tous workers de test confondus)."""
    n = {"total": 0}

    def _avant(*_a, **_k):
        n["total"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _avant)
    try:
        yield n
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _avant)


class _ErreurClient(Exception):
    """Imite botocore.exceptions.ClientError (attribut .response)."""

    def __init__(self, code: str, statut: int):
        super().__init__(code)
        self.response = {"Error": {"Code": code},
                         "ResponseMetadata": {"HTTPStatusCode": statut}}


class _FauxR2:
    def __init__(self, exc: Exception | None = None):
        self.exc = exc
        self.threads: list[str] = []

    def _appel(self):
        self.threads.append(threading.current_thread().name)
        if self.exc is not None:
            raise self.exc

    def get_object(self, **kw):
        self._appel()

        class _Corps:
            def iter_chunks(self, chunk_size=65536):
                yield b"abc"

            def close(self):
                pass

        return {"Body": _Corps(), "ContentLength": 3}

    def put_object(self, **kw):
        self._appel()


@pytest.fixture
def faux_r2(monkeypatch):
    import app.services.r2 as r2

    def _poser(exc: Exception | None = None) -> _FauxR2:
        faux = _FauxR2(exc)
        monkeypatch.setattr(r2, "is_configured", lambda: True)
        monkeypatch.setattr(r2, "get_r2_client", lambda: faux)
        return faux

    return _poser


# ═══ 1. R2 ═══════════════════════════════════════════════════════════════

async def test_client_r2_delais_courts(monkeypatch):
    import app.services.r2 as r2

    monkeypatch.setattr(settings, "R2_ACCESS_KEY_ID", "cle-de-test")
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", "secret-de-test")
    monkeypatch.setattr(settings, "R2_ENDPOINT_URL", "https://r2.invalid")
    r2._get_client.cache_clear()
    try:
        client = r2._get_client()
        cfg = client.meta.config
        assert cfg.connect_timeout == 3
        assert cfg.read_timeout == 10
        assert cfg.retries["total_max_attempts"] == 2
    finally:
        r2._get_client.cache_clear()


async def test_ouvrir_objet_hors_boucle_et_classement(faux_r2):
    from app.services.r2 import ouvrir_objet

    faux = faux_r2()
    obj = await ouvrir_objet("images/previews/x.jpg")
    assert obj["ContentLength"] == 3
    assert faux.threads and faux.threads[0] != threading.main_thread().name

    faux_r2(_ErreurClient("NoSuchKey", 404))
    with pytest.raises(HTTPException) as e:
        await ouvrir_objet("images/previews/absente.jpg")
    assert e.value.status_code == 404

    for panne in (TimeoutError("lecture trop lente"),
                  _ErreurClient("InternalError", 500),
                  ConnectionError("injoignable")):
        faux_r2(panne)
        with pytest.raises(HTTPException) as e:
            await ouvrir_objet("images/previews/x.jpg")
        assert e.value.status_code == 503, panne


async def test_r2_en_panne_repond_503_et_journalise(client, faux_r2, caplog, monkeypatch):
    # Sans domaine public, /watt/images lit l'objet par le client R2.
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "")
    faux_r2(TimeoutError("R2 ne répond pas"))
    with caplog.at_level(logging.WARNING, logger="app.services.r2"):
        r = await client.get("/watt/images/images/previews/abc.jpg")
    assert r.status_code == 503, r.text
    assert "indisponible" in r.json()["detail"]
    assert any("[R2] get_object en échec" in m for m in caplog.messages)

    faux_r2(_ErreurClient("NoSuchKey", 404))
    r = await client.get("/watt/images/images/previews/abc.jpg")
    assert r.status_code == 404

    faux_r2()
    r = await client.get("/watt/images/images/previews/abc.jpg")
    assert r.status_code == 200 and r.content == b"abc"


async def test_envoi_r2_en_panne_repond_503(client, faux_r2):
    from PIL import Image

    a = await _user()
    try:
        h = await _login(client, a["email"])
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), (1, 2, 3)).save(buf, format="PNG")
        faux_r2(ConnectionError("R2 injoignable"))
        r = await client.post("/watt/upload-image", headers=h,
                              files={"file": ("c.png", buf.getvalue(), "image/png")},
                              data={"kind": "avatar"})
        assert r.status_code == 503, r.text
    finally:
        await _cleanup(a["id"])


async def test_audio_redirection_302(client, monkeypatch):
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://media.exemple.test/")
    r = await client.get("/watt/stream/tracks/Mon Son.m4a", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://media.exemple.test/tracks/Mon%20Son.m4a"
    assert r.headers["cache-control"] == "no-store"
    # Les gardes passent AVANT la redirection.
    for cle in ("images/originals/x.mp3", "tracks/a.png", "tracks/sans-extension"):
        r = await client.get(f"/watt/stream/{cle}", follow_redirects=False)
        assert r.status_code == 404, cle


async def test_audio_son_retire_ne_redirige_pas(client, monkeypatch):
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://media.exemple.test")
    a = await _user()
    cle = f"tracks/{a['id']}/retire-{uuid.uuid4().hex[:6]}.mp3"
    try:
        async with SessionLocal() as db:
            db.add(Track(artist_id=a["id"], title="Retiré", r2_key=cle, is_deleted=True))
            await db.commit()
        r = await client.get(f"/watt/stream/{cle}", follow_redirects=False)
        assert r.status_code == 404
        assert "location" not in r.headers
    finally:
        await _cleanup(a["id"])


# ═══ 3. Logs ═════════════════════════════════════════════════════════════

def test_masquer_email():
    from app.core.logging import masquer_email, masquer_emails_dans

    assert masquer_email("tom.lecomte1@gmail.com") == "t***@gmail.com"
    assert masquer_email(None) == "-"
    assert masquer_email("") == "-"
    assert masquer_emails_dans("envoi à a.b@c.fr et x@y.io") == "envoi à a***@c.fr et x***@y.io"


def test_logs_configures_info_horodates_emails_masques():
    from app.core.logging import FiltreEmails, configurer_logs

    racine = logging.getLogger()
    configurer_logs()
    avant = len(racine.handlers)
    configurer_logs()
    assert len(racine.handlers) == avant  # idempotent
    assert racine.level == logging.INFO

    ours = [h for h in racine.handlers
            if any(isinstance(f, FiltreEmails) for f in h.filters)]
    assert len(ours) == 1
    rec = logging.LogRecord("app.x", logging.INFO, __file__, 1,
                            "envoi vers %s", ("tom.lecomte1@gmail.com",), None)
    ligne = ours[0].format(rec) if ours[0].filter(rec) else ""
    assert "t***@gmail.com" in ligne and "tom.lecomte1" not in ligne
    assert '"timestamp"' in ligne and '"level": "info"' in ligne


async def test_refus_resend_journalise_et_masque(monkeypatch, caplog):
    import app.services.emails as emails

    class _Rep:
        status_code = 403
        text = '{"message":"domain not verified"}'

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Rep()

    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(emails.httpx, "AsyncClient", _Client)
    with caplog.at_level(logging.WARNING, logger="app.services.emails"):
        ok = await emails._send("tom.lecomte1@gmail.com", "Sujet", "<p>x</p>")
    assert ok is False
    assert any("refusé par Resend" in m and "t***@gmail.com" in m for m in caplog.messages)
    assert "tom.lecomte1" not in caplog.text


# ═══ 4. Emails d'inscription en arrière-plan ═════════════════════════════

async def test_inscription_emails_en_arriere_plan(client, monkeypatch):
    import app.services.emails as emails
    from app.routers import auth as auth_router

    appels: list[tuple] = []

    async def _bienvenue(to, *, name=None):
        appels.append(("bienvenue", to))

    async def _verif(to, *, link):
        appels.append(("verification", to, link))
        return True

    monkeypatch.setattr(emails, "send_welcome_email", _bienvenue)
    monkeypatch.setattr(emails, "send_verification_email", _verif)

    # La route confie l'envoi à BackgroundTasks (exécuté après la réponse).
    ajouts: list = []
    from fastapi import BackgroundTasks

    origine = BackgroundTasks.add_task

    def _espion(self, fn, *a, **k):
        ajouts.append(fn)
        return origine(self, fn, *a, **k)

    monkeypatch.setattr(BackgroundTasks, "add_task", _espion)

    email = f"pytest-lote-insc-{uuid.uuid4().hex[:8]}@smyleplay.example"
    r = await client.post("/auth/register", json={
        "email": email, "password": _PWD, "accept_terms": True, "age_confirmed": True,
    })
    try:
        assert r.status_code == 201, r.text
        assert auth_router._emails_inscription in ajouts
        assert ("bienvenue", email) in appels
        verif = [a for a in appels if a[0] == "verification"]
        assert verif and "#token=" in verif[0][2]
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.email == email))
            await db.commit()


# ═══ 7. Images ═══════════════════════════════════════════════════════════

def test_plafond_images_40_megapixels():
    from PIL import Image

    from app.core.fichiers import verifier_image

    assert settings.UPLOAD_MAX_IMAGE_PIXELS == 40_000_000
    buf = io.BytesIO()
    Image.new("1", (7000, 6000)).save(buf, format="PNG")  # 42 Mpx, ~5 Ko
    with pytest.raises(HTTPException) as e:
        verifier_image(buf.getvalue(), ("png",))
    assert e.value.status_code == 400
    assert Image.MAX_IMAGE_PIXELS == 40_000_000


# ═══ 8. Requêtes groupées (N+1) ══════════════════════════════════════════

async def test_conversations_sans_n_plus_1(client, monkeypatch):
    monkeypatch.setattr(settings, "SHOW_MESSAGERIE", True)
    moi = await _user()
    autres = [await _user() for _ in range(3)]
    try:
        async with SessionLocal() as db:
            for i, o in enumerate(autres):
                a, b = sorted([moi["id"], o["id"]], key=str)
                t = MessageThread(participant_a=a, participant_b=b)
                db.add(t)
                await db.flush()
                db.add(Message(thread_id=t.id, sender_id=o["id"], content=f"salut {i}"))
                if i == 0:
                    db.add(Message(thread_id=t.id, sender_id=o["id"], content="deux"))
            await db.commit()
        h = await _login(client, moi["email"])

        with _compteur_requetes() as n:
            r = await client.get("/messages/threads", headers=h)
        assert r.status_code == 200, r.text
        fils = r.json()
        assert len(fils) == 3
        par_autre = {f["other_user_id"]: f for f in fils}
        premier = par_autre[str(autres[0]["id"])]
        assert premier["unread_count"] == 2
        assert premier["other_user_name"].startswith("LotE ")
        assert {f["last_message_preview"] for f in fils} >= {"salut 1", "salut 2"}
        # Authentification + fils + 3 requêtes groupées : constant, quel que
        # soit le nombre de conversations (avant : 3 par conversation).
        assert n["total"] <= 7, n
    finally:
        await _cleanup(moi["id"], *[o["id"] for o in autres])


async def test_abonnes_sans_n_plus_1(client):
    moi = await _user()
    fans = [await _user() for _ in range(4)]
    try:
        async with SessionLocal() as db:
            for i, f in enumerate(fans):
                db.add(UserFollow(follower_id=f["id"], followee_id=moi["id"]))
                for j in range(i):
                    db.add(Track(artist_id=f["id"], title=f"S{j}", plays=10))
            await db.commit()
        h = await _login(client, moi["email"])
        with _compteur_requetes() as n:
            r = await client.get("/watt/me/followers", headers=h)
        assert r.status_code == 200, r.text
        cartes = {c["id"]: c for c in r.json()["followers"]}
        assert len(cartes) == 4
        for i, f in enumerate(fans):
            assert cartes[str(f["id"])]["trackCount"] == i
            assert cartes[str(f["id"])]["plays"] == 10 * i
        assert n["total"] <= 6, n  # avant : 1 requête de plus par abonné
    finally:
        await _cleanup(moi["id"], *[f["id"] for f in fans])


async def test_watt_adns_retiree(client):
    r = await client.get("/watt/adns")
    assert r.status_code == 404


# ═══ 5, 6, 9, 10. Exploitation ═══════════════════════════════════════════

def test_railway_redemarre_toujours():
    import tomllib

    conf = tomllib.loads((RACINE / "railway.toml").read_text(encoding="utf-8"))
    assert conf["deploy"]["restartPolicyType"] == "always"


def test_migrations_lock_timeout():
    env = (API / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "SET lock_timeout" in env
    assert '"ALEMBIC_LOCK_TIMEOUT", "5s"' in env
    assert "connection.commit()" in env


def test_python_3_11():
    assert (RACINE / ".python-version").read_text(encoding="utf-8").strip() == "3.11"


def test_sauvegarde_medias_rouge_si_non_configuree():
    import yaml

    wf = yaml.safe_load((RACINE / ".github/workflows/backup-media.yml").read_text(encoding="utf-8"))
    etape = wf["jobs"]["backup"]["steps"][0]
    assert etape["id"] == "reglages"
    assert "exit 1" in etape["run"]
    assert "::error::" in etape["run"]
