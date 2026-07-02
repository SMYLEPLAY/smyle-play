#!/usr/bin/env python3
"""
SMYLE PLAY — WATT Deploy Watcher Pipeline
─────────────────────────────────────────
Détecte les nouveaux fichiers audio dans les 4 dossiers playlist,
les uploade sur Cloudflare R2, et regenere tracks.json pour Railway.

Appelé par la tâche planifiée watt-deploy-watcher toutes les minutes.

Sortie (stdout) : JSON structuré avec
  - uploaded:   liste des fichiers uploadés sur R2
  - skipped:    liste des fichiers déjà présents sur R2
  - catalog_changed: bool — tracks.json a été modifié ou non
  - errors:     liste des erreurs non-fatales
  - mode:       'full' (R2 ok) | 'catalog-only' (pas de creds R2)

Code de sortie :
  0 = succès complet ou rien à faire
  1 = erreur fatale (config manquante sévère, etc.)
"""

import os
import sys
import json
import mimetypes
import traceback
from pathlib import Path

# ── Chargement .env (credentials R2 locaux) ───────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    # python-dotenv absent → on lit juste les variables déjà exportées
    pass

# ── Import du scanner existant pour garder la même logique id/name/url ───────

sys.path.insert(0, str(BASE_DIR))
from scanner import (
    get_audio_duration,
    make_display_name,
    make_track_id,
)
from config import Config

# Validation ADN — optionnelle, ne bloque jamais le pipeline
try:
    from agents.dna_classifier import classify_track as _classify_track
    _DNA_AVAILABLE = True
except Exception:
    _DNA_AVAILABLE = False

# Mapping playlist_key → ADN attendu (pour la validation)
_EXPECTED_DNA = {
    'sunset-lover':  'SUNSET_LOVER',
    'night-city':    'NIGHT_CITY',
    'jungle-osmose': 'JUNGLE_OSMOSE',
    # 'hit-mix' : pas de contrainte (compilation)
}

# ── Configuration R2 ──────────────────────────────────────────────────────────

R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID', '')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY', '')
R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY', '')
R2_BUCKET = os.environ.get('R2_BUCKET', 'smyle-play-audio')
CLOUD_AUDIO_BASE_URL = os.environ.get('CLOUD_AUDIO_BASE_URL', '').rstrip('/')

AUDIO_EXTENSIONS = Config.AUDIO_EXTENSIONS
PLAYLISTS = Config.PLAYLISTS


def r2_available() -> bool:
    """True si tous les credentials R2 sont présents."""
    return bool(R2_ACCOUNT_ID and R2_ACCESS_KEY and R2_SECRET_KEY and R2_BUCKET)


def make_r2_client():
    """Retourne un client boto3 S3 configuré pour R2, ou None si impossible."""
    if not r2_available():
        return None
    try:
        import boto3
        return boto3.client(
            's3',
            endpoint_url=f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            region_name='auto',
        )
    except ImportError:
        return None


# ── Scan local ────────────────────────────────────────────────────────────────

def scan_local_files():
    """
    Scanne les 4 dossiers playlist et retourne la liste complète des fichiers audio.
    Retourne : [{playlist_key, label, folder, r2_folder, theme, filename, filepath, size, duration}]
    """
    entries = []
    for cfg in PLAYLISTS:
        folder_path = BASE_DIR / cfg['folder']
        if not folder_path.is_dir():
            continue
        for item in sorted(folder_path.iterdir()):
            if not item.is_file():
                continue
            if item.name.startswith('.'):
                continue
            if item.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            entries.append({
                'playlist_key': cfg['key'],
                'label':        cfg['label'],
                'folder':       cfg['folder'],
                'r2_folder':    cfg.get('r2_folder', cfg['folder'].strip()),
                'theme':        cfg['theme'],
                'filename':     item.name,
                'filepath':     str(item),
                'size':         item.stat().st_size,
                'duration':     get_audio_duration(str(item)),
            })
    return entries


# ── Upload R2 ─────────────────────────────────────────────────────────────────

