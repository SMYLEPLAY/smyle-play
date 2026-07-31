#!/usr/bin/env python3
"""One-shot admin — backfill des previews 30 s des voix (P0-c « Sortie Flask »).

Portage CLI de l'ancien endpoint Flask POST /api/admin/backfill-voice-previews
(supprimé avec flask_app.py, décision Tom 2026-07-30 : conservé en script).

Pour chaque ligne de voices_for_sale avec preview_url IS NULL et sample_url
non nul : télécharge le sample, coupe à 30 s (pydub), exporte en mp3 192k,
uploade sur R2 (<stem>_preview.mp3) et renseigne preview_url.

DRY-RUN PAR DÉFAUT : liste les candidates sans rien écrire. Passer --apply
pour exécuter réellement.

Usage :
    DATABASE_URL=postgresql://... R2_* posées (mêmes noms que l'app) :
    python3 scripts/backfill_voice_previews.py            # dry-run
    python3 scripts/backfill_voice_previews.py --apply    # exécution

Dépendances : celles de requirements.txt (sqlalchemy[asyncio]+asyncpg, boto3,
pydub) — lancer depuis la racine du repo avec l'env de l'app.
"""

import argparse
import asyncio
import io
import os
import sys
import urllib.request

# Réutilise la config de l'app (R2, DATABASE_URL normalisée asyncpg).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "watt-api"))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402


def _normalize_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _r2_client():
    import boto3

    from app.config import settings

    if not (settings.effective_r2_access_key_id and settings.effective_r2_endpoint_url):
        raise SystemExit("R2 non configuré (R2_ACCESS_KEY* / R2_ENDPOINT_URL ou R2_ACCOUNT_ID)")
    return boto3.client(
        "s3",
        aws_access_key_id=settings.effective_r2_access_key_id,
        aws_secret_access_key=settings.effective_r2_secret_access_key,
        endpoint_url=settings.effective_r2_endpoint_url,
    ), settings


async def run(apply: bool) -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise SystemExit("DATABASE_URL manquante")
    engine = create_async_engine(_normalize_async_url(db_url))

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id::text, sample_url FROM voices_for_sale "
                    "WHERE preview_url IS NULL AND sample_url IS NOT NULL"
                )
            )
        ).fetchall()

    print(f"{len(rows)} voix sans preview.")
    if not rows:
        return 0
    if not apply:
        for vid, sample in rows:
            print(f"  [dry-run] {vid} ← {sample}")
        print("Relancer avec --apply pour générer les previews.")
        return 0

    from pydub import AudioSegment  # import tardif : seulement si --apply

    r2, settings = _r2_client()
    bucket = settings.R2_BUCKET
    base_url = (settings.effective_r2_public_base_url or "").rstrip("/")

    done = skipped = 0
    async with engine.begin() as conn:
        for vid, sample_url in rows:
            try:
                if not sample_url.startswith("http"):
                    print(f"  SKIP {vid}: sample_url non absolu ({sample_url})")
                    skipped += 1
                    continue
                req = urllib.request.Request(
                    sample_url, headers={"User-Agent": "smyle-backfill/1.0"}
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()

                audio = AudioSegment.from_file(io.BytesIO(raw))
                out = io.BytesIO()
                audio[:30000].export(out, format="mp3", bitrate="192k")
                out.seek(0)

                if base_url and sample_url.startswith(base_url):
                    key = sample_url[len(base_url):].lstrip("/")
                else:
                    print(f"  SKIP {vid}: impossible de dériver la clé R2")
                    skipped += 1
                    continue
                stem = key.rsplit(".", 1)[0] if "." in key else key
                preview_key = f"{stem}_preview.mp3"

                r2.upload_fileobj(
                    out, bucket, preview_key, ExtraArgs={"ContentType": "audio/mpeg"}
                )
                preview_url = f"{base_url}/{preview_key}"
                await conn.execute(
                    text("UPDATE voices_for_sale SET preview_url = :pu WHERE id = :id"),
                    {"pu": preview_url, "id": vid},
                )
                done += 1
                print(f"  OK   {vid} → {preview_key}")
            except Exception as e:  # noqa: BLE001 — one-shot : on continue, on liste
                skipped += 1
                print(f"  ERR  {vid}: {e}")

    print(f"Terminé : {done} générées, {skipped} sautées/échouées sur {len(rows)}.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="exécute réellement (défaut : dry-run)")
    raise SystemExit(asyncio.run(run(ap.parse_args().apply)))
