"""
Suppression de compte RGPD (pack légal v1, 2026-06-10 — complétée au Lot D).

Principe : on EFFACE tout ce qui n'appartient qu'au compte, et on ANONYMISE ce
que d'autres personnes ont payé ou que la loi oblige à garder.

1. EFFACÉ (immédiatement, dans une seule transaction)
   - les œuvres que PERSONNE n'a achetées : sons, recettes, images, ADN, ADN
     visuels, voix, playlists, albums (lignes supprimées, avec leurs likes,
     galeries, empreintes et statistiques d'écoute) ;
   - les abonnements (dans les deux sens), les notifications, les
     statistiques personnelles (téléchargements, jours d'activité, trophées,
     likes), les jetons d'email ;
   - l'IP d'inscription et tous les champs de profil ;
   - les fichiers stockés de ces œuvres et du profil (avatar, bannière,
     extraits de voix, vidéos de playlist) : inscrits dans la table
     `fichiers_a_traiter` DANS la transaction de la suppression (Lot G), puis
     supprimés après la réponse, et seulement s'ils ne sont plus référencés
     par aucune ligne restante. Une purge interrompue (redémarrage, stockage
     indisponible) est rejouée chaque jour.

2. ANONYMISÉ (conservé)
   - les œuvres DÉJÀ ACHETÉES par quelqu'un d'autre : la ligne et le fichier
     restent (l'acheteur garde son exemplaire), l'œuvre est retirée du public,
     et son auteur devient « Artiste supprimé ». Pourquoi ne pas les
     supprimer : l'acheteur a payé un accès durable (CGU, licence) ; effacer
     l'œuvre lui retirerait ce qu'il a payé et casserait la numérotation des
     exemplaires (#X/N). Une fois le compte anonymisé, l'œuvre ne porte plus
     aucune donnée personnelle de l'auteur.
   - les contenus RETIRÉS par la modération : conservés comme preuve (DSA).
   - les conversations (Lot G) : l'autre personne garde son historique ; les
     messages du compte supprimé restent, signés « Artiste supprimé » (la
     ligne `users` anonymisée ne porte plus ni email ni nom).
   - le registre des transactions (obligation comptable) : intact. Ses lignes
     pointent vers la ligne `users` anonymisée (plus d'email, de nom, d'IP) :
     le lien ne désigne plus personne.
   - les achats du compte (exemplaires, ADN possédés), les paiements par carte
     et les parrainages : conservés pour l'intégrité des numérotations et de la
     comptabilité, rattachés au compte anonymisé.

3. Smyles : TOUS perdus (achetés, offerts ET gagnés en vendant). Le solde est
   détruit par une transaction BURN tracée au registre (la masse en
   circulation reste réconciliée). L'utilisateur y renonce explicitement
   (case + saisie de « SUPPRIMER », vérifiées par le serveur).

4. Rang Pionnier : libéré (et remis au créateur suivant, comme une révocation).

5. Déconnexion immédiate : l'email anonymisé ne correspond plus à aucun jeton,
   le mot de passe « ! » ne correspond à aucun hash, `token_version` augmente.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

DELETED_EMAIL_SUFFIX = "@deleted.watt"

# Œuvres « conservées » : achetées par un autre compte, ou retirées par la
# modération (preuve). Une requête par type ; `:u` = id du compte supprimé.
_SQL_GARDES = {
    "prompts": (
        "SELECT p.id FROM prompts p WHERE p.artist_id = :u AND ("
        " p.taken_down_at IS NOT NULL OR EXISTS (SELECT 1 FROM unlocked_prompts up"
        "  WHERE up.prompt_id = p.id AND up.current_owner_id <> :u))"
    ),
    "adns": (
        "SELECT a.id FROM adns a WHERE a.artist_id = :u AND ("
        " a.taken_down_at IS NOT NULL OR EXISTS (SELECT 1 FROM owned_adns o"
        "  WHERE o.adn_id = a.id AND o.user_id <> :u))"
    ),
    "visual_adns": (
        "SELECT a.id FROM visual_adns a WHERE a.artist_id = :u AND ("
        " a.taken_down_at IS NOT NULL OR EXISTS (SELECT 1 FROM owned_visual_adns o"
        "  WHERE o.visual_adn_id = a.id AND o.user_id <> :u))"
    ),
    "voices_for_sale": (
        "SELECT v.id FROM voices_for_sale v WHERE v.artist_id = :u AND ("
        " v.taken_down_at IS NOT NULL OR EXISTS (SELECT 1 FROM owned_voices o"
        "  WHERE o.voice_id = v.id AND o.user_id <> :u))"
    ),
    "playlists": (
        "SELECT p.id FROM playlists p WHERE p.owner_id = :u AND ("
        " p.taken_down_at IS NOT NULL OR EXISTS (SELECT 1 FROM owned_playlist_adns o"
        "  WHERE o.playlist_id = p.id AND o.user_id <> :u))"
    ),
    "albums": (
        "SELECT a.id FROM albums a WHERE a.owner_id = :u AND ("
        " a.taken_down_at IS NOT NULL OR EXISTS (SELECT 1 FROM owned_album_adns o"
        "  WHERE o.album_id = a.id AND o.user_id <> :u))"
    ),
}

# Un son est conservé s'il a été retiré par la modération, ou s'il porte une
# recette / un beat / une image / une voix achetés (l'acheteur l'écoute).
_SQL_SONS_GARDES = (
    "SELECT t.id FROM tracks t WHERE t.artist_id = :u AND ("
    " t.taken_down_at IS NOT NULL"
    " OR t.prompt_id = ANY(:pg) OR t.beat_id = ANY(:pg)"
    " OR EXISTS (SELECT 1 FROM prompts p WHERE p.linked_track_id = t.id AND p.id = ANY(:pg))"
    " OR EXISTS (SELECT 1 FROM voices_for_sale v WHERE v.linked_track_id = t.id AND v.id = ANY(:vg)))"
)

_OWNER_COL = {"playlists": "owner_id", "albums": "owner_id"}


async def _ids(db: AsyncSession, sql: str, **params) -> list[uuid.UUID]:
    return [r[0] for r in (await db.execute(text(sql), params)).all()]


async def _oeuvres_gardees(db: AsyncSession, uid: uuid.UUID) -> dict[str, list[uuid.UUID]]:
    gardes = {t: await _ids(db, sql, u=uid) for t, sql in _SQL_GARDES.items()}
    gardes["tracks"] = await _ids(
        db, _SQL_SONS_GARDES, u=uid, pg=gardes["prompts"], vg=gardes["voices_for_sale"]
    )
    return gardes


def _cle_du_compte(key: str | None, uid, *, voix: bool = False) -> bool:
    """La clé désigne-t-elle un fichier envoyé par CE compte ? Dossiers au
    nom du compte (sons, images, vidéos de playlist `PLAYLISTS/<id>/`), et —
    seulement pour les URL lues sur SES voix — le dossier commun `voices/`
    (les extraits de voix n'ont pas de dossier par compte)."""
    from app.services.media_ownership import cle_sure, key_owned_by

    if not cle_sure(key):
        return False
    if key_owned_by(key, uid):
        return True
    parts = key.split("/")
    if len(parts) == 3 and parts[0] == "PLAYLISTS" and parts[1].lower() == str(uid).lower():
        return True
    return voix and len(parts) == 2 and parts[0] == "voices"


def _cles_depuis_urls(urls, uid, *, voix: bool = False) -> set[str]:
    """Clés de stockage désignées par des URL (avatar, pochettes, extraits…),
    limitées aux fichiers envoyés par CE compte."""
    from app.services.media_ownership import media_url_key

    out: set[str] = set()
    for url in urls:
        ours, key = media_url_key(url)
        if ours and key and _cle_du_compte(key, uid, voix=voix):
            out.add(key)
    return out


async def _cles_a_purger(db: AsyncSession, uid: uuid.UUID, gardes: dict) -> set[str]:
    """Fichiers des œuvres qui vont être effacées + avatar et bannière.
    Collecté AVANT les suppressions."""
    from app.services.media_ownership import key_owned_by

    cles: set[str] = set()
    urls: list[str | None] = []
    p = {"u": uid}

    rows = (await db.execute(text(
        "SELECT r2_key, audio_url, cover_url FROM tracks "
        "WHERE artist_id = :u AND NOT (id = ANY(:g))"), {**p, "g": gardes["tracks"]})).all()
    for r in rows:
        if r.r2_key and key_owned_by(r.r2_key, uid):
            cles.add(r.r2_key)
        urls += [r.audio_url, r.cover_url]

    rows = (await db.execute(text(
        "SELECT id, image_r2_key, preview_r2_key FROM prompts "
        "WHERE artist_id = :u AND NOT (id = ANY(:g))"), {**p, "g": gardes["prompts"]})).all()
    produits = [r.id for r in rows]
    for r in rows:
        # Clés d'images produits : générées par le serveur pour CE produit
        # (originals / previews), jamais partagées hors des lignes en base.
        cles.update(k for k in (r.image_r2_key, r.preview_r2_key) if k)
    if produits:
        for r in (await db.execute(text(
            "SELECT image_r2_key, preview_r2_key FROM prompt_gallery_images "
            "WHERE prompt_id = ANY(:ids)"), {"ids": produits})).all():
            cles.update(k for k in (r.image_r2_key, r.preview_r2_key) if k)

    urls_voix: list[str | None] = []
    for r in (await db.execute(text(
        "SELECT sample_url, preview_url FROM voices_for_sale "
        "WHERE artist_id = :u AND NOT (id = ANY(:g))"), {**p, "g": gardes["voices_for_sale"]})).all():
        urls_voix += [r.sample_url, r.preview_url]
    cles |= _cles_depuis_urls([u for u in urls_voix if u], uid, voix=True)
    for r in (await db.execute(text(
        "SELECT cover_video_url FROM playlists "
        "WHERE owner_id = :u AND NOT (id = ANY(:g))"), {**p, "g": gardes["playlists"]})).all():
        urls.append(r.cover_video_url)
    for r in (await db.execute(text(
        "SELECT avatar_url, cover_photo_url FROM users WHERE id = :u"), p)).all():
        urls += [r.avatar_url, r.cover_photo_url]

    return cles | _cles_depuis_urls([u for u in urls if u], uid)


async def apercu_suppression(db: AsyncSession, user: User) -> dict:
    """Ce que la suppression fera perdre (écran de confirmation)."""
    uid = user.id
    gardes = await _oeuvres_gardees(db, uid)
    total = {}
    for table, col in (("tracks", "artist_id"), ("prompts", "artist_id"), ("adns", "artist_id"),
                       ("visual_adns", "artist_id"), ("voices_for_sale", "artist_id"),
                       ("playlists", "owner_id"), ("albums", "owner_id")):
        total[table] = int((await db.execute(
            text(f"SELECT count(*) FROM {table} WHERE {col} = :u"), {"u": uid}  # noqa: S608
        )).scalar() or 0)
    conservees = sum(len(v) for v in gardes.values())
    return {
        "smyles": {
            "total": int(user.credits_balance or 0),
            "gagnes_en_vendant": int(user.smyles_gagnes or 0) + int(user.smyles_promo_gagnes or 0),
            "achetes": int(user.smyles_achetes or 0),
            "offerts": max(0, int(user.smyles_promo or 0) - int(user.smyles_promo_gagnes or 0)),
        },
        "oeuvres": {
            "total": sum(total.values()),
            "effacees": max(0, sum(total.values()) - conservees),
            "conservees_pour_acheteurs": conservees,
        },
        "pionnier_rang": user.pioneer_rank,
    }


async def _bruler_smyles(db: AsyncSession, user: User) -> None:
    """Détruit tout le solde (achetés, offerts, gagnés) avec une ligne BURN au
    registre. Le CHECK de somme des sous-soldes reste vrai (tout à 0)."""
    from app.models.transaction import Transaction, TransactionStatus, TransactionType

    row = (await db.execute(text(
        "SELECT credits_balance, smyles_achetes, smyles_gagnes, smyles_promo, "
        "smyles_promo_gagnes, smyles_gagnes_bloque FROM users WHERE id = :u FOR UPDATE"),
        {"u": user.id})).first()
    solde = int(row.credits_balance or 0)
    await db.execute(text(
        "UPDATE users SET credits_balance = 0, smyles_achetes = 0, smyles_gagnes = 0, "
        "smyles_promo = 0, smyles_promo_gagnes = 0, smyles_gagnes_bloque = 0 WHERE id = :u"),
        {"u": user.id})
    if solde > 0:
        db.add(Transaction(
            type=TransactionType.BURN,
            status=TransactionStatus.COMPLETED,
            buyer_id=user.id,
            credits_amount=solde,
            artist_revenue=0,
            platform_fee=0,
            idempotency_key=f"suppression_compte:{user.id}",
            completed_at=datetime.now(timezone.utc),
            metadata_json={
                "source": "suppression_compte",
                "achetes": int(row.smyles_achetes or 0),
                "gagnes": int(row.smyles_gagnes or 0),
                "promo": int(row.smyles_promo or 0),
                "promo_gagnes": int(row.smyles_promo_gagnes or 0),
                "gagnes_bloque": int(row.smyles_gagnes_bloque or 0),
            },
        ))
        await db.flush()


async def _liberer_pionnier(db: AsyncSession, user: User) -> None:
    if user.pioneer_rank is None:
        return
    from app.services.pioneer import PioneerNotHeld, revoke_pioneer

    try:
        await revoke_pioneer(
            db, user_id=user.id, reason="Compte supprimé par son titulaire", revoked_by=None
        )
    except PioneerNotHeld:
        pass


async def _verrouiller(db: AsyncSession, uid: uuid.UUID) -> None:
    """Lot G — verrous pris AVANT de calculer ce qui est conservé : la ligne
    du compte (tout achat d'une de ses œuvres la verrouille aussi, pour
    créditer le vendeur) puis ses produits en vente. Un achat simultané
    attend la fin de la suppression (puis échoue proprement : œuvre
    introuvable), ou la suppression attend l'achat (et voit alors l'œuvre
    comme achetée, donc conservée). Aucun achat ne peut se perdre entre les
    deux. Même ordre que l'achat : comptes, puis produits."""
    await db.execute(text("SELECT id FROM users WHERE id = :u FOR UPDATE"), {"u": uid})
    await db.execute(text("SELECT id FROM prompts WHERE artist_id = :u ORDER BY id FOR UPDATE"),
                     {"u": uid})


async def delete_account(db: AsyncSession, user: User) -> list:
    """Supprime le compte (voir le docstring du module). Commit.
    Renvoie les identifiants des opérations de purge de fichiers inscrites
    (table fichiers_a_traiter), à traiter en tâche de fond."""
    from app.services.fichiers_a_traiter import programmer

    uid = user.id
    p = {"u": uid}

    await _verrouiller(db, uid)
    gardes = await _oeuvres_gardees(db, uid)
    cles = await _cles_a_purger(db, uid, gardes)

    # 1. Œuvres jamais achetées : effacées (cascade likes, galeries, empreintes,
    #    écoutes, contenus de playlists). Œuvres achetées : retirées du public.
    for table, col in (("albums", "owner_id"), ("playlists", "owner_id"), ("tracks", "artist_id"),
                       ("prompts", "artist_id"), ("adns", "artist_id"),
                       ("visual_adns", "artist_id"), ("voices_for_sale", "artist_id")):
        await db.execute(
            text(f"DELETE FROM {table} WHERE {col} = :u AND NOT (id = ANY(:g))"),  # noqa: S608
            {**p, "g": gardes[table]},
        )
    await db.execute(text("UPDATE prompts SET is_published = false, is_deleted = true "
                          "WHERE artist_id = :u"), p)
    await db.execute(text("UPDATE tracks SET is_deleted = true WHERE artist_id = :u"), p)
    for table in ("adns", "visual_adns", "voices_for_sale"):
        await db.execute(text(f"UPDATE {table} SET is_published = false, is_deleted = true "  # noqa: S608
                              "WHERE artist_id = :u"), p)
    for table in ("playlists", "albums"):
        await db.execute(text(f"UPDATE {table} SET visibility = 'private', adn_for_sale = false "  # noqa: S608
                              "WHERE owner_id = :u"), p)

    # 2. Données personnelles d'activité. Lot G : les conversations ne sont
    #    plus effacées (l'autre personne perdait son historique) — elles
    #    restent, rattachées au compte anonymisé.
    await db.execute(text("DELETE FROM user_follows WHERE follower_id = :u OR followee_id = :u"), p)
    await db.execute(text("DELETE FROM notifications WHERE user_id = :u"), p)
    await db.execute(text("UPDATE notifications SET actor_id = NULL WHERE actor_id = :u"), p)
    for table in ("analytics_events", "download_events", "user_activity_days", "user_achievements",
                  "prompt_likes", "password_reset_tokens", "email_verification_tokens"):
        await db.execute(text(f"DELETE FROM {table} WHERE user_id = :u"), p)  # noqa: S608
    await db.execute(text("UPDATE content_reports SET reporter_email = NULL WHERE reporter_id = :u"), p)
    await db.execute(text(
        "UPDATE trade_offers SET status = 'cancelled', resolved_at = now() "
        "WHERE status = 'pending' AND (sender_id = :u OR receiver_id = :u)"), p)
    # Ses exemplaires ne sont plus en revente.
    await db.execute(text("UPDATE unlocked_prompts SET resale_price = NULL WHERE current_owner_id = :u"), p)

    # 3. Smyles détruits, rang Pionnier libéré.
    await _bruler_smyles(db, user)
    await _liberer_pionnier(db, user)

    # 4. Profil anonymisé.
    await db.refresh(user)
    user.email = f"deleted-{uid}{DELETED_EMAIL_SUFFIX}"
    user.email_canonical = None  # Lot I : plus aucune trace de l'adresse
    user.password_hash = "!"  # ne peut matcher aucun hash bcrypt valide
    user.token_version = int(user.token_version or 0) + 1
    user.artist_name = "Artiste supprimé"
    for champ in ("bio", "avatar_url", "cover_photo_url", "universe_description", "influences",
                  "genre", "city", "soundcloud", "instagram", "youtube", "tiktok", "spotify",
                  "twitter_x", "brand_color", "profile_bg_color", "profile_brand_color", "roles",
                  "signup_ip", "referral_code", "last_checkin_date", "onboarding_done_at"):
        setattr(user, champ, None)
    user.profile_public = False
    user.email_verified = False
    user.streak_count = 0

    ids = await programmer(db, sorted(cles), "supprimer", "suppression_compte")
    await db.commit()
    return ids


async def purger_fichiers(cles: list[str]) -> dict:
    """Compatibilité (outils) : inscrit puis traite tout de suite la purge de
    ces clés. Le chemin normal passe par `delete_account`, qui inscrit les
    opérations dans sa propre transaction."""
    from app.database import SessionLocal
    from app.services.fichiers_a_traiter import programmer, traiter_en_attente

    async with SessionLocal() as db:
        ids = await programmer(db, cles, "supprimer", "suppression_compte")
        await db.commit()
    return await traiter_en_attente(ids)