def upload_new_to_r2(entries, s3):
    """
    Upload uniquement les fichiers absents de R2 (head_object → 404).
    Retourne (uploaded, skipped, errors) — listes de dicts.
    """
    from botocore.exceptions import ClientError

    uploaded, skipped, errors = [], [], []

    for e in entries:
        r2_key = f"{e['r2_folder']}/{e['filename']}"
        try:
            s3.head_object(Bucket=R2_BUCKET, Key=r2_key)
            skipped.append({'key': r2_key, 'playlist': e['playlist_key']})
            continue
        except ClientError as err:
            code = err.response['Error']['Code']
            if code not in ('404', 'NoSuchKey', '403'):
                errors.append({'key': r2_key, 'error': f'head_object: {code}'})
                continue
            # sinon → pas trouvé, on upload

        mime, _ = mimetypes.guess_type(e['filename'])
        ct = mime or 'audio/wav'
        try:
            s3.upload_file(
                e['filepath'], R2_BUCKET, r2_key,
                ExtraArgs={'ContentType': ct},
            )
            uploaded.append({
                'key': r2_key,
                'playlist': e['playlist_key'],
                'size_mb': round(e['size'] / (1024 * 1024), 1),
            })
        except Exception as ex:
            errors.append({'key': r2_key, 'error': str(ex)})

    return uploaded, skipped, errors


# ── Régénération tracks.json ──────────────────────────────────────────────────

def load_existing_catalog():
    """Lit tracks.json existant, retourne {} si absent ou invalide."""
    path = BASE_DIR / 'tracks.json'
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def detect_base_url(existing):
    """
    Extrait CLOUD_AUDIO_BASE_URL d'une URL existante dans tracks.json.
    Évite de casser les URLs déjà présentes si la variable d'env n'est pas définie.
    """
    for pl in existing.values():
        for track in pl.get('tracks', []):
            url = track.get('url')
            if url and url.startswith('http'):
                proto, rest = url.split('://', 1)
                host = rest.split('/', 1)[0]
                return f'{proto}://{host}'
    return None


def build_url_alt_lookup(existing):
    """
    Construit {filename: url_alt} depuis tracks.json existant.
    Préserve le champ url_alt pour les tracks qui l'avaient déjà.
    """
    lookup = {}
    for pl in existing.values():
        for track in pl.get('tracks', []):
            f = track.get('file')
            alt = track.get('url_alt')
            if f and alt:
                lookup[f] = alt
    return lookup


def existing_filenames(existing):
    """Retourne {playlist_key: set(filenames)} pour détecter les nouveaux tracks."""
    out = {}
    for key, pl in existing.items():
        out[key] = {t.get('file') for t in pl.get('tracks', []) if t.get('file')}
    return out


def validate_dna_placement(entries, existing):
    """
    Pour chaque NOUVEAU fichier (absent de tracks.json existant), classifie l'ADN
    via agents/dna_classifier.py et vérifie que le dossier de dépôt est cohérent.
    Retourne une liste de warnings {file, folder, expected_dna, detected_dna, confidence}.
    Ne bloque jamais le pipeline — juste informe.
    """
    if not _DNA_AVAILABLE:
        return []

    known = existing_filenames(existing)
    warnings = []

    for e in entries:
        pl_key   = e['playlist_key']
        filename = e['filename']
        # Ne classifier que les nouveaux fichiers
        if filename in known.get(pl_key, set()):
            continue

        expected = _EXPECTED_DNA.get(pl_key)
        if expected is None:
            # HIT MIX ou playlist libre — pas de contrainte
            continue

        try:
            result = _classify_track({
                'name':  make_display_name(filename),
                'genre': '',
                'tags':  '',
            })
        except Exception as ex:
            warnings.append({
                'file':     filename,
                'folder':   e['folder'],
                'error':    f'dna_classifier: {ex}',
            })
            continue

        detected   = result.get('dna', '')
        confidence = result.get('confidence', 0.0)

        if detected and detected != expected and confidence >= 0.4:
            warnings.append({
                'file':         filename,
                'folder':       e['folder'],
                'expected_dna': expected,
                'detected_dna': detected,
                'confidence':   round(confidence, 2),
                'hint':         f'ce morceau ressemble plus à {detected} qu\'à {expected}',
            })

    return warnings


