"""Étape 5 (2026-10-02) — limitation anti-attaques partagée.

Couvre :
  • choix du stockage : Redis si REDIS_URL (et client installé), sinon mémoire
    avec avertissement ; jamais d'exception au démarrage ;
  • compteur PARTAGÉ : deux « workers » branchés sur le même stockage cumulent
    leurs requêtes (ce que Redis apporte), alors que le stockage mémoire
    historique laissait passer 2× la limite ;
  • 429 propre en français avec Retry-After ;
  • limites posées sur connexion, inscription, mot de passe oublié, renvoi de
    l'email de vérification, envois de fichiers et achats ;
  • /health n'est JAMAIS limité.
"""
import logging
import sys
import uuid

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from limits.storage import MemoryStorage
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core import ratelimit as rl


# ── Stockage partagé de test (joue le rôle de Redis) ─────────────────────
_PARTAGE: dict = {}


class _StockagePartage(MemoryStorage):
    """Toutes les instances partagent les mêmes compteurs, comme deux
    workers uvicorn branchés sur le même Redis."""

    STORAGE_SCHEME = ["wattpartage"]

    def __init__(self, uri=None, **kw):
        super().__init__(uri, **kw)
        if not _PARTAGE:
            _PARTAGE.update(
                storage=self.storage, expirations=self.expirations,
                events=self.events, locks=self.locks,
            )
        self.storage = _PARTAGE["storage"]
        self.expirations = _PARTAGE["expirations"]
        self.events = _PARTAGE["events"]
        self.locks = _PARTAGE["locks"]


def _worker(storage_uri: str, limite: str = "3/minute") -> FastAPI:
    """Mini-application = un worker, avec son propre limiteur."""
    lim = rl.build_limiter(storage_uri, enabled=True)
    app = FastAPI()
    app.state.limiter = lim
    app.add_exception_handler(RateLimitExceeded, rl.rate_limit_handler)

    @app.post("/auth/login")
    @lim.limit(limite)
    async def login(request: Request):
        return {"ok": True}

    return app


