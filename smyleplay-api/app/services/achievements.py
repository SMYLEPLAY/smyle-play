"""
Phase 9.6 — Service trophées (achievements).

Le système est simple :
  - 3 axes indépendants (BUYER / FAN / ARTIST), cf. AchievementAxis
  - Chaque axe a N paliers (Achievement) avec un threshold et un credit_reward
  - Quand un user atteint un nouveau palier, on lui crée une UserAchievement
    et on grant les crédits BONUS (si reward > 0) via grant_credits_atomic

Le service expose 3 fonctions :
  - check_and_grant_achievements : appelé après une action (unlock prompt,
    unlock ADN, vente). Idempotent : si l'achievement est déjà débloqué,
    skip silencieusement.
  - get_user_progress : retourne la valeur courante du user sur un axe
    (utile pour l'endpoint /me/achievements)
  - list_user_achievements_with_progress : liste tous les achievements
    + progression du user (débloqué ou pas, valeur actuelle vs threshold)

Pattern atomique : le service fait des INSERT/UPDATE dans la session passée,
le caller est responsable du commit. Tous les write passent par des
savepoints (begin_nested) pour rollback propre en cas de race.

Anti-race : la contrainte UNIQUE (user_id, achievement_id) sur
user_achievements garantit qu'un même badge ne peut être inséré qu'une
seule fois. Si deux coroutines essaient en parallèle, l'une réussit,
l'autre se prend une IntegrityError qu'on catch et skip.
"""
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import (
    Achievement,
    AchievementAxis,
    UserAchievement,
)
from app.models.owned_adn import OwnedAdn
from app.models.transaction import TransactionType
from app.models.unlocked_prompt import UnlockedPrompt
from app.models.user import User
from app.services.credits import grant_credits_atomic


# -----------------------------------------------------------------------------
# Calcul de la progression sur un axe
# -----------------------------------------------------------------------------

async def get_user_progress(
    db: AsyncSession,
    *,
    user_id: UUID,
    axis: AchievementAxis,
) -> int:
    """
    Retourne la valeur courante du user sur l'axe demandé.

    Mapping :
      - BUYER  : nb d'UnlockedPrompt où current_owner_id = user_id
                 (current_owner et non original_buyer pour Phase 10 P2P)
      - FAN    : nb d'OwnedAdn où user_id = user_id
      - ARTIST : User.credits_earned_total (compteur cumulé jamais décrémenté)
    """
    if axis == AchievementAxis.BUYER:
        result = await db.execute(
            select(func.count(UnlockedPrompt.id))
            .where(UnlockedPrompt.current_owner_id == user_id)
        )
        return int(result.scalar() or 0)

    if axis == AchievementAxis.FAN:
        result = await db.execute(
            select(func.count())
            .select_from(OwnedAdn)
            .where(OwnedAdn.user_id == user_id)
        )
        return int(result.scalar() or 0)

    if axis == AchievementAxis.ARTIST:
        user = await db.get(User, user_id)
        if user is None:
            return 0
        return int(user.credits_earned_total or 0)

    return 0  # axis inconnu — pas de crash


# -----------------------------------------------------------------------------
# Check + grant : la fonction hookée dans unlock_*_atomic
# -----------------------------------------------------------------------------

