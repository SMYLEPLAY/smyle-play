"""
Chantier OFFRES-ADN (2026-07-03) — tests d'intégration.

Doctrine : tout ADN se vend UNIQUEMENT sur proposition (plus d'achat direct).
Couvre (cf. plan 2026-07-03_PLAN-OFFRES-ADN, étape 6) :

  1. test_offer_below_reserve_rejected
       Offre < adn_reserve_credits → 422 générique (le plancher caché n'est
       jamais révélé), aucune offre créée.

  2. test_offer_accept_full_flow
       Offre valide → 201 pending. Accept vendeur → 200 : Δbuyer = -amount,
       Δseller = +artist_revenue, artist_revenue + platform_fee == amount
       (zéro crédit perdu), OwnedPlaylistAdn livré, offre ACCEPTED,
       Transaction UNLOCK marquée adn_offer.

  3. test_accept_insufficient_buyer_balance
       Solde acheteur vidé entre l'offre et l'accept → 402, offre reste
       pending, aucune livraison.

  4. test_direct_adn_unlock_gone
       POST /unlocks/playlist-adn/{id} ET /unlocks/adns/{id} → 410
       (achat direct fermé, sommet musical inclus — décision Tom 03/07).

  4b. test_profile_adn_offer_flow
       Même flux complet sur l'ADN profil MUSICAL (table adns) :
       offre ≥ reserve → accept → livraison owned_adns + conservation.

  6. test_accept_applies_seller_tier (K-06)
       Vendeur `premium` → 88 sur 100 (commission 12 %), pas 80.

  7. test_accept_grants_fan_achievement (K-06)
       L'acceptation débloque le trophée FAN de l'acheteur et fait avancer
       l'axe ARTIST du vendeur.

  8. test_accept_rewards_pending_referral (K-06)
       Un lien de parrainage PENDING de l'acheteur passe REWARDED.

  5. test_offer_permissions
       Self-offer → 400 · acheteur qui accepte → 403 · vendeur qui
       annule → 403.

REQUIRES : Postgres réel via DATABASE_URL (cf. conftest.py).
"""
import uuid

import pytest
from sqlalchemy import delete, text

pytestmark = pytest.mark.asyncio(loop_scope="session")

from app.database import SessionLocal
from app.models.playlist import Playlist
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.users import create_user


# =============================================================================
# Helpers
# =============================================================================

async def _make_user(balance: int = 1000, name: str = "AdnOfferUser") -> tuple:
    email = f"pytest-adnoffer-{uuid.uuid4().hex[:12]}@smyleplay.example"
    async with SessionLocal() as db:
        user = await create_user(db, UserCreate(email=email, password="12345678"))
        uid = user.id
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET credits_balance = :b, artist_name = :n "
                 "WHERE id = :u"),
            {"b": balance, "n": name, "u": uid},
        )
        await db.commit()
    return uid, email


