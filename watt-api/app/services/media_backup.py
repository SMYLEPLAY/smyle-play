"""
Sauvegarde des médias R2 — étape 5 sécurité (2026-10-02).

Jusqu'ici seule la BASE était sauvegardée (workflow backup-db.yml, pg_dump
nocturne vers R2). Les fichiers eux-mêmes — sons, pochettes, avatars, images
IA originales, voix, vidéos de playlist — n'avaient AUCUNE copie : une
suppression accidentelle, un bug, ou un jeton R2 compromis = fichiers perdus
pour de bon, alors que la base continue de pointer dessus.

Ce module copie les objets du bucket public (R2_BUCKET) et, s'il existe, du
bucket privé (R2_PRIVATE_BUCKET) vers un bucket de SAUVEGARDE
(R2_BACKUP_BUCKET), sous les préfixes `public/` et `prive/`.

Garanties :
  • INCRÉMENTAL : un objet n'est recopié que s'il est nouveau ou modifié
    (taille différente, ou modifié dans la source APRÈS la dernière copie) —
    même règle que `aws s3 sync`. Relancer la commande ne recopie rien.
  • LECTURE SEULE sur la source : ce module n'appelle JAMAIS delete_object,
    et refuse de tourner si le bucket de sauvegarde est un bucket source.
  • RIEN n'est supprimé dans la sauvegarde non plus : un fichier effacé de
    la source reste récupérable dans la sauvegarde.
  • `dry_run` : liste ce qui serait copié, sans rien écrire.
  • Restauration d'UN objet (`restaurer_objet`) : de la sauvegarde vers sa
    place d'origine, sans écraser un objet existant sauf `ecraser=True`.

Ce module ne dépend PAS de app.config (la commande tourne aussi hors de
l'application, par ex. dans GitHub Actions, avec seulement boto3) : le client
S3 et les noms de buckets lui sont passés en paramètres.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator

logger = logging.getLogger(__name__)

PREFIXE_PUBLIC = "public/"
PREFIXE_PRIVE = "prive/"


class ConfigurationSauvegardeInvalide(ValueError):
    """Buckets manquants ou incohérents (ex. sauvegarde == source)."""


@dataclass
class ResumeSauvegarde:
    source: str
    destination: str
    dry_run: bool
    examines: int = 0
    copies: int = 0
    deja_a_jour: int = 0
    echecs: int = 0
    reportes: int = 0
    octets_copies: int = 0
    erreurs: list[str] = field(default_factory=list)

    def ligne(self) -> str:
        verbe = "à copier" if self.dry_run else "copiés"
        return (
            f"{self.source} → {self.destination} : {self.examines} examinés, "
            f"{self.copies} {verbe} ({self.octets_copies / 1024 / 1024:.1f} Mo), "
            f"{self.deja_a_jour} déjà à jour, {self.reportes} reportés, "
            f"{self.echecs} en échec"
        )


def _lister(client: Any, bucket: str, prefixe: str = "") -> Iterator[dict]:
    """Tous les objets d'un bucket (pagination incluse)."""
    paginator = client.get_paginator("list_objects_v2")
    params = {"Bucket": bucket}
    if prefixe:
        params["Prefix"] = prefixe
    for page in paginator.paginate(**params):
        for obj in page.get("Contents", []) or []:
            yield obj


def _a_jour(src: dict, dst: dict | None) -> bool:
    """La copie de sauvegarde `dst` est-elle à jour pour l'objet `src` ?"""
    if dst is None:
        return False
    if dst.get("Size") != src.get("Size"):
        return False
    m_src: datetime | None = src.get("LastModified")
    m_dst: datetime | None = dst.get("LastModified")
    if m_src is None or m_dst is None:
        return True  # tailles identiques et dates inconnues : on ne recopie pas
    return m_dst >= m_src


