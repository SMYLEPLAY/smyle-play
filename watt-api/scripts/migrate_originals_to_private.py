#!/usr/bin/env python
"""
Migration des IMAGES ORIGINALES payantes : bucket PUBLIC → bucket PRIVÉ.

Contexte sécurité (2026-07-25)
------------------------------
L'original d'une image payante vit sous le préfixe `images/originals/{uid}.{ext}`
où `uid` est le MÊME que celui de son aperçu public `images/previews/{uid}.jpg`.
La clé de l'original est donc DEVINABLE ; tant qu'il réside dans le bucket
PUBLIC (`R2_BUCKET`), il est atteignable sans achat via l'URL r2.dev. Ce script
déplace tous les objets `images/originals/` du bucket PUBLIC vers le bucket
PRIVÉ (`R2_PRIVATE_BUCKET`), puis les SUPPRIME du public.

Aucune migration DB : les clés `image_r2_key` stockées en base restent
identiques — seul le BUCKET change. Le code lecture (routers/images.py) lit
désormais le bucket privé avec fallback public pendant la transition.

Idempotent
----------
- Si l'objet existe déjà dans le PRIVÉ → on ne le re-copie pas (skip copy).
- Si l'objet n'est plus dans le PUBLIC → skip.
- Peut être relancé sans risque : un objet déjà migré (présent en privé,
  absent en public) est simplement compté en skip.

Sécurité d'exécution
--------------------
- `--dry-run` (DÉFAUT) : liste seulement, ne copie/supprime RIEN.
- `--apply`            : exécute réellement la copie puis la suppression.
- Refuse de tourner si `R2_PRIVATE_BUCKET` est absent ou == `R2_BUCKET`
  (sinon la « migration » ne déplacerait rien et supprimerait du public).

Usage
-----
    # Simulation (par défaut, ne modifie rien) :
    railway run python watt-api/scripts/migrate_originals_to_private.py

    # Exécution réelle :
    railway run python watt-api/scripts/migrate_originals_to_private.py --apply

Les credentials R2 sont lus depuis l'environnement (présents sur Railway) via
app.services.r2.get_r2_client().
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permet `python watt-api/scripts/migrate_originals_to_private.py` en ajoutant
# le dossier `watt-api/` (parent du dossier scripts) au sys.path pour importer
# le package `app`.
_WATT_API_ROOT = Path(__file__).resolve().parents[1]
if str(_WATT_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_WATT_API_ROOT))

from app.config import settings  # noqa: E402
from app.services.r2 import get_r2_client, is_configured  # noqa: E402

# Préfixe des originaux payants à migrer (jamais les aperçus/covers).
ORIGINALS_PREFIX = "images/originals/"


def _object_exists(client, bucket: str, key: str) -> bool:
    """True si l'objet existe dans le bucket (head_object), False sinon."""
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:  # noqa: BLE001 — 404 NoSuchKey ou tout autre → absent
        return False


