"""
Phase 9.4 — Library : contenu possédé par l'utilisateur connecté.

Routes (auth requis) :
  GET  /me/library/prompts       (liste paginée de mes prompts débloqués)
  GET  /me/library/adns          (liste paginée de mes ADN possédés)

Le contenu COMPLET est exposé ici (prompt_text, example_outputs) parce
que l'utilisateur a payé pour ces objets. L'autorisation est implicite :
on filtre par current_owner_id (UnlockedPrompt) et user_id (OwnedAdn)
côté query — un user ne voit que ce qu'il possède.

Pas de GET /library/prompts/{id} ni /library/adns/{id} en Phase 9 :
les détails sont déjà inclus dans les listings (un prompt n'est pas
si volumineux) et la pagination suffit. On pourra ajouter des endpoints
"single item" en 9.6 si besoin (ex: vue plein écran d'un prompt).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.discovery import (
    LibraryAdnsResponse,
    LibraryPromptsResponse,
)
from app.services.discovery import (
    list_user_library_adns,
    list_user_library_prompts,
)

router = APIRouter(prefix="/me/library", tags=["library"])


@router.get("/prompts", response_model=LibraryPromptsResponse)
async def list_my_library_prompts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mes prompts débloqués (current_owner_id = moi). Inclut le prompt_text
    complet — c'est ma library, j'ai payé.
    """
    items, total = await list_user_library_prompts(
        db, user_id=current_user.id, page=page, per_page=per_page
    )
    return LibraryPromptsResponse(
        items=items, total=total, page=page, per_page=per_page
    )


@router.get("/adns", response_model=LibraryAdnsResponse)
async def list_my_library_adns(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mes ADN possédés. Inclut example_outputs (gated content) car possédé.
    """
    items, total = await list_user_library_adns(
        db, user_id=current_user.id, page=page, per_page=per_page
    )
    return LibraryAdnsResponse(
        items=items, total=total, page=page, per_page=per_page
    )
