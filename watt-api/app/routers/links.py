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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.links import (
    LinkError,
    link_image_to_track,
    link_products,
    linkable_candidates,
    public_oeuvre,
    track_link_state,
    track_linkable_images,
    unlink_products,
    unlink_track,
)

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


@router.get("/artist/me/prompts/{prompt_id}/linkable")
async def list_linkable_prompts(
    prompt_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Liste des produits de l'artiste eligibles a etre lies a prompt_id (C4 lien
    retroactif). Nature OPPOSEE (image → sons, son → images), owner, non
    supprime, non deja lie, hors prompt_id. Apercu LEGER uniquement (id, title,
    productType, priceCredits, coverUrl|previewKey) — aucun champ gate.
      - 404 si prompt_id absent / pas owner / supprime.
      - Si prompt_id est deja lie, renvoie quand meme la liste des candidats
        libres (le front gere l'etat « deja lie »).
    """
    try:
        return await linkable_candidates(
            db, owner_id=current_user.id, prompt_id=prompt_id
        )
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


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



# ──────────────────────────────────────────────────────────────────────────
# Lot 2 — liaison au niveau du MORCEAU (un son sans recette peut recevoir une
# image) + lecture publique d'une Œuvre (page /o/{id}).
# ──────────────────────────────────────────────────────────────────────────


class TrackLinkBody(BaseModel):
    image_id: UUID
    # Même sens que LinkBody.bundle_exclusive (« né ensemble » vs lié après coup).
    bundle_exclusive: bool = False


@router.post("/artist/me/tracks/{track_id}/link")
async def link_track(
    track_id: UUID,
    body: TrackLinkBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ajoute une image à un morceau publié (avec ou sans recette) → Œuvre.
    404 si absent / pas owner ; 409 si déjà lié. Renvoie l'id de l'Œuvre."""
    try:
        img = await link_image_to_track(
            db, owner_id=current_user.id, track_id=track_id,
            image_id=body.image_id, bundle_exclusive=body.bundle_exclusive,
        )
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    await db.commit()
    return {"oeuvreId": str(img.id), "url": f"/o/{img.id}"}


@router.get("/artist/me/tracks/{track_id}/link")
async def get_track_link(
    track_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """État de liaison du morceau (l'éditeur du créateur s'en sert)."""
    try:
        return await track_link_state(db, owner_id=current_user.id, track_id=track_id)
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/artist/me/tracks/{track_id}/linkable")
async def list_track_linkable(
    track_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Images libres du créateur, liables à ce morceau."""
    try:
        return await track_linkable_images(db, owner_id=current_user.id, track_id=track_id)
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.delete("/artist/me/tracks/{track_id}/link", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_track_route(
    track_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Délie l'image du morceau. Idempotent."""
    try:
        await unlink_track(db, owner_id=current_user.id, track_id=track_id)
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    await db.commit()


@router.get("/watt/oeuvres/{oeuvre_id}")
async def get_public_oeuvre(
    oeuvre_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Œuvre publique (1 son + 1 image) pour la page /o/{id}. 404 si absente,
    non publiée, retirée, ou créateur au profil privé.

    Lot 3 : `bundle` = offre « Acheter l'Œuvre » (prix du son + prix de
    l'image − 10 %), calculée pour l'acheteur connecté si un jeton accompagne
    la requête (perks, moitié déjà possédée), sinon au prix public. None si
    l'achat groupé n'existe pas (son en écoute libre, beat, propre œuvre)."""
    data = await public_oeuvre(db, oeuvre_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Œuvre introuvable.")
    from app.services.oeuvre_c4_purchase import oeuvre_offer

    viewer = await _optional_viewer_id(request, db)
    data["bundle"] = await oeuvre_offer(db, oeuvre_id=oeuvre_id, buyer_id=viewer)
    return data


async def _optional_viewer_id(request: Request, db: AsyncSession):
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    try:
        from sqlalchemy import select as _select

        from app.auth.jwt import decode_access_token

        email = decode_access_token(auth[7:].strip())
        if not email:
            return None
        return (await db.execute(
            _select(User.id).where(User.email == email, User.is_banned.is_(False))
        )).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        return None


@router.post("/watt/oeuvres/{oeuvre_id}/acheter", status_code=status.HTTP_201_CREATED)
@limiter.limit(LIMIT_PURCHASE)
async def buy_oeuvre(
    oeuvre_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Achat de l'Œuvre entière (décision Tom 23/09) : son + image − 10 %, en
    un achat atomique ; ou la moitié manquante au prix plein. Le son doit
    avoir une recette (pas d'achat groupé en « écoute libre »)."""
    from app.routers.unlocks import _raise_unlock_error
    from app.services.oeuvre_c4_purchase import OeuvreNotBundlable, buy_oeuvre_atomic

    try:
        out = await buy_oeuvre_atomic(db, buyer_id=current_user.id, oeuvre_id=oeuvre_id)
        await db.commit()
    except OeuvreNotBundlable as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        await db.rollback()
        _raise_unlock_error(e)
    return out