async def _post(app: FastAPI, ip: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/auth/login", headers={"X-Forwarded-For": ip})


# ── Choix du stockage ──────────────────────────────────────────────────────

def test_sans_redis_url_memoire_et_avertissement(monkeypatch, caplog):
    monkeypatch.setattr(settings, "REDIS_URL", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with caplog.at_level(logging.WARNING, logger="app.core.ratelimit"):
        assert rl._storage_uri() == "memory://"
    assert "REDIS_URL absent" in caplog.text


def test_redis_url_schema_invalide_repli_memoire(monkeypatch, caplog):
    monkeypatch.setattr(settings, "REDIS_URL", "http://pas-redis:6379")
    with caplog.at_level(logging.ERROR, logger="app.core.ratelimit"):
        assert rl._storage_uri() == "memory://"
    assert "ignoré" in caplog.text


def test_redis_url_sans_paquet_redis_repli_memoire(monkeypatch, caplog):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://default:x@redis.railway.internal:6379")
    monkeypatch.setitem(sys.modules, "redis", None)  # import redis → ImportError
    with caplog.at_level(logging.ERROR, logger="app.core.ratelimit"):
        assert rl._storage_uri() == "memory://"
    assert "pas installé" in caplog.text
    # Le mot de passe de l'URL n'apparaît jamais dans les logs.
    assert ":x@" not in caplog.text


def test_redis_url_valide_est_retenue(monkeypatch):
    pytest.importorskip("redis")
    url = "redis://default:x@redis.railway.internal:6379"
    monkeypatch.setattr(settings, "REDIS_URL", url)
    assert rl._storage_uri() == url


def test_construction_ne_plante_jamais(monkeypatch):
    """Stockage inutilisable → limiteur mémoire, le site démarre quand même."""
    lim = rl.build_limiter("schema-inconnu://x", enabled=True)
    assert rl.storage_kind(lim) == "memoire"


def test_limiteur_par_defaut_en_memoire_sans_redis():
    # En test (comme en prod aujourd'hui) REDIS_URL est absent.
    if not settings.REDIS_URL:
        assert rl.storage_kind(rl.limiter) == "memoire"


# ── Compteur partagé entre workers ─────────────────────────────────────────

async def test_compteur_partage_entre_deux_workers():
    _PARTAGE.clear()
    w1, w2 = _worker("wattpartage://"), _worker("wattpartage://")
    ip = f"203.0.113.{uuid.uuid4().int % 200}"
    codes = [
        (await _post(w1, ip)).status_code,
        (await _post(w2, ip)).status_code,
        (await _post(w1, ip)).status_code,
        (await _post(w2, ip)).status_code,  # 4e requête : limite 3 atteinte
    ]
    assert codes == [200, 200, 200, 429]


async def test_memoire_seule_laisse_passer_le_double():
    """Constat de l'audit : sans stockage partagé, 2 workers = 2× la limite."""
    w1, w2 = _worker("memory://"), _worker("memory://")
    ip = "198.51.100.7"
    codes = [(await _post(w, ip)).status_code for w in (w1, w1, w1, w2, w2, w2)]
    assert codes.count(200) == 6


async def test_redis_injoignable_repli_memoire_sans_blocage():
    """Redis en panne : on bascule en mémoire, la connexion n'est pas bloquée
    et la limite continue de s'appliquer."""
    pytest.importorskip("redis")
    w = _worker("redis://127.0.0.1:1")  # port fermé
    ip = "192.0.2.10"
    codes = [(await _post(w, ip)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


# ── Réponse 429 ────────────────────────────────────────────────────────────

async def test_reponse_429_en_francais_avec_retry_after():
    w = _worker("memory://", limite="1/minute")
    ip = "192.0.2.55"
    assert (await _post(w, ip)).status_code == 200
    r = await _post(w, ip)
    assert r.status_code == 429
    assert r.json()["detail"].startswith("Trop de tentatives.")
    assert "minute" in r.json()["detail"]
    assert 1 <= int(r.headers["retry-after"]) <= 60


def test_attente_lisible():
    assert rl._attente_lisible(30) == "moins d'une minute"
    assert rl._attente_lisible(60) == "1 minute"
    assert rl._attente_lisible(61) == "2 minutes"
    assert rl._attente_lisible(3600) == "1 heure"
    assert rl._attente_lisible(7200) == "2 heures"


# ── Limites posées sur les bonnes routes ───────────────────────────────────

ROUTES_LIMITEES = {
    "app.routers.auth.login": rl.LIMIT_LOGIN,
    "app.routers.auth.register": rl.LIMIT_REGISTER,
    "app.routers.auth.forgot_password": rl.LIMIT_FORGOT_PASSWORD,
    "app.routers.auth.resend_verification": rl.LIMIT_RESEND_VERIFICATION,
    "app.routers.watt_compat.upload_image": rl.LIMIT_UPLOAD,
    "app.routers.watt_compat.upload_audio": rl.LIMIT_UPLOAD,
    "app.routers.watt_compat.upload_voice_sample": rl.LIMIT_UPLOAD,
    "app.routers.watt_compat.upload_playlist_cover": rl.LIMIT_UPLOAD,
    "app.routers.images.create_my_image": rl.LIMIT_UPLOAD,
    "app.routers.images.add_my_image_gallery": rl.LIMIT_UPLOAD,
    "app.routers.payments.credits_checkout": rl.LIMIT_PURCHASE,
    "app.routers.packs.open_mystery": rl.LIMIT_PURCHASE,
    "app.routers.unlocks.unlock_prompt": rl.LIMIT_PURCHASE,
}


def test_limites_posees_sur_les_routes_sensibles():
    import app.main  # noqa: F401 — enregistre toutes les routes

    connues = rl.limiter._route_limits
    for nom, attendu in ROUTES_LIMITEES.items():
        assert nom in connues, f"{nom} n'est pas limitée"
        posees = {str(lim.limit) for lim in connues[nom]}
        from limits import parse_many

        assert posees == {str(i) for i in parse_many(attendu)}, (nom, posees)


def test_renvoi_verification_a_sa_propre_limite():
    from limits import parse_many

    assert rl.LIMIT_RESEND_VERIFICATION == settings.RATE_LIMIT_RESEND_VERIFICATION
    # Limites plus strictes qu'avant l'étape 5 (et une fenêtre journalière).
    assert any(item.GRANULARITY.name == "day" for item in parse_many(rl.LIMIT_FORGOT_PASSWORD))
    assert any(item.GRANULARITY.name == "hour" for item in parse_many(rl.LIMIT_LOGIN))


# ── Intégration sur la vraie application ───────────────────────────────────

@pytest.fixture
def limiteur_actif(_limiteur_neutre):
    """Rallume le vrai limiteur pour ce test (conftest le remet en l'état)."""
    rl.limiter.enabled = True
    return rl.limiter


async def test_mot_de_passe_oublie_429_en_francais(client, limiteur_actif):
    ip = f"10.{uuid.uuid4().int % 250}.0.1"
    email = f"inconnu-{uuid.uuid4().hex[:8]}@smyleplay.example"
    codes = []
    for _ in range(4):
        r = await client.post(
            "/auth/forgot-password", json={"email": email},
            headers={"X-Forwarded-For": ip},
        )
        codes.append(r.status_code)
    assert codes[:3] == [200, 200, 200], codes
    assert codes[3] == 429
    assert "Trop de tentatives" in r.json()["detail"]
    assert "retry-after" in r.headers


async def test_health_jamais_limite(client, limiteur_actif):
    for _ in range(120):
        r = await client.get("/health", headers={"X-Forwarded-For": "10.9.9.9"})
        assert r.status_code != 429
