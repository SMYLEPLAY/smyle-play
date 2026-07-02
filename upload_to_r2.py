#!/usr/bin/env python3
"""
SMYLE PLAY — Upload des fichiers audio vers Cloudflare R2
─────────────────────────────────────────────────────────
Usage :
  1. Installe boto3 :   pip3 install boto3
  2. Lance le script :  python3 upload_to_r2.py

Variables d'environnement requises (ou modifie les constantes ci-dessous) :
  R2_ACCOUNT_ID    → ton Account ID Cloudflare
  R2_ACCESS_KEY    → Access Key ID (depuis R2 → Manage R2 API Tokens)
  R2_SECRET_KEY    → Secret Access Key
  R2_BUCKET        → nom de ton bucket (ex: "smyle-play-audio")

Résultat : tous les fichiers audio des 4 playlists sont uploadés dans R2
  avec la même structure de dossiers que sur le disque.
"""

import os
import sys
import mimetypes

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print('\n  ❌  boto3 non installé. Lance : pip3 install boto3\n')
    sys.exit(1)

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Tu peux renseigner les valeurs directement ici, ou les passer en variable d'env.

R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID', 'TON_ACCOUNT_ID_ICI')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY', 'TON_ACCESS_KEY_ICI')
R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY', 'TON_SECRET_KEY_ICI')
R2_BUCKET     = os.environ.get('R2_BUCKET',     'smyle-play-audio')

AUDIO_EXTENSIONS = ('.wav', '.mp3', '.flac', '.aac', '.ogg', '.m4a')

PLAYLIST_FOLDERS = [
    'SUNSET LOVER',
    ' JUNGLE OSMOSE',
    'NIGHT CITY',
    'HIT MIX',
]

# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    if 'TON_' in R2_ACCOUNT_ID:
        print('\n  ❌  Configure tes credentials R2 dans upload_to_r2.py ou en variables d\'env.\n')
        sys.exit(1)

    endpoint = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'

    s3 = boto3.client(
        's3',
        endpoint_url         = endpoint,
        aws_access_key_id    = R2_ACCESS_KEY,
        aws_secret_access_key= R2_SECRET_KEY,
        region_name          = 'auto',
    )

    base_dir     = os.path.dirname(os.path.abspath(__file__))
    total_files  = 0
    total_bytes  = 0
    skipped      = 0

    print(f'\n  SMYLE PLAY → Upload R2 ({R2_BUCKET})')
    print(f'  Endpoint : {endpoint}\n')

    for folder in PLAYLIST_FOLDERS:
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            print(f'  ⚠  Dossier introuvable : {folder!r}')
            continue

        files = sorted(
            f for f in os.listdir(folder_path)
            if f.lower().endswith(AUDIO_EXTENSIONS) and not f.startswith('.')
        )

        print(f'  📁  {folder.strip()} ({len(files)} fichiers)')

        for filename in files:
            filepath   = os.path.join(folder_path, filename)
            r2_key     = f'{folder}/{filename}'   # garde l'espace initial si présent
            size_mb    = os.path.getsize(filepath) / (1024 * 1024)

            # Déterminer le Content-Type
            mime, _ = mimetypes.guess_type(filename)
            ct = mime or 'audio/wav'

            try:
                # Vérifie si le fichier existe déjà (évite re-upload inutile)
                s3.head_object(Bucket=R2_BUCKET, Key=r2_key)
                print(f'    ↩  {filename[:50]:<50} ({size_mb:.1f} MB) — déjà uploadé')
                skipped += 1
                continue
            except ClientError as e:
                if e.response['Error']['Code'] not in ('404', 'NoSuchKey'):
                    raise

            print(f'    ↑  {filename[:50]:<50} ({size_mb:.1f} MB)', end='', flush=True)
            try:
                s3.upload_file(
                    filepath, R2_BUCKET, r2_key,
                    ExtraArgs={'ContentType': ct},
                )
                total_files += 1
                total_bytes += os.path.getsize(filepath)
                print(' ✓')
            except Exception as e:
                print(f' ✗  {e}')

    print(f'\n  ✅  Upload terminé : {total_files} fichiers ({total_bytes/(1024**3):.2f} GB)')
    if skipped:
        print(f'     {skipped} fichier(s) déjà présents — ignorés')

    # Afficher l'URL publique à utiliser dans CLOUD_AUDIO_BASE_URL
    print(f'\n  ─────────────────────────────────────────────────')
    print(f'  Copie cette URL dans ta variable d\'env Railway :')
    print(f'  CLOUD_AUDIO_BASE_URL = https://{R2_BUCKET}.{R2_ACCOUNT_ID}.r2.dev')
    print(f'  (ou l\'URL publique de ton bucket R2 si tu as configuré un domaine custom)')
    print(f'  ─────────────────────────────────────────────────\n')


if __name__ == '__main__':
    main()
