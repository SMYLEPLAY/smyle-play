from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import is_admin_user
from app.auth.jwt import get_current_user
from app.config import settings
from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.database import get_db
from app.models.user import User
from app.schemas.credit import (
    CreditPack,
    CreditPacksResponse,
    TranchePrix,
    GrantCreditsRequest,
    TransactionRead,
)
from app.services.credits import (
    ACHAT_MAX_SMYLES,
    ACHAT_MIN_SMYLES,
    ACHAT_PAS_SMYLES,
    CREDIT_PACKS,
    TRANCHES_PRIX,
    grant_credits_atomic,
)

router = APIRouter(prefix="/credits", tags=["credits"])


def _euros_fr(cents: int) -> str:
    """« 147500 » → « 1 475,00 € » (espace fine insécable pour les milliers)."""
    return f"{cents / 100:,.2f} €".replace(",", "\u202f").replace(".", ",")


@router.get("/packs", response_model=CreditPacksResponse)
async def list_packs(request: Request, db: AsyncSession = Depends(get_db)):
    """Liste publique des packs de crédits disponibles.

    S-11 (2026-09-04, annexe A §M5) : la grille n'est servie que si l'item de
    mode lancement `achatSmyles` est VISIBLE. Sinon elle exposerait une
    tarification en euros pour un achat qui n'existe pas encore (Stripe non
    branché, `POST /credits/grant` réservé à `is_official`) — une promesse de
    prix que rien ne peut honorer. Rallumable par `SHOW_ACHAT_SMYLES=true`.
    """
    if not settings.launch_flags_dict()["achatSmyles"]:
        return CreditPacksResponse(packs=[])
    _ref = CREDIT_PACKS[0]["price_eur_cents"] / CREDIT_PACKS[0]["credits"]
    packs = [
        CreditPack(
            id=p["id"],
            credits=p["credits"],
            price_eur_cents=p["price_eur_cents"],
            # Lot L : format français (« 8,00 € », « 1 475,00 € »), prix unitaire exact.
            price_eur_display=_euros_fr(p["price_eur_cents"]),
            unit_price_cents=p["price_eur_cents"] // p["credits"],
            unit_price_display=(
                f"{p['price_eur_cents'] / 100 / p['credits']:.4f}".rstrip("0").replace(".", ",")
                + " € / Smyle"),
            remise_pct=max(0, int(round(
                100 * (1 - (p["price_eur_cents"] / p["credits"]) / _ref)))),
        )
        for p in CREDIT_PACKS
    ]
    from app.services.stripe_payments import TVA_MENTION, achat_carte_ouvert_pour

    # Étape 2 : paiement proposé seulement s'il est réellement ouvert pour CE
    # visiteur (clé de test → admins seulement ; compte bloqué → message).
    viewer = await _optional_viewer(request, db)
    ouvert = achat_carte_ouvert_pour(viewer)
    message = None
    if not ouvert:
        message = "L'achat par carte arrive bientôt."
    elif viewer is not None and viewer.achat_carte_bloque_at is not None:
        ouvert = False
        message = "L'achat par carte est suspendu sur ton compte. Contacte-nous pour le rétablir."
    _ref_m = TRANCHES_PRIX[0][1]
    tranches = [
        TranchePrix(
            a_partir_de=seuil,
            prix_millieme=m,
            prix_display=f"{m / 1000:.3f}".rstrip("0").replace(".", ",") + " €",
            remise_pct=max(0, int(round(100 * (1 - m / _ref_m)))),
        )
        for seuil, m in TRANCHES_PRIX
    ]
    return CreditPacksResponse(
        packs=packs,
        tranches=tranches,
        min_smyles=ACHAT_MIN_SMYLES,
        max_smyles=ACHAT_MAX_SMYLES,
        pas_smyles=ACHAT_PAS_SMYLES,
        mention_tva=TVA_MENTION if settings.MENTION_TVA_FRANCHISE else None,
        paiement_carte=ouvert,
        message=message,
    )


async def _optional_viewer(request: Request, db: AsyncSession) -> User | None:
    """Viewer optionnel — LECTURE seulement (Lot A, M1 : version de jeton et
    compte suspendu vérifiés comme get_current_user)."""
    from app.auth.jwt import bearer_from_request, resolve_optional_user

    return await resolve_optional_user(db, bearer_from_request(request))


@router.post("/grant", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(LIMIT_PURCHASE)
async def grant_credits(
    payload: GrantCreditsRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Attribution manuelle de crédits — RÉSERVÉE aux administrateurs
    (is_official OU is_admin, K-01). Crédite UNIQUEMENT l'appelant.

    SÉCURITÉ (Phase 0 lancement, 2026-07-23) : cet endpoint créditait librement
    le compte connecté (stub « en attendant Stripe »). Ouvert au public, il
    permettait à n'importe qui de se fabriquer des Smyles à volonté et de
    détruire l'économie. Il est désormais gaté sur is_official ; les Smyles des
    utilisateurs se gagnent (streak, parrainage) ou, plus tard, s'achètent via
    un webhook Stripe signé et vérifié côté serveur — jamais par appel direct.
    """
    # K-01 : is_official OU is_admin (règle partagée). Message inchangé :
    # cet endpoint est atteignable par n'importe quel membre connecté.
    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Réservé. Les Smyles se gagnent en explorant, en publiant et en jouant.",
        )
    try:
        tx = await grant_credits_atomic(
            db=db,
            user_id=current_user.id,
            amount=payload.credits,
            reason=payload.reason,
        )
        await db.commit()
        await db.refresh(tx)
        return tx
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