def build_tracks_json(entries):
    """
    Construit le dict tracks.json à partir du scan local.
    Format identique à celui consommé par scanner.load_static_tracks() + app.py.
    - Préserve les URLs existantes si CLOUD_AUDIO_BASE_URL n'est pas défini (fallback).
    - Préserve les champs url_alt existants pour ne pas casser la fallback fallback du front.
    """
    import urllib.parse

    existing = load_existing_catalog()
    base_url = CLOUD_AUDIO_BASE_URL or detect_base_url(existing)
    url_alt_lookup = build_url_alt_lookup(existing)

    # On repart de la config pour préserver l'ordre des playlists et leurs métadonnées
    catalog = {}
    for cfg in PLAYLISTS:
        catalog[cfg['key']] = {
            'label':          cfg['label'],
            'folder':         cfg['folder'],
            'r2_folder':      cfg.get('r2_folder', cfg['folder'].strip()),
            'theme':          cfg['theme'],
            'tracks':         [],
            'total_duration': 0.0,
        }

    for e in entries:
        pl = catalog[e['playlist_key']]
        url = None
        if base_url:
            url = (
                base_url + '/' +
                urllib.parse.quote(e['r2_folder'], safe='') + '/' +
                urllib.parse.quote(e['filename'], safe='')
            )
        track = {
            'id':       make_track_id(e['playlist_key'], e['filename']),
            'file':     e['filename'],
            'name':     make_display_name(e['filename']),
            'duration': e['duration'],
            'url':      url,
        }
        if e['filename'] in url_alt_lookup:
            track['url_alt'] = url_alt_lookup[e['filename']]
        pl['tracks'].append(track)
        pl['total_duration'] += e['duration']

    for pl in catalog.values():
        pl['total_duration'] = round(pl['total_duration'], 1)
        pl['tracks'].sort(key=lambda t: t['file'])

    return catalog


def update_tracks_json(new_catalog):
    """
    Écrit tracks.json si le contenu a changé.
    Retourne True si modifié, False sinon.
    """
    path = BASE_DIR / 'tracks.json'
    new_text = json.dumps(new_catalog, ensure_ascii=False, indent=2) + '\n'

    if path.is_file():
        try:
            old_text = path.read_text(encoding='utf-8')
            if old_text == new_text:
                return False
        except Exception:
            pass

    path.write_text(new_text, encoding='utf-8')
    return True


# ── Entrée principale ────────────────────────────────────────────────────────

def list_r2_audio_keys(s3):
    """Liste toutes les clés audio présentes sur R2 (préfixées par les 4 playlists)."""
    keys = set()
    for cfg in PLAYLISTS:
        prefix = cfg.get('r2_folder', cfg['folder'].strip()) + '/'
        try:
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=R2_BUCKET, Prefix=prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if os.path.splitext(key)[1].lower() in AUDIO_EXTENSIONS:
                        keys.add(key)
        except Exception:
            pass
    return keys


def cleanup_r2_orphans(entries, s3, dry_run=False):
    """
    Supprime de R2 les fichiers qui ne sont plus présents localement.
    Retourne (deleted, orphans_found, errors).
    Par défaut dry_run=True si aucun fichier local — sécurité anti-vidage complet.
    """
    from botocore.exceptions import ClientError

    local_keys = set()
    for e in entries:
        local_keys.add(f"{e['r2_folder']}/{e['filename']}")

    # SAFETY : si aucun fichier local, on ne supprime RIEN sur R2
    # (évite de vider le bucket si les dossiers locaux sont vides par erreur)
    if not local_keys:
        return [], [], [{'stage': 'cleanup', 'error': 'safety: local scan returned 0 files — cleanup skipped to prevent bucket wipe'}]

    r2_keys = list_r2_audio_keys(s3)
    orphans = sorted(r2_keys - local_keys)

    deleted, errors = [], []
    for key in orphans:
        if dry_run:
            deleted.append({'key': key, 'action': 'would-delete'})
            continue
        try:
            s3.delete_object(Bucket=R2_BUCKET, Key=key)
            deleted.append({'key': key, 'action': 'deleted'})
        except ClientError as ex:
            errors.append({'key': key, 'error': str(ex)})

    return deleted, orphans, errors


