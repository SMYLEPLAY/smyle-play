"""Programme PIONNIER — Brique 2 (décision Tom 23/09).

Pionnier = les 100 PREMIERS créateurs qui PUBLIENT une œuvre. Avantage :
commission plafonnée à 10 % à vie (règle du taux le plus favorable, cf.
`tiers.commission_pct_for`). Rang FIGÉ à vie (`users.pioneer_rank`, 1..100).

Trois entrées :
  1. EN DIRECT (flag `FEATURE_PIONEER`) : à la première publication d'une œuvre,
     le créateur reçoit le rang suivant s'il reste des places ;
  2. RATTRAPAGE (action admin en deux temps) : aperçu SANS écriture, puis
     confirmation qui écrit, avec exclusion de comptes par identifiant ;
  3. COMPTEUR PUBLIC « places restantes » (flag `FEATURE_PIONEER`).

─── Garantie « sans course » ───────────────────────────────────────────────────
Toute attribution (directe ou rattrapage) prend d'abord un VERROU APPLICATIF
transactionnel unique (`pg_advisory_xact_lock(_LOCK_KEY)`). Les attributions
sont donc strictement sérialisées : deux publications simultanées ne peuvent pas
lire le même « dernier rang » ni dépasser 100. Filets en base, au cas où :
UNIQUE(pioneer_rank) et CHECK 1..100 (migration 0091).

Anti-deadlock : l'attribution tourne dans une transaction COURTE et SÉPARÉE de
la publication (après son commit). Elle ne prend que deux verrous, toujours dans
le même ordre — le verrou applicatif, puis la ligne du créateur. Aucune autre
transaction ne prend ce verrou applicatif (en particulier pas les ventes) → pas
de cycle possible. Et une attribution qui échouerait ne peut PAS faire échouer
la publication, déjà validée.

─── Éligibilité ────────────────────────────────────────────────────────────────
  - au moins une œuvre EN LIGNE (définition unique : `publications.py`) — une
    œuvre retirée par la modération ne qualifie donc pas ;
  - exclusions automatiques : compte trésorerie, compte vitrine (`is_official`),
    comptes administrateurs (`is_admin`), comptes suspendus (`is_banned`),
    comptes supprimés (email `…@deleted.watt`), et comptes exclus par l'admin
    (`pioneer_excluded`, exclusion PERSISTÉE) ;
  - email vérifié : NON exigé au rattrapage (la vérification d'email est récente
    et non bloquante : les premiers créateurs n'ont pour la plupart jamais
    vérifié, l'exiger les écarterait tous) ; en direct, exigé SEULEMENT si
    `REQUIRE_EMAIL_VERIFIED` est actif.

Ordre du rattrapage : date de la PREMIÈRE œuvre actuellement en ligne
(`created_at`, puis id en départage — ordre total, reproductible).
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.adn import Adn
from app.models.prompt import Prompt
from app.models.track import Track
from app.models.visual_adn import VisualAdn
from app.models.voice import Voice
from app.services.publications import SQL_OEUVRES_EN_LIGNE

log = logging.getLogger(__name__)

PIONEER_SLOTS = 100

# Clé du verrou applicatif (pg_advisory_xact_lock). Valeur fixe et unique à
# l'application : ASCII « PION » = 0x50494F4E.
_LOCK_KEY = 0x50494F4E

_DELETED_EMAIL_SUFFIX = "@deleted.watt"
_DELETED_PATTERN = "%" + _DELETED_EMAIL_SUFFIX

# Exclusions automatiques, sur l'alias `u` de la table users.
_SQL_EXCLUSIONS = (
    "NOT u.is_treasury AND NOT u.is_official AND NOT u.is_admin "
    "AND NOT u.is_banned AND NOT u.pioneer_excluded "
    "AND u.email NOT LIKE :deleted_pattern"
)


def _mask_email(email: str | None) -> str | None:
    """« tom.lecomte@gmail.com » -> « to***@gmail.com » : assez pour reconnaître
    un compte, sans exposer l'adresse (même règle de discrétion que le tableau
    de bord de bêta, qui n'affiche aucun email)."""
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    return (local[:2] + "***@" + domain) if local else "***@" + domain


class PioneerRetroConflict(Exception):
    """La liste à confirmer ne correspond plus à la liste recalculée (des
    données ont changé entre l'aperçu et la confirmation) → relancer l'aperçu."""


async def _lock(db: AsyncSession) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})


async def pioneer_stats(db: AsyncSession) -> dict:
    n = (await db.execute(
        text("SELECT count(*) FROM users WHERE pioneer_rank IS NOT NULL")
    )).scalar_one()
    n = int(n)
    return {"total": PIONEER_SLOTS, "attribuees": n, "restantes": max(0, PIONEER_SLOTS - n)}


