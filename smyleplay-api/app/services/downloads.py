"""
Journal de téléchargements (H0.5+). `log_download` est BEST-EFFORT : il ne
doit jamais faire échouer un téléchargement légitime. Appelé après le gate de
possession, donc on ne journalise que des accès autorisés.
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.download_event import DownloadEvent


async def log_download(
    db: AsyncSession, *, user_id: UUID, product_id: UUID, kind: str
) -> None:
    try:
        db.add(DownloadEvent(user_id=user_id, product_id=product_id, kind=kind))
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
