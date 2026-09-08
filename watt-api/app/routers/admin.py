"""Endpoints d'administration — cockpit économique (A4) + crédit manuel (K-02).

Gardés par `require_admin` (is_official OU is_admin — K-01). Réservé : ne pas
exposer publiquement les données de solvabilité / réserve.

K-02 (2026-09-04, annexe B §2 / tâche B-M1) — créditer un testeur.
Jusqu'ici il n'existait AUCUN moyen de créditer un autre compte :
`POST /credits/grant` crédite uniquement l'appelant (`user_id=current_user.id`)
et son schéma est `extra="forbid"`, donc impossible de viser quelqu'un d'autre.
La seule voie restante était du SQL manuel sur la base Railway, en deux ordres
(ledger + buckets) — hors ledger applicatif, sans trace de l'auteur. On ajoute
ici l'endpoint : la ligne `transactions` (append-only, trigger
`enforce_transaction_no_delete`) EST l'audit, et elle porte `granted_by`.

  POST /admin/users/{user_id}/credits   → crédite un compte (type GRANT, promo)
  GET  /admin/grants?limit=             → derniers grants, avec métadonnées
  GET  /admin/eco-cockpit               → cockpit économique (lecture seule)
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.database import get_db
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.credit import TransactionRead
from app.services.beta_dashboard import beta_dashboard_data
from app.services.credits import grant_credits_atomic
from app.services.dashboard import eco_cockpit_data

router = APIRouter(prefix="/admin", tags=["admin"])

# Suffixe d'email posé par l'anonymisation RGPD (services/account_deletion.py).
_DELETED_EMAIL_SUFFIX = "@deleted.watt"


class AdminGrantRequest(BaseModel):
    """Corps du crédit admin. `extra="forbid"` : un champ inattendu (typo,
    tentative de viser un autre bucket) doit être un 422, pas un silence."""

    model_config = ConfigDict(extra="forbid")

    credits: int = Field(ge=1, le=10000, description="Nombre de Smyles à créditer")
    reason: str = Field(min_length=1, max_length=500, description="Motif — tracé au ledger")


class AdminGrantRead(TransactionRead):
    """Une ligne de grant, enrichie de ses métadonnées d'audit."""

    buyer_id: UUID | None = None
    metadata_json: dict | None = None


@router.post(
    "/users/{user_id}/credits",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(LIMIT_PURCHASE)
async def grant_credits_to_user(
    user_id: UUID,
    payload: AdminGrantRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Crédite un compte tiers en Smyles `promo` (non encaissables, dépensés
    en premier — cohérent avec `_TXTYPE_BUCKET[GRANT]`).

    L'audit est la ligne `transactions` : type `grant`, `buyer_id` = le
    bénéficiaire, et `metadata_json` qui porte `granted_by` / `granted_by_email`
    / `source`. Le ledger étant append-only, cette trace est indélébile.
    """
    target = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalars().first()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Compte introuvable")
    if target.is_banned:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Compte suspendu : crédit refusé.",
        )
    if str(target.email or "").endswith(_DELETED_EMAIL_SUFFIX):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Compte supprimé : crédit refusé.",
        )

    try:
        tx = await grant_credits_atomic(
            db=db,
            user_id=user_id,
            amount=payload.credits,
            reason=payload.reason,
            tx_type=TransactionType.GRANT,
            metadata={
                "granted_by": str(admin.id),
                "granted_by_email": admin.email,
                "source": "admin_grant",
            },
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    await db.refresh(tx)
    return tx


@router.get("/grants", response_model=list[AdminGrantRead])
async def list_grants(
    limit: int = Query(default=50, ge=1, le=200),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Derniers crédits admin, les plus récents d'abord (lecture seule)."""
    rows = (
        await db.execute(
            select(Transaction)
            .where(Transaction.type == TransactionType.GRANT)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return rows


@router.get("/eco-cockpit")
async def eco_cockpit(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await eco_cockpit_data(db)


# ─────────────────────────────────────────────────────────────────────────────
# B3 — Tableau de bord de bêta (2026-09-08)
#
# Tom ne peut pas voir ce qui se passe dans sa bêta sans écrire du SQL, et le
# seul tableau qui existait (`/admin/funnel`) comptait des événements
# télémétrie `signup` / `purchase` que le front n'émet jamais : il était
# structurellement vide. Ici, chaque chiffre d'activité vient du registre des
# transactions ou d'une table métier — un fait comptable, indépendant du
# consentement, d'un bloqueur ou de JavaScript.
#
#   GET /admin/beta?days=7&limit=20  → l'état de la bêta en une requête
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/beta")
async def beta_dashboard(
    days: int = Query(
        default=7, ge=1, le=365,
        description="Fenêtre glissante, en jours, pour les compteurs « sur la fenêtre »",
    ),
    limit: int = Query(
        default=20, ge=1, le=100,
        description="Nombre de ventes récentes et de créateurs listés",
    ),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """État de la bêta, en lecture seule et borné.

    Sections : `comptes`, `publications`, `ventes` (dont les `limit` dernières,
    lisibles), `masse_smyles` (création / dépense / destruction / circulation +
    réconciliation), `createurs`, `conversion_fiche_vers_deblocage`.

    Aucune donnée sensible : ni mot de passe, ni IP, ni e-mail — les personnes
    sont désignées par leur pseudo. Ce que la base ne sait pas mesurer est
    renvoyé avec `mesurable: false` et sa raison, jamais avec un chiffre inventé.
    """
    return await beta_dashboard_data(db, days=days, limit=limit)
