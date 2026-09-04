from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.config import settings


def _normalize_async_url(url: str) -> str:
    """
    Normalise l'URL DATABASE_URL pour usage asyncpg.
    - Railway fournit souvent `postgres://...` (deprecated SQLA 2.x)
    - Flask utilise `postgresql://` (driver sync psycopg2)
    - FastAPI/SQLA async requiert `postgresql+asyncpg://`
    On transforme au runtime pour partager une unique var d'env en prod.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


# En test, PAS de pool de connexions (NullPool) : les tests DB-free montés sur
# un `TestClient` synchrone (ex. tests/test_pages_flag.py) exécutent l'app sur
# LEUR PROPRE boucle asyncio (thread anyio). Une route qui ouvre `SessionLocal()`
# (pages `/u/<slug>`, `/oeuvre/<slug>` — aperçu social) y crée une connexion
# asyncpg liée à cette boucle ; rendue au pool partagé, elle est réutilisée par
# les tests suivants sur la boucle de session pytest-asyncio → `InterfaceError`
# / `MissingGreenlet` en cascade (PR #489, runs CI du 2026-08-05). Avec NullPool,
# chaque session ouvre et ferme sa propre connexion : rien ne traverse les
# boucles. En dev/prod (`ENVIRONMENT != "test"`) : pool par défaut, inchangé.
# F-01 (2026-09-04) : bornes du pool en dev/prod. `pool_pre_ping` teste la
# connexion avant de la prêter (Railway coupe les connexions inactives ; sans
# lui la première requête après une coupure renvoie une 500 « connection was
# closed »), `pool_recycle=1800` les renouvelle avant le timeout côté serveur.
# Les bornes de TAILLE (2 workers × (5 + 10) = 30 connexions max, sous les 100
# du plan Postgres Railway) ne sont posées QUE hors test : NullPool n'accepte
# ni `pool_size`, ni `max_overflow`, ni `pool_timeout` (TypeError au boot).
_POOL_SIZE_KWARGS: dict = {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30,
}


def build_engine_kwargs(app_settings) -> dict:
    """Arguments de `create_async_engine` selon l'environnement.

    Extrait en fonction pour être testable sans reconstruire le module (le
    moteur importable, lui, est toujours celui de l'environnement courant).
    """
    kwargs: dict = {
        "echo": False,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    if app_settings.ENVIRONMENT == "test":
        kwargs["poolclass"] = NullPool
        return kwargs
    kwargs.update(_POOL_SIZE_KWARGS)
    return kwargs


def build_engine(app_settings):
    """Moteur async construit à partir d'un objet Settings (ou équivalent)."""
    return create_async_engine(
        _normalize_async_url(app_settings.DATABASE_URL),
        **build_engine_kwargs(app_settings),
    )


engine = build_engine(settings)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
