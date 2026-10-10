"""
Contrôle des fichiers envoyés — étape 5 sécurité (2026-10-02).

Toutes les routes d'envoi (images IA + galerie, avatar / bannière / pochette,
sons, voix, vidéo de couverture de playlist) passent par ce module :

  1. Lecture BORNÉE (`lire_fichier_borne`) : le fichier est lu par morceaux et
     refusé (413) dès qu'il dépasse la taille maximale de son type — on ne
     charge jamais 2 Go en mémoire pour découvrir qu'il est trop gros.
  2. Type RÉEL par signature (« magic bytes ») : l'extension et le
     Content-Type annoncés par le navigateur sont IGNORÉS (falsifiables).
     L'extension enregistrée est déduite du contenu, jamais du nom envoyé.
  3. Refus du balisage déguisé : SVG, HTML, XML, scripts — même renommés en
     .png ou glissés en tête d'un fichier — sont refusés. Un SVG/HTML servi
     depuis notre stockage peut exécuter du JavaScript (XSS stocké).
  4. Images : décodage de contrôle par Pillow (fichier réellement lisible) et
     plafond de pixels (bombe de décompression : un PNG de 50 Ko peut
     décrire 50 000 × 50 000 pixels et saturer la mémoire à l'aperçu).

Les noms de fichiers stockés sont générés côté serveur (uuid aléatoire) par
chaque route ; le nom d'origine n'est jamais réutilisé.

Messages d'erreur en français, affichés tels quels par le front (`detail`).
"""
from __future__ import annotations

import io
import re

from fastapi import HTTPException, UploadFile, status

from app.config import settings

_MO = 1024 * 1024
_CHUNK = 1024 * 1024

# Extension → type MIME servi (Content-Type posé sur l'objet R2).
MIME_PAR_EXT: dict[str, str] = {
    # images
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    # sons
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "webm": "audio/webm",
    # vidéos (couverture de playlist)
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "m4v": "video/x-m4v",
}
MIME_VIDEO_WEBM = "video/webm"


def max_octets(mo: int) -> int:
    return int(mo) * _MO


# ── 1. Lecture bornée ─────────────────────────────────────────────────────

async def lire_fichier_borne(file: UploadFile, max_bytes: int) -> bytes:
    """Lit le fichier par morceaux ; 413 dès que `max_bytes` est dépassé,
    400 s'il est vide."""
    morceaux: list[bytes] = []
    total = 0
    while True:
        bloc = await file.read(_CHUNK)
        if not bloc:
            break
        total += len(bloc)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,  # contenu trop lourd
                detail=(
                    f"Fichier trop lourd. Limite : {max_bytes // _MO} Mo."
                ),
            )
        morceaux.append(bloc)
    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Fichier vide."
        )
    return b"".join(morceaux)


# ── 2. Balisage déguisé (SVG / HTML / XML / script) ──────────────────────

# Un navigateur « renifle » le type d'une ressource sur ses premiers octets :
# c'est là qu'un fichier piégé place son balisage. On inspecte les 4 premiers
# Ko (métadonnées EXIF/XMP comprises), sans tenir compte de la casse.
_ZONE_INSPECTEE = 4096
# NB : « <?xml » n'est cherché qu'en TÊTE de fichier (règle « commence par
# < » ci-dessous) — des métadonnées XMP légitimes peuvent en contenir.
_BALISAGE = re.compile(
    rb"<\s*(?:script|svg|html|body|iframe|object|embed|!doctype)\b",
    re.IGNORECASE,
)


def contient_balisage(data: bytes) -> bool:
    """Vrai si le début du fichier contient du SVG / HTML / XML / script."""
    debut = data[:_ZONE_INSPECTEE]
    # Un SVG/HTML « nu » commence (après BOM / blancs) par « < ».
    sans_bom = debut.lstrip(b"\xef\xbb\xbf").lstrip()
    if sans_bom.startswith(b"<"):
        return True
    return bool(_BALISAGE.search(debut))


# ── 3. Signatures ─────────────────────────────────────────────────────────

def detecter_image(data: bytes) -> str | None:
    """'jpg' | 'png' | 'webp' | 'gif' d'après les octets, sinon None."""
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def _marque_ftyp(data: bytes) -> bytes | None:
    """Marque principale d'un conteneur ISO-BMFF (MP4/M4A/MOV), sinon None."""
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return data[8:12]
    return None


