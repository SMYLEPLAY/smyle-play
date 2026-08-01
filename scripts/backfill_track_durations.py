#!/usr/bin/env python3
"""One-shot — backfill de duration_seconds pour les tracks existants (P2).

Pour chaque track avec duration_seconds IS NULL et r2_key non nul :
télécharge l'objet R2, calcule la durée (pydub), met à jour la ligne.

DRY-RUN PAR DÉFAUT (liste seulement). --apply pour exécuter.
Usage : DATABASE_URL + R2_* posées, depuis la racine :
    python3 scripts/backfill_track_durations.py [--apply] [--limit N]
"""

import argparse
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "watt-api"))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402


def _normalize_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def run(apply: bool, limit: int) -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise SystemExit("DATABASE_URL manquante")
    engine = create_async_engine(_normalize_async_url(db_url))

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id::text, r2_key FROM tracks "
                    "WHERE duration_seconds IS NULL AND r2_key IS NOT NULL "
                    "ORDER BY created_at LIMIT :lim"
                ),
                {"lim": limit},
            )
        ).fetchall()

    print(f"{len(rows)} tracks sans durée (limite {limit}).")
    if not rows:
        return 0
    if not apply:
        for tid, key in rows:
            print(f"  [dry-run] {tid} ← {key}")
        print("Relancer avec --apply pour calculer et écrire les durées.")
        return 0

    import boto3
    from pydub import AudioSegment

    from app.config import settings

    r2 = boto3.client(
        "s3",
        aws_access_key_id=settings.effective_r2_access_key_id,
        aws_secret_access_key=settings.effective_r2_secret_access_key,
        endpoint_url=settings.effective_r2_endpoint_url,
    )
    bucket = settings.R2_BUCKET

    done = skipped = 0
    async with engine.begin() as conn:
        for tid, key in rows:
            try:
                obj = r2.get_object(Bucket=bucket, Key=key)
                data = obj["Body"].read()
                dur = round(len(AudioSegment.from_file(io.BytesIO(data))) / 1000.0, 2)
                await conn.execute(
                    text("UPDATE tracks SET duration_seconds = :d WHERE id = :id"),
                    {"d": dur, "id": tid},
                )
                done += 1
                print(f"  OK   {tid} → {dur}s")
            except Exception as e:  # noqa: BLE001 — one-shot : on continue
                skipped += 1
                print(f"  ERR  {tid} ({key}): {e}")

    print(f"Terminé : {done} mis à jour, {skipped} échecs sur {len(rows)}.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=500)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(run(a.apply, a.limit)))
