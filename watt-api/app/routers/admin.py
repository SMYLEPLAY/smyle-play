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

B1 (2026-09-08) — rendre K-02 utilisable sans SQL. K-02 exige un UUID que
RIEN n'expose : aucune route n'énumérait les comptes pour un admin,
`/watt/search/artists` ne remonte que les profils publiés (un testeur frais
est invisible, et cette confidentialité est VOULUE — on n'y touche pas), et
`tools/inspect_db_state.py` n'imprime pas l'id. Le seul contournement était
`psql` ou promouvoir/rétrograder le compte avec `tools/make_admin.py` parce
que lui affiche l'id. On ajoute la recherche admin et le crédit par email.

  GET  /admin/users?q=&limit=           → cherche un compte (admin only, B1)
  POST /admin/users/{user_id}/credits   → crédite un compte (type GRANT, promo)
  POST /admin/credits                   → idem, cible par email OU user_id (B1)
  GET  /admin/grants?limit=             → derniers grants, avec métadonnées
  GET  /admin/eco-cockpit               → cockpit économique (lecture seule)
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.core.ratelimit import LIMIT_PURCHASE, limiter
from app.database import get_db
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.routers.watt_compat import _derive_artist_slug
from app.schemas.credit import TransactionRead
from app.services.beta_dashboard import beta_dashboard_data
from app.services.credits import grant_credits_atomic
from app.services.dashboard import eco_cockpit_data

router = APIRouter(prefix="/admin", tags=["admin"])

# Suffixe d'email posé par l'anonymisation RGPD (services/account_deletion.py).
_DELETED_EMAIL_SUFFIX = "@deleted.watt"

# Bornes de GET /admin/users. Défaut bas : on cherche UN testeur, pas un
# annuaire. Plafond dur pour qu'un `?limit=100000` ne devienne pas un dump
# de la table users depuis un simple navigateur.
_USERS_DEFAULT_LIMIT = 20
_USERS_MAX_LIMIT = 100


class AdminGrantRequest(BaseModel):
    """Corps du crédit admin. `extra="forbid"` : un champ inattendu (typo,
    tentative de viser un autre bucket) doit être un 422, pas un silence."""

    model_config = ConfigDict(extra="forbid")

    credits: int = Field(ge=1, le=10000, description="Nombre de Smyles à créditer")
    reason: str = Field(min_length=1, max_length=500, description="Motif — tracé au ledger")


class AdminCreditsRequest(AdminGrantRequest):
    """Crédit admin ciblé par email OU identifiant (B1).

    Exactement UN des deux champs. On n'a pas voulu détendre le type du
    paramètre de chemin de `/admin/users/{user_id}/credits` (voir plus bas) :
    un corps explicite garde le contrat existant intact et laisse la place à
    d'autres formes de cible plus tard.
    """

    user_id: UUID | None = None
    email: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _exactly_one_target(self):
        if (self.user_id is None) == (self.email is None):
            raise ValueError("Fournir exactement un de `user_id` ou `email`.")
        return self


class AdminUserRead(BaseModel):
    """Fiche d'un compte pour l'administration.

    Liste de champs EXPLICITE, jamais `from_attributes` sur le modèle User :
    la table porte `password_hash`, `signup_ip`, `token_version`,
    `referral_code`… qui n'ont rien à faire dans une réponse HTTP. Ajouter un
    champ ici doit être un geste conscient.
    """

    id: UUID
    email: str
    artist_name: str | None = None
    slug: str
    credits_balance: int
    created_at: datetime
    profile_public: bool
    is_banned: bool


def _user_out(u: User) -> AdminUserRead:
    return AdminUserRead(
        id=u.id,
        email=u.email,
        artist_name=u.artist_name,
        slug=_derive_artist_slug(u),
        credits_balance=int(u.credits_balance or 0),
        created_at=u.created_at,
        profile_public=bool(u.profile_public),
        is_banned=bool(u.is_banned),
    )


def _search_patterns(q: str) -> list[str]:
    """Motifs ILIKE dérivés de la requête.

    Le slug public n'est pas une colonne : `_derive_artist_slug` le calcule
    (slugify de `artist_name`, ou local-part de l'email pour les comptes
    univers). Chercher « marie-dupont » doit donc aussi matcher le nom
    d'artiste « Marie Dupont » — d'où l'échange tiret/underscore ↔ espace.
    """
    base = q.strip()
    variants = {base, base.replace("-", " ").replace("_", " "), base.replace(" ", "-")}
    return [f"%{v}%" for v in variants if v]


async def _resolve_target(db: AsyncSession, *, user_id: UUID | None, email: str | None) -> User:
    """Charge le compte à créditer et refuse les cibles interdites.

    Source unique des règles de K-02 (404 inconnu, 400 banni, 400 supprimé),
    partagée par les deux routes de crédit pour qu'elles ne divergent jamais.
    """
    if user_id is not None:
        stmt = select(User).where(User.id == user_id)
    else:
        stmt = select(User).where(func.lower(User.email) == (email or "").strip().lower())
    target = (await db.execute(stmt)).scalars().first()
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
    return target


async def _do_grant(
    db: AsyncSession, *, admin: User, target: User, credits: int, reason: str
) -> Transaction:
    """Crédite via `grant_credits_atomic` — jamais de mutation de solde à la
    main — et trace l'auteur au ledger (append-only)."""
    try:
        tx = await grant_credits_atomic(
            db=db,
            user_id=target.id,
            amount=credits,
            reason=reason,
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
    target = await _resolve_target(db, user_id=user_id, email=None)
    return await _do_grant(
        db, admin=admin, target=target, credits=payload.credits, reason=payload.reason
    )


@router.post(
    "/credits",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(LIMIT_PURCHASE)
async def grant_credits_by_target(
    payload: AdminCreditsRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Même crédit que ci-dessus, mais la cible peut être un EMAIL (B1).

    Pourquoi une route neuve plutôt que détendre `/admin/users/{user_id}` ?
    Le paramètre de chemin est typé `UUID` : le relâcher en `str` ferait
    passer « uuid invalide » de 422 à 404, changerait le schéma OpenAPI de
    la route livrée par K-02 et obligerait à URL-encoder les emails (`+`
    dans un chemin est un piège classique). Un corps explicite ne casse rien,
    rend la cible lisible dans les logs, et laisse la place à d'autres formes
    de cible. Les deux routes partagent `_resolve_target` / `_do_grant`.
    """
    target = await _resolve_target(db, user_id=payload.user_id, email=payload.email)
    return await _do_grant(
        db, admin=admin, target=target, credits=payload.credits, reason=payload.reason
    )


@router.get("/users", response_model=list[AdminUserRead])
async def search_users(
    q: str = Query(default="", max_length=200, description="Email, pseudo ou slug (partiel)"),
    limit: int = Query(default=_USERS_DEFAULT_LIMIT, ge=1, le=_USERS_MAX_LIMIT),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Cherche un compte pour l'administration — la brique qui manquait à K-02.

    Distinct de `/watt/search/artists`, qui filtre `profile_public = TRUE`
    (doctrine de confidentialité voulue, intacte) : ici on voit TOUS les
    comptes, y compris un testeur inscrit il y a trente secondes. D'où la
    garde `require_admin` : un non-admin reçoit 403.

    Recherche insensible à la casse (ILIKE), partielle, sur email et nom
    d'artiste. `q` vide = les derniers inscrits (cas « je viens de faire
    signer Marie, elle est en haut de la liste »).
    """
    stmt = select(User)
    patterns = _search_patterns(q)
    if patterns:
        stmt = stmt.where(
            or_(
                *[User.email.ilike(p) for p in patterns],
                *[User.artist_name.ilike(p) for p in patterns],
            )
        )
    rows = (
        await db.execute(stmt.order_by(User.created_at.desc()).limit(limit))
    ).scalars().all()
    return [_user_out(u) for u in rows]


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


# ─────────────────────────────────────────────────────────────────────────────
# Brique 2 — Programme PIONNIER : rattrapage en DEUX TEMPS (2026-09-23)
#
# Les créateurs qui ont publié AVANT l'activation doivent recevoir leur rang,
# dans l'ordre de leur première œuvre. Ce n'est PAS une migration automatique :
# on ne voit pas les données de prod, et certains comptes (ex. un compte de test)
# ne doivent pas prendre une place. Donc :
#
#   POST /admin/pioneer/retro/preview  { exclude_ids }                 → n'écrit RIEN
#   POST /admin/pioneer/retro/confirm  { exclude_ids, expected_user_ids } → écrit
#
# La confirmation n'écrit que si la liste recalculée est EXACTEMENT celle que
# l'admin a vue (sinon 409 : relancer l'aperçu). Les exclusions sont PERSISTÉES :
# un compte exclu ne recevra jamais de rang, ni ici ni plus tard en direct.
# Idempotent. Utilisable flag FEATURE_PIONEER OFF (ordre recommandé : rattrapage
# PUIS activation, pour que les rangs suivent l'ordre réel de publication).
# ─────────────────────────────────────────────────────────────────────────────

from app.services.pioneer import (  # noqa: E402 — regroupé avec la section
    PioneerNotHeld,
    PioneerRetroConflict,
    list_revocations,
    liste_pionniers,
    pioneer_stats,
    retro_candidates,
    retro_confirm,
    revoke_pioneer,
)


class PioneerRetroPreviewIn(BaseModel):
    exclude_ids: list[UUID] = Field(default_factory=list, max_length=500)


class PioneerRetroConfirmIn(BaseModel):
    exclude_ids: list[UUID] = Field(default_factory=list, max_length=500)
    expected_user_ids: list[UUID] = Field(default_factory=list, max_length=100)


@router.post("/pioneer/retro/preview")
async def pioneer_retro_preview(
    payload: PioneerRetroPreviewIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """APERÇU — n'écrit rien. Liste ordonnée des comptes qui recevraient un
    rang Pionnier si l'on confirmait maintenant (exclusions appliquées)."""
    return {
        "places": await pioneer_stats(db),
        "candidats": await retro_candidates(db, payload.exclude_ids),
        "ecrit": False,
    }


@router.post("/pioneer/retro/confirm")
async def pioneer_retro_confirm(
    payload: PioneerRetroConfirmIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """CONFIRMATION — écrit les rangs de la liste vue à l'aperçu."""
    try:
        result = await retro_confirm(
            db,
            exclude_ids=payload.exclude_ids,
            expected_user_ids=payload.expected_user_ids,
        )
    except PioneerRetroConflict as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    await db.commit()
    return result


# ── Anti-squat Pionnier (Lot 2, « à vie sauf fraude ») ──────────────────────

class PioneerRevokeIn(BaseModel):
    # Motif OBLIGATOIRE : il est journalisé (pioneer_revocations).
    reason: str = Field(min_length=3, max_length=500)


@router.post("/pioneer/{user_id}/revoke")
async def pioneer_revoke(
    user_id: UUID,
    payload: PioneerRevokeIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Révoque un rang Pionnier (fraude / squat), motif obligatoire, et remet
    la place en jeu : elle revient au prochain créateur éligible, sous le même
    verrou sans course que l'attribution. Le compte révoqué est exclu à vie."""
    try:
        result = await revoke_pioneer(
            db, user_id=user_id, reason=payload.reason, revoked_by=admin.id
        )
    except PioneerNotHeld as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    await db.commit()
    return result


@router.get("/pioneer/revocations")
async def pioneer_revocations(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Journal des révocations de rang Pionnier (le plus récent d'abord)."""
    return {"revocations": await list_revocations(db)}


# ── « Prêt à sortir » (Lot 2) — base du futur agent analytique ──────────────

@router.get("/pret-a-sortir")
async def pret_a_sortir(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Une ligne par sortie mensuelle (M1…M6) : critère, valeur actuelle, feu
    vert / orange / rouge, fiabilité. Chiffres tirés de la base uniquement."""
    from app.services.launch_readiness import readiness

    return await readiness(db)


# ── Trophées : préparation du rallumage (Lot 3, décision Tom 23/09) ─────────

@router.post("/trophees/preparer-rallumage")
async def trophees_preparer_rallumage(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """À lancer juste AVANT de passer SHOW_TROPHEES à true : enregistre, sans
    aucun Smyle, les paliers déjà atteints. Après le rallumage, seuls les
    paliers franchis ensuite créditent. Idempotent, sans risque de le relancer."""
    from app.services.achievements import enregistrer_paliers_sans_recompense

    out = await enregistrer_paliers_sans_recompense(db)
    await db.commit()
    return out


# ── Étape 2 — écrans admin : Pionniers, contenus retirés, achats par carte ──

@router.get("/pioneer/liste")
async def pioneer_liste(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Pionniers actuels, par rang (écran « Pionniers » de la page admin)."""
    return {"places": await pioneer_stats(db), "pionniers": await liste_pionniers(db)}


class MotifIn(BaseModel):
    # Motif OBLIGATOIRE, journalisé.
    reason: str = Field(min_length=3, max_length=500)


@router.get("/contenus-retires")
async def contenus_retires_liste(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Contenus retirés par la modération (écran « Contenus retirés »)."""
    from app.services.moderation import contenus_retires

    return {"contenus": await contenus_retires(db)}


@router.post("/contenus-retires/{cible_type}/{cible_id}/restaurer")
async def contenu_restaurer(
    cible_type: str,
    cible_id: str,
    payload: MotifIn,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Restaure un contenu retiré (motif obligatoire, journalisé). Seul chemin
    autorisé à lever un retrait : la base refuse toute autre voie."""
    from app.services.moderation import RestaurationImpossible, restaurer_contenu

    try:
        out = await restaurer_contenu(
            db, admin_id=admin.id, cible_type=cible_type, cible_id=cible_id,
            motif=payload.reason,
        )
    except RestaurationImpossible as e:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    await db.commit()
    return out
