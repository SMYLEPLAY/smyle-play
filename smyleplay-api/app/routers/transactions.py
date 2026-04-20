from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.credit import TransactionRead, TransactionsListResponse
from app.services.credits import get_user_transactions

router = APIRouter(prefix="/users/me/transactions", tags=["transactions"])


@router.get("", response_model=TransactionsListResponse)
async def list_my_transactions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Historique paginé des transactions de l'utilisateur connecté."""
    items, total = await get_user_transactions(db, current_user.id, page, per_page)
    return TransactionsListResponse(
        items=[TransactionRead.model_validate(tx) for tx in items],
        total=total,
        page=page,
        per_page=per_page,
    )
