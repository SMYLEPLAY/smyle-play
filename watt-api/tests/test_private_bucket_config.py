"""Sécurité (2026-07-25) — bucket PRIVÉ des images originales payantes.

Vérifie la property `effective_private_bucket` de la config :
  - non défini (R2_PRIVATE_BUCKET=None) → retombe sur le bucket public
    (R2_BUCKET) : AUCUNE rupture avant que le bucket privé soit créé.
  - défini → retourne bien le bucket privé.

Test unitaire pur (pas de DB, pas de réseau) : on instancie Settings avec un
DATABASE_URL factice (champ requis) et on ne touche à rien d'autre.
"""
from app.config import Settings

_DUMMY_DB = "postgresql+asyncpg://x:x@localhost:5432/x"


def test_effective_private_bucket_fallback_sur_public_quand_absent():
    s = Settings(
        DATABASE_URL=_DUMMY_DB,
        R2_BUCKET="smyle-play-audio",
        R2_PRIVATE_BUCKET=None,
    )
    assert s.effective_private_bucket == s.R2_BUCKET
    assert s.effective_private_bucket == "smyle-play-audio"


def test_effective_private_bucket_utilise_le_prive_quand_defini():
    s = Settings(
        DATABASE_URL=_DUMMY_DB,
        R2_BUCKET="smyle-play-audio",
        R2_PRIVATE_BUCKET="smyle-play-originals-private",
    )
    assert s.effective_private_bucket == "smyle-play-originals-private"
    assert s.effective_private_bucket != s.R2_BUCKET
