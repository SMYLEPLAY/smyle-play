"""
Routeur « Oeuvre complete » (C4) — liaison 1:1 son <-> image.

  POST   /artist/me/prompts/{prompt_id}/link   body {other_prompt_id}
  DELETE /artist/me/prompts/{prompt_id}/link

Emplacement : router DEDIE plutot que greffe dans images.py ou tracks.py.
Raison : la liaison est GENERIQUE (elle opere sur deux lignes `prompts` quelle
que soit leur nature, son OU image) ; la loger dans images.py la teinterait
« image », dans tracks.py « son ». Un router neutre /artist/me/prompts/.../link
reflete mieux la symetrie bidirectionnelle de la feature. Auth owner stricte :
les deux produits doivent appartenir a l'utilisateur courant (404 sinon).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.links import LinkError, link_products, unlink_products

router = APIRouter(tags=["links"])


class LinkBody(BaseModel):
    other_prompt_id: UUID
    # Nature du lien (C4). True = « ne ensemble » : les deux produits sont
    # crees dans la MEME action (flux A « vendre aussi la pochette comme
    # image », pose par dashboard.js) → masques en carte individuelle sur les
    # surfaces publiques, visibles seulement via l'oeuvre. False (defaut) =
    # « lie apres coup » (flux B images-create.js / lien manuel) → les deux
    # restent visibles individuellement. L'achat separe reste possible des
    # deux cotes dans tous les cas.
    bundle_exclusive: bool = False


@router.post(
    "/artist/me/prompts/{prompt_id}/link",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def link_prompt(
    prompt_id: UUID,
    body: LinkBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lie deux produits de l'artiste en une oeuvre complete (1:1, nature croisee).
      - 404 si l'un des deux est absent / pas owner / supprime.
      - 409 si deja lie OU natures incompatibles (image+image, son+son).
    Achat/prix/rarete inchanges : pur lien d'affichage.
    """
    try:
        await link_products(
            db,
            owner_id=current_user.id,
            prompt_a_id=prompt_id,
            prompt_b_id=body.other_prompt_id,
            bundle_exclusive=body.bundle_exclusive,
        )
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    await db.commit()


@router.delete(
    "/artist/me/prompts/{prompt_id}/link",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_prompt(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delie le produit de son partenaire (clear des deux cotes). 404 si absent /
    pas owner. Idempotent si deja non lie.
    """
    try:
        await unlink_products(
            db, owner_id=current_user.id, prompt_id=prompt_id
        )
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    await db.commit()
