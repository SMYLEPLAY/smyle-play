"""
Achat « œuvre complète » (chantier C5) — bundle atomique des deux ADN de
collection d'une même œuvre (ADN Playlist + ADN Album) en UNE transaction.

  buy_oeuvre_atomic(db, buyer_id=..., slug=...) -> _BuyOeuvreResult

Calque STRICT du flux d'achat ADN (unlock_playlist_adn_atomic /
unlock_album_adn_atomic) : mêmes garanties (lock utilisateurs, compute_split,
débit waterfall smyles_promo→achetes→gagnes, Transaction PENDING→COMPLETED,
idempotence via PK composite des tables Owned*AdN).

Différence : on débloque les DEUX faces ensemble, au prix PACK -15%
(compute_oeuvre_pack_price), avec le perk artiste -30% appliqué par face en
amont. Le perk -20% « ADN collection » ne s'applique pas au pack (perk aval —
cf. compute_oeuvre_pack_price). Les deux faces ayant le MÊME owner (définition
d'une œuvre), tout le revenu va à cet artiste unique.

Conditions : playlist ET album publics, même oeuvre_slug, même owner, tous deux
adn_for_sale avec adn_price. Pré-requis : l'acheteur ne possède DÉJÀ aucune des
deux faces (sinon AlreadyOwned → achète l'autre à l'unité).
"""
from app.services.unlocks import (
    AdnNotPurchasable,
    AlreadyOwned,
    InsufficientCredits,
    SelfPurchaseForbidden,
)


class _BuyOeuvreResult:
    __slots__ = ("paid", "playlist_id", "album_id", "transaction")

    def __init__(self, paid, playlist_id, album_id, transaction):
        self.paid = paid
        self.playlist_id = playlist_id
        self.album_id = album_id
        self.transaction = transaction


