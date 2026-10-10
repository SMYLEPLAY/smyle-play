"""
Sauvegarde / restauration des médias R2 (sons, images, voix, vidéos).

Étape 5 sécurité (2026-10-02). Copie les buckets R2 public (R2_BUCKET) et
privé (R2_PRIVATE_BUCKET, s'il existe) vers un bucket DÉDIÉ de sauvegarde
(R2_BACKUP_BUCKET), sous `public/` et `prive/`. Incrémental (ne recopie que
le nouveau ou le modifié), ne supprime JAMAIS rien — ni dans la source, ni
dans la sauvegarde. Logique : app/services/media_backup.py.

Déclenchement planifié : .github/workflows/backup-media.yml (chaque nuit,
même principe que la sauvegarde de la base). Peut aussi se lancer à la main.

N'utilise PAS app.config : seules des variables d'environnement R2 sont
nécessaires (pas de DATABASE_URL), et seul boto3 doit être installé.

VARIABLES
─────────
    R2_ACCESS_KEY_ID  (ou R2_ACCESS_KEY)     ┐ jeton R2 : lecture sur les
    R2_SECRET_ACCESS_KEY (ou R2_SECRET_KEY)  ┘ buckets sources + écriture
                                               sur le bucket de sauvegarde
    R2_ENDPOINT_URL   (ou R2_ACCOUNT_ID)
    R2_BUCKET          bucket public          (défaut : smyle-play-audio)
    R2_PRIVATE_BUCKET  bucket privé           (optionnel)
    R2_BACKUP_BUCKET   bucket de sauvegarde   (OBLIGATOIRE, dédié)

USAGE (depuis watt-api/)
─────
    python tools/backup_media.py sauvegarder --dry-run     # ce qui serait copié
    python tools/backup_media.py sauvegarder               # copie réelle
    python tools/backup_media.py sauvegarder --limite 500  # au plus 500 copies
    python tools/backup_media.py restaurer tracks/mon-son-abc123.mp3 --origine public --dry-run
    python tools/backup_media.py restaurer images/originals/x.png --origine prive
    python tools/backup_media.py restaurer <clé> --origine public --ecraser

Sortie : 0 si tout s'est bien passé, 1 sinon (configuration, échec de copie).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parent.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.services.media_backup import (  # noqa: E402
    ConfigurationSauvegardeInvalide,
    restaurer_objet,
    sauvegarder_tout,
)


def _env(*noms: str) -> str | None:
    for nom in noms:
        v = (os.environ.get(nom) or "").strip()
        if v:
            return v
    return None


def config_depuis_env() -> dict:
    endpoint = _env("R2_ENDPOINT_URL")
    if not endpoint:
        compte = _env("R2_ACCOUNT_ID")
        endpoint = f"https://{compte}.r2.cloudflarestorage.com" if compte else None
    return {
        "access_key": _env("R2_ACCESS_KEY_ID", "R2_ACCESS_KEY"),
        "secret_key": _env("R2_SECRET_ACCESS_KEY", "R2_SECRET_KEY"),
        "endpoint": endpoint,
        "bucket_public": _env("R2_BUCKET") or "smyle-play-audio",
        "bucket_prive": _env("R2_PRIVATE_BUCKET"),
        "bucket_sauvegarde": _env("R2_BACKUP_BUCKET"),
    }


def client_r2(cfg: dict):
    """Client boto3 vers R2. Les secrets ne sont jamais affichés."""
    manquants = [k for k in ("access_key", "secret_key", "endpoint") if not cfg.get(k)]
    if manquants:
        raise ConfigurationSauvegardeInvalide(
            "identifiants R2 incomplets (R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, "
            "R2_ENDPOINT_URL ou R2_ACCOUNT_ID)"
        )
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name="auto",
        # R2 n'accepte pas toutes les sommes de contrôle automatiques des
        # boto3 récents (même réglage que le workflow backup-db.yml).
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )


def _sauvegarder(args, cfg, client) -> int:
    resumes = sauvegarder_tout(
        client,
        bucket_public=cfg["bucket_public"],
        bucket_prive=cfg["bucket_prive"],
        bucket_sauvegarde=cfg["bucket_sauvegarde"],
        dry_run=args.dry_run,
        limite=args.limite,
    )
    titre = "ESSAI (rien n'est écrit)" if args.dry_run else "Sauvegarde des médias"
    print(f"== {titre} ==")
    for r in resumes:
        print("  " + r.ligne())
        for e in r.erreurs:
            print(f"    ! {e}")
    # Ligne machine (logs / récapitulatif GitHub Actions).
    print(json.dumps({
        "sauvegarde_medias": [
            {
                "source": r.source, "destination": r.destination, "essai": r.dry_run,
                "examines": r.examines, "copies": r.copies,
                "deja_a_jour": r.deja_a_jour, "reportes": r.reportes,
                "echecs": r.echecs, "octets_copies": r.octets_copies,
            }
            for r in resumes
        ]
    }, ensure_ascii=False))
    return 1 if any(r.echecs for r in resumes) else 0


def _restaurer(args, cfg, client) -> int:
    try:
        msg = restaurer_objet(
            client,
            cle=args.cle,
            origine=args.origine,
            bucket_public=cfg["bucket_public"],
            bucket_prive=cfg["bucket_prive"],
            bucket_sauvegarde=cfg["bucket_sauvegarde"],
            dry_run=args.dry_run,
            ecraser=args.ecraser,
        )
    except (FileNotFoundError, FileExistsError) as exc:
        print(f"Restauration impossible : {exc}")
        return 1
    print(msg)
    return 0


def main(argv: list[str] | None = None, *, client=None) -> int:
    parser = argparse.ArgumentParser(description="Sauvegarde / restauration des médias R2")
    sous = parser.add_subparsers(dest="commande", required=True)

    p_sauv = sous.add_parser("sauvegarder", help="copie incrémentale vers R2_BACKUP_BUCKET")
    p_sauv.add_argument("--dry-run", action="store_true", help="n'écrit rien, affiche le plan")
    p_sauv.add_argument("--limite", type=int, default=None,
                        help="nombre max de copies pour ce passage")

    p_rest = sous.add_parser("restaurer", help="remet UN objet à sa place d'origine")
    p_rest.add_argument("cle", help="clé de l'objet, ex. tracks/mon-son-abc123.mp3")
    p_rest.add_argument("--origine", choices=("public", "prive"), default="public")
    p_rest.add_argument("--dry-run", action="store_true")
    p_rest.add_argument("--ecraser", action="store_true",
                        help="remplace l'objet s'il existe déjà à destination")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # boto3 / urllib3 trop bavards en INFO.
    for bruyant in ("botocore", "boto3", "urllib3", "s3transfer"):
        logging.getLogger(bruyant).setLevel(logging.WARNING)

    cfg = config_depuis_env()
    try:
        client = client or client_r2(cfg)
        if args.commande == "sauvegarder":
            return _sauvegarder(args, cfg, client)
        return _restaurer(args, cfg, client)
    except ConfigurationSauvegardeInvalide as exc:
        print(f"Configuration invalide : {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