def _copier(client: Any, src_bucket: str, cle: str, dst_bucket: str, dst_cle: str) -> None:
    """Copie serveur à serveur (aucun transit des octets par la machine).
    Repli téléchargement → envoi si la copie directe est refusée."""
    try:
        client.copy_object(
            Bucket=dst_bucket,
            Key=dst_cle,
            CopySource={"Bucket": src_bucket, "Key": cle},
            MetadataDirective="COPY",
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.info("copie directe refusée pour %s (%s) : repli lecture/écriture",
                    cle, type(exc).__name__)
    obj = client.get_object(Bucket=src_bucket, Key=cle)
    extra = {}
    if obj.get("ContentType"):
        extra["ContentType"] = obj["ContentType"]
    if obj.get("CacheControl"):
        extra["CacheControl"] = obj["CacheControl"]
    try:
        client.upload_fileobj(obj["Body"], dst_bucket, dst_cle, ExtraArgs=extra or None)
    finally:
        try:
            obj["Body"].close()
        except Exception:  # noqa: BLE001
            pass


def sauvegarder_bucket(
    client: Any,
    *,
    source: str,
    destination: str,
    prefixe_destination: str,
    dry_run: bool = False,
    limite: int | None = None,
) -> ResumeSauvegarde:
    """Copie incrémentale de `source` vers `destination/prefixe_destination`."""
    if not source or not destination:
        raise ConfigurationSauvegardeInvalide("bucket source ou destination manquant")
    if source == destination:
        raise ConfigurationSauvegardeInvalide(
            "le bucket de sauvegarde doit être différent du bucket source"
        )
    resume = ResumeSauvegarde(
        source=source, destination=f"{destination}/{prefixe_destination}", dry_run=dry_run
    )

    try:
        # Inventaire de la sauvegarde existante (une seule passe de listing).
        existants: dict[str, dict] = {}
        for obj in _lister(client, destination, prefixe_destination):
            existants[obj["Key"][len(prefixe_destination):]] = obj
        objets = _lister(client, source)
        _parcourir(client, objets, existants, resume, source, destination,
                   prefixe_destination, dry_run, limite)
    except Exception as exc:  # noqa: BLE001 — bucket illisible (droits, réseau)
        resume.echecs += 1
        resume.erreurs.append(f"lecture impossible : {type(exc).__name__}")
        logger.error("sauvegarde %s interrompue (%s)", source, type(exc).__name__)
    return resume


def _parcourir(client, objets, existants, resume, source, destination,
               prefixe_destination, dry_run, limite) -> None:
    for obj in objets:
        cle = obj["Key"]
        resume.examines += 1
        if _a_jour(obj, existants.get(cle)):
            resume.deja_a_jour += 1
            continue
        if limite is not None and resume.copies >= limite:
            resume.reportes += 1  # sera copié au prochain passage
            continue
        if dry_run:
            resume.copies += 1
            resume.octets_copies += int(obj.get("Size") or 0)
            continue
        try:
            _copier(client, source, cle, destination, prefixe_destination + cle)
            resume.copies += 1
            resume.octets_copies += int(obj.get("Size") or 0)
        except Exception as exc:  # noqa: BLE001
            resume.echecs += 1
            if len(resume.erreurs) < 20:
                resume.erreurs.append(f"{cle} : {type(exc).__name__}")
            logger.warning("sauvegarde échouée pour %s (%s)", cle, type(exc).__name__)


def plan_de_sauvegarde(
    *, bucket_public: str | None, bucket_prive: str | None, bucket_sauvegarde: str | None
) -> list[tuple[str, str]]:
    """[(bucket source, préfixe dans la sauvegarde)] — refuse une config
    dangereuse (sauvegarde absente, ou identique à une source)."""
    if not bucket_sauvegarde:
        raise ConfigurationSauvegardeInvalide(
            "R2_BACKUP_BUCKET n'est pas défini : aucune sauvegarde possible"
        )
    plan: list[tuple[str, str]] = []
    if bucket_public:
        plan.append((bucket_public, PREFIXE_PUBLIC))
    if bucket_prive and bucket_prive != bucket_public:
        plan.append((bucket_prive, PREFIXE_PRIVE))
    if not plan:
        raise ConfigurationSauvegardeInvalide("aucun bucket source configuré")
    for src, _ in plan:
        if src == bucket_sauvegarde:
            raise ConfigurationSauvegardeInvalide(
                "R2_BACKUP_BUCKET doit être un bucket DÉDIÉ, différent de "
                "R2_BUCKET et de R2_PRIVATE_BUCKET"
            )
    return plan


def sauvegarder_tout(
    client: Any,
    *,
    bucket_public: str | None,
    bucket_prive: str | None,
    bucket_sauvegarde: str | None,
    dry_run: bool = False,
    limite: int | None = None,
) -> list[ResumeSauvegarde]:
    plan = plan_de_sauvegarde(
        bucket_public=bucket_public,
        bucket_prive=bucket_prive,
        bucket_sauvegarde=bucket_sauvegarde,
    )
    return [
        sauvegarder_bucket(
            client,
            source=src,
            destination=bucket_sauvegarde,  # type: ignore[arg-type]
            prefixe_destination=prefixe,
            dry_run=dry_run,
            limite=limite,
        )
        for src, prefixe in plan
    ]


def _existe(client: Any, bucket: str, cle: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=cle)
        return True
    except Exception as exc:  # noqa: BLE001
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
        if code in ("404", "NoSuchKey", "NotFound") or isinstance(exc, KeyError):
            return False
        raise


def restaurer_objet(
    client: Any,
    *,
    cle: str,
    origine: str,
    bucket_public: str | None,
    bucket_prive: str | None,
    bucket_sauvegarde: str | None,
    dry_run: bool = False,
    ecraser: bool = False,
) -> str:
    """Remet UN objet de la sauvegarde à sa place d'origine.

    `origine` : 'public' ou 'prive'. Renvoie un message lisible. Lève
    FileNotFoundError si l'objet n'est pas dans la sauvegarde, FileExistsError
    s'il existe déjà à destination et que `ecraser` est faux.
    """
    cle = (cle or "").lstrip("/")
    if not cle:
        raise ConfigurationSauvegardeInvalide("clé de l'objet manquante")
    if origine == "public":
        cible, prefixe = bucket_public, PREFIXE_PUBLIC
    elif origine == "prive":
        cible, prefixe = (bucket_prive or bucket_public), PREFIXE_PRIVE
        if not bucket_prive or bucket_prive == bucket_public:
            # Pas de bucket privé distinct : la sauvegarde l'a rangé en public/.
            prefixe = PREFIXE_PUBLIC
    else:
        raise ConfigurationSauvegardeInvalide("origine attendue : public ou prive")
    if not cible or not bucket_sauvegarde or cible == bucket_sauvegarde:
        raise ConfigurationSauvegardeInvalide("buckets mal configurés")

    source_cle = prefixe + cle
    if not _existe(client, bucket_sauvegarde, source_cle):
        raise FileNotFoundError(f"{source_cle} absent de {bucket_sauvegarde}")
    if not ecraser and _existe(client, cible, cle):
        raise FileExistsError(
            f"{cle} existe déjà dans {cible} (relancer avec --ecraser pour le remplacer)"
        )
    if dry_run:
        return f"[essai] {bucket_sauvegarde}/{source_cle} serait restauré vers {cible}/{cle}"
    _copier(client, bucket_sauvegarde, source_cle, cible, cle)
    return f"Restauré : {bucket_sauvegarde}/{source_cle} → {cible}/{cle}"
