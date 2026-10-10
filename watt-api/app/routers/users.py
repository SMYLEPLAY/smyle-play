from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import ADMIN_FORBIDDEN_DETAIL, is_admin_user
from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


class SuppressionCompte(BaseModel):
    """Lot D — renonciation explicite, vérifiée côté serveur : la case
    « je renonce à mes Smyles » cochée ET le mot SUPPRIMER saisi."""

    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(default="", max_length=40)
    renonce_smyles: bool = False


def _verifier_renonciation(payload: SuppressionCompte | None) -> None:
    if payload is None or not payload.renonce_smyles or (payload.confirmation or "").strip() != "SUPPRIMER":
        raise HTTPException(
            422,
            detail=("Pour supprimer ton compte, coche la renonciation à tes Smyles "
                    "et tape SUPPRIMER."),
        )


async def _supprimer(db, user, background_tasks):
    from app.services.account_deletion import delete_account, purger_fichiers

    cles = await delete_account(db, user)
    if cles:
        background_tasks.add_task(purger_fichiers, cles)


@router.get("/me/suppression")
async def apercu_suppression(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lot D — ce que la suppression fera perdre (affiché dans l'écran de
    confirmation) : Smyles par catégorie, œuvres, rang Pionnier."""
    from app.services.account_deletion import apercu_suppression as _apercu

    return await _apercu(db, current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    background_tasks: BackgroundTasks,
    payload: SuppressionCompte | None = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Suppression de compte RGPD (pack légal v1, complétée au Lot D).

    Exige une renonciation explicite (corps JSON : `renonce_smyles: true` et
    `confirmation: "SUPPRIMER"`), sinon 422. Effacement des données
    personnelles, des œuvres jamais achetées et de leurs fichiers (purge en
    tâche de fond), anonymisation de l'auteur des œuvres déjà achetées,
    registre conservé. Détail : services/account_deletion.py.
    """
    _verifier_renonciation(payload)
    await _supprimer(db, current_user, background_tasks)


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me_post(
    payload: SuppressionCompte,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Même suppression que DELETE /users/me (pour les clients qui
    n'envoient pas de corps avec DELETE)."""
    _verifier_renonciation(payload)
    await _supprimer(db, current_user, background_tasks)


@router.post("/me/accept-terms", response_model=UserRead)
async def accept_terms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lot D — accepte les CGU en vigueur (version + date). Idempotent."""
    from datetime import datetime, timezone

    from app.core.legal import CGU_VERSION

    if current_user.accepted_terms_version != CGU_VERSION:
        current_user.accepted_terms_version = CGU_VERSION
        current_user.accepted_terms_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(current_user)
    return current_user


@router.get("/me/export")
async def export_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export des données personnelles (RGPD art. 15/20 — accès/portabilité).
    Renvoie un JSON téléchargeable de toutes les données du compte (profil,
    transactions, achats, ventes, œuvres, messages, signalements faits,
    abonnements, consentements). Lecture seule.
    """
    from fastapi.responses import JSONResponse

    from app.services.account_export import export_account_data

    data = await export_account_data(db, current_user)
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": 'attachment; filename="mes-donnees-watt.json"'
        },
    )


@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/me/onboarding")
async def mark_onboarding_done(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Parcours V1 — le guide d'accueil a été vu (fermé ou terminé). La date de
    la première fois est conservée : rouvrir le guide depuis le menu ne la
    change pas. Idempotent."""
    from datetime import datetime, timezone

    if current_user.onboarding_done_at is None:
        current_user.onboarding_done_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(current_user)
    return {"onboarding_done_at": current_user.onboarding_done_at.isoformat()}


@router.get("/me/listing-slots")
async def read_my_listing_slots(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Jauge d'emplacements de vente (C6.3) : produits publiés vs limite du
    palier. `enforced=False` tant que les paliers payants ne sont pas ouverts
    (la jauge s'affiche mais ne bloque pas)."""
    from app.services.listings import listing_slots_status

    return await listing_slots_status(db, current_user.id, current_user.tier)


@router.get("/eco-cockpit")
async def eco_cockpit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A4 — cockpit économique (admin only, lecture seule). Gardé par la règle
    d'administration partagée (is_official OU is_admin — K-01). Solvabilité +
    Smyles en circulation + canari + business."""
    if not is_admin_user(current_user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=ADMIN_FORBIDDEN_DETAIL
        )
    from app.services.dashboard import eco_cockpit_data

    return await eco_cockpit_data(db)


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return current_user
