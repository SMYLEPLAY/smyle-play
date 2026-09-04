"""L-04 (2026-09-02) — `/health` vérifie la base et expose la version.

Avant : `{"status": "ok"}` sans rien tester → un déploiement avec une base
injoignable passait le healthcheck Railway, et rien ne disait quel commit
tournait (incident webhook du 01/08 : merges jamais déployés, invisibles).

Après :
  - 200 `{"status": "ok", "db": "ok", "commit", "alembic_head", "r2_configured"}`
    quand `SELECT 1` répond en moins de 3 s ;
  - 503 `{"status": "degraded", "db": "down"}` sinon (ici : `engine.connect`
    monkeypatché pour lever, sans toucher à la vraie base).
"""
import asyncio

import app.database as database
import app.main as app_main


async def test_health_ok_with_db(client, monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "0123456789abcdef")

    resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["commit"] == "0123456"  # SHA tronqué à 7 caractères
    assert isinstance(body["r2_configured"], bool)
    # Tête Alembic lue dynamiquement dans watt-api/alembic/versions/.
    assert body["alembic_head"] == app_main._alembic_head()
    assert body["alembic_head"]  # jamais vide (repli constante sinon)


async def test_health_commit_vide_sans_variable_railway(client, monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)

    resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json()["commit"] == ""


class _MoteurQuiLeve:
    """Doublure de `app.database.engine` (AsyncEngine a des __slots__ : son
    attribut `connect` n'est pas monkeypatchable sur l'instance — on remplace
    le moteur du module, que le handler importe à chaque appel)."""

    def connect(self, *args, **kwargs):
        raise ConnectionRefusedError("postgres injoignable (simulé)")


async def test_health_503_when_db_down(client, monkeypatch):
    monkeypatch.setattr(database, "engine", _MoteurQuiLeve())

    resp = await client.get("/health")

    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "db": "down"}


async def test_health_503_when_db_timeout(client, monkeypatch):
    """La vérification est BORNÉE : une base qui ne répond jamais ne doit pas
    bloquer la sonde (Railway attend `healthcheckTimeout` puis rejette)."""

    class _ConnexionQuiPend:
        async def __aenter__(self):
            await asyncio.sleep(3600)

        async def __aexit__(self, *exc):
            return False

    class _MoteurQuiPend:
        def connect(self):
            return _ConnexionQuiPend()

    monkeypatch.setattr(database, "engine", _MoteurQuiPend())
    # Pas question d'attendre 3 s réelles en test : on réduit le délai.
    original_wait_for = asyncio.wait_for

    async def _wait_for_court(aw, timeout):
        return await original_wait_for(aw, timeout=0.05)

    monkeypatch.setattr(app_main.asyncio, "wait_for", _wait_for_court)

    resp = await client.get("/health")

    assert resp.status_code == 503
    assert resp.json()["db"] == "down"


def test_alembic_head_correspond_a_la_derniere_migration():
    """La valeur exposée est la tête réelle de watt-api/alembic/versions/
    (lecture dynamique — une nouvelle migration n'a rien à mettre à jour ici).
    La constante de repli n'est volontairement PAS comparée : elle ne sert que
    si l'ini est introuvable, et la figer ici casserait chaque PR de migration."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(app_main._ALEMBIC_INI))
    cfg.set_main_option("script_location", str(app_main._ALEMBIC_INI.parent / "alembic"))
    cfg.set_main_option("prepend_sys_path", "")
    cfg.set_main_option("path_separator", "os")
    head = ScriptDirectory.from_config(cfg).get_current_head()

    assert head  # une seule tête (sinon `alembic upgrade head` casse en CI)
    assert app_main._alembic_head() == head


def test_alembic_head_repli_si_ini_introuvable(monkeypatch, tmp_path):
    monkeypatch.setattr(app_main, "_ALEMBIC_INI", tmp_path / "absent" / "alembic.ini")
    app_main._alembic_head.cache_clear()
    try:
        assert app_main._alembic_head() == app_main._ALEMBIC_HEAD_FALLBACK
    finally:
        app_main._alembic_head.cache_clear()