async def is_eligible(db: AsyncSession, user_id: UUID, *, live: bool) -> bool:
    """Le compte peut-il recevoir un rang MAINTENANT ? (ne regarde pas s'il
    reste des places, ni s'il en a déjà un)."""
    need_email = bool(live and settings.REQUIRE_EMAIL_VERIFIED)
    row = (await db.execute(
        text(
            "SELECT 1 FROM users u WHERE u.id = :uid AND " + _SQL_EXCLUSIONS + " "
            "AND (NOT :need_email OR u.email_verified) "
            "AND EXISTS (SELECT 1 FROM (" + SQL_OEUVRES_EN_LIGNE + ") o "
            "            WHERE o.uid = u.id)"
        ),
        {"uid": user_id, "need_email": need_email, "deleted_pattern": _DELETED_PATTERN},
    )).first()
    return row is not None


async def award_pioneer(db: AsyncSession, user_id: UUID, *, live: bool = True) -> int | None:
    """Attribue le rang suivant à `user_id` s'il est éligible et qu'il reste
    une place. Renvoie son rang (nouveau OU déjà détenu), ou None.

    Idempotent. Sérialisé par le verrou applicatif. NE vérifie PAS le flag :
    c'est à l'appelant (direct = flag requis ; le rattrapage passe par
    `retro_confirm`). L'appelant commit.
    """
    await _lock(db)
    row = (await db.execute(
        text("SELECT pioneer_rank FROM users WHERE id = :uid"), {"uid": user_id}
    )).first()
    if row is None:
        return None
    if row.pioneer_rank is not None:
        return int(row.pioneer_rank)  # rang figé à vie : rien à faire
    stats = await pioneer_stats(db)
    if stats["restantes"] <= 0:
        return None
    if not await is_eligible(db, user_id, live=live):
        return None
    rank = int((await db.execute(
        text("SELECT COALESCE(MAX(pioneer_rank), 0) + 1 FROM users")
    )).scalar_one())
    if rank > PIONEER_SLOTS:
        return None
    await db.execute(
        text(
            "UPDATE users SET pioneer_rank = :r, is_pioneer = TRUE, "
            "pioneer_awarded_at = now() WHERE id = :uid AND pioneer_rank IS NULL"
        ),
        {"r": rank, "uid": user_id},
    )
    return rank


async def retro_candidates(db: AsyncSession, exclude_ids: list[UUID] | None = None) -> list[dict]:
    """APERÇU du rattrapage — n'écrit RIEN. Comptes qui recevraient un rang,
    dans l'ordre, dans la limite des places restantes. Email non exigé."""
    stats = await pioneer_stats(db)
    if stats["restantes"] <= 0:
        return []
    base = int((await db.execute(
        text("SELECT COALESCE(MAX(pioneer_rank), 0) FROM users")
    )).scalar_one())
    rows = (await db.execute(
        text(
            "WITH o AS (" + SQL_OEUVRES_EN_LIGNE + "), "
            "premieres AS (SELECT uid, MIN(created_at) AS premiere, "
            "              count(*) AS oeuvres FROM o GROUP BY uid) "
            "SELECT u.id, u.artist_name, u.email, p.premiere, p.oeuvres "
            "FROM premieres p JOIN users u ON u.id = p.uid "
            "WHERE u.pioneer_rank IS NULL AND " + _SQL_EXCLUSIONS + " "
            "AND NOT (u.id = ANY(CAST(:exclude AS uuid[]))) "
            "ORDER BY p.premiere ASC, u.id ASC LIMIT :lim"
        ),
        {
            "exclude": list(exclude_ids or []),
            "lim": stats["restantes"],
            "deleted_pattern": _DELETED_PATTERN,
        },
    )).all()
    return [
        {
            "rang": base + i + 1,
            "user_id": str(r.id),
            "pseudo": r.artist_name,
            "email_masque": _mask_email(r.email),
            "premiere_oeuvre": r.premiere.isoformat() if r.premiere else None,
            "oeuvres_en_ligne": int(r.oeuvres),
        }
        for i, r in enumerate(rows)
    ]


