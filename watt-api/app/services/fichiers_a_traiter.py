"""Opérations sur les fichiers stockés, durables et rejouées (Lot G).

Table `fichiers_a_traiter` (migration 0104). Une ligne = une opération sur
UNE clé de stockage :

  supprimer    fichier d'un compte supprimé (bucket public ET privé), sauf
               s'il est encore désigné par une ligne restante ;
  vers_prive   contenu retiré par la modération : copie vers le bucket privé
               (R2_PRIVATE_BUCKET) puis suppression du bucket public. Le
               fichier n'a alors plus AUCUNE adresse publique ;
  vers_public  restauration : copie retour vers le public, puis suppression
               du privé ;
  proteger_audio  (Lot H) version d'écoute légère + original sous clé
               secrète (app.services.apercu_audio).

Les lignes sont écrites DANS la transaction de l'action (suppression de
compte, retrait, restauration) : si l'action est annulée, rien n'est
programmé ; si elle est validée, l'opération ne peut plus être perdue.
`traiter_en_attente()` est lancée juste après la réponse (tâche de fond),
puis chaque jour par la boucle d'entretien (services/analytics.py).

Sans bucket privé configuré : `vers_prive` reste EN ATTENTE (rien n'est
déplacé, le fichier reste à son adresse publique). L'application refuse déjà
tout service du contenu retiré (écoute, téléchargement, aperçu) ; seule une
personne qui aurait noté l'adresse publique directe du fichier pourrait
encore l'ouvrir. Dès que R2_PRIVATE_BUCKET est posé, la boucle quotidienne
déplace tout ce qui attendait.
"""
from __future__ import annotations

import logging
import uuid
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ACTIONS = ("supprimer", "vers_prive", "vers_public", "proteger_audio")
# Lot H — voir app.services.apercu_audio (valeurs dupliquées pour éviter un
# import circulaire au chargement).
MOTIF_ANCIEN_ORIGINAL = "ancien_original"
DELAI_SUPPRESSION_ANCIEN_JOURS = 3
MAX_PAR_PASSAGE = 500


async def programmer(
    db: AsyncSession, cles: Iterable[str], action: str, motif: str | None = None
) -> list[uuid.UUID]:
    """Enregistre une opération par clé (sans doublon dans l'appel). Ne
    commit pas. Une restauration annule les déplacements vers le privé encore
    en attente pour ces clés (et inversement)."""
    if action not in ACTIONS:
        raise ValueError(f"action inconnue : {action}")
    from app.services.media_ownership import cle_sure

    uniques = [c for c in dict.fromkeys(c.strip() for c in cles if c) if cle_sure(c)]
    if not uniques:
        return []
    contraire = {"vers_prive": "vers_public", "vers_public": "vers_prive"}.get(action)
    if contraire:
        await db.execute(text(
            "UPDATE fichiers_a_traiter SET fait_le = now(), resultat = 'annule' "
            "WHERE fait_le IS NULL AND action = :a AND cle = ANY(:c)"),
            {"a": contraire, "c": uniques})
    ids = []
    for cle in uniques:
        ids.append((await db.execute(text(
            "INSERT INTO fichiers_a_traiter (cle, action, motif) VALUES (:c, :a, :m) RETURNING id"),
            {"c": cle, "a": action, "m": (motif or "")[:40] or None})).scalar_one())
    return ids


# ── Références encore actives ───────────────────────────────────────────────

_SQL_REFERENCE = (
    "SELECT 1 FROM tracks WHERE {t_filtre} (r2_key = :k OR position(:k in coalesce(audio_url, '')) > 0 "
    "  OR position(:k in coalesce(cover_url, '')) > 0) "
    "UNION ALL SELECT 1 FROM prompts WHERE {p_filtre} (image_r2_key = :k OR preview_r2_key = :k) "
    "UNION ALL SELECT 1 FROM prompt_gallery_images g JOIN prompts p ON p.id = g.prompt_id "
    "  WHERE {g_filtre} (g.image_r2_key = :k OR g.preview_r2_key = :k) "
    "UNION ALL SELECT 1 FROM users WHERE position(:k in coalesce(avatar_url, '')) > 0 "
    "  OR position(:k in coalesce(cover_photo_url, '')) > 0 "
    "UNION ALL SELECT 1 FROM voices_for_sale WHERE {v_filtre} (position(:k in coalesce(sample_url, '')) > 0 "
    "  OR position(:k in coalesce(preview_url, '')) > 0) "
    "UNION ALL SELECT 1 FROM playlists WHERE {l_filtre} position(:k in coalesce(cover_video_url, '')) > 0 "
    "LIMIT 1"
)