def _iter_original_keys(client, bucket: str):
    """
    Itère toutes les clés sous `images/originals/` du bucket, paginé
    (list_objects_v2 + ContinuationToken) pour gérer > 1000 objets.
    """
    token: str | None = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": ORIGINALS_PREFIX, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for item in resp.get("Contents", []) or []:
            key = item.get("Key")
            # Garde-fou : ne jamais toucher une clé hors préfixe (défensif).
            if key and key.startswith(ORIGINALS_PREFIX):
                yield key
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
            if not token:
                break
        else:
            break


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Déplace les images originales payantes (images/originals/) du "
            "bucket PUBLIC vers le bucket PRIVÉ, puis les supprime du public."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Exécute réellement la copie + suppression. Sans ce flag : dry-run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulation (défaut) : liste seulement, ne modifie rien.",
    )
    args = parser.parse_args()

    apply = bool(args.apply)
    mode = "APPLY" if apply else "DRY-RUN"

    # ── Garde-fous de configuration ────────────────────────────────────────
    if not is_configured():
        print(
            "[ABORT] R2 non configuré (R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY "
            "/ R2_ENDPOINT_URL manquants). Rien à faire.",
            file=sys.stderr,
        )
        return 2

    public_bucket = settings.R2_BUCKET
    private_bucket = settings.R2_PRIVATE_BUCKET

    if not private_bucket:
        print(
            "[ABORT] R2_PRIVATE_BUCKET non défini. Définis-le (bucket privé "
            "dédié aux originaux) avant de lancer la migration.",
            file=sys.stderr,
        )
        return 2
    if private_bucket == public_bucket:
        print(
            f"[ABORT] R2_PRIVATE_BUCKET == R2_BUCKET ({public_bucket!r}). Le "
            "bucket privé doit être DISTINCT du public — sinon on supprimerait "
            "du public sans rien avoir déplacé.",
            file=sys.stderr,
        )
        return 2

    client = get_r2_client()
    if client is None:
        print("[ABORT] Client R2 indisponible.", file=sys.stderr)
        return 2

    print(
        f"[{mode}] Migration {ORIGINALS_PREFIX!r} : "
        f"PUBLIC={public_bucket!r} → PRIVÉ={private_bucket!r}"
    )
    if not apply:
        print("[DRY-RUN] Aucune copie ni suppression ne sera effectuée. "
              "Ajoute --apply pour exécuter.")

    copied = 0
    deleted = 0
    skipped_already_private = 0
    skipped_missing_public = 0
    errors = 0
    total = 0

    for key in _iter_original_keys(client, public_bucket):
        total += 1
        try:
            # 1) Déjà présent dans le privé ? → ne pas re-copier (idempotent).
            already_private = _object_exists(client, private_bucket, key)

            if already_private:
                skipped_already_private += 1
                print(f"  [skip-copy] déjà en privé : {key}")
            else:
                # Vérifie que la source existe encore côté public.
                if not _object_exists(client, public_bucket, key):
                    skipped_missing_public += 1
                    print(f"  [skip] absent du public : {key}")
                    continue
                if apply:
                    client.copy_object(
                        Bucket=private_bucket,
                        Key=key,
                        CopySource={"Bucket": public_bucket, "Key": key},
                    )
                copied += 1
                print(f"  [copy] {key}")

            # 2) Supprimer du public (seulement si l'objet est bien en privé).
            #    En dry-run on ne supprime rien. En apply, on ne supprime que si
            #    la copie a réussi (already_private OU copy_object sans exception).
            if apply:
                # Sécurité : re-vérifier la présence en privé avant de supprimer
                # du public (ne jamais supprimer un original sans copie sûre).
                if _object_exists(client, private_bucket, key):
                    if _object_exists(client, public_bucket, key):
                        client.delete_object(Bucket=public_bucket, Key=key)
                        deleted += 1
                        print(f"  [del-public] {key}")
                else:
                    errors += 1
                    print(
                        f"  [ERROR] copie non confirmée en privé, suppression "
                        f"publique ANNULÉE : {key}",
                        file=sys.stderr,
                    )
            else:
                # Dry-run : indiquer ce qui SERAIT supprimé.
                print(f"  [would-del-public] {key}")

        except Exception as exc:  # noqa: BLE001 — on continue objet par objet
            errors += 1
            print(f"  [ERROR] {key} : {type(exc).__name__}: {exc}", file=sys.stderr)

    print("─" * 60)
    print(f"[{mode}] Terminé.")
    print(f"  objets listés (public)     : {total}")
    print(f"  copiés vers privé          : {copied}")
    print(f"  supprimés du public        : {deleted}")
    print(f"  skip (déjà en privé)       : {skipped_already_private}")
    print(f"  skip (absents du public)   : {skipped_missing_public}")
    print(f"  erreurs                    : {errors}")
    if not apply:
        print("  (DRY-RUN : rien n'a été modifié — relance avec --apply)")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