async def retro_confirm(
    db: AsyncSession,
    *,
    exclude_ids: list[UUID],
    expected_user_ids: list[UUID],
) -> dict:
    """CONFIRMATION du rattrapage — écrit. L'appelant commit.

    1. verrou applicatif ;
    2. exclusions PERSISTÉES (`pioneer_excluded`) pour les comptes sans rang —
       ils ne recevront jamais de rang, ni maintenant ni plus tard en direct ;
    3. recalcul de la liste : elle doit être EXACTEMENT celle que l'admin a vue
       (`expected_user_ids`, dans l'ordre). Sinon → PioneerRetroConflict ;
    4. attribution des rangs dans cet ordre.

    Idempotent : re-confirmer une liste déjà appliquée ne fait rien.
    """
    await _lock(db)
    exclude = list(dict.fromkeys(exclude_ids))
    deja_pionniers = []
    if exclude:
        deja_pionniers = [
            str(r.id) for r in (await db.execute(
                text("SELECT id FROM users WHERE id = ANY(CAST(:ids AS uuid[])) AND pioneer_rank IS NOT NULL"),
                {"ids": exclude},
            )).all()
        ]
        await db.execute(
            text(
                "UPDATE users SET pioneer_excluded = TRUE "
                "WHERE id = ANY(CAST(:ids AS uuid[])) AND pioneer_rank IS NULL"
            ),
            {"ids": exclude},
        )

    attendu = [str(u) for u in expected_user_ids]
    recalcule = [c["user_id"] for c in await retro_candidates(db, exclude)]

    if recalcule != attendu:
        # Double clic / relance : tout est déjà appliqué → no-op, pas d'erreur.
        if attendu:
            deja = (await db.execute(
                text("SELECT count(*) FROM users WHERE id = ANY(CAST(:ids AS uuid[])) AND pioneer_rank IS NOT NULL"),
                {"ids": [UUID(u) for u in attendu]},
            )).scalar_one()
            if int(deja) == len(attendu):
                return {"attribues": [], "deja_applique": True,
                        "exclusions_ignorees_deja_pionniers": deja_pionniers,
                        **(await pioneer_stats(db))}
        raise PioneerRetroConflict(
            "La liste a changé depuis l'aperçu (nouvelle publication, retrait, "
            "attribution en direct…). Relance l'aperçu puis confirme à nouveau."
        )

    base = int((await db.execute(
        text("SELECT COALESCE(MAX(pioneer_rank), 0) FROM users")
    )).scalar_one())
    attribues = []
    for i, uid in enumerate(attendu):
        rang = base + i + 1
        await db.execute(
            text(
                "UPDATE users SET pioneer_rank = :r, is_pioneer = TRUE, "
                "pioneer_awarded_at = now() WHERE id = :uid AND pioneer_rank IS NULL"
            ),
            {"r": rang, "uid": UUID(uid)},
        )
        attribues.append({"rang": rang, "user_id": uid})
    return {"attribues": attribues, "deja_applique": False,
            "exclusions_ignorees_deja_pionniers": deja_pionniers,
            **(await pioneer_stats(db))}


# ─────────────────────────────────────────────────────────────────────────────
# Attribution EN DIRECT, après le commit de la publication
# ─────────────────────────────────────────────────────────────────────────────
#
# Plutôt que d'ajouter un appel dans chacun des ~10 points de publication
# (images, marketplace, beats, voix, ADN visuel, tracks, PATCH de publication…)
# au risque d'en oublier un — ou d'en oublier un futur —, on écoute la session :
# tout objet œuvre créé ou modifié pendant un flush signale son créateur ; au
# COMMIT, les créateurs signalés deviennent candidats ; à la fin de la requête,
# `get_db` lance l'attribution dans une transaction séparée.
#
# L'écouteur n'est qu'un INDICE : c'est la requête SQL d'éligibilité qui décide.
# Un candidat dont la publication a été annulée (rollback) n'a pas d'œuvre en
# ligne → il n'est simplement pas éligible.

_WORK_MODELS = (Prompt, Adn, VisualAdn, Voice, Track)
_PENDING = "pioneer_pending"
_COMMITTED = "pioneer_committed"
_registered = False


def _collect(session, flush_context) -> None:
    if not settings.FEATURE_PIONEER:
        return
    works = _WORK_MODELS
    pending = None
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, works):
            aid = getattr(obj, "artist_id", None)
            if aid is not None:
                if pending is None:
                    pending = session.info.setdefault(_PENDING, set())
                pending.add(aid)


def _promote(session) -> None:
    pending = session.info.pop(_PENDING, None)
    if pending:
        session.info.setdefault(_COMMITTED, set()).update(pending)


def register_listeners() -> None:
    """Branche la collecte sur les sessions de l'application (idempotent)."""
    global _registered
    if _registered:
        return
    from app.database import AppSession

    event.listen(AppSession, "after_flush", _collect)
    event.listen(AppSession, "after_commit", _promote)
    _registered = True


async def award_committed_candidates(info: dict) -> None:
    """Appelé par `get_db` après la requête. Ne lève JAMAIS : une attribution
    ratée ne doit pas transformer une publication réussie en erreur."""
    candidats = info.pop(_COMMITTED, None)
    if not candidats or not settings.FEATURE_PIONEER:
        return
    from app.database import SessionLocal

    for uid in candidats:
        try:
            async with SessionLocal() as db:
                rang = await award_pioneer(db, uid, live=True)
                await db.commit()
            if rang is not None:
                log.info("pioneer.award", extra={"user_id": str(uid), "rang": rang})
        except Exception:  # noqa: BLE001 — jamais bloquant pour la publication
            log.exception("pioneer.award_failed", extra={"user_id": str(uid)})