async def encore_reference(db: AsyncSession, cle: str) -> bool:
    """Le fichier est-il encore désigné par une ligne restante (quelle qu'elle soit) ?"""
    sql = _SQL_REFERENCE.format(t_filtre="", p_filtre="", g_filtre="", v_filtre="", l_filtre="")
    return (await db.execute(text(sql), {"k": cle})).first() is not None


async def utilise_hors_retrait(db: AsyncSession, cle: str) -> bool:
    """Le fichier est-il désigné par un contenu qui N'EST PAS retiré par la
    modération ? (Alors il doit rester public : un même fichier peut servir à
    plusieurs lignes.)"""
    sql = _SQL_REFERENCE.format(
        t_filtre="taken_down_at IS NULL AND",
        p_filtre="taken_down_at IS NULL AND",
        g_filtre="p.taken_down_at IS NULL AND",
        v_filtre="taken_down_at IS NULL AND",
        l_filtre="taken_down_at IS NULL AND",
    )
    return (await db.execute(text(sql), {"k": cle})).first() is not None


# ── Exécution ───────────────────────────────────────────────────────────────

class _Attente(Exception):
    """L'opération ne peut pas encore se faire (réglage manquant) : on la
    laisse en attente sans compter d'échec."""


async def _executer(db: AsyncSession, cle: str, action: str) -> str:
    from app.config import settings
    from app.services.r2 import (
        bucket_prive_distinct,
        copier_objet,
        is_configured,
        objet_existe,
        supprimer_objet,
    )

    if not is_configured():
        raise _Attente("stockage non configuré")
    public = settings.R2_BUCKET
    prive = bucket_prive_distinct()

    if action == "supprimer":
        if await encore_reference(db, cle):
            return "encore_utilise"
        await supprimer_objet(cle, bucket=public)
        if prive:
            await supprimer_objet(cle, bucket=prive)
        return "supprime"

    if action == "vers_prive":
        if await utilise_hors_retrait(db, cle):
            return "encore_public"  # restauré entre-temps, ou partagé
        if prive is None:
            raise _Attente("bucket privé non configuré")
        if await objet_existe(cle, bucket=public):
            await copier_objet(cle, source=public, destination=prive)
            await supprimer_objet(cle, bucket=public)
            return "deplace"
        return "deja_prive" if await objet_existe(cle, bucket=prive) else "absent"

    if action == "vers_public":
        if prive is None:
            return "jamais_deplace"
        if await objet_existe(cle, bucket=prive):
            await copier_objet(cle, source=prive, destination=public)
            await supprimer_objet(cle, bucket=prive)
            return "remis"
        return "deja_public"

    if action == "proteger_audio":
        # Lot H — version d'écoute légère + original sous clé secrète.
        from app.services.apercu_audio import OutilAudioAbsent, proteger_audio

        try:
            return await proteger_audio(db, cle)
        except OutilAudioAbsent:
            raise _Attente("ffmpeg absent")

    raise ValueError(action)


MAX_TENTATIVES_PROTECTION = 5