async def check_and_grant_achievements(
    db: AsyncSession,
    *,
    user_id: UUID,
    axis: AchievementAxis,
) -> list[UserAchievement]:
    """
    Pour l'axis demandé : trouve tous les Achievement dont le threshold est
    atteint et qui ne sont PAS encore débloqués par user_id, puis les
    débloque (INSERT UserAchievement + grant BONUS si reward > 0).

    Retourne la liste des UserAchievement nouvellement créés (vide si rien
    de nouveau). Utile pour la réponse API ("vous venez de débloquer X").

    Idempotence : si l'achievement est déjà débloqué, il est exclu via
    LEFT JOIN. Si une race concurrente l'insère pendant qu'on est dedans,
    on catch IntegrityError et on skip.

    Le caller commit. On utilise begin_nested pour isoler chaque grant
    (un grant qui foire ne pollue pas les autres).
    """
    progress = await get_user_progress(db, user_id=user_id, axis=axis)
    if progress <= 0:
        return []

    # Achievements de l'axe, threshold atteint, pas encore débloqués par le user
    q = (
        select(Achievement)
        .outerjoin(
            UserAchievement,
            and_(
                UserAchievement.achievement_id == Achievement.id,
                UserAchievement.user_id == user_id,
            ),
        )
        .where(
            Achievement.axis == axis,
            Achievement.threshold <= progress,
            UserAchievement.id.is_(None),
        )
        .order_by(Achievement.threshold.asc())
    )
    candidates = list((await db.execute(q)).scalars().all())

    newly_unlocked: list[UserAchievement] = []

    for ach in candidates:
        # Savepoint par achievement : si grant_credits foire ou si race
        # IntegrityError, on rollback ce savepoint sans tout casser.
        try:
            async with db.begin_nested():
                ua = UserAchievement(
                    user_id=user_id,
                    achievement_id=ach.id,
                )
                db.add(ua)
                await db.flush()  # déclenche UNIQUE check tôt

                # Grant des crédits BONUS si reward > 0
                if ach.credit_reward > 0:
                    bonus_tx = await grant_credits_atomic(
                        db,
                        user_id=user_id,
                        amount=ach.credit_reward,
                        reason=f"achievement:{ach.code}",
                        tx_type=TransactionType.BONUS,
                        metadata={
                            "achievement_id": str(ach.id),
                            "achievement_code": ach.code,
                        },
                    )
                    ua.bonus_transaction_id = bonus_tx.id
                    await db.flush()

            # Si on arrive ici, le savepoint a commit → l'achievement est
            # définitivement débloqué pour ce user.
            newly_unlocked.append(ua)

        except IntegrityError:
            # Race : un autre process a déjà inséré ce UserAchievement.
            # C'est attendu, on continue avec les autres candidates.
            continue

    return newly_unlocked


# -----------------------------------------------------------------------------
# Lecture : catalog + progression user
# -----------------------------------------------------------------------------

async def list_all_achievements(db: AsyncSession) -> list[Achievement]:
    """Catalog public, ordonné par axis puis threshold puis display_order."""
    q = (
        select(Achievement)
        .order_by(
            Achievement.axis.asc(),
            Achievement.threshold.asc(),
            Achievement.display_order.asc(),
        )
    )
    return list((await db.execute(q)).scalars().all())


async def list_user_achievements_with_progress(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> dict:
    """
    Retourne un dict structuré pour /me/achievements :

      {
        "progress": {"buyer": 12, "fan": 3, "artist": 250},
        "items": [
          {
            "achievement": Achievement,
            "unlocked": True,
            "unlocked_at": datetime | None,
            "bonus_transaction_id": UUID | None,
          },
          ...
        ]
      }

    Charge tout en 4 requêtes (3 progress + 1 LEFT JOIN). Pas optimal pour
    des centaines d'achievements, mais V1 a 13 entries → no-op.
    """
    progress = {
        "buyer": await get_user_progress(
            db, user_id=user_id, axis=AchievementAxis.BUYER
        ),
        "fan": await get_user_progress(
            db, user_id=user_id, axis=AchievementAxis.FAN
        ),
        "artist": await get_user_progress(
            db, user_id=user_id, axis=AchievementAxis.ARTIST
        ),
    }

    # LEFT JOIN : on prend tous les Achievement et on attache UserAchievement
    # si le user l'a débloqué.
    q = (
        select(Achievement, UserAchievement)
        .outerjoin(
            UserAchievement,
            and_(
                UserAchievement.achievement_id == Achievement.id,
                UserAchievement.user_id == user_id,
            ),
        )
        .order_by(
            Achievement.axis.asc(),
            Achievement.threshold.asc(),
            Achievement.display_order.asc(),
        )
    )
    rows = (await db.execute(q)).all()

    items = [
        {
            "achievement": ach,
            "unlocked": ua is not None,
            "unlocked_at": ua.unlocked_at if ua is not None else None,
            "bonus_transaction_id": (
                ua.bonus_transaction_id if ua is not None else None
            ),
        }
        for ach, ua in rows
    ]

    return {"progress": progress, "items": items}
