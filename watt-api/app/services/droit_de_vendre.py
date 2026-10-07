"""Seuil d'abonnés pour vendre — Étape 3, Brique 4 (flag FEATURE_SELL_GATE).

Règle : pour METTRE EN VENTE un contenu payant (prompt, image, beat, ADN, ADN
visuel, voix, ADN de playlist ou d'album, pack recette + beat), un créateur doit
avoir un nombre d'abonnés RÉELS qui dépend de la taille de la plateforme en
actifs (paliers `settings.SELL_GATE_PALIERS`, par défaut) :
      0 –   499 actifs →  5 abonnés
    500 – 1 999 actifs → 15 abonnés
  2 000 – 9 999 actifs → 30 abonnés
        10 000+ actifs → 50 abonnés

Gagner et dépenser restent ouverts à TOUS : seul le passage « en vente » est
filtré (création publiée, ou publication d'un brouillon). Modifier un contenu
déjà en vente n'est jamais bloqué.

  - ABONNÉ RÉEL : compte qui suit le créateur, dont l'email est vérifié, et qui
    n'est ni suspendu, ni supprimé, ni un compte technique (trésorerie, vitrine
    officielle, administrateur/test), ni exclu par l'admin (`pioneer_excluded`,
    exclusion persistée des comptes de test ou frauduleux).
  - EXEMPTÉS : Pionniers, administrateurs, compte officiel.
  - DROITS ACQUIS : un créateur qui avait déjà un contenu payant EN VENTE créé
    avant `SELL_GATE_DEPUIS` (jour d'activation) garde le droit. Sans date,
    tout contenu payant actuellement en vente donne le droit (équivalent tant
    que le seuil est actif, puisqu'on ne peut plus en créer sans le passer).
  - Taille de la plateforme : `objectif_actifs.actifs_en_cache` (définition
    UNIQUE des actifs, en cache ~60 s).

Flag OFF → `statut_vente` répond « autorisé » sans rien calculer.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.objectif_actifs import actifs_en_cache

# Comptes qui ne comptent jamais comme abonnés réels.
_ABONNE_REEL = (
    "u.email_verified AND NOT u.is_banned AND NOT u.is_treasury "
    "AND NOT u.is_official AND NOT u.is_admin AND NOT u.pioneer_excluded "
    "AND u.email NOT LIKE '%@deleted.watt'"
)

SQL_ABONNES_REELS = (
    "SELECT count(DISTINCT f.follower_id) FROM user_follows f "
    "JOIN users u ON u.id = f.follower_id "
    "WHERE f.followee_id = :uid AND f.follower_id <> :uid AND " + _ABONNE_REEL
)

# Contenus payants EN VENTE (hors retraits de modération) créés avant :avant.
SQL_DROITS_ACQUIS = (
    "SELECT EXISTS ( "
    "  SELECT 1 FROM prompts WHERE artist_id = :uid AND price_credits > 0 "
    "    AND is_published AND NOT is_deleted AND taken_down_at IS NULL AND created_at < :avant "
    "  UNION ALL SELECT 1 FROM adns WHERE artist_id = :uid AND price_credits > 0 "
    "    AND is_published AND NOT is_deleted AND taken_down_at IS NULL AND created_at < :avant "
    "  UNION ALL SELECT 1 FROM visual_adns WHERE artist_id = :uid AND price_credits > 0 "
    "    AND is_published AND NOT is_deleted AND taken_down_at IS NULL AND created_at < :avant "
    "  UNION ALL SELECT 1 FROM voices_for_sale WHERE artist_id = :uid AND price_credits > 0 "
    "    AND is_published AND NOT is_deleted AND taken_down_at IS NULL AND created_at < :avant "
    "  UNION ALL SELECT 1 FROM playlists WHERE owner_id = :uid AND adn_for_sale "
    "    AND adn_price IS NOT NULL AND visibility = 'public' AND created_at < :avant "
    "  UNION ALL SELECT 1 FROM albums WHERE owner_id = :uid AND adn_for_sale "
    "    AND adn_price IS NOT NULL AND visibility = 'public' AND created_at < :avant "
    ")"
)


def passe_en_vente(collection, patch) -> bool:
    """Playlist / album : le PATCH fait-il PASSER l'ADN en vente ?
    En vente = `adn_for_sale` ET `visibility == 'public'` (règle de
    `adn_offers.resolve_adn_target`)."""
    avant = bool(collection.adn_for_sale) and collection.visibility == "public"
    pour_vente = collection.adn_for_sale if patch.adn_for_sale is None else patch.adn_for_sale
    visibilite = collection.visibility if patch.visibility is None else patch.visibility
    apres = bool(pour_vente) and visibilite == "public"
    return apres and not avant


class VenteBloquee(HTTPException):
    """403 lisible par le front : `detail` est une phrase prête à afficher."""


def abonnes_requis(actifs: int) -> int:
    """Nombre d'abonnés réels requis pour une plateforme de `actifs` actifs."""
    requis = 0
    for minimum, n in sorted(settings.SELL_GATE_PALIERS):
        if actifs >= int(minimum):
            requis = int(n)
    return requis


