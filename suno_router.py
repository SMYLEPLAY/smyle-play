#!/usr/bin/env python3
"""
SMYLE PLAY — Suno Router
─────────────────────────
Surveille ~/Downloads et route automatiquement les nouveaux fichiers audio
téléchargés depuis Suno vers le bon dossier playlist du projet.

Approche hybride :
  1. Breadcrumb — si le fichier correspond à un titre enregistré via
     `add_breadcrumb.py` (ou le skill watt-prompt), route direct.
  2. DNA classifier — sinon analyse le nom de fichier pour deviner la playlist.
  3. A_CLASSER — si la confiance est trop basse, on met le fichier en triage
     manuel (dossier A_CLASSER/ à la racine du projet).

Fichiers d'état (dans .watcher-logs/) :
  • pending_downloads.json — breadcrumbs en attente
  • suno_router_seen.json  — fichiers déjà traités (pour ne pas doubler)
  • suno_router.log        — log humain des routages

Appelé par : com.smyleplay.suno-router.plist (LaunchAgent sur ~/Downloads)
        ou :  python3 suno_router.py               (manuel)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Répertoires ─────────────────────────────────────────────────────────────
PROJECT_DIR    = Path(__file__).resolve().parent
DOWNLOADS_DIR  = Path.home() / 'Downloads'
LOG_DIR        = PROJECT_DIR / '.watcher-logs'
LOG_DIR.mkdir(exist_ok=True)

PENDING_FILE   = LOG_DIR / 'pending_downloads.json'
SEEN_FILE      = LOG_DIR / 'suno_router_seen.json'
LOG_FILE       = LOG_DIR / 'suno_router.log'

# ── Extensions et dossiers cibles ───────────────────────────────────────────
AUDIO_EXTS = ('.wav', '.mp3', '.flac', '.aac', '.ogg', '.m4a')

DNA_TO_FOLDER = {
    'SUNSET_LOVER':  'SUNSET LOVER',
    'NIGHT_CITY':    'NIGHT CITY',
    'JUNGLE_OSMOSE': ' JUNGLE OSMOSE',   # l'espace initial est volontaire
    'HIT_MIX':       'HIT MIX',
}

TRIAGE_FOLDER  = PROJECT_DIR / 'A_CLASSER'
TRIAGE_FOLDER.mkdir(exist_ok=True)

# ── Paramètres ──────────────────────────────────────────────────────────────
MIN_CONFIDENCE      = 0.40   # en dessous → A_CLASSER/
STABILITY_DELAY_S   = 3.0    # délai d'immobilité avant de considérer un fichier stable
STABILITY_CHECKS    = 2      # nombre de checks pour confirmer la stabilité
MAX_AGE_MINUTES     = 60     # on n'analyse que les fichiers téléchargés récemment

# ── Classifier ──────────────────────────────────────────────────────────────
sys.path.insert(0, str(PROJECT_DIR))
try:
    from agents.dna_classifier import classify_track
except ImportError:
    classify_track = None


# ── Utilitaires ─────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    with LOG_FILE.open('a') as f:
        f.write(line + '\n')


def normalize(text: str) -> str:
    """Minuscule, sans ponctuation, sans espaces multiples."""
    text = text.lower()
    text = re.sub(r'\.(wav|mp3|flac|aac|ogg|m4a)$', '', text)
    text = re.sub(r'[^a-z0-9àâäéèêëïîôöùûüÿç]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def is_stable(file: Path) -> bool:
    """Vérifie que le fichier n'est plus en cours d'écriture."""
    try:
        size_a = file.stat().st_size
        time.sleep(STABILITY_DELAY_S)
        size_b = file.stat().st_size
        return size_a == size_b and size_a > 0
    except FileNotFoundError:
        return False


def too_old(file: Path) -> bool:
    """Skip les fichiers déjà vieux (pas un téléchargement récent)."""
    try:
        age_s = time.time() - file.stat().st_mtime
        return age_s > MAX_AGE_MINUTES * 60
    except FileNotFoundError:
        return True


# ── Breadcrumb matching ─────────────────────────────────────────────────────
def find_breadcrumb(filename: str, pending: dict) -> dict | None:
    """Retourne l'entrée breadcrumb qui matche le nom du fichier, ou None."""
    entries = pending.get('entries', [])
    norm_name = normalize(filename)

    # Match le plus spécifique en premier : titre long > titre court
    candidates = sorted(entries, key=lambda e: -len(e.get('title', '')))

    for entry in candidates:
        title = entry.get('title', '')
        if not title:
            continue
        norm_title = normalize(title)
        if norm_title and norm_title in norm_name:
            return entry
    return None