def detecter_audio(data: bytes) -> str | None:
    """'mp3' | 'wav' | 'flac' | 'ogg' | 'm4a' | 'aac' | 'webm', sinon None."""
    if len(data) < 12:
        return None
    if data[:3] == b"ID3":
        return "mp3"
    if data[:4] in (b"RIFF", b"RF64") and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"\x1a\x45\xdf\xa3":  # EBML (WebM / Matroska)
        return "webm"
    if _marque_ftyp(data) is not None:
        return "m4a"
    # Trame MPEG brute : 11 bits de synchro à 1.
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        couche = (data[1] >> 1) & 0x03
        if couche == 0:
            # « couche 0 » = en-tête ADTS (AAC brut) : 0xFFF1 / 0xFFF9.
            return "aac" if (data[1] & 0xF6) == 0xF0 else None
        return "mp3"
    return None


def detecter_video(data: bytes) -> str | None:
    """'mp4' | 'mov' | 'm4v' | 'webm' d'après les octets, sinon None."""
    if len(data) < 12:
        return None
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    marque = _marque_ftyp(data)
    if marque is not None:
        if marque == b"qt  ":
            return "mov"
        if marque == b"M4V ":
            return "m4v"
        return "mp4"
    # QuickTime ancien : pas de 'ftyp', premier atome moov/mdat/wide/free.
    if data[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip"):
        return "mov"
    return None


# ── 4. Vérifications complètes par famille ────────────────────────────────

def _refus(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def appliquer_plafond_pillow() -> None:
    """Lot E — aligne le plafond interne de Pillow (MAX_IMAGE_PIXELS) sur
    UPLOAD_MAX_IMAGE_PIXELS : toute ouverture d'image par le serveur (contrôle
    ET aperçu) refuse une bombe de décompression, même hors de ce module."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = int(settings.UPLOAD_MAX_IMAGE_PIXELS)


def verifier_image(data: bytes, formats: tuple[str, ...]) -> str:
    """Contrôle une image ; renvoie son extension réelle ('jpg', 'png'…).

    `formats` : extensions acceptées par la route (ex. ('jpg','png','webp')).
    """
    noms = ", ".join(f.upper() for f in formats)
    if contient_balisage(data):
        raise _refus(
            "Fichier refusé : les SVG, pages web et scripts ne sont pas "
            f"acceptés. Utilise une image {noms}."
        )
    ext = detecter_image(data)
    if ext is None or ext not in formats:
        raise _refus(
            f"Ce fichier n'est pas une image valide. Formats acceptés : {noms}."
        )

    from PIL import Image

    appliquer_plafond_pillow()
    try:
        with Image.open(io.BytesIO(data)) as img:
            largeur, hauteur = img.size
            if largeur * hauteur > settings.UPLOAD_MAX_IMAGE_PIXELS:
                raise _refus(
                    f"Image trop grande ({largeur} × {hauteur} pixels). "
                    "Réduis ses dimensions avant de l'envoyer."
                )
            img.verify()  # structure lisible jusqu'au bout (sans tout décoder)
    except HTTPException:
        raise
    except Image.DecompressionBombError:
        raise _refus(
            "Image trop grande. Réduis ses dimensions avant de l'envoyer."
        )
    except Exception:
        raise _refus("Image illisible ou endommagée. Réessaie avec un autre fichier.")
    return ext


def verifier_audio(data: bytes) -> str:
    """Contrôle un son ; renvoie son extension réelle ('mp3', 'wav'…)."""
    if contient_balisage(data):
        raise _refus(
            "Fichier refusé : ce n'est pas un fichier audio "
            "(MP3, WAV, M4A, OGG, FLAC, AAC ou WebM)."
        )
    ext = detecter_audio(data)
    if ext is None:
        raise _refus(
            "Ce fichier n'est pas un son valide. Formats acceptés : "
            "MP3, WAV, M4A, OGG, FLAC, AAC ou WebM."
        )
    return ext


def verifier_video(data: bytes) -> str:
    """Contrôle une vidéo courte ; renvoie son extension réelle."""
    if contient_balisage(data):
        raise _refus(
            "Fichier refusé : ce n'est pas une vidéo (MP4, WebM ou MOV)."
        )
    ext = detecter_video(data)
    if ext is None:
        raise _refus(
            "Ce fichier n'est pas une vidéo valide. Formats acceptés : "
            "MP4, WebM ou MOV."
        )
    return ext


def mime_pour(ext: str, *, video: bool = False) -> str:
    """Content-Type à poser sur l'objet stocké (déduit du contenu)."""
    if video and ext == "webm":
        return MIME_VIDEO_WEBM
    return MIME_PAR_EXT.get(ext, "application/octet-stream")
