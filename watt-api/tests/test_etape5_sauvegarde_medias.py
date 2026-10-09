"""Étape 5 (2026-10-02) — sauvegarde des médias R2 (faux client S3).

Incrémentale, idempotente, mode essai, jamais de suppression, refus d'une
configuration dangereuse, restauration d'UN objet, commande en ligne.
"""
import importlib.util
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services import media_backup as mb

# Chargement de la commande par son chemin (tools/ n'est pas un paquet).
_spec = importlib.util.spec_from_file_location(
    "backup_media_cli", Path(__file__).resolve().parents[1] / "tools" / "backup_media.py"
)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


class _Introuvable(Exception):
    def __init__(self):
        super().__init__("404")
        self.response = {"Error": {"Code": "404"}}


class FauxS3:
    """Sous-ensemble de l'API S3 utilisé par la sauvegarde. Interdit toute
    suppression (un appel delete_* fait échouer le test)."""

    def __init__(self, buckets: dict[str, dict[str, bytes]], page=2):
        self.t = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.b: dict[str, dict[str, dict]] = {}
        for nom, objets in buckets.items():
            self.b[nom] = {}
            for k, v in objets.items():
                self._ecrire(nom, k, v, "audio/mpeg")
        self.page = page
        self.copies = 0
        self.copie_directe_ok = True

    def _horloge(self):
        self.t += timedelta(seconds=1)
        return self.t

    def _ecrire(self, bucket, key, data, ct):
        self.b.setdefault(bucket, {})[key] = {
            "data": data, "LastModified": self._horloge(), "ContentType": ct,
        }

    # -- API --
    def get_paginator(self, nom):
        assert nom == "list_objects_v2"
        s3 = self

        class _P:
            def paginate(self, Bucket, Prefix=""):
                cles = sorted(k for k in s3.b[Bucket] if k.startswith(Prefix))
                for i in range(0, max(len(cles), 1), s3.page):
                    lot = cles[i:i + s3.page]
                    yield {"Contents": [
                        {"Key": k, "Size": len(s3.b[Bucket][k]["data"]),
                         "LastModified": s3.b[Bucket][k]["LastModified"]}
                        for k in lot
                    ]} if lot else {}
        return _P()

    def copy_object(self, Bucket, Key, CopySource, MetadataDirective):
        if not self.copie_directe_ok:
            raise RuntimeError("copie inter-bucket refusée")
        src = self.b[CopySource["Bucket"]][CopySource["Key"]]
        self._ecrire(Bucket, Key, src["data"], src["ContentType"])
        self.copies += 1

    def get_object(self, Bucket, Key):
        o = self.b[Bucket][Key]
        return {"Body": io.BytesIO(o["data"]), "ContentType": o["ContentType"]}

    def upload_fileobj(self, fileobj, Bucket, Key, ExtraArgs=None):
        self._ecrire(Bucket, Key, fileobj.read(), (ExtraArgs or {}).get("ContentType"))
        self.copies += 1

    def head_object(self, Bucket, Key):
        if Key not in self.b.get(Bucket, {}):
            raise _Introuvable()
        return {}

    def __getattr__(self, nom):
        if nom.startswith("delete"):
            raise AssertionError(f"suppression interdite : {nom}")
        raise AttributeError(nom)


def _s3():
    return FauxS3({
        "public": {"tracks/a.mp3": b"aaaa", "images/previews/p.jpg": b"pp", "tracks/b.wav": b"bbbbbb"},
        "prive": {"images/originals/o.png": b"original"},
        "sauvegarde": {},
    })


def _tout(s3, **kw):
    return mb.sauvegarder_tout(
        s3, bucket_public="public", bucket_prive="prive",
        bucket_sauvegarde="sauvegarde", **kw,
    )


def test_premiere_sauvegarde_copie_tout():
    s3 = _s3()
    pub, priv = _tout(s3)
    assert (pub.examines, pub.copies, pub.echecs) == (3, 3, 0)
    assert (priv.examines, priv.copies) == (1, 1)
    assert set(s3.b["sauvegarde"]) == {
        "public/tracks/a.mp3", "public/images/previews/p.jpg",
        "public/tracks/b.wav", "prive/images/originals/o.png",
    }
    assert s3.b["sauvegarde"]["public/tracks/a.mp3"]["data"] == b"aaaa"
    assert pub.octets_copies == 4 + 2 + 6


