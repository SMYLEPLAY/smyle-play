"""
Service OFFRES-ADN (chantier 2026-07-03).

Doctrine : tout ADN (playlist / album / visuel) se vend UNIQUEMENT sur
proposition — plus d'achat direct. L'acheteur (sender) fait une offre en
Smyles sur un ADN cible ; le vendeur (receiver = créateur) accepte ou refuse.

Ce module fournit :
  - resolve_adn_target()      : résolution + règles de vendabilité par type
  - accept_adn_offer_atomic() : transfert des fonds au MONTANT DE L'OFFRE
                                (pas au prix affiché, pas de perk pyramide)
                                + livraison (Owned*) + Transaction d'audit.

Calque STRICT des garanties de services/unlocks.py : begin_nested (savepoint),
_acquire_user_locks (ordre trié = pas de deadlock), compute_split, maintien
des sous-soldes Smyles (promo → achetés → gagnés), idempotence via contrainte
UNIQUE (AlreadyOwned).
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.services.unlocks import (
    AdnNotPurchasable,
    AlreadyOwned,
    InsufficientCredits,
    UnlockError,
)

# Types d'ADN vendables sur offre. String en DB (pas d'enum) : ajouter un
# type futur = ajouter une entrée ici, zéro migration.
# profile_adn = ADN profil MUSICAL (table adns, sommet pyramide) — ajouté
# 03/07 sur décision Tom : même règle pour TOUT ADN, sommet inclus.
ADN_TARGET_TYPES = ("playlist_adn", "album_adn", "visual_adn", "profile_adn")


class ReserveNotMet(UnlockError):
    """Offre en dessous du plancher caché fixé par l'artiste."""


@dataclass
class AdnTarget:
    """Snapshot de l'ADN ciblé par une offre."""
    target_type: str
    target_id: UUID
    seller_id: UUID
    title: str
    reserve: int | None       # plancher caché (None = pas de plancher)
    listed_price: int | None  # prix affiché historique (indicatif)


async def resolve_adn_target(db, *, target_type: str, target_id) -> AdnTarget:
    """
    Résout l'ADN ciblé et vérifie qu'il est proposable à l'offre.
    Lève AdnNotPurchasable si introuvable / non vendable.
    """
    if target_type == "playlist_adn":
        from app.models.playlist import Playlist
        row = (await db.execute(
            select(Playlist).where(Playlist.id == target_id)
        )).scalar_one_or_none()
        if row is None or not row.adn_for_sale or row.visibility != "public":
            raise AdnNotPurchasable(
                "ADN playlist introuvable ou non proposé à la vente"
            )
        return AdnTarget(
            target_type=target_type,
            target_id=row.id,
            seller_id=row.owner_id,
            title=row.title,
            reserve=row.adn_reserve_credits,
            listed_price=row.adn_price,
        )

    if target_type == "album_adn":
        from app.models.album import Album
        row = (await db.execute(
            select(Album).where(Album.id == target_id)
        )).scalar_one_or_none()
        if row is None or not row.adn_for_sale or row.visibility != "public":
            raise AdnNotPurchasable(
                "ADN album introuvable ou non proposé à la vente"
            )
        return AdnTarget(
            target_type=target_type,
            target_id=row.id,
            seller_id=row.owner_id,
            title=row.title,
            reserve=row.adn_reserve_credits,
            listed_price=row.adn_price,
        )

    if target_type == "visual_adn":
        from app.models.owned_visual_adn import OwnedVisualAdn
        from app.models.visual_adn import VisualAdn
        row = (await db.execute(
            select(VisualAdn).where(VisualAdn.id == target_id)
        )).scalar_one_or_none()
        if row is None or not row.is_published or row.is_deleted:
            raise AdnNotPurchasable(
                "ADN visuel introuvable ou non proposé à la vente"
            )
        # Stock-out : édition limitée épuisée → plus d'offres possibles.
        if row.max_supply is not None:
            sold = (await db.execute(
                select(func.count(OwnedVisualAdn.visual_adn_id)).where(
                    OwnedVisualAdn.visual_adn_id == target_id
                )
            )).scalar_one()
            if int(sold) >= int(row.max_supply):
                raise AdnNotPurchasable("ADN visuel épuisé (édition limitée)")
        return AdnTarget(
            target_type=target_type,
            target_id=row.id,
            seller_id=row.artist_id,
            title="ADN visuel",
            reserve=row.adn_reserve_credits,
            listed_price=row.price_credits,
        )

    if target_type == "profile_adn":
        from app.models.adn import Adn
        from app.models.owned_adn import OwnedAdn
        row = (await db.execute(
            select(Adn).where(Adn.id == target_id)
        )).scalar_one_or_none()
        if row is None or not row.is_published or row.is_deleted:
            raise AdnNotPurchasable(
                "ADN d'artiste introuvable ou non proposé à la vente"
            )
        # Stock-out : édition limitée épuisée → plus d'offres possibles.
        if row.max_supply is not None:
            sold = (await db.execute(
                select(func.count(OwnedAdn.adn_id)).where(
                    OwnedAdn.adn_id == target_id
                )
            )).scalar_one()
            if int(sold) >= int(row.max_supply):
                raise AdnNotPurchasable("ADN d'artiste épuisé (édition limitée)")
        return AdnTarget(
            target_type=target_type,
            target_id=row.id,
            seller_id=row.artist_id,
            title="ADN d'artiste",
            reserve=row.adn_reserve_credits,
            listed_price=row.price_credits,
        )

    raise AdnNotPurchasable(f"Type d'ADN inconnu : {target_type}")


