"""
Propriété des fichiers envoyés (Lot A — sécurité, 2026-10-07).

Un son ou une pochette ne peut désigner QUE des fichiers envoyés par le compte
qui publie. Le serveur range chaque envoi sous un dossier au nom du compte :

  - audio d'un son   : tracks/<id du compte>/<nom>-<aléa>.<ext>
                       (POST /watt/upload)
  - image            : images/<usage>/<id du compte>/<aléa>.<ext>
                       (POST /watt/upload-image : avatar, cover, track-cover…)

Le dossier est choisi par le serveur (jamais par le navigateur) : une clé qui
porte l'id du compte prouve que le fichier vient d'un envoi de ce compte. Les
clés plus anciennes (sans dossier de compte) ne sont plus acceptées à la
création d'un son ; les sons existants ne sont pas touchés.

Les URL externes (hors stockage WATT) ne désignent aucun de nos fichiers et
restent acceptées telles quelles (le validateur de forme
`schemas.track.validate_media_url` s'applique toujours).
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from app.config import settings

# Préfixes de proxy same-origin qui pointent vers notre stockage.
_PROXY_PREFIXES = ("/watt/stream/", "/watt/images/")

# Usages d'image que le navigateur peut demander (champ `kind`). Le reste est
# ramené à « image » : ni les originaux payants ni les aperçus de produits
# (dossiers réservés au serveur) ne peuvent être visés.
_IMAGE_KIND_RE = re.compile(r"^[a-z0-9-]{1,40}$")
_RESERVED_IMAGE_KINDS = {"originals", "previews", "gallery"}


class MediaOwnershipError(ValueError):
    """Fichier désigné qui ne vient pas d'un envoi de ce compte. → 422."""


def safe_image_kind(kind: str | None) -> str:
    """Usage d'image nettoyé (dossier R2) ; jamais un dossier réservé."""
    k = re.sub(r"[^a-z0-9\-]", "", (kind or "image").lower())[:40] or "image"
    if k in _RESERVED_IMAGE_KINDS:
        return "image"
    return k


def track_audio_prefix(user_id) -> str:
    """Dossier R2 des fichiers audio de sons envoyés par ce compte."""
    return f"tracks/{user_id}"


def image_prefix(kind: str, user_id) -> str:
    """Dossier R2 des images envoyées par ce compte pour cet usage."""
    return f"images/{safe_image_kind(kind)}/{user_id}"


def key_owned_by(key: str | None, user_id) -> bool:
    """La clé R2 désigne-t-elle un fichier envoyé par ce compte ?"""
    if not key or user_id is None:
        return False
    k = key.strip()
    if not k or k.startswith("/") or "\\" in k:
        return False
    parts = k.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    uid = str(user_id).lower()
    if len(parts) == 3 and parts[0] == "tracks":
        return parts[1].lower() == uid
    if len(parts) == 4 and parts[0] == "images":
        kind = parts[1]
        return (
            bool(_IMAGE_KIND_RE.match(kind))
            and kind not in _RESERVED_IMAGE_KINDS
            and parts[2].lower() == uid
        )
    return False


def _r2_hosts() -> set[str]:
    hosts: set[str] = set()
    base = settings.effective_r2_public_base_url
    if base:
        h = (urlsplit(base).hostname or "").lower()
        if h:
            hosts.add(h)
    return hosts


