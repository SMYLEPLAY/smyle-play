#!/usr/bin/env python3
"""
SMYLE PLAY — add_breadcrumb
────────────────────────────
Enregistre l'intention de routage pour le prochain téléchargement Suno.

Usage :
  python3 add_breadcrumb.py "Midnight Cruise" NIGHT_CITY
  python3 add_breadcrumb.py "Golden Hour" SUNSET_LOVER
  python3 add_breadcrumb.py "Neon Canopy" JUNGLE_OSMOSE
  python3 add_breadcrumb.py "triste" HIT_MIX

Options :
  --list    → affiche les breadcrumbs en attente
  --clear   → vide tous les breadcrumbs
  --remove <titre>  → retire un breadcrumb spécifique

Le skill watt-prompt peut appeler ce script à la fin d'une génération :
  > add_breadcrumb.py "{track_title}" {DNA_CIBLE}
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR  = Path(__file__).resolve().parent
PENDING_FILE = PROJECT_DIR / '.watcher-logs' / 'pending_downloads.json'
PENDING_FILE.parent.mkdir(exist_ok=True)

VALID_DNA = {'SUNSET_LOVER', 'NIGHT_CITY', 'JUNGLE_OSMOSE', 'HIT_MIX'}
TTL_HOURS = 24  # un breadcrumb expire après 24h


def load() -> dict:
    if not PENDING_FILE.exists():
        return {'entries': []}
    try:
        return json.loads(PENDING_FILE.read_text())
    except Exception:
        return {'entries': []}


def save(data: dict) -> None:
    PENDING_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def prune_expired(data: dict) -> dict:
    """Retire les entrées expirées."""
    now = datetime.utcnow()
    kept = []
    for e in data.get('entries', []):
        try:
            expires = datetime.fromisoformat(e.get('expires_at', ''))
            if expires > now:
                kept.append(e)
        except Exception:
            # Pas de date d'expiration → on garde
            kept.append(e)
    data['entries'] = kept
    return data


def add(title: str, dna: str) -> None:
    if dna not in VALID_DNA:
        print(f"❌  ADN invalide : {dna}. Valeurs valides : {', '.join(sorted(VALID_DNA))}")
        sys.exit(2)

    data = prune_expired(load())
    now = datetime.utcnow()
    entry = {
        'title':      title.strip(),
        'dna':        dna,
        'created_at': now.isoformat(timespec='seconds'),
        'expires_at': (now + timedelta(hours=TTL_HOURS)).isoformat(timespec='seconds'),
    }
    data['entries'].append(entry)
    save(data)
    print(f'✓  Breadcrumb ajouté : "{title}" → {dna} (expire dans {TTL_HOURS}h)')


def list_cmd() -> None:
    data = prune_expired(load())
    entries = data.get('entries', [])
    if not entries:
        print('(aucun breadcrumb en attente)')
        return
    print(f'{len(entries)} breadcrumb(s) en attente :')
    for e in entries:
        print(f'  • "{e["title"]}" → {e["dna"]}  (créé {e["created_at"]})')


def clear() -> None:
    save({'entries': []})
    print('✓  Breadcrumbs vidés')


def remove(title: str) -> None:
    data = load()
    before = len(data.get('entries', []))
    data['entries'] = [
        e for e in data.get('entries', [])
        if e.get('title', '').lower() != title.lower()
    ]
    save(data)
    after = len(data['entries'])
    print(f'✓  {before - after} breadcrumb(s) supprimé(s)')


# ── CLI ─────────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    if args[0] == '--list':
        list_cmd()
        return

    if args[0] == '--clear':
        clear()
        return

    if args[0] == '--remove':
        if len(args) < 2:
            print('Usage : add_breadcrumb.py --remove <titre>')
            sys.exit(2)
        remove(args[1])
        return

    if len(args) < 2:
        print('Usage : add_breadcrumb.py "<titre>" <DNA>')
        print('DNA : SUNSET_LOVER | NIGHT_CITY | JUNGLE_OSMOSE | HIT_MIX')
        sys.exit(2)

    title, dna = args[0], args[1].upper()
    add(title, dna)


if __name__ == '__main__':
    main()
