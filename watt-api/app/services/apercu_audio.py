"""Écoute publique en version légère, original réservé aux acheteurs (Lot H).

Avant : l'adresse d'écoute d'un son menait au fichier ORIGINAL — le même que
celui vendu avec la recette (« Recette + fichier »). N'importe qui pouvait le
récupérer sans payer, et un WAV de plusieurs dizaines de Mo se chargeait
lentement sur téléphone.

Après « protection » d'un son :
  - une VERSION D'ÉCOUTE (MP3 128 kb/s, stéréo, durée complète, métadonnées
    retirées) est rangée sous une nouvelle clé, `apercu-<aléatoire>.mp3`,
    dans le même dossier. C'est la seule adresse publique du son
    (`tracks.audio_url` et `tracks.apercu_key`) ;
  - l'ORIGINAL est recopié sous une clé secrète `hd-<32 hex>.<ext>`, jamais
    renvoyée au navigateur (`tracks.r2_key`). Seul le téléchargement réservé
    aux acheteurs (et au créateur) le lit, côté serveur ;
  - l'ancienne clé de l'original (déjà exposée publiquement) est supprimée
    du stockage 3 jours plus tard (opération `supprimer`, motif
    `ancien_original`) : le temps que la sauvegarde quotidienne des médias
    en garde une copie. La nouvelle copie est vérifiée avant.

Le travail se fait par la file durable `fichiers_a_traiter` (action
`proteger_audio`) : juste après la publication d'un son, et pour tous les
sons déjà en ligne par la boucle d'entretien (démarrage, puis chaque jour).
Sans ffmpeg (développement) ou sans stockage : l'opération reste en attente.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess  # noqa: S404 — ffmpeg, arguments fixes, aucun shell
import tempfile
import uuid
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.fichiers_a_traiter import (  # valeurs partagées avec la file
    DELAI_SUPPRESSION_ANCIEN_JOURS,  # noqa: F401 — réexporté
    MOTIF_ANCIEN_ORIGINAL,
)

logger = logging.getLogger(__name__)

DEBIT_ECOUTE = "128k"
_DELAI_FFMPEG_S = 300


class OutilAudioAbsent(Exception):
    """ffmpeg n'est pas installé sur cette machine."""


class ConversionImpossible(Exception):
    """Le fichier n'a pas pu être converti en version d'écoute."""


# ── Clés ────────────────────────────────────────────────────────────────────

def _dossier(cle: str) -> str:
    return cle.rsplit("/", 1)[0] if "/" in cle else ""


def nouvelle_cle(cle: str, prefixe: str, ext: str) -> str:
    """Clé voisine (même dossier) au nom aléatoire : `<dossier>/<prefixe>-<hex>.<ext>`.
    Le dossier est conservé pour que les contrôles de propriété
    (`tracks/<id du compte>/…`) et la purge d'un compte supprimé restent vrais."""
    nom = f"{prefixe}-{uuid.uuid4().hex}.{ext}"
    d = _dossier(cle)
    return f"{d}/{nom}" if d else nom


def url_ecoute(cle_apercu: str) -> str:
    """Adresse d'écoute same-origin (proxy audio), segments encodés."""
    return "/watt/stream/" + "/".join(quote(s, safe="") for s in cle_apercu.split("/"))


# ── Conversion ──────────────────────────────────────────────────────────────

_FORMATS = (
    # (extension, type, arguments d'encodage). MP3 d'abord (lu partout) ; AAC
    # en secours si l'ffmpeg du serveur n'a pas l'encodeur MP3.
    ("mp3", "audio/mpeg", ["-c:a", "libmp3lame", "-b:a", DEBIT_ECOUTE,
                           "-id3v2_version", "0", "-write_id3v1", "0"]),
    ("m4a", "audio/mp4", ["-c:a", "aac", "-b:a", DEBIT_ECOUTE, "-movflags", "+faststart"]),
)


