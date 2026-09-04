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
_ENGINE_KWARGS: dict = {"echo": False}
if settings.ENVIRONMENT == "test":
    _ENGINE_KWARGS["poolclass"] = NullPool

engine = create_async_engine(
    _normalize_async_url(settings.DATABASE_URL),
    **_ENGINE_KWARGS,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