def cleanup_local_junk(dry_run=False):
    """
    Supprime les fichiers indésirables dans les 4 dossiers playlist :
      - .DS_Store (macOS metadata)
      - .asd (Ableton Session Data)
      - ._* (fichiers fork macOS)
    Retourne la liste des fichiers supprimés/détectés.
    """
    JUNK_PATTERNS = ('.DS_Store', '.asd')
    JUNK_PREFIXES = ('._',)
    removed = []

    for cfg in PLAYLISTS:
        folder_path = BASE_DIR / cfg['folder']
        if not folder_path.is_dir():
            continue
        for item in folder_path.iterdir():
            if not item.is_file():
                continue
            name = item.name
            is_junk = (
                name in JUNK_PATTERNS
                or name.endswith('.asd')
                or name.startswith(JUNK_PREFIXES)
                or name == '.DS_Store'
            )
            if is_junk:
                action = 'would-remove' if dry_run else 'removed'
                if not dry_run:
                    try:
                        item.unlink()
                    except Exception as ex:
                        removed.append({'path': str(item), 'action': 'error', 'error': str(ex)})
                        continue
                removed.append({'path': str(item.relative_to(BASE_DIR)), 'action': action})

    return removed


def main():
    # Flags CLI : --cleanup-r2 (active la suppression R2), --dry-run
    argv = sys.argv[1:]
    do_cleanup_r2   = '--cleanup-r2' in argv
    dry_run         = '--dry-run' in argv
    skip_local_junk = '--no-local-cleanup' in argv

    result = {
        'mode':             'full',
        'uploaded':         [],
        'skipped_count':    0,
        'catalog_changed':  False,
        'track_count':      0,
        'dna_warnings':     [],
        'cleanup_local':    [],
        'cleanup_r2':       [],
        'errors':           [],
    }

    try:
        # Étape 0 — cleanup local (fichiers indésirables : .DS_Store, .asd, ._*)
        if not skip_local_junk:
            result['cleanup_local'] = cleanup_local_junk(dry_run=dry_run)

        # Étape 1 — scan des fichiers locaux
        entries = scan_local_files()
        result['track_count'] = len(entries)

        # Étape 2 — validation ADN (sur les nouveaux fichiers uniquement)
        existing = load_existing_catalog()
        result['dna_warnings'] = validate_dna_placement(entries, existing)

        # Étape 3 — upload R2 si possible
        s3 = make_r2_client()
        if s3 is not None:
            uploaded, skipped, errors = upload_new_to_r2(entries, s3)
            result['uploaded'] = uploaded
            result['skipped_count'] = len(skipped)
            result['errors'].extend(errors)

            # Étape 3bis — cleanup orphelins R2 (uniquement si --cleanup-r2)
            if do_cleanup_r2:
                deleted, orphans, cleanup_errors = cleanup_r2_orphans(entries, s3, dry_run=dry_run)
                result['cleanup_r2'] = deleted
                result['errors'].extend(cleanup_errors)
        else:
            result['mode'] = 'catalog-only'
            result['errors'].append({
                'stage': 'r2',
                'error': 'R2 credentials missing locally — upload skipped. '
                         'Create a .env file with R2_ACCOUNT_ID/R2_ACCESS_KEY/R2_SECRET_KEY '
                         'or export them in ~/.zshrc.',
            })

        # Étape 4 — regénération tracks.json (toujours, même si R2 KO)
        catalog = build_tracks_json(entries)
        result['catalog_changed'] = update_tracks_json(catalog)

    except Exception as ex:
        result['errors'].append({
            'stage': 'fatal',
            'error': str(ex),
            'trace': traceback.format_exc().splitlines()[-5:],
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