def _date_activation() -> datetime:
    """Borne des droits acquis : minuit (UTC) du jour d'activation, ou
    maintenant si la date n'est pas renseignée / invalide."""
    brut = (settings.SELL_GATE_DEPUIS or "").strip()
    if brut:
        try:
            d = date.fromisoformat(brut)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def compter_abonnes_reels(db: AsyncSession, user_id: UUID) -> int:
    return int((await db.execute(
        text(SQL_ABONNES_REELS), {"uid": user_id}
    )).scalar_one())


async def a_des_droits_acquis(db: AsyncSession, user_id: UUID) -> bool:
    return bool((await db.execute(
        text(SQL_DROITS_ACQUIS), {"uid": user_id, "avant": _date_activation()}
    )).scalar_one())


async def statut_vente(db: AsyncSession, user) -> dict:
    """Peut-il mettre en vente ? Toujours un dict complet (pour le front)."""
    base = {"actif": bool(settings.FEATURE_SELL_GATE), "peut_vendre": True,
            "raison": None, "abonnes": None, "requis": None, "manquants": 0,
            "message": None}
    if not settings.FEATURE_SELL_GATE:
        return {**base, "raison": "seuil_inactif"}
    if getattr(user, "is_admin", False) or getattr(user, "is_official", False):
        return {**base, "raison": "exempte"}
    if getattr(user, "is_pioneer", False):
        return {**base, "raison": "pionnier"}
    requis = abonnes_requis(await actifs_en_cache(db))
    abonnes = await compter_abonnes_reels(db, user.id)
    if abonnes >= requis:
        return {**base, "raison": "seuil_atteint", "abonnes": abonnes, "requis": requis}
    if await a_des_droits_acquis(db, user.id):
        return {**base, "raison": "droits_acquis", "abonnes": abonnes, "requis": requis}
    manquants = requis - abonnes
    return {
        **base,
        "peut_vendre": False,
        "raison": "abonnes_insuffisants",
        "abonnes": abonnes,
        "requis": requis,
        "manquants": manquants,
        "message": (
            f"Encore {manquants} abonné{'s' if manquants > 1 else ''} pour pouvoir "
            f"vendre (il en faut {requis}). Tu peux déjà publier gratuitement, "
            f"gagner et dépenser des Smyles."
        ),
    }


async def exiger_droit_de_vendre(db: AsyncSession, user) -> None:
    """À appeler AVANT toute mise en vente. Lève 403 (message clair) si le
    seuil est actif et non atteint. No-op si FEATURE_SELL_GATE est OFF."""
    if not settings.FEATURE_SELL_GATE:
        return
    st = await statut_vente(db, user)
    if not st["peut_vendre"]:
        raise VenteBloquee(status_code=status.HTTP_403_FORBIDDEN, detail=st["message"])