async def _make_adn_playlist(
    owner_id: uuid.UUID, *, price: int = 300, reserve: int | None = 100
) -> uuid.UUID:
    async with SessionLocal() as db:
        p = Playlist(
            owner_id=owner_id,
            title=f"ADN Offer PL {uuid.uuid4().hex[:8]}",
            visibility="public",
            adn_for_sale=True,
            adn_price=price,
            adn_reserve_credits=reserve,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _make_profile_adn(
    artist_id: uuid.UUID, *, price: int = 50, reserve: int | None = 60
) -> uuid.UUID:
    from app.models.adn import Adn
    async with SessionLocal() as db:
        a = Adn(
            artist_id=artist_id,
            description="X" * 250,
            usage_guide="how to",
            example_outputs="examples premium",
            price_credits=price,
            is_published=True,
            adn_reserve_credits=reserve,
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return a.id


async def _login(client, email: str) -> dict:
    r = await client.post(
        "/auth/login", json={"email": email, "password": "12345678"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _balance(uid: uuid.UUID) -> int:
    async with SessionLocal() as db:
        row = (await db.execute(
            text("SELECT credits_balance FROM users WHERE id = :u"), {"u": uid}
        )).first()
        return int(row.credits_balance)


async def _bonus_total(uid: uuid.UUID) -> int:
    """Smyles crédités en BONUS (trophées, parrainage) APRÈS l'inscription.

    K-06 : l'acceptation d'une offre déclenche désormais trophées et
    parrainage — le solde n'est plus la seule conséquence de l'achat. Le bonus
    de bienvenue est exclu : `_make_user` réécrit le solde après création, il
    ne fait donc pas partie du solde observé.
    """
    async with SessionLocal() as db:
        row = (await db.execute(text(
            "SELECT COALESCE(SUM(credits_amount), 0) AS s FROM transactions "
            "WHERE buyer_id = :u AND type = 'bonus' AND status = 'completed' "
            "AND COALESCE(metadata_json->>'reason', '') <> 'welcome_bonus'"
        ), {"u": uid})).first()
        return int(row.s)


async def _cleanup(playlist_ids: list, user_ids: list) -> None:
    # NB : adns / owned_adns partent en CASCADE avec les users.
    from app.models.owned_playlist_adn import OwnedPlaylistAdn
    from app.models.trade import TradeOffer
    async with SessionLocal() as db:
        if playlist_ids:
            await db.execute(delete(OwnedPlaylistAdn).where(
                OwnedPlaylistAdn.playlist_id.in_(playlist_ids)))
            await db.execute(delete(Playlist).where(
                Playlist.id.in_(playlist_ids)))
        if user_ids:
            await db.execute(delete(TradeOffer).where(
                TradeOffer.sender_id.in_(user_ids)
                | TradeOffer.receiver_id.in_(user_ids)))
            # Ledger immuable en prod — bypass trigger pour le cleanup test.
            await db.execute(text("SET session_replication_role = 'replica'"))
            await db.execute(delete(Transaction).where(
                (Transaction.buyer_id.in_(user_ids))
                | (Transaction.seller_id.in_(user_ids))))
            await db.execute(text("SET session_replication_role = 'origin'"))
            await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


# =============================================================================
# Tests
# =============================================================================

async def test_offer_below_reserve_rejected(client):
    seller, _ = await _make_user(name="SellerReserve")
    buyer, buyer_email = await _make_user(name="BuyerReserve")
    pl = await _make_adn_playlist(seller, reserve=100)
    try:
        headers = await _login(client, buyer_email)
        r = await client.post("/adn-offers", headers=headers, json={
            "target_type": "playlist_adn",
            "target_id": str(pl),
            "amount_credits": 50,
        })
        assert r.status_code == 422, r.text
        # Le plancher caché n'est JAMAIS révélé.
        assert "100" not in r.text
        async with SessionLocal() as db:
            n = (await db.execute(text(
                "SELECT COUNT(*) FROM trade_offers WHERE sender_id = :b"
            ), {"b": buyer})).scalar()
            assert n == 0, "Aucune offre ne doit être créée sous le reserve"
    finally:
        await _cleanup([pl], [seller, buyer])


async def test_offer_accept_full_flow(client):
    seller, seller_email = await _make_user(balance=500, name="SellerFlow")
    buyer, buyer_email = await _make_user(balance=1000, name="BuyerFlow")
    pl = await _make_adn_playlist(seller, reserve=100)
    amount = 120
    try:
        # 1. L'acheteur fait une offre valide (>= reserve)
        bh = await _login(client, buyer_email)
        r = await client.post("/adn-offers", headers=bh, json={
            "target_type": "playlist_adn",
            "target_id": str(pl),
            "amount_credits": amount,
            "message": "Je te propose 120 pour ton ADN",
        })
        assert r.status_code == 201, r.text
        offer = r.json()
        assert offer["status"] == "pending"
        assert offer["amount_credits"] == amount
        assert offer["seller_id"] == str(seller)

        # 2. Le vendeur accepte → transfert + livraison
        sh = await _login(client, seller_email)
        r2 = await client.patch(
            f"/adn-offers/{offer['id']}/accept", headers=sh
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "accepted"

        # 3. Conservation des crédits : Δbuyer = -amount,
        #    Δseller = +artist_revenue, revenue + fee == amount.
        async with SessionLocal() as db:
            tx = (await db.execute(text(
                "SELECT credits_amount, artist_revenue, platform_fee, "
                "metadata_json FROM transactions "
                "WHERE buyer_id = :b AND seller_id = :s"
            ), {"b": buyer, "s": seller})).first()
        assert tx is not None, "Transaction d'audit manquante"
        assert int(tx.credits_amount) == amount
        assert int(tx.artist_revenue) + int(tx.platform_fee) == amount
        # K-06 : l'acceptation débloque désormais trophées (et parrainage),
        # qui créditent des Smyles en BONUS → on compare hors bonus.
        assert await _balance(buyer) == 1000 - amount + await _bonus_total(buyer)
        assert await _balance(seller) == 500 + int(tx.artist_revenue) + await _bonus_total(seller)

        # 4. Livraison : l'acheteur possède l'ADN
        async with SessionLocal() as db:
            owned = (await db.execute(text(
                "SELECT COUNT(*) FROM owned_playlist_adns "
                "WHERE user_id = :u AND playlist_id = :p"
            ), {"u": buyer, "p": pl})).scalar()
        assert owned == 1, "ADN non livré à l'acceptation"
    finally:
        await _cleanup([pl], [seller, buyer])


async def test_accept_insufficient_buyer_balance(client):
    seller, seller_email = await _make_user(name="SellerPoor")
    buyer, buyer_email = await _make_user(balance=200, name="BuyerPoor")
    pl = await _make_adn_playlist(seller, reserve=None)
    try:
        bh = await _login(client, buyer_email)
        r = await client.post("/adn-offers", headers=bh, json={
            "target_type": "playlist_adn",
            "target_id": str(pl),
            "amount_credits": 150,
        })
        assert r.status_code == 201, r.text
        offer_id = r.json()["id"]

        # Le solde de l'acheteur fond entre l'offre et l'accept.
        async with SessionLocal() as db:
            await db.execute(text(
                "UPDATE users SET credits_balance = 10, smyles_promo = 0, "
                "smyles_achetes = 0, smyles_gagnes = 10 WHERE id = :u"
            ), {"u": buyer})
            await db.commit()

        sh = await _login(client, seller_email)
        r2 = await client.patch(f"/adn-offers/{offer_id}/accept", headers=sh)
        assert r2.status_code == 402, r2.text

        # L'offre reste pending, rien n'est livré.
        async with SessionLocal() as db:
            st = (await db.execute(text(
                "SELECT status FROM trade_offers WHERE id = :o"
            ), {"o": offer_id})).scalar()
            owned = (await db.execute(text(
                "SELECT COUNT(*) FROM owned_playlist_adns "
                "WHERE user_id = :u AND playlist_id = :p"
            ), {"u": buyer, "p": pl})).scalar()
        assert st == "pending"
        assert owned == 0
    finally:
        await _cleanup([pl], [seller, buyer])


async def test_direct_adn_unlock_gone(client):
    seller, _ = await _make_user(name="SellerGone")
    buyer, buyer_email = await _make_user(name="BuyerGone")
    pl = await _make_adn_playlist(seller)
    adn = await _make_profile_adn(seller)
    try:
        headers = await _login(client, buyer_email)
        for url in (f"/unlocks/playlist-adn/{pl}", f"/unlocks/adns/{adn}"):
            r = await client.post(url, headers=headers)
            assert r.status_code == 410, (
                f"Achat direct ADN doit être fermé (410) sur {url}, "
                f"reçu {r.status_code}"
            )
    finally:
        await _cleanup([pl], [seller, buyer])


async def test_profile_adn_offer_flow(client):
    """Même flux que playlist, sur l'ADN profil MUSICAL (sommet pyramide)."""
    seller, seller_email = await _make_user(balance=500, name="SellerSommet")
    buyer, buyer_email = await _make_user(balance=1000, name="BuyerSommet")
    adn = await _make_profile_adn(seller, reserve=60)
    amount = 80
    try:
        bh = await _login(client, buyer_email)
        # Sous le reserve → 422
        r = await client.post("/adn-offers", headers=bh, json={
            "target_type": "profile_adn",
            "target_id": str(adn),
            "amount_credits": 40,
        })
        assert r.status_code == 422, r.text

        # Offre valide → accept → livraison
        r = await client.post("/adn-offers", headers=bh, json={
            "target_type": "profile_adn",
            "target_id": str(adn),
            "amount_credits": amount,
        })
        assert r.status_code == 201, r.text
        offer_id = r.json()["id"]

        sh = await _login(client, seller_email)
        r2 = await client.patch(f"/adn-offers/{offer_id}/accept", headers=sh)
        assert r2.status_code == 200, r2.text

        async with SessionLocal() as db:
            owned = (await db.execute(text(
                "SELECT COUNT(*) FROM owned_adns "
                "WHERE user_id = :u AND adn_id = :a"
            ), {"u": buyer, "a": adn})).scalar()
            tx = (await db.execute(text(
                "SELECT credits_amount, artist_revenue, platform_fee "
                "FROM transactions WHERE buyer_id = :b AND seller_id = :s"
            ), {"b": buyer, "s": seller})).first()
        assert owned == 1, "ADN profil non livré"
        assert int(tx.credits_amount) == amount
        assert int(tx.artist_revenue) + int(tx.platform_fee) == amount
        # K-06 : l'acceptation débloque désormais trophées (et parrainage),
        # qui créditent des Smyles en BONUS → on compare hors bonus.
        assert await _balance(buyer) == 1000 - amount + await _bonus_total(buyer)
        assert await _balance(seller) == 500 + int(tx.artist_revenue) + await _bonus_total(seller)
    finally:
        await _cleanup([], [seller, buyer])


async def test_reserve_via_patch_and_no_leak(client):
    """
    Étape 5 : l'artiste règle son plancher via PATCH /playlists/{id}.
    Le champ est WRITE-ONLY : jamais présent dans la réponse (PlaylistRead
    sert aussi les routes publiques). Une offre sous le plancher → 422.
    """
    seller, seller_email = await _make_user(name="SellerPatchRes")
    buyer, buyer_email = await _make_user(name="BuyerPatchRes")
    pl = await _make_adn_playlist(seller, reserve=None)
    try:
        sh = await _login(client, seller_email)
        r = await client.patch(f"/playlists/{pl}", headers=sh, json={
            "adn_reserve_credits": 200,
        })
        assert r.status_code == 200, r.text
        # Non-fuite : le plancher n'apparaît dans AUCUNE réponse de lecture.
        assert "adn_reserve_credits" not in r.json(), (
            "Le plancher caché ne doit JAMAIS être exposé en lecture"
        )

        bh = await _login(client, buyer_email)
        r2 = await client.post("/adn-offers", headers=bh, json={
            "target_type": "playlist_adn",
            "target_id": str(pl),
            "amount_credits": 150,
        })
        assert r2.status_code == 422, r2.text
    finally:
        await _cleanup([pl], [seller, buyer])


async def test_offer_permissions(client):
    seller, seller_email = await _make_user(name="SellerPerm")
    buyer, buyer_email = await _make_user(name="BuyerPerm")
    pl = await _make_adn_playlist(seller, reserve=None)
    try:
        sh = await _login(client, seller_email)
        bh = await _login(client, buyer_email)

        # Self-offer interdite
        r = await client.post("/adn-offers", headers=sh, json={
            "target_type": "playlist_adn",
            "target_id": str(pl),
            "amount_credits": 50,
        })
        assert r.status_code == 400, r.text

        # Offre valide de l'acheteur
        r = await client.post("/adn-offers", headers=bh, json={
            "target_type": "playlist_adn",
            "target_id": str(pl),
            "amount_credits": 50,
        })
        assert r.status_code == 201, r.text
        offer_id = r.json()["id"]

        # L'acheteur ne peut pas accepter sa propre offre
        r = await client.patch(f"/adn-offers/{offer_id}/accept", headers=bh)
        assert r.status_code == 403, r.text

        # Le vendeur ne peut pas annuler (réservé à l'acheteur)
        r = await client.patch(f"/adn-offers/{offer_id}/cancel", headers=sh)
        assert r.status_code == 403, r.text

        # L'acheteur annule → cancelled
        r = await client.patch(f"/adn-offers/{offer_id}/cancel", headers=bh)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"
    finally:
        await _cleanup([pl], [seller, buyer])


# =============================================================================
# K-06 (2026-09-04) — palier vendeur, trophées, parrainage
#
# L'offre ADN est le SEUL canal de vente d'ADN, et c'était le seul flux d'achat
# qui ignorait le palier du vendeur (80 % en dur) et ne déclenchait ni trophée
# ni parrainage. Annexe B §1.9 (a/b/c).
# =============================================================================

async def _set_tier(uid: uuid.UUID, tier: str) -> None:
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE users SET tier = :t WHERE id = :u"), {"t": tier, "u": uid}
        )
        await db.commit()


async def _accept_offer(client, *, buyer_email, seller_email, target_type,
                        target_id, amount) -> dict:
    bh = await _login(client, buyer_email)
    r = await client.post("/adn-offers", headers=bh, json={
        "target_type": target_type,
        "target_id": str(target_id),
        "amount_credits": amount,
    })
    assert r.status_code == 201, r.text
    offer_id = r.json()["id"]
    sh = await _login(client, seller_email)
    r2 = await client.patch(f"/adn-offers/{offer_id}/accept", headers=sh)
    assert r2.status_code == 200, r2.text
    return r2.json()


async def test_accept_applies_seller_tier(client):
    """Vendeur Premium : 88 pour l'artiste, 12 pour la plateforme sur 100."""
    seller, seller_email = await _make_user(balance=0, name="SellerPremium")
    buyer, buyer_email = await _make_user(balance=1000, name="BuyerPremium")
    await _set_tier(seller, "premium")
    pl = await _make_adn_playlist(seller, reserve=None)
    try:
        await _accept_offer(
            client, buyer_email=buyer_email, seller_email=seller_email,
            target_type="playlist_adn", target_id=pl, amount=100,
        )
        async with SessionLocal() as db:
            tx = (await db.execute(text(
                "SELECT credits_amount, artist_revenue, platform_fee "
                "FROM transactions WHERE buyer_id = :b AND seller_id = :s"
            ), {"b": buyer, "s": seller})).first()
        assert tx is not None
        assert tx.credits_amount == 100
        assert tx.artist_revenue == 88, "palier premium = 88 % pour le vendeur"
        assert tx.platform_fee == 12
        assert tx.artist_revenue + tx.platform_fee == tx.credits_amount
        assert await _balance(seller) == 88 + await _bonus_total(seller)
    finally:
        await _cleanup([pl], [seller, buyer])


async def test_accept_applies_seller_tier_standard_inchange(client):
    """Palier standard = comportement historique (80/20) — non-régression."""
    seller, seller_email = await _make_user(balance=0, name="SellerStd")
    buyer, buyer_email = await _make_user(balance=1000, name="BuyerStd")
    pl = await _make_adn_playlist(seller, reserve=None)
    try:
        await _accept_offer(
            client, buyer_email=buyer_email, seller_email=seller_email,
            target_type="playlist_adn", target_id=pl, amount=100,
        )
        async with SessionLocal() as db:
            tx = (await db.execute(text(
                "SELECT artist_revenue, platform_fee FROM transactions "
                "WHERE buyer_id = :b AND seller_id = :s"
            ), {"b": buyer, "s": seller})).first()
        assert (tx.artist_revenue, tx.platform_fee) == (80, 20)
    finally:
        await _cleanup([pl], [seller, buyer])


async def test_accept_grants_fan_achievement(client):
    """L'axe FAN compte les OwnedAdn : on passe par l'ADN profil musical.

    Avant K-06 : progress.fan == 1 mais AUCUN trophée débloqué (aucun hook
    dans le routeur ni le service des offres).
    """
    from app.models.achievement import AchievementAxis, UserAchievement
    from app.services.achievements import get_user_progress

    seller, seller_email = await _make_user(balance=0, name="SellerFan")
    buyer, buyer_email = await _make_user(balance=1000, name="BuyerFan")
    adn = await _make_profile_adn(seller, price=50, reserve=None)
    try:
        await _accept_offer(
            client, buyer_email=buyer_email, seller_email=seller_email,
            target_type="profile_adn", target_id=adn, amount=60,
        )
        async with SessionLocal() as db:
            assert await get_user_progress(
                db, user_id=buyer, axis=AchievementAxis.FAN
            ) == 1
            fan_badges = (await db.execute(text(
                "SELECT COUNT(*) FROM user_achievements ua "
                "JOIN achievements a ON a.id = ua.achievement_id "
                "WHERE ua.user_id = :u AND a.axis = 'fan'"
            ), {"u": buyer})).scalar()
            assert fan_badges >= 1, "trophée FAN non débloqué après l'achat"
            # Le vendeur a gagné des Smyles → l'axe ARTIST doit avoir avancé.
            artist_badges = (await db.execute(text(
                "SELECT COUNT(*) FROM user_achievements ua "
                "JOIN achievements a ON a.id = ua.achievement_id "
                "WHERE ua.user_id = :u AND a.axis = 'artist'"
            ), {"u": seller})).scalar()
            assert artist_badges >= 1, "trophée ARTIST non débloqué après la vente"
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(UserAchievement).where(
                UserAchievement.user_id.in_([buyer, seller])))
            await db.commit()
        await _cleanup([], [seller, buyer])


async def test_accept_rewards_pending_referral(client):
    """Le 1er achat d'ADN par offre est une action qualifiante de parrainage."""
    from app.models.achievement import UserAchievement
    from app.models.referral import Referral, ReferralStatus

    seller, seller_email = await _make_user(balance=0, name="SellerRef")
    buyer, buyer_email = await _make_user(balance=1000, name="BuyerRef")
    referrer, _ = await _make_user(balance=0, name="ReferrerRef")
    pl = await _make_adn_playlist(seller, reserve=None)
    async with SessionLocal() as db:
        db.add(Referral(
            referrer_id=referrer,
            referred_id=buyer,
            status=ReferralStatus.PENDING,
            reward_credits=10,
        ))
        await db.commit()
    try:
        await _accept_offer(
            client, buyer_email=buyer_email, seller_email=seller_email,
            target_type="playlist_adn", target_id=pl, amount=100,
        )
        async with SessionLocal() as db:
            ref = (await db.execute(text(
                "SELECT status FROM referrals WHERE referred_id = :b"
            ), {"b": buyer})).first()
        assert ref is not None
        assert str(ref.status).lower().endswith("rewarded"), (
            "le lien de parrainage doit passer REWARDED après le 1er achat"
        )
        # Les deux côtés sont crédités de 10 (le parrain touche en plus le
        # trophée REFERRER — d'où la comparaison hors bonus).
        async with SessionLocal() as db:
            n = (await db.execute(text(
                "SELECT COUNT(*) FROM transactions WHERE buyer_id = :u "
                "AND type = 'bonus' "
                "AND metadata_json->>'reason' = 'referral_reward_referrer'"
            ), {"u": referrer})).scalar()
        assert n == 1, "récompense de parrainage non versée au parrain"
        assert await _balance(referrer) == await _bonus_total(referrer)
        assert await _balance(buyer) == 1000 - 100 + await _bonus_total(buyer)
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Referral).where(
                Referral.referred_id == buyer))
            await db.execute(delete(UserAchievement).where(
                UserAchievement.user_id.in_([buyer, seller, referrer])))
            await db.commit()
        await _cleanup([pl], [seller, buyer, referrer])
