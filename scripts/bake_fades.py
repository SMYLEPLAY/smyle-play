#!/usr/bin/env python3
"""
bake_fades.py — Applique un VRAI fondu de sortie DANS les fichiers audio WATT,
pour corriger les fins de morceaux mal finies (masters Suno qui coupent sec).

Non destructif : chaque original est d'abord SAUVEGARDÉ localement, puis on
ré-uploade la version fondue sur R2 à la MÊME clé (l'URL ne change pas → aucune
modif en base, ça marche instantanément partout, iOS compris).

Pour chaque son (depuis le catalogue officiel /watt/tracks-catalog) :
  1. Télécharge le fichier depuis son URL R2 publique.
  2. Sauvegarde l'original dans --backup-dir.
  3. ffmpeg : fondu de sortie sur les N dernières secondes (+ court fondu d'entrée
     anti-clic). Optionnel : coupe le silence de fin avant le fondu (--trim-silence).
  4. Ré-uploade la version fondue sur R2 (même clé, overwrite).

⚠️ DRY-RUN par défaut. Rien n'est téléchargé/écrit tant que --execute n'est pas passé.

Pré-requis :
  • ffmpeg + ffprobe installés (brew install ffmpeg).
  • pip install requests boto3
  • Identifiants R2 (Cloudflare) en variables d'environnement :
      R2_ACCOUNT_ID           (ou R2_ENDPOINT_URL complet)
      R2_ACCESS_KEY_ID
      R2_SECRET_ACCESS_KEY
      R2_BUCKET               (ex: smyle-play-audio)
  • WATT_API_BASE (ex: https://web-production-e30c8c.up.railway.app)

Exemples :
  # Voir le plan (aucune écriture) :
  WATT_API_BASE=https://web-production-e30c8c.up.railway.app \
  R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET=smyle-play-audio \
  python3 scripts/bake_fades.py --universe night-city --fade 5

  # Appliquer :
  ... python3 scripts/bake_fades.py --universe night-city --fade 5 --execute
  # Tous les univers :
  ... python3 scripts/bake_fades.py --universe all --fade 5 --execute
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    import requests
except ImportError:
    sys.exit("pip install requests")


def need(cmd: str):
    if shutil.which(cmd) is None:
        sys.exit(f"'{cmd}' introuvable. Installe-le (brew install ffmpeg).")


def r2_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        sys.exit("pip install boto3")
    # Accepte les DEUX nommages du code WATT (app/services/r2.py) :
    #   moderne : R2_ENDPOINT_URL · R2_ACCESS_KEY_ID · R2_SECRET_ACCESS_KEY
    #   legacy  : R2_ACCOUNT_ID   · R2_ACCESS_KEY    · R2_SECRET_KEY
    endpoint = os.environ.get("R2_ENDPOINT_URL") or (
        f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
        if os.environ.get("R2_ACCOUNT_ID") else None
    )
    ak = os.environ.get("R2_ACCESS_KEY_ID") or os.environ.get("R2_ACCESS_KEY")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY") or os.environ.get("R2_SECRET_KEY")
    if not (endpoint and ak and sk):
        sys.exit("Manque les identifiants R2. Fournis soit R2_ENDPOINT_URL soit "
                 "R2_ACCOUNT_ID, + (R2_ACCESS_KEY_ID ou R2_ACCESS_KEY) + "
                 "(R2_SECRET_ACCESS_KEY ou R2_SECRET_KEY).")
    return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=ak,
                        aws_secret_access_key=sk, config=Config(signature_version="s3v4"))


def key_from_url(url: str) -> str:
    """Clé R2 = chemin décodé après le domaine (ex: 'NIGHT CITY/sw-001 — X.wav')."""
    return unquote(urlparse(url).path).lstrip("/")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="night-city",
                    help="night-city | jungle-osmose | sunset-lover | hit-mix | all")
    ap.add_argument("--fade", type=float, default=5.0, help="Durée du fondu de sortie (s)")
    ap.add_argument("--execute", action="store_true", help="Applique réellement (sinon dry-run)")
    ap.add_argument("--backup-dir", default="./_masters_backup", help="Sauvegarde des originaux")
    ap.add_argument("--trim-silence", action="store_true",
                    help="Coupe le silence de fin avant le fondu (optionnel)")
    ap.add_argument("--trim-end", type=float, default=0.0,
                    help="Coupe les N dernières secondes (la fin foireuse) AVANT le fondu")
    ap.add_argument("--only", default=None,
                    help="Ne traiter QUE le son dont le nom correspond (ex: 'Liquide Chrome')")
    ap.add_argument("--exclude", default=None,
                    help="Exclure un ou plusieurs sons (séparés par des virgules), "
                         "ex: 'Liquide Chrome' pour préserver un réglage spécial déjà fait")
    ap.add_argument("--cut-at", type=float, default=0.0,
                    help="Coupe le son à ce temps ABSOLU en secondes (ex: 254 pour 4min14), puis fondu")
    args = ap.parse_args()

    base = os.environ.get(
        "WATT_API_BASE", "https://web-production-e30c8c.up.railway.app"
    ).rstrip("/")

    catalog = requests.get(f"{base}/watt/tracks-catalog", timeout=30).json()
    unis = list(catalog.keys()) if args.universe == "all" else [args.universe]
    from re import sub as _sub
    def _n(s): return _sub(r"[^a-z0-9]", "", (s or "").lower())
    excl = [_n(x) for x in (args.exclude or "").split(",") if x.strip()]
    jobs = []
    for u in unis:
        for t in catalog.get(u, {}).get("tracks", []):
            if not t.get("url"):
                continue
            nm = _n(t["name"])
            if args.only and _n(args.only) not in nm:
                continue
            if any(e in nm for e in excl):
                continue
            jobs.append((u, t["name"], t["url"], key_from_url(t["url"])))
    if not jobs:
        sys.exit(f"Aucun son trouvé{' pour --only ' + args.only if args.only else ''}.")

    print(f"{len(jobs)} son(s) · fondu {args.fade}s"
          f"{' · coupe fin ' + str(args.trim_end) + 's' if args.trim_end else ''}"
          f"{' · trim silence' if args.trim_silence else ''}\n=== PLAN ===")
    for u, name, url, key in jobs:
        print(f"  [{u}] {name:26s} → {key}")
    if not args.execute:
        print("\nDRY-RUN — rien n'a été fait. Ajoute --execute pour appliquer.")
        return 0

    # À partir d'ici seulement : besoin de ffmpeg + R2.
    need("ffmpeg"); need("ffprobe")
    s3 = r2_client()
    bucket = os.environ.get("R2_BUCKET", "smyle-play-audio")
    backup = Path(args.backup_dir); backup.mkdir(parents=True, exist_ok=True)
    ok = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for u, name, url, key in jobs:
            try:
                ext = Path(key).suffix or ".wav"
                src = tmp / f"in{ext}"; dst = tmp / f"out{ext}"
                bpath = backup / key
                bpath.parent.mkdir(parents=True, exist_ok=True)
                # SOURCE = l'original SAUVEGARDÉ s'il existe (pas de cumul quand on
                # re-teste des réglages) ; sinon on télécharge et on sauvegarde.
                if bpath.exists():
                    shutil.copy2(bpath, src)
                else:
                    r = requests.get(url, timeout=300); r.raise_for_status()
                    src.write_bytes(r.content)
                    shutil.copy2(src, bpath)
                # ffmpeg : (option) trim silence de fin → (option) coupe N sec de
                # fin → fondu de sortie sur la nouvelle fin (+ court fade-in).
                d = duration(src)
                end = max(0.0, d - args.trim_end)      # fin utile après coupe relative
                if args.cut_at > 0:                    # coupe à un temps ABSOLU
                    end = min(end, args.cut_at)
                if end <= args.fade + 0.5:
                    print(f"  ⏭  {name}: trop court ({d:.1f}s)")
                    continue
                st = max(0.0, end - args.fade)
                chain = []
                if args.trim_silence:
                    chain.append("areverse,silenceremove=start_periods=1:"
                                 "start_threshold=-50dB:start_silence=0.3,areverse")
                if args.trim_end > 0 or args.cut_at > 0:
                    chain.append(f"atrim=0:{end:.3f}")
                chain.append("afade=t=in:st=0:d=0.05")
                chain.append(f"afade=t=out:st={st:.3f}:d={args.fade:.3f}")
                af = ",".join(chain)
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(src), "-af", af,
                     "-c:a", "pcm_s16le" if ext.lower() == ".wav" else "libmp3lame", str(dst)],
                    check=True, capture_output=True,
                )
                # 4) upload back (same key)
                ctype = "audio/wav" if ext.lower() == ".wav" else "audio/mpeg"
                s3.upload_file(str(dst), bucket, key, ExtraArgs={"ContentType": ctype})
                print(f"  ✅ {name}")
                ok += 1
            except subprocess.CalledProcessError as e:
                print(f"  ❌ {name}: ffmpeg {e.stderr.decode()[:120] if e.stderr else ''}")
            except Exception as e:
                print(f"  ❌ {name}: {e}")
    print(f"\nTerminé : {ok}/{len(jobs)} fichiers fondus. Originaux dans {backup}/")
    print("Astuce : R2 peut mettre quelques minutes de cache — recharge en dur ou attends un peu.")
    print("Une fois OK, tu peux couper le fondu de sortie du player pour éviter le double :")
    print("  window.SMYLE_FADE = { enabled: true, seconds: 2 }   // ou enabled:false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