def test_deuxieme_passage_ne_recopie_rien():
    s3 = _s3()
    _tout(s3)
    avant = s3.copies
    pub, priv = _tout(s3)
    assert s3.copies == avant
    assert pub.copies == 0 and pub.deja_a_jour == 3
    assert priv.copies == 0 and priv.deja_a_jour == 1


def test_seuls_nouveaux_et_modifies_sont_recopies():
    s3 = _s3()
    _tout(s3)
    s3._ecrire("public", "tracks/c.mp3", b"nouveau", "audio/mpeg")       # nouveau
    s3._ecrire("public", "tracks/a.mp3", b"aaaa-v2", "audio/mpeg")       # modifié
    pub, _ = _tout(s3)
    assert pub.copies == 2 and pub.deja_a_jour == 2
    assert s3.b["sauvegarde"]["public/tracks/a.mp3"]["data"] == b"aaaa-v2"


def test_meme_taille_mais_modifie_apres_la_copie():
    s3 = _s3()
    _tout(s3)
    s3._ecrire("public", "tracks/a.mp3", b"AAAA", "audio/mpeg")  # même taille
    pub, _ = _tout(s3)
    assert pub.copies == 1
    assert s3.b["sauvegarde"]["public/tracks/a.mp3"]["data"] == b"AAAA"


def test_essai_n_ecrit_rien():
    s3 = _s3()
    pub, priv = _tout(s3, dry_run=True)
    assert pub.copies == 3 and priv.copies == 1
    assert s3.b["sauvegarde"] == {}
    assert "à copier" in pub.ligne()


def test_suppression_dans_la_source_conservee_dans_la_sauvegarde():
    s3 = _s3()
    _tout(s3)
    del s3.b["public"]["tracks/a.mp3"]  # effacé côté source (accident)
    _tout(s3)
    assert "public/tracks/a.mp3" in s3.b["sauvegarde"]


def test_limite_reporte_le_reste():
    s3 = _s3()
    pub, _ = _tout(s3, limite=1)
    assert pub.copies == 1 and pub.reportes == 2
    pub, _ = _tout(s3)
    assert pub.copies == 2


def test_repli_lecture_ecriture_si_copie_directe_refusee():
    s3 = _s3()
    s3.copie_directe_ok = False
    pub, priv = _tout(s3)
    assert pub.copies == 3 and pub.echecs == 0
    assert s3.b["sauvegarde"]["prive/images/originals/o.png"]["data"] == b"original"


def test_bucket_illisible_compte_comme_echec():
    s3 = _s3()
    del s3.b["prive"]  # droits manquants / bucket absent
    pub, priv = _tout(s3)
    assert pub.copies == 3
    assert priv.echecs == 1 and priv.erreurs


@pytest.mark.parametrize("pub,priv,sauv", [
    ("public", "prive", None),        # pas de bucket de sauvegarde
    ("public", "prive", "public"),    # sauvegarde == source publique
    ("public", "prive", "prive"),     # sauvegarde == source privée
    (None, None, "sauvegarde"),       # aucune source
])
def test_configuration_dangereuse_refusee(pub, priv, sauv):
    with pytest.raises(mb.ConfigurationSauvegardeInvalide):
        mb.plan_de_sauvegarde(bucket_public=pub, bucket_prive=priv, bucket_sauvegarde=sauv)


def test_sans_bucket_prive_distinct_un_seul_passage():
    plan = mb.plan_de_sauvegarde(
        bucket_public="public", bucket_prive="public", bucket_sauvegarde="s"
    )
    assert plan == [("public", "public/")]


# ── Restauration d'un objet ────────────────────────────────────────────────

def _restaurer(s3, cle, origine="public", **kw):
    return mb.restaurer_objet(
        s3, cle=cle, origine=origine, bucket_public="public",
        bucket_prive="prive", bucket_sauvegarde="sauvegarde", **kw,
    )