def consume_breadcrumb(entry: dict, pending: dict) -> None:
    """Retire l'entrée du registre (usage unique)."""
    pending['entries'] = [
        e for e in pending.get('entries', []) if e is not entry
    ]
    save_json(PENDING_FILE, pending)


# ── DNA fallback ────────────────────────────────────────────────────────────
def classify_by_filename(filename: str) -> tuple[str | None, float, dict]:
    """Retourne (folder_key, confidence, full_result) ou (None, 0, {}) si classifier KO."""
    if classify_track is None:
        return None, 0.0, {}
    result = classify_track({'name': filename, 'genre': '', 'tags': '', 'bpm': None})
    dna = result.get('dna', '')
    conf = result.get('confidence', 0.0)
    return dna, conf, result


# ── Routage ─────────────────────────────────────────────────────────────────
def route_file(src: Path) -> dict:
    """Route un fichier vers le bon dossier. Retourne un dict de résultat."""
    filename = src.name
    pending  = load_json(PENDING_FILE, {'entries': []})

    # 1. Breadcrumb
    bc = find_breadcrumb(filename, pending)
    if bc:
        dna = bc.get('dna', '')
        folder = DNA_TO_FOLDER.get(dna)
        if folder:
            dst = PROJECT_DIR / folder / filename
            shutil.move(str(src), str(dst))
            consume_breadcrumb(bc, pending)
            return {
                'action':     'moved',
                'src':        str(src),
                'dst':        str(dst),
                'method':     'breadcrumb',
                'dna':        dna,
                'confidence': 1.0,
                'breadcrumb_title': bc.get('title'),
            }

    # 2. DNA classifier
    dna, conf, full = classify_by_filename(filename)
    if dna and conf >= MIN_CONFIDENCE:
        folder = DNA_TO_FOLDER.get(dna)
        if folder:
            dst = PROJECT_DIR / folder / filename
            shutil.move(str(src), str(dst))
            return {
                'action':     'moved',
                'src':        str(src),
                'dst':        str(dst),
                'method':     'classifier',
                'dna':        dna,
                'confidence': conf,
                'scores':     full.get('scores'),
            }

    # 3. Triage
    dst = TRIAGE_FOLDER / filename
    shutil.move(str(src), str(dst))
    return {
        'action':     'triaged',
        'src':        str(src),
        'dst':        str(dst),
        'method':     'low-confidence',
        'dna':        dna or 'unknown',
        'confidence': conf,
    }


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> int:
    if not DOWNLOADS_DIR.exists():
        log(f'Downloads dir not found: {DOWNLOADS_DIR}')
        return 1

    seen = load_json(SEEN_FILE, {})

    candidates = [
        p for p in DOWNLOADS_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() in AUDIO_EXTS
        and not p.name.startswith('.')
    ]

    processed = []
    skipped   = 0

    for file in sorted(candidates):
        key = str(file)

        # Déjà traité
        if key in seen:
            skipped += 1
            continue

        # Trop vieux (pas un téléchargement frais)
        if too_old(file):
            seen[key] = {'status': 'too_old', 'mtime': file.stat().st_mtime}
            skipped += 1
            continue

        # Pas encore stable (Suno en train d'écrire) — on attendra le prochain run
        if not is_stable(file):
            log(f'Skip (instable) : {file.name}')
            continue

        # Router
        try:
            result = route_file(file)
            seen[key] = {'status': result['action'], 'mtime': time.time()}
            log(
                f"{result['action'].upper()} — {file.name} → {Path(result['dst']).parent.name}/ "
                f"(via {result['method']}, conf={result['confidence']:.2f})"
            )
            processed.append(result)
        except Exception as e:
            log(f'ERREUR sur {file.name}: {e}')
            seen[key] = {'status': 'error', 'error': str(e), 'mtime': time.time()}

    save_json(SEEN_FILE, seen)

    summary = {
        'processed_count': len(processed),
        'skipped_count':   skipped,
        'results':         processed,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