async def buy_oeuvre_atomic(db, *, buyer_id, slug: str) -> _BuyOeuvreResult:
    from sqlalchemy import select, text, func
    from sqlalchemy.exc import IntegrityError

    from app.models.album import Album
    from app.models.owned_album_adn import OwnedAlbumAdn
    from app.models.owned_playlist_adn import OwnedPlaylistAdn
    from app.models.playlist import Playlist
    from app.models.transaction import (
        Transaction,
        TransactionStatus,
        TransactionType,
    )
    from app.services.credits import (
        _acquire_user_locks,
        compute_oeuvre_pack_price,
        compute_split,
    )
    from app.services.marketplace import user_owns_artist_adn

    # ── Résolution de l'œuvre : 2 faces publiques, même slug, même owner ────
    playlist = (await db.execute(
        select(Playlist).where(
            Playlist.oeuvre_slug == slug,
            Playlist.visibility == "public",
        ).order_by(Playlist.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    album = (await db.execute(
        select(Album).where(
            Album.oeuvre_slug == slug,
            Album.visibility == "public",
        ).order_by(Album.created_at.asc()).limit(1)
    )).scalar_one_or_none()

    if playlist is None or album is None:
        raise AdnNotPurchasable(
            "Œuvre incomplète — les deux faces (son + visuel) doivent être publiées."
        )
    if album.owner_id != playlist.owner_id:
        # Même slug mais owners différents → ce n'est pas une œuvre unique.
        raise AdnNotPurchasable("Œuvre introuvable.")

    owner_id = playlist.owner_id
    if buyer_id == owner_id:
        raise SelfPurchaseForbidden("Tu ne peux pas acheter ta propre œuvre.")

    # Les deux ADN de collection doivent être en vente.
    if not playlist.adn_for_sale or not playlist.adn_price:
        raise AdnNotPurchasable("L'ADN de la playlist n'est pas en vente.")
    if not album.adn_for_sale or not album.adn_price:
        raise AdnNotPurchasable("L'ADN de l'album n'est pas en vente.")

    # Possession préalable : le pack exige les DEUX faces non possédées.
    owns_pl = (await db.execute(
        select(OwnedPlaylistAdn).where(
            OwnedPlaylistAdn.user_id == buyer_id,
            OwnedPlaylistAdn.playlist_id == playlist.id,
        )
    )).scalar_one_or_none()
    owns_al = (await db.execute(
        select(OwnedAlbumAdn).where(
            OwnedAlbumAdn.user_id == buyer_id,
            OwnedAlbumAdn.album_id == album.id,
        )
    )).scalar_one_or_none()
    if owns_pl is not None or owns_al is not None:
        raise AlreadyOwned(
            "Tu possèdes déjà une face de l'œuvre — achète l'autre à l'unité."
        )

    # Perk artiste -30% (si l'acheteur possède l'ADN profil/visuel de l'owner),
    # appliqué par face PUIS remise pack -15% sur la somme (plancher inclus).
    has_artist_perk = await user_owns_artist_adn(
        db, user_id=buyer_id, artist_id=owner_id
    )
    paid = compute_oeuvre_pack_price(
        [int(playlist.adn_price), int(album.adn_price)], has_artist_perk
    )

    async with db.begin_nested():
        await _acquire_user_locks(db, [buyer_id, owner_id])

        artist_revenue, platform_fee = compute_split(paid)
        assert artist_revenue + platform_fee == paid

        buyer_row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :uid"),
            {"uid": buyer_id},
        )).first()
        if buyer_row is None:
            raise AdnNotPurchasable("Acheteur introuvable")
        if int(buyer_row.credits_balance) < paid:
            raise InsufficientCredits(
                required=paid, available=int(buyer_row.credits_balance)
            )

        tx = Transaction(
            type=TransactionType.UNLOCK,
            status=TransactionStatus.PENDING,
            buyer_id=buyer_id,
            seller_id=owner_id,
            credits_amount=paid,
            artist_revenue=artist_revenue,
            platform_fee=platform_fee,
            metadata_json={
                "kind": "oeuvre_pack",
                "oeuvre_slug": slug,
                "playlist_id": str(playlist.id),
                "album_id": str(album.id),
                "owner_id": str(owner_id),
            },
        )
        db.add(tx)
        await db.flush()

        # Débit acheteur — waterfall promo → achetés → gagnés (miroir ADN unit).
        await db.execute(
            text(
                "UPDATE users SET smyles_promo = GREATEST(0, smyles_promo - :paid), "
                "smyles_achetes = GREATEST(0, smyles_achetes - GREATEST(0, :paid - smyles_promo)), "
                "smyles_gagnes = GREATEST(0, smyles_gagnes - GREATEST(0, :paid - smyles_promo - smyles_achetes)), "
                "credits_balance = credits_balance - :paid WHERE id = :uid"
            ),
            {"paid": paid, "uid": buyer_id},
        )
        # Crédit artiste (revenu primaire).
        await db.execute(
            text(
                "UPDATE users "
                "SET credits_balance = credits_balance + :rev, "
                "    smyles_gagnes = smyles_gagnes + :rev, "
                "    credits_earned_total = credits_earned_total + :rev "
                "WHERE id = :uid"
            ),
            {"rev": artist_revenue, "uid": owner_id},
        )

        # Déblocage des DEUX faces. PK composite → IntegrityError = course/double.
        db.add(OwnedPlaylistAdn(user_id=buyer_id, playlist_id=playlist.id))
        db.add(OwnedAlbumAdn(user_id=buyer_id, album_id=album.id))
        try:
            await db.flush()
        except IntegrityError as e:
            raise AlreadyOwned(
                "Tu possèdes déjà une face de l'œuvre."
            ) from e

        tx.status = TransactionStatus.COMPLETED
        tx.completed_at = func.now()
        await db.flush()

    return _BuyOeuvreResult(
        paid=paid,
        playlist_id=playlist.id,
        album_id=album.id,
        transaction=tx,
    )
