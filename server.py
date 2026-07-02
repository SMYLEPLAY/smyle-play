#!/usr/bin/env python3
"""
SMYLE PLAY — Serveur local
  • Sert les fichiers statiques (index.html, style.css, script.js, audio…)
  • Expose GET /api/tracks → JSON de toutes les playlists scannées en temps réel

Usage :  python3 server.py [port]   (port par défaut : 8080)

Architecture :
  Ce fichier doit être placé à la RACINE du dossier, au même niveau que les
  dossiers audio (SUNSET LOVER, JUNGLE OSMOSE, NIGHT CITY, HIT MIX).
  Pour ajouter un morceau : déposer le fichier dans le bon dossier — aucun
  code à modifier.
"""

import os
import re
import sys
import json
import wave
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ── CONFIG DES PLAYLISTS ────────────────────────────────────────────────────
# Seule cette section est à modifier si tu ajoutes une nouvelle playlist.

PLAYLISTS_CONFIG = [
    {
        'key':    'sunset-lover',
        'label':  'SUNSET LOVER',
        'folder': 'SUNSET LOVER',
        'theme':  'sunset-lover',
    },
    {
        'key':    'jungle-osmose',
        'label':  'JUNGLE OSMOSE',
        'folder': ' JUNGLE OSMOSE',   # ← espace initial intentionnel (nom disque)
        'theme':  'jungle-osmose',
    },
    {
        'key':    'night-city',
        'label':  'NIGHT CITY',
        'folder': 'NIGHT CITY',
        'theme':  'night-city',
    },
    {
        'key':    'hit-mix',
        'label':  'HIT MIX',
        'folder': 'HIT MIX',
        'theme':  'hit-mix',
    },
]

AUDIO_EXTENSIONS = ('.wav', '.mp3', '.flac', '.aac', '.ogg', '.m4a')

# ── MODE CLOUD ───────────────────────────────────────────────────────────────
# Si CLOUD_AUDIO_BASE_URL est défini (ex: "https://pub-xxx.r2.dev"),
# chaque track aura un champ "url" pointant vers Cloudflare R2.
# En mode local cette variable est vide → l'app utilise les fichiers locaux.
CLOUD_AUDIO_BASE_URL = os.environ.get('CLOUD_AUDIO_BASE_URL', '').rstrip('/')


# ── DURÉE AUDIO ──────────────────────────────────────────────────────────────

def get_audio_duration(filepath: str) -> float:
    """
    Retourne la durée en secondes.
    • WAV  → calcul précis via le module wave standard
    • MP3  → estimation depuis la taille (≈128 kbps)
    • Autres → 0 (le client calcule via l'API Audio HTML5)
    """
    try:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.wav':
            with wave.open(filepath, 'r') as f:
                frames = f.getnframes()
                rate   = f.getframerate()
                if rate > 0:
                    return round(frames / float(rate), 1)
        elif ext == '.mp3':
            # Approximation 128 kbps — assez précise pour l'affichage
            size = os.path.getsize(filepath)
            return round(size / (128 * 1024 / 8), 1)
    except Exception:
        pass
    return 0


# ── UTILITAIRES ─────────────────────────────────────────────────────────────

def make_display_name(filename: str) -> str:
    """Dérive un nom d'affichage lisible depuis le nom de fichier brut."""
    name = filename

    # 1. Supprimer l'extension
    name = re.sub(r'\.(mp3\.wav|wav|mp3|flac|aac|ogg|m4a)$', '', name, flags=re.IGNORECASE)

    # 2. Supprimer les préfixes Suno typiques : "sw-001 — ", "jg-002 – ", "nc-003 - "…
    name = re.sub(r'^[a-z]{1,3}-\d+\s*[—\u2013-]+\s*', '', name, flags=re.IGNORECASE)

    # 3. Supprimer le suffixe " Drift" en fin
    name = re.sub(r'\s+Drift\s*$', '', name, flags=re.IGNORECASE)

    # 4. Nettoyer les espaces multiples
    name = re.sub(r'\s+', ' ', name).strip()

    # 5. Title case
    def title_word(w):
        return w[0].upper() + w[1:].lower() if w else w

    name = ' '.join(title_word(w) for w in name.split(' '))

    return name or filename


def make_track_id(folder_key: str, filename: str) -> str:
    """Génère un ID stable pour le compteur de plays en localStorage."""
    parts  = folder_key.split('-')
    prefix = ''.join(p[0] for p in parts)
    sanitized = re.sub(r'[^a-z0-9]', '', filename.lower())[:24]
    return f"{prefix}-{sanitized}"


def scan_playlists(base_dir: str) -> dict:
    """Scanne les dossiers et retourne la structure complète des playlists."""
    result = {}

    for cfg in PLAYLISTS_CONFIG:
        folder_path = os.path.join(base_dir, cfg['folder'])
        tracks      = []
        total_dur   = 0.0

        if os.path.isdir(folder_path):
            files = sorted(
                f for f in os.listdir(folder_path)
                if os.path.isfile(os.path.join(folder_path, f))
                and f.lower().endswith(AUDIO_EXTENSIONS)
                and not f.startswith('.')
            )
            for f in files:
                filepath = os.path.join(folder_path, f)
                dur      = get_audio_duration(filepath)
                total_dur += dur
                # URL cloud R2 si configurée, sinon None (chemin local)
                cloud_url = None
                if CLOUD_AUDIO_BASE_URL:
                    cloud_url = (
                        CLOUD_AUDIO_BASE_URL + '/' +
                        urllib.parse.quote(cfg['folder'], safe='') + '/' +
                        urllib.parse.quote(f, safe='')
                    )

                tracks.append({
                    'id':       make_track_id(cfg['key'], f),
                    'file':     f,
                    'name':     make_display_name(f),
                    'duration': dur,
                    'url':      cloud_url,   # None en local, URL R2 en production
                })

        result[cfg['key']] = {
            'label':          cfg['label'],
            'folder':         cfg['folder'],
            'theme':          cfg['theme'],
            'tracks':         tracks,
            'total_duration': round(total_dur, 1),
        }

    return result


# ── HANDLER HTTP ─────────────────────────────────────────────────────────────

class SmyleHandler(SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path.split('?')[0] in ('/api/tracks', '/api/playlists'):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data     = scan_playlists(base_dir)
            body     = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def log_message(self, fmt, *args):
        if args and ('/api/' in str(args[0]) or str(args[1]) not in ('200', '304')):
            super().log_message(fmt, *args)


# ── POINT D'ENTRÉE ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    port     = int(os.environ.get('PORT', sys.argv[1] if len(sys.argv) > 1 else 8080))
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    httpd = HTTPServer(('', port), SmyleHandler)

    print(f'\n  ╔══════════════════════════════════════╗')
    print(f'  ║  SMYLE PLAY → http://localhost:{port}  ║')
    print(f'  ╠══════════════════════════════════════╣')
    print(f'  ║  Dossier : {base_dir[:28]}  ║')
    print(f'  ║  Ctrl+C pour arrêter le serveur      ║')
    print(f'  ╚══════════════════════════════════════╝\n')

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n  Serveur arrêté.')
        httpd.server_close()