async def _already_owned(db, *, target_type: str, target_id, buyer_id) -> bool:
    if target_type == "playlist_adn":
        from app.models.owned_playlist_adn import OwnedPlaylistAdn
        q = select(OwnedPlaylistAdn).where(
            OwnedPlaylistAdn.user_id == buyer_id,
            OwnedPlaylistAdn.playlist_id == target_id,
        )
    elif target_type == "album_adn":
        from app.models.owned_album_adn import OwnedAlbumAdn
        q = select(OwnedAlbumAdn).where(
            OwnedAlbumAdn.user_id == buyer_id,
            OwnedAlbumAdn.album_id == target_id,
        )
    elif target_type == "profile_adn":
        from app.models.owned_adn import OwnedAdn
        q = select(OwnedAdn).where(
            OwnedAdn.user_id == buyer_id,
            OwnedAdn.adn_id == target_id,
        )
    else:  # visual_adn
        from app.models.owned_visual_adn import OwnedVisualAdn
        q = select(OwnedVisualAdn).where(
            OwnedVisualAdn.user_id == buyer_id,
            OwnedVisualAdn.visual_adn_id == target_id,
        )
    return (await db.execute(q)).scalar_one_or_none() is not None


def _make_owned(target_type: str, target_id, buyer_id):
    if target_type == "playlist_adn":
        from app.models.owned_playlist_adn import OwnedPlaylistAdn
        return OwnedPlaylistAdn(user_id=buyer_id, playlist_id=target_id)
    if target_type == "album_adn":
        from app.models.owned_album_adn import OwnedAlbumAdn
        return OwnedAlbumAdn(user_id=buyer_id, album_id=target_id)
    if target_type == "profile_adn":
        from app.models.owned_adn import OwnedAdn
        return OwnedAdn(user_id=buyer_id, adn_id=target_id)
    from app.models.owned_visual_adn import OwnedVisualAdn
    return OwnedVisualAdn(user_id=buyer_id, visual_adn_id=target_id)


class _AcceptAdnOfferResult:
    __slots__ = ("owned", "transaction", "paid")

    def __init__(self, owned, transaction, paid: int):
        self.owned = owned
        self.transaction = transaction
        self.paid = paid