def fabriquer_apercu(data: bytes, ext: str) -> tuple[bytes, str, str]:
    """Version d'écoute 128 kb/s : (octets, extension, type). Bloquant : à
    appeler dans un thread. Aucune étiquette (ni titre, ni logiciel) n'est
    recopiée : rien ne fuit du fichier source."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise OutilAudioAbsent("ffmpeg")
    ext = "".join(c for c in (ext or "bin").lower() if c.isalnum())[:5] or "bin"
    erreurs = []
    with tempfile.TemporaryDirectory(prefix="watt-apercu-") as dossier:
        source = os.path.join(dossier, f"source.{ext}")
        with open(source, "wb") as f:
            f.write(data)
        for ext_sortie, mime, encodage in _FORMATS:
            sortie = os.path.join(dossier, f"apercu.{ext_sortie}")
            commande = [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-i", source,
                "-vn", "-map_metadata", "-1", "-fflags", "+bitexact",
                "-ac", "2", "-ar", "44100",
                *encodage,
                sortie,
            ]
            try:
                subprocess.run(  # noqa: S603 — liste d'arguments, pas de shell
                    commande, check=True, capture_output=True, timeout=_DELAI_FFMPEG_S,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                detail = getattr(exc, "stderr", b"") or b""
                erreurs.append(detail.decode("utf-8", "replace")[-150:])
                continue
            with open(sortie, "rb") as f:
                resultat = f.read()
            if len(resultat) >= 1024:
                return resultat, ext_sortie, mime
            erreurs.append("version d'écoute vide")
    raise ConversionImpossible(" | ".join(erreurs)[-300:])


# ── Stockage ────────────────────────────────────────────────────────────────

async def _lire_objet(cle: str, bucket: str) -> bytes:
    from app.services.r2 import R2Indisponible, appel_r2, get_r2_client

    client = get_r2_client()
    if client is None:
        raise R2Indisponible("non_configure")
    obj = await appel_r2(client.get_object, Bucket=bucket, Key=cle,
                         operation="get_object", key=cle)
    return await asyncio.to_thread(obj["Body"].read)


async def _taille(cle: str, bucket: str) -> int | None:
    from app.services.r2 import R2Absent, R2Indisponible, appel_r2, get_r2_client

    client = get_r2_client()
    if client is None:
        raise R2Indisponible("non_configure")
    try:
        tete = await appel_r2(client.head_object, Bucket=bucket, Key=cle,
                              operation="head_object", key=cle)
    except R2Absent:
        return None
    return int(tete.get("ContentLength") or 0)


async def _copier_vers(cle: str, nouvelle: str, bucket: str) -> None:
    from app.services.r2 import R2Indisponible, appel_r2, get_r2_client

    client = get_r2_client()
    if client is None:
        raise R2Indisponible("non_configure")
    await appel_r2(
        client.copy_object, Bucket=bucket, Key=nouvelle,
        CopySource={"Bucket": bucket, "Key": cle},
        operation="copy_object", key=nouvelle,
    )


# ── Opération de la file ────────────────────────────────────────────────────

async def proteger_audio(db: AsyncSession, cle: str) -> str:
    """Protège le fichier `cle` (original d'un ou plusieurs sons). Écrit en
    base dans la transaction de l'appelant (qui commit). Lève une exception
    si le stockage ou la conversion échoue (l'opération sera rejouée)."""
    from app.config import settings
    from app.services.fichiers_a_traiter import programmer
    from app.services.r2 import envoyer_objet

    sons = (await db.execute(text(
        "SELECT id, apercu_key, taken_down_at FROM tracks WHERE r2_key = :k FOR UPDATE"),
        {"k": cle})).all()
    if not sons:
        return "aucun_son"
    if all(s.apercu_key for s in sons):
        return "deja_protege"
    if any(s.taken_down_at is not None for s in sons):
        # Retiré par la modération : son fichier suit le circuit du retrait.
        return "retire"

    bucket = settings.R2_BUCKET
    taille = await _taille(cle, bucket)
    if taille is None:
        return "absent"
    ext = cle.rsplit(".", 1)[-1].lower() if "." in cle else "bin"

    data = await _lire_objet(cle, bucket)
    apercu, ext_apercu, mime_apercu = await asyncio.to_thread(fabriquer_apercu, data, ext)
    del data

    cle_apercu = nouvelle_cle(cle, "apercu", ext_apercu)
    cle_hd = nouvelle_cle(cle, "hd", ext)
    await envoyer_objet(cle_apercu, apercu, mime_apercu)
    await _copier_vers(cle, cle_hd, bucket)
    if await _taille(cle_hd, bucket) != taille:
        raise ConversionImpossible("copie de l'original incomplète")

    await db.execute(text(
        "UPDATE tracks SET r2_key = :hd, apercu_key = :ap, audio_url = :url "
        "WHERE r2_key = :k"),
        {"hd": cle_hd, "ap": cle_apercu, "url": url_ecoute(cle_apercu), "k": cle})
    # L'ancienne adresse de l'original a été publique : supprimée plus tard
    # (après la sauvegarde des médias), seulement si plus rien ne la désigne.
    await programmer(db, [cle], "supprimer", motif=MOTIF_ANCIEN_ORIGINAL)
    logger.info("[audio] son protégé (%s sons, %s Ko → %s Ko d'écoute)",
                len(sons), taille // 1024, len(apercu) // 1024)
    return "protege"


async def programmer_protections_manquantes(db: AsyncSession) -> int:
    """Inscrit `proteger_audio` pour chaque fichier original de son pas encore
    protégé et sans opération en attente. Ne commit pas."""
    from app.services.fichiers_a_traiter import programmer

    cles = (await db.execute(text(
        "SELECT DISTINCT t.r2_key FROM tracks t "
        "WHERE t.r2_key IS NOT NULL AND t.apercu_key IS NULL AND t.taken_down_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM fichiers_a_traiter f WHERE f.cle = t.r2_key "
        "  AND f.action = 'proteger_audio' AND f.fait_le IS NULL)"))).scalars().all()
    ids = await programmer(db, cles, "proteger_audio")
    return len(ids)
