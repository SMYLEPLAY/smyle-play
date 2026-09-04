"""F-01 (2026-09-04) — bornes du pool de connexions SQLAlchemy.

Le moteur était construit avec `echo=False` seul : aucune vérification de
vivacité et aucun recyclage. Railway coupe les connexions inactives → la
première requête suivante remontait une 500 « connection was closed ».

Ce test vérifie les deux réglages sur un moteur construit HORS test (les
bornes de taille ne s'appliquent qu'à ce cas : en `ENVIRONMENT=test` le pool
est un NullPool, qui refuse `pool_size`/`max_overflow`/`pool_timeout` — cf.
L-03, isolation des boucles asyncio entre TestClient et pytest-asyncio).
"""
from types import SimpleNamespace

import pytest
from sqlalchemy.pool import NullPool

from app.database import build_engine, build_engine_kwargs

_DUMMY_URL = "postgresql+asyncpg://user:pass@localhost:5432/db_inexistante"


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(DATABASE_URL=_DUMMY_URL, ENVIRONMENT=environment)


@pytest.mark.parametrize("environment", ["production", "development", "test"])
def test_pre_ping_et_recycle_dans_tous_les_environnements(environment: str):
    kwargs = build_engine_kwargs(_settings(environment))
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 1800


def test_bornes_de_taille_hors_test():
    kwargs = build_engine_kwargs(_settings("production"))
    assert kwargs["pool_size"] == 5
    assert kwargs["max_overflow"] == 10
    assert kwargs["pool_timeout"] == 30
    assert "poolclass" not in kwargs


def test_nullpool_en_test_sans_bornes_de_taille():
    """NullPool lève TypeError si on lui passe pool_size/max_overflow/
    pool_timeout : les bornes doivent rester hors du dict en test."""
    kwargs = build_engine_kwargs(_settings("test"))
    assert kwargs["poolclass"] is NullPool
    for interdit in ("pool_size", "max_overflow", "pool_timeout"):
        assert interdit not in kwargs


def test_moteur_hors_test_expose_pre_ping_et_recycle():
    """Construction réelle (aucune connexion ouverte : SQLAlchemy est paresseux)."""
    moteur = build_engine(_settings("production"))
    try:
        assert moteur.pool._pre_ping is True
        assert moteur.pool._recycle == 1800
        assert moteur.pool.size() == 5
    finally:
        moteur.sync_engine.dispose()


def test_moteur_en_test_utilise_nullpool():
    moteur = build_engine(_settings("test"))
    try:
        assert isinstance(moteur.pool, NullPool)
        assert moteur.pool._pre_ping is True
    finally:
        moteur.sync_engine.dispose()
