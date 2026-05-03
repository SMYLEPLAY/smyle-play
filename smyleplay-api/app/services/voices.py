"""
Services voices — CRUD + unlock atomic (P1-F9 backend).

Le pattern `unlock_voice_atomic` est calqué sur `unlock_adn_atomic` :
  - Pas de perk applicable (le perk -30% est réservé aux prompts pour les
    détenteurs d'ADN, pas extensible aux voix).
  - Lock buyer + seller dans l'ordre UUID croissant (anti-deadlock).
  - INSERT Transaction PENDING → débit buyer → crédit seller → INSERT
    OwnedVoice → COMPLETED Transaction.
  - IntegrityError sur OwnedVoice = double-unlock concurrent → AlreadyOwned.

Hook achievements : axis FAN pour le buyer (collection), ARTIST pour le
seller (revenus). Cohérent avec ADN (les voix sont aussi un asset de
collection/possession, pas une "consommation" comme le prompt).

Voir docstring de `app.services.unlocks` pour le pattern atomique détaillé.
"""
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.owned_adn import OwnedAdn  # noqa: F401  (réservé pour future relation)
from app.models.transaction import (
    Transaction,
    TransactionStatus,
    TransactionType,
)
from app.models.voice import OwnedVoice, Voice
from app.services.credits import _acquire_user_locks, compute_split
from app.services.unlocks import (
    AlreadyOwned,
    InsufficientCredits,
    SelfPurchaseForbidden,
    UnlockError,
)


# -----------------------------------------------------------------------------
# Exception métier dédiée voix (alignée sur le pattern ADN/Prompt).
# -----------------------------------------------------------------------------

class VoiceNotPurchasable(UnlockError):
    """Voix introuvable ou non publiée. → HTTP 404."""


# -----------------------------------------------------------------------------
# Result tuple pour le router
# -----------------------------------------------------------------------------

class _UnlockVoiceResult:
    __slots__ = ("owned_voice", "transaction", "paid", "sample_url")

    def __init__(
        self,
        owned_voice: OwnedVoice,
        transaction: Transaction,
        paid: int,
        sample_url: str,
    ):
        self.owned_voice = owned_voice
        self.transaction = transaction
        self.paid = paid
        self.sample_url = sample_url


# -----------------------------------------------------------------------------
# UNLOCK VOICE
# -----------------------------------------------------------------------------

async def unlock_voice_atomic(
    db: AsyncSession,
    *,
    buyer_id: UUID,
    voice_id: UUID,
) -> _UnlockVoiceResult:
    """
    Achète une voix. Mêmes invariants que unlock_adn_atomic (pas de perk).

    Étapes (savepoint, le caller commit en sortie) :
      1. SELECT voice (sans lock — info de routage)
      2. Refus self-purchase (early)
      3. Acquire locks ordonnés sur (buyer, artist)
      4. SELECT balance buyer (lockée), check suffisance
      5. INSERT Transaction PENDING
      6. UPDATE buyer balance -= paid
      7. UPDATE seller balance += artist_revenue + earned_total += rev
      8. INSERT OwnedVoice → IntegrityError → AlreadyOwned
      9. UPDATE Transaction COMPLETED
    """
    voice_row = (await db.execute(
        select(Voice).where(Voice.id == voice_id)
    )).scalar_one_or_none()
    if voice_row is None or not voice_row.is_published:
        raise VoiceNotPurchasable("Voice not found or not published")

    artist_id = voice_row.artist_id
    paid = voice_row.price_credits
    sample_url = voice_row.sample_url

    if buyer_id == artist_id:
        raise SelfPurchaseForbidden(
            "An artist cannot unlock their own voice"
        )

    async with db.begin_nested():
        await _acquire_user_locks(db, [buyer_id, artist_id])

        artist_revenue, platform_fee = compute_split(paid)
        assert artist_revenue + platform_fee == paid

        buyer_row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": buyer_id},
        )).first()
        if buyer_row is None:
            raise VoiceNotPurchasable("Buyer not found")
        buyer_balance = int(buyer_row.credits_balance)
        if buyer_balance < paid:
            raise InsufficientCredits(required=paid, available=buyer_balance)

        tx = Transaction(
            type=TransactionType.UNLOCK,
            status=TransactionStatus.PENDING,
            buyer_id=buyer_id,
            seller_id=artist_id,
            credits_amount=paid,
            artist_revenue=artist_revenue,
            platform_fee=platform_fee,
            metadata_json={
                "voice_id": str(voice_id),
                "artist_id": str(artist_id),
                # On fige la licence au moment de l'achat — si l'artiste
                # change la licence après coup sur la fiche, l'acheteur
                # garde la licence d'origine.
                "license": voice_row.license,
            },
        )
        db.add(tx)
        await db.flush()

        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance - :paid "
                "WHERE id = :uid"
            ),
            {"paid": paid, "uid": buyer_id},
        )
        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance + :rev, "
                "    credits_earned_total = credits_earned_total + :rev "
                "WHERE id = :uid"
            ),
            {"rev": artist_revenue, "uid": artist_id},
        )

        owned = OwnedVoice(user_id=buyer_id, voice_id=voice_id)
        db.add(owned)
        try:
            await db.flush()
        except IntegrityError as e:
            raise AlreadyOwned("You already own this voice") from e

        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    # Hook achievements (hors savepoint principal). FAN buyer / ARTIST seller.
    # Import local pour éviter un cycle services.voices ↔ services.achievements.
    from app.models.achievement import AchievementAxis
    from app.services.achievements import check_and_grant_achievements
    await check_and_grant_achievements(
        db, user_id=buyer_id, axis=AchievementAxis.FAN
    )
    await check_and_grant_achievements(
        db, user_id=artist_id, axis=AchievementAxis.ARTIST
    )

    return _UnlockVoiceResult(
        owned_voice=owned,
        transaction=tx,
        paid=paid,
        sample_url=sample_url,
    )


# -----------------------------------------------------------------------------
# Helpers CRUD — appelés depuis le router voices.py
# -----------------------------------------------------------------------------

async def user_owns_voice(
    db: AsyncSession, *, user_id: UUID, voice_id: UUID
) -> bool:
    """Vrai ssi l'user a déjà unlocké cette voix. Lookup PK composite."""
    row = (await db.execute(
        select(OwnedVoice).where(
            OwnedVoice.user_id == user_id,
            OwnedVoice.voice_id == voice_id,
        )
    )).scalar_one_or_none()
    return row is not None


async def list_voices_for_artist(
    db: AsyncSession, *, artist_id: UUID, only_published: bool
) -> list[Voice]:
    """
    Liste les voix d'un artiste.

    - `only_published=True` pour la vue publique /u/<slug> (visiteurs).
    - `only_published=False` pour la vue propriétaire /api/voices/me
      (l'artiste doit voir aussi ses brouillons).

    Tri : publiées en tête puis brouillons, ordre de création desc.
    """
    stmt = select(Voice).where(Voice.artist_id == artist_id)
    if only_published:
        stmt = stmt.where(Voice.is_published.is_(True))
    stmt = stmt.order_by(Voice.is_published.desc(), Voice.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_voices_owned_by(
    db: AsyncSession, *, user_id: UUID
) -> list[Voice]:
    """
    Liste les voix unlockées par un user (pour /library).
    JOIN explicite owned_voices ↔ voices_for_sale.
    """
    stmt = (
        select(Voice)
        .join(OwnedVoice, OwnedVoice.voice_id == Voice.id)
        .where(OwnedVoice.user_id == user_id)
        .order_by(OwnedVoice.owned_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())
