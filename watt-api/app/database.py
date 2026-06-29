from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
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


engine = create_async_engine(
    _normalize_async_url(settings.DATABASE_URL),
    echo=False,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