async def accept_adn_offer_atomic(db, *, offer) -> _AcceptAdnOfferResult:
    """
    Exécute l'acceptation d'une offre ADN (TradeOffer avec target_type).

    - Re-résout la cible (vendabilité + reserve peuvent avoir changé).
    - Reserve : amount < reserve → ReserveNotMet (refus).
    - Transfert AU MONTANT DE L'OFFRE : compute_split(amount) → part artiste
      + commission plateforme. Aucun perk pyramide (le prix est négocié).
    - Livraison : Owned{Playlist,Album,Visual}Adn (idempotent → AlreadyOwned).
    - Transaction d'audit type UNLOCK, metadata marquée adn_offer.

    Le CALLER gère le statut de l'offre, les notifs et le commit.
    """
    from app.models.transaction import (
        Transaction,
        TransactionStatus,
        TransactionType,
    )
    from app.services.credits import _acquire_user_locks, compute_split

    buyer_id = offer.sender_id
    amount = int(offer.amount_credits or 0)
    if amount < 1:
        raise AdnNotPurchasable("Montant d'offre invalide")

    target = await resolve_adn_target(
        db, target_type=offer.target_type, target_id=offer.target_id
    )

    # Reserve re-vérifié à l'accept (l'artiste a pu la monter entre-temps).
    if target.reserve is not None and amount < int(target.reserve):
        raise ReserveNotMet(
            "Offre en dessous du minimum fixé par l'artiste"
        )

    if await _already_owned(
        db, target_type=target.target_type,
        target_id=target.target_id, buyer_id=buyer_id,
    ):
        raise AlreadyOwned("L'acheteur possède déjà cet ADN")

    async with db.begin_nested():
        await _acquire_user_locks(db, [buyer_id, target.seller_id])

        artist_revenue, platform_fee = compute_split(amount)
        assert artist_revenue + platform_fee == amount

        buyer_row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": buyer_id},
        )).first()
        if buyer_row is None:
            raise AdnNotPurchasable("Acheteur introuvable")
        if int(buyer_row.credits_balance) < amount:
            raise InsufficientCredits(
                required=amount, available=int(buyer_row.credits_balance)
            )

        tx = Transaction(
            type=TransactionType.UNLOCK,
            status=TransactionStatus.PENDING,
            buyer_id=buyer_id,
            seller_id=target.seller_id,
            credits_amount=amount,
            artist_revenue=artist_revenue,
            platform_fee=platform_fee,
            metadata_json={
                "adn_offer": True,
                "offer_id": str(offer.id),
                "target_type": target.target_type,
                "target_id": str(target.target_id),
                "listed_price": target.listed_price,
            },
        )
        db.add(tx)
        await db.flush()

        # Débit acheteur — maintien des sous-soldes (promo → achetés → gagnés)
        await db.execute(
            text(
                "UPDATE users SET smyles_promo = GREATEST(0, smyles_promo - :paid), "
                "smyles_achetes = GREATEST(0, smyles_achetes - GREATEST(0, :paid - smyles_promo)), "
                "smyles_gagnes = GREATEST(0, smyles_gagnes - GREATEST(0, :paid - smyles_promo - smyles_achetes)), "
                "credits_balance = credits_balance - :paid WHERE id = :uid"
            ),
            {"paid": amount, "uid": buyer_id},
        )
        # Crédit vendeur (part artiste)
        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance + :rev, "
                "    smyles_gagnes = smyles_gagnes + :rev, "
                "    credits_earned_total = credits_earned_total + :rev "
                "WHERE id = :uid"
            ),
            {"rev": artist_revenue, "uid": target.seller_id},
        )

        owned = _make_owned(target.target_type, target.target_id, buyer_id)
        db.add(owned)
        try:
            await db.flush()
        except IntegrityError as e:
            raise AlreadyOwned("L'acheteur possède déjà cet ADN") from e

        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    return _AcceptAdnOfferResult(owned=owned, transaction=tx, paid=amount)