def media_url_key(url: str | None) -> tuple[bool, str | None]:
    """(désigne notre stockage ?, clé R2 ou None).

    Notre stockage = proxy same-origin `/watt/stream|images/<clé>` (relatif ou
    absolu, quel que soit l'hôte), domaine public R2 configuré, ou tout hôte
    Cloudflare R2 (`*.r2.dev`, `*.r2.cloudflarestorage.com`). Une URL
    externe → (False, None).
    """
    if not url:
        return False, None
    u = url.strip()
    if not u:
        return False, None
    if u.startswith("/"):
        path = u
        host = ""
    else:
        try:
            parts = urlsplit(u)
        except ValueError:
            return True, None
        path = parts.path or ""
        host = (parts.hostname or "").lower()
    for prefix in _PROXY_PREFIXES:
        if path.startswith(prefix):
            return True, unquote(path[len(prefix):]) or None
    if host and (
        host in _r2_hosts()
        or host.endswith(".r2.dev")
        or host.endswith(".r2.cloudflarestorage.com")
    ):
        return True, unquote(path).lstrip("/") or None
    if not host:
        # Relatif hors proxy (déjà refusé par validate_media_url) : jamais à soi.
        return True, None
    return False, None


def media_url_owned_or_external(url: str | None, user_id) -> bool:
    """True si l'URL est externe, vide, ou désigne un fichier de ce compte."""
    ours, key = media_url_key(url)
    if not ours:
        return True
    return key_owned_by(key, user_id)


def assert_track_media_owned(
    user_id,
    *,
    r2_key: str | None = None,
    audio_url: str | None = None,
    cover_url: str | None = None,
) -> None:
    """Lève MediaOwnershipError si un des fichiers désignés n'est pas à ce compte."""
    if r2_key is not None and r2_key.strip() and not key_owned_by(r2_key, user_id):
        raise MediaOwnershipError("Fichier audio non reconnu pour ce compte.")
    if not media_url_owned_or_external(audio_url, user_id):
        raise MediaOwnershipError("Fichier audio non reconnu pour ce compte.")
    if not media_url_owned_or_external(cover_url, user_id):
        raise MediaOwnershipError("Image non reconnue pour ce compte.")


# ── Parcours V1 — un son se publie TOUJOURS avec son fichier audio ──────────

_AUDIO_EXTS = {"mp3", "wav", "m4a", "ogg", "flac", "aac", "webm"}

AUDIO_MANQUANT = (
    "Un son se publie avec son fichier audio : envoie d'abord le fichier, "
    "puis publie."
)


def exiger_audio_du_compte(user_id, *, r2_key: str | None, audio_url: str | None) -> str:
    """Clé R2 du fichier audio du son, après contrôle. Lève MediaOwnershipError :
      - aucun fichier désigné (ni clé, ni URL de notre stockage) ;
      - fichier hors du dossier d'envoi de CE compte (tracks/<id>/…) ;
      - extension qui n'est pas un format audio ;
      - URL audio externe, ou qui ne désigne pas le même fichier que la clé.
    """
    url = (audio_url or "").strip() or None
    cle = (r2_key or "").strip() or None
    ours, cle_url = media_url_key(url)
    if url and not ours:
        raise MediaOwnershipError("Le fichier audio doit être envoyé sur WATT.")
    if cle is None:
        cle = cle_url
    if cle is None:
        raise MediaOwnershipError(AUDIO_MANQUANT)
    if cle_url is not None and cle_url != cle:
        raise MediaOwnershipError("Fichier audio non reconnu pour ce compte.")
    if not key_owned_by(cle, user_id):
        raise MediaOwnershipError("Fichier audio non reconnu pour ce compte.")
    ext = cle.rsplit(".", 1)[-1].lower() if "." in cle else ""
    if ext not in _AUDIO_EXTS:
        raise MediaOwnershipError("Ce fichier n'est pas un fichier audio.")
    return cle


async def audio_present_sur_stockage(cle: str) -> bool | None:
    """Le fichier existe-t-il sur le stockage ? None si le stockage n'est pas
    configuré (développement, tests) : rien n'est vérifié dans ce cas."""
    import asyncio

    from app.services.r2 import get_r2_client, is_configured

    if not is_configured():
        return None
    client = get_r2_client()
    if client is None:
        return None

    def _head() -> bool:
        try:
            client.head_object(Bucket=settings.R2_BUCKET, Key=cle)
            return True
        except Exception:
            return False

    return await asyncio.get_running_loop().run_in_executor(None, _head)