async def traiter_en_attente(ids: list | None = None, *, limite: int = MAX_PAR_PASSAGE) -> dict:
    """Traite les opérations en attente (toutes, ou celles de `ids`), dans
    l'ordre d'arrivée. Ne lève jamais. Renvoie un résumé."""
    from app.database import SessionLocal

    resume = {"faites": 0, "en_attente": 0, "echecs": 0}
    try:
        async with SessionLocal() as db:
            filtre = "AND id = ANY(:ids)" if ids else ""
            lignes = (await db.execute(text(
                "SELECT id, cle, action FROM fichiers_a_traiter "
                f"WHERE fait_le IS NULL {filtre} "  # noqa: S608
                # Lot H — l'ancienne adresse d'un original n'est supprimée
                # qu'après quelques jours (sauvegarde des médias faite).
                "AND NOT (action = 'supprimer' AND coalesce(motif, '') = :m_ancien "
                "         AND cree_le > now() - make_interval(days => :j)) "
                # Lot I — un son qui ne se convertit pas n'est plus rejoué sans
                # fin (à chaque démarrage et chaque jour) : 5 essais, puis il
                # reste visible en attente avec sa dernière erreur.
                "AND NOT (action = 'proteger_audio' AND tentatives >= :max_t) "
                "ORDER BY cree_le LIMIT :l"),
                {"ids": list(ids or []), "l": limite, "max_t": MAX_TENTATIVES_PROTECTION,
                 "m_ancien": MOTIF_ANCIEN_ORIGINAL, "j": DELAI_SUPPRESSION_ANCIEN_JOURS})).all()
            for ligne in lignes:
                # La ligne a pu être annulée entre-temps (restauration).
                encore = (await db.execute(text(
                    "SELECT 1 FROM fichiers_a_traiter WHERE id = :i AND fait_le IS NULL FOR UPDATE SKIP LOCKED"),
                    {"i": ligne.id})).first()
                if encore is None:
                    await db.commit()
                    continue
                try:
                    res = await _executer(db, ligne.cle, ligne.action)
                except _Attente:
                    resume["en_attente"] += 1
                    await db.rollback()
                    continue
                except Exception as exc:  # noqa: BLE001 — R2 en panne, droits…
                    resume["echecs"] += 1
                    await db.rollback()
                    await db.execute(text(
                        "UPDATE fichiers_a_traiter SET tentatives = tentatives + 1, "
                        "derniere_erreur = :e WHERE id = :i"),
                        {"i": ligne.id, "e": f"{type(exc).__name__}: {str(exc)[:200]}"})
                    await db.commit()
                    continue
                await db.execute(text(
                    "UPDATE fichiers_a_traiter SET fait_le = now(), resultat = :r, "
                    "tentatives = tentatives + 1, derniere_erreur = NULL WHERE id = :i"),
                    {"i": ligne.id, "r": res})
                await db.commit()
                resume["faites"] += 1
    except Exception:  # noqa: BLE001
        logger.warning("[fichiers] traitement des opérations en attente : échec", exc_info=True)
    if any(resume.values()):
        logger.info("[fichiers] opérations : %s", resume)
    return resume


# ── Clés concernées par un retrait de la modération ─────────────────────────

async def _cle_partagee(db: AsyncSession, cle: str, track_id) -> bool:
    """La pochette `cle` sert-elle ailleurs qu'au son `track_id` ?"""
    motif = "%" + cle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return (await db.execute(text(
        "SELECT 1 WHERE EXISTS (SELECT 1 FROM tracks WHERE id <> :t AND cover_url LIKE :m) "
        "OR EXISTS (SELECT 1 FROM prompts WHERE preview_r2_key = :k OR image_r2_key = :k) "
        "OR EXISTS (SELECT 1 FROM prompt_gallery_images WHERE preview_r2_key = :k OR image_r2_key = :k) "
        "OR EXISTS (SELECT 1 FROM users WHERE avatar_url LIKE :m)"),
        {"t": track_id, "m": motif, "k": cle})).first() is not None

async def cles_du_contenu(db: AsyncSession, ttype: str, tid) -> list[str]:
    """Fichiers propres au contenu retiré : audio d'un son (+ sa pochette si
    elle ne sert à rien d'autre, Lot I), original + aperçu (+ galerie) d'une
    image, extraits d'une voix. Une pochette PARTAGÉE (avec une autre ligne,
    une image du catalogue ou un avatar) n'est pas déplacée."""
    from app.services.media_ownership import media_url_key

    cles: list[str] = []
    if ttype == "track":
        r = (await db.execute(text(
            "SELECT r2_key, audio_url, cover_url FROM tracks WHERE id = :i"), {"i": tid})).first()
        if r:
            cles.append(r.r2_key or "")
            cles.append(media_url_key(r.audio_url)[1] or "")
            cle_cover = media_url_key(r.cover_url)[1]
            if cle_cover and not await _cle_partagee(db, cle_cover, tid):
                cles.append(cle_cover)
    elif ttype in ("image", "prompt"):
        r = (await db.execute(text(
            "SELECT image_r2_key, preview_r2_key FROM prompts WHERE id = :i"), {"i": tid})).first()
        if r:
            cles += [r.image_r2_key or "", r.preview_r2_key or ""]
        for g in (await db.execute(text(
                "SELECT image_r2_key, preview_r2_key FROM prompt_gallery_images WHERE prompt_id = :i"),
                {"i": tid})).all():
            cles += [g.image_r2_key or "", g.preview_r2_key or ""]
    elif ttype == "voix":
        r = (await db.execute(text(
            "SELECT sample_url, preview_url FROM voices_for_sale WHERE id = :i"), {"i": tid})).first()
        if r:
            cles += [media_url_key(r.sample_url)[1] or "", media_url_key(r.preview_url)[1] or ""]
    return [c for c in dict.fromkeys(cles) if c]