def test_restaurer_un_objet_perdu():
    s3 = _s3()
    _tout(s3)
    del s3.b["public"]["tracks/a.mp3"]
    msg = _restaurer(s3, "tracks/a.mp3")
    assert "Restauré" in msg
    assert s3.b["public"]["tracks/a.mp3"]["data"] == b"aaaa"
    del s3.b["prive"]["images/originals/o.png"]
    _restaurer(s3, "images/originals/o.png", origine="prive")
    assert s3.b["prive"]["images/originals/o.png"]["data"] == b"original"


def test_restaurer_n_ecrase_pas_sans_option():
    s3 = _s3()
    _tout(s3)
    s3._ecrire("public", "tracks/a.mp3", b"version-actuelle", "audio/mpeg")
    with pytest.raises(FileExistsError):
        _restaurer(s3, "tracks/a.mp3")
    assert s3.b["public"]["tracks/a.mp3"]["data"] == b"version-actuelle"
    _restaurer(s3, "tracks/a.mp3", ecraser=True)
    assert s3.b["public"]["tracks/a.mp3"]["data"] == b"aaaa"


def test_restaurer_essai_et_absent():
    s3 = _s3()
    _tout(s3)
    del s3.b["public"]["tracks/a.mp3"]
    assert "[essai]" in _restaurer(s3, "tracks/a.mp3", dry_run=True)
    assert "tracks/a.mp3" not in s3.b["public"]
    with pytest.raises(FileNotFoundError):
        _restaurer(s3, "tracks/jamais-sauvegarde.mp3")


# ── Commande en ligne ──────────────────────────────────────────────────────

@pytest.fixture
def env_r2(monkeypatch):
    for k in ("R2_ACCESS_KEY_ID", "R2_ACCESS_KEY", "R2_SECRET_ACCESS_KEY",
              "R2_SECRET_KEY", "R2_ENDPOINT_URL", "R2_ACCOUNT_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("R2_BUCKET", "public")
    monkeypatch.setenv("R2_PRIVATE_BUCKET", "prive")
    monkeypatch.setenv("R2_BACKUP_BUCKET", "sauvegarde")


def test_cli_sauvegarde_puis_restauration(env_r2, capsys):
    s3 = _s3()
    assert cli.main(["sauvegarder", "--dry-run"], client=s3) == 0
    assert s3.b["sauvegarde"] == {}
    assert cli.main(["sauvegarder"], client=s3) == 0
    sortie = capsys.readouterr().out
    assert "Sauvegarde des médias" in sortie and '"copies": 3' in sortie
    del s3.b["public"]["tracks/b.wav"]
    assert cli.main(["restaurer", "tracks/b.wav", "--origine", "public"], client=s3) == 0
    assert "tracks/b.wav" in s3.b["public"]
    assert cli.main(["restaurer", "tracks/b.wav"], client=s3) == 1  # existe déjà


def test_cli_sans_bucket_de_sauvegarde(env_r2, monkeypatch, capsys):
    monkeypatch.delenv("R2_BACKUP_BUCKET")
    assert cli.main(["sauvegarder"], client=_s3()) == 1
    assert "R2_BACKUP_BUCKET" in capsys.readouterr().out


def test_cli_identifiants_absents(env_r2, capsys):
    assert cli.main(["sauvegarder"]) == 1
    assert "identifiants R2 incomplets" in capsys.readouterr().out


def test_cli_echec_de_copie_code_retour_1(env_r2):
    s3 = _s3()
    s3.copie_directe_ok = False
    s3.upload_fileobj = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("réseau"))
    assert cli.main(["sauvegarder"], client=s3) == 1


def test_config_depuis_env_noms_legacy(monkeypatch, env_r2):
    monkeypatch.setenv("R2_ACCESS_KEY", "ak")
    monkeypatch.setenv("R2_SECRET_KEY", "sk")
    monkeypatch.setenv("R2_ACCOUNT_ID", "compte")
    cfg = cli.config_depuis_env()
    assert cfg["access_key"] == "ak" and cfg["secret_key"] == "sk"
    assert cfg["endpoint"] == "https://compte.r2.cloudflarestorage.com"


def test_module_sans_suppression():
    """Le code de sauvegarde n'appelle jamais une suppression."""
    src = Path(mb.__file__).read_text(encoding="utf-8")
    assert "delete_object" not in src.replace("JAMAIS delete_object", "")
    assert "delete_objects" not in src
