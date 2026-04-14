"""
SMYLE PLAY — Scanner de playlists
Scanne les dossiers locaux (dev) ou le bucket R2 (production).
Aucune dépendance externe en mode local (stdlib uniquement).
"""

import os
import re
import wave
import urllib.parse
import logging

logger = logging.getLogger(__name__)


# ── Durée audio ──────────────────────────────────────────────────────────────

def get_audio_duration(filepath: str) -> float:
    """Retourne la durée en secondes. WAV = précis, MP3 = estimé 128kbps."""
    try:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.wav':
            with wave.open(filepath, 'r') as f:
                frames = f.getnframes()
                rate   = f.getframerate()
                return round(frames / float(rate), 1) if rate > 0 else 0
        elif ext == '.mp3':
            size = os.path.getsize(filepath)
            return round(size / (128 * 1024 / 8), 1)
    except Exception as e:
        logger.debug(f'Duration error for {filepath}: {e}')
    return 0


# ── Utilitaires noms ─────────────────────────────────────────────────────────

def make_display_name(filename: str) -> str:
    """Dérive un nom lisible depuis le nom de fichier brut."""
    name = filename
    name = re.sub(r'\.(mp3\.wav|wav|mp3|flac|aac|ogg|m4a)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^[a-z]{1,3}-\d+\s*[—\u2013-]+\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+Drift\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()

    def title_word(w):
        return w[0].upper() + w[1:].lower() if w else w

    return ' '.join(title_word(w) for w in name.split(' ')) or filename


def make_track_id(folder_key: str, filename: str) -> str:
    """ID stable pour localStorage / DB."""
    prefix    = ''.join(p[0] for p in folder_key.split('-'))
    sanitized = re.sub(r'[^a-z0-9]', '', filename.lower())[:24]
    return f'{prefix}-{sanitized}'


# ── Scanner local ─────────────────────────────────────────────────────────────

def scan_local(cfg: dict, base_dir: str, cloud_base_url: str, audio_extensions: tuple) -> dict:
    """Scanne un dossier local et retourne les tracks avec durées."""
    folder_path = os.path.join(base_dir, cfg['folder'])
    tracks      = []
    total_dur   = 0.0

    if os.path.isdir(folder_path):
        files = sorted(
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
            and f.lower().endswith(audio_extensions)
            and not f.startswith('.')
        )
        for f in files:
            filepath = os.path.join(folder_path, f)
            dur      = get_audio_duration(filepath)
            total_dur += dur

            cloud_url = None
            if cloud_base_url:
                cloud_url = (
                    cloud_base_url + '/' +
                    urllib.parse.quote(cfg['folder'], safe='') + '/' +
                    urllib.parse.quote(f, safe='')
                )

            tracks.append({
                'id':       make_track_id(cfg['key'], f),
                'file':     f,
                'name':     make_display_name(f),
                'duration': dur,
                'url':      cloud_url,
            })
    else:
        logger.warning(f"Dossier introuvable : {folder_path!r}")

    return {
        'label':          cfg['label'],
        'folder':         cfg['folder'],
        'theme':          cfg['theme'],
        'tracks':         tracks,
        'total_duration': round(total_dur, 1),
    }


# ── Scanner R2 (production sans fichiers locaux) ──────────────────────────────

def scan_r2(cfg: dict, r2_client, bucket: str, cloud_base_url: str) -> dict:
    """
    Scanne un bucket R2 pour lister les tracks d'un dossier.
    Utilisé quand les fichiers ne sont PAS présents localement (ex: Railway).
    """
    tracks    = []
    total_dur = 0.0
    prefix    = cfg['folder'].lstrip('/') + '/'  # ex: "SUNSET LOVER/"

    try:
        paginator = r2_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                key      = obj['Key']
                filename = key[len(prefix):]
                if not filename or filename.startswith('.'):
                    continue
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ('.wav', '.mp3', '.flac', '.aac', '.ogg', '.m4a'):
                    continue

                cloud_url = (
                    cloud_base_url + '/' +
                    urllib.parse.quote(cfg['folder'], safe='') + '/' +
                    urllib.parse.quote(filename, safe='')
                )
                tracks.append({
                    'id':       make_track_id(cfg['key'], filename),
                    'file':     filename,
                    'name':     make_display_name(filename),
                    'duration': 0,   # durée inconnue sans téléchargement
                    'url':      cloud_url,
                })
    except Exception as e:
        logger.error(f'R2 scan error for {cfg["folder"]}: {e}')

    tracks.sort(key=lambda t: t['file'])
    return {
        'label':          cfg['label'],
        'folder':         cfg['folder'],
        'theme':          cfg['theme'],
        'tracks':         tracks,
        'total_duration': round(total_dur, 1),
    }


# ── Point d'entrée principal ─────────────────────────────────────────────────

def scan_playlists(base_dir: str, cloud_base_url: str = '', playlists_config: list = None,
                   audio_extensions: tuple = None, r2_client=None, r2_bucket: str = '') -> dict:
    """
    Scanne toutes les playlists.
    - Mode local  : parcourt les dossiers sur le disque
    - Mode cloud  : utilise R2 si r2_client fourni ET dossier local absent
    """
    from config import Config
    if playlists_config is None:
        playlists_config = Config.PLAYLISTS
    if audio_extensions is None:
        audio_extensions = Config.AUDIO_EXTENSIONS

    result = {}
    for cfg in playlists_config:
        folder_path = os.path.join(base_dir, cfg['folder'])
        local_exists = os.path.isdir(folder_path)

        if local_exists:
            # Dev local ou Railway avec volumes persistants
            result[cfg['key']] = scan_local(cfg, base_dir, cloud_base_url, audio_extensions)
        elif r2_client and r2_bucket and cloud_base_url:
            # Production sans fichiers locaux → liste depuis R2
            result[cfg['key']] = scan_r2(cfg, r2_client, r2_bucket, cloud_base_url)
        else:
            # Fallback : playlist vide
            result[cfg['key']] = {
                'label': cfg['label'], 'folder': cfg['folder'],
                'theme': cfg['theme'], 'tracks': [], 'total_duration': 0,
            }

    return result
