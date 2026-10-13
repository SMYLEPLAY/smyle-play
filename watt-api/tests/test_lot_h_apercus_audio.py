"""Lot H — écoute publique en version légère, original réservé aux acheteurs.

1. Conversion : un WAV devient un MP3 128 kb/s (ffmpeg), sans métadonnées.
2. Protection d'un son : version d'écoute + original sous clé secrète, base
   mise à jour, ancienne adresse supprimée seulement après le délai.
3. Le proxy d'écoute refuse l'original d'un son protégé, sert la version
   d'écoute ; aucune liste publique ne renvoie la clé de l'original.
4. Rattrapage : chaque son pas encore protégé est inscrit une seule fois ;
   la publication d'un son inscrit sa protection.
"""
import io
import math
import shutil
import struct
import uuid
import wave

import pytest
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal

from tests.test_lot_a_securite import _cleanup, _user
from tests.test_parcours_v1 import _oeuvre

pytestmark = pytest.mark.asyncio(loop_scope="session")

FFMPEG = shutil.which("ffmpeg") is not None


def _wav(secondes: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        frames = bytearray()
        for i in range(int(44100 * secondes)):
            v = int(12000 * math.sin(2 * math.pi * 440 * i / 44100))
            frames += struct.pack("<hh", v, v)
        w.writeframes(bytes(frames))
    return buf.getvalue()


class _Absent(Exception):
    def __init__(self):
        super().__init__("NoSuchKey")
        self.response = {"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}}


class _Corps:
    def __init__(self, data):
        self._d = data

    def read(self):
        return self._d


class _S3Memoire:
    """Doublure du client boto3 : {bucket: {clé: octets}}."""

    def __init__(self):
        self.b: dict[str, dict[str, bytes]] = {}

    def _bk(self, bucket):
        return self.b.setdefault(bucket, {})

    def get_object(self, Bucket, Key):
        if Key not in self._bk(Bucket):
            raise _Absent()
        return {"Body": _Corps(self._bk(Bucket)[Key])}

    def head_object(self, Bucket, Key):
        if Key not in self._bk(Bucket):
            raise _Absent()
        return {"ContentLength": len(self._bk(Bucket)[Key])}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self._bk(Bucket)[Key] = bytes(Body)

    def copy_object(self, Bucket, Key, CopySource):
        src = self._bk(CopySource["Bucket"])
        if CopySource["Key"] not in src:
            raise _Absent()
        self._bk(Bucket)[Key] = src[CopySource["Key"]]

    def delete_object(self, Bucket, Key):
        self._bk(Bucket).pop(Key, None)


def _brancher(monkeypatch) -> _S3Memoire:
    from app.services import r2

    s3 = _S3Memoire()
    monkeypatch.setattr(r2, "is_configured", lambda: True)
    monkeypatch.setattr(r2, "get_r2_client", lambda: s3)
    return s3


async def _sql(sql: str, **p):
    async with SessionLocal() as db:
        res = await db.execute(text(sql), p)
        try:
            rows = res.all()
        except Exception:  # noqa: BLE001
            rows = None
        await db.commit()
        return rows


# ═══ 1. Conversion ═══════════════════════════════════════════════════════════

@pytest.mark.skipif(not FFMPEG, reason="ffmpeg absent")
def test_fabriquer_apercu_produit_un_mp3():
    from app.services.apercu_audio import fabriquer_apercu

    mp3, ext, mime = fabriquer_apercu(_wav(2.0), "wav")
    assert (ext, mime) == ("mp3", "audio/mpeg")
    assert len(mp3) > 1024
    # Trame MPEG (0xFFE…) dès le début : pas d'étiquette ID3 (métadonnées retirées).
    assert mp3[:3] != b"ID3"
    assert mp3[0] == 0xFF and (mp3[1] & 0xE0) == 0xE0


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg absent")
def test_secours_aac_si_pas_d_encodeur_mp3(monkeypatch):
    from app.services import apercu_audio

    faux = (("mp3", "audio/mpeg", ["-c:a", "encodeur_inexistant"]),) + apercu_audio._FORMATS[1:]
    monkeypatch.setattr(apercu_audio, "_FORMATS", faux)
    data, ext, mime = apercu_audio.fabriquer_apercu(_wav(1.0), "wav")
    assert (ext, mime) == ("m4a", "audio/mp4") and len(data) > 1024


def test_fabriquer_apercu_refuse_un_fichier_illisible():
    from app.services.apercu_audio import ConversionImpossible, OutilAudioAbsent, fabriquer_apercu

    with pytest.raises((ConversionImpossible, OutilAudioAbsent)):
        fabriquer_apercu(b"pas un son" * 50, "wav")


def test_nouvelles_cles_restent_dans_le_dossier_du_compte():
    from app.services.apercu_audio import nouvelle_cle, url_ecoute
    from app.services.media_ownership import key_owned_by

    uid = uuid.uuid4()
    cle = f"tracks/{uid}/mon-son-abc123.wav"
    hd = nouvelle_cle(cle, "hd", "wav")
    ap = nouvelle_cle(cle, "apercu", "mp3")
    assert hd.startswith(f"tracks/{uid}/hd-") and hd.endswith(".wav")
    assert ap.startswith(f"tracks/{uid}/apercu-") and ap.endswith(".mp3")
    assert len(hd.rsplit("-", 1)[-1].split(".")[0]) == 32  # 128 bits aléatoires
    assert key_owned_by(hd, uid) and key_owned_by(ap, uid)
    assert url_ecoute("NIGHT CITY/apercu-x.mp3") == "/watt/stream/NIGHT%20CITY/apercu-x.mp3"


# ═══ 2. Protection d'un son ══════════════════════════════════════════════════

@pytest.mark.skipif(not FFMPEG, reason="ffmpeg absent")
async def test_proteger_un_son_puis_supprimer_l_ancienne_adresse(monkeypatch):
    from app.services.fichiers_a_traiter import programmer, traiter_en_attente

    s3 = _brancher(monkeypatch)
    pub = settings.R2_BUCKET
    a = await _user()
    try:
        o = await _oeuvre(a["id"])
        original = _wav(1.5)
        s3._bk(pub)[o["key"]] = original
        async with SessionLocal() as db:
            ids = await programmer(db, [o["key"]], "proteger_audio")
            await db.commit()
        res = await traiter_en_attente(ids)
        assert res["faites"] == 1, res

        t = (await _sql("SELECT r2_key, apercu_key, audio_url FROM tracks WHERE id = :i",
                        i=o["track"]))[0]
        assert t.apercu_key and t.r2_key != o["key"]
        assert t.audio_url == f"/watt/stream/{t.apercu_key}"
        assert s3._bk(pub)[t.r2_key] == original           # original intact, clé secrète
        assert s3._bk(pub)[t.apercu_key][:1] == b"\xff"     # version d'écoute MP3
        assert o["key"] in s3._bk(pub)                       # ancienne adresse : pas encore

        # Relancer ne refait rien.
        async with SessionLocal() as db:
            ids2 = await programmer(db, [t.r2_key], "proteger_audio")
            await db.commit()
        await traiter_en_attente(ids2)
        r = await _sql("SELECT resultat FROM fichiers_a_traiter WHERE id = ANY(:i)", i=ids2)
        assert r[0].resultat == "deja_protege"

        # Avant le délai : la suppression de l'ancienne adresse attend.
        await traiter_en_attente()
        assert o["key"] in s3._bk(pub)
        # Après le délai : supprimée (plus rien ne la désigne).
        await _sql("UPDATE fichiers_a_traiter SET cree_le = now() - interval '4 days' "
                   "WHERE cle = :k AND motif = 'ancien_original'", k=o["key"])
        await traiter_en_attente()
        assert o["key"] not in s3._bk(pub)
        assert t.r2_key in s3._bk(pub) and t.apercu_key in s3._bk(pub)
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE cle LIKE :m", m=f"%{a['id']}%")
        await _cleanup(a["id"])


async def test_sans_ffmpeg_la_protection_reste_en_attente(monkeypatch):
    from app.services import apercu_audio
    from app.services.fichiers_a_traiter import programmer, traiter_en_attente

    s3 = _brancher(monkeypatch)
    monkeypatch.setattr(apercu_audio.shutil, "which", lambda _n: None)
    a = await _user()
    try:
        o = await _oeuvre(a["id"])
        s3._bk(settings.R2_BUCKET)[o["key"]] = _wav(0.5)
        async with SessionLocal() as db:
            ids = await programmer(db, [o["key"]], "proteger_audio")
            await db.commit()
        res = await traiter_en_attente(ids)
        assert res["en_attente"] == 1
        t = (await _sql("SELECT r2_key, apercu_key FROM tracks WHERE id = :i", i=o["track"]))[0]
        assert t.r2_key == o["key"] and t.apercu_key is None
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE cle LIKE :m", m=f"%{a['id']}%")
        await _cleanup(a["id"])


# ═══ 3. Écoute et listes publiques ═══════════════════════════════════════════

async def test_proxy_refuse_l_original_et_sert_l_ecoute(client, monkeypatch):
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://pub-test.r2.dev")
    a = await _user()
    try:
        o = await _oeuvre(a["id"])
        hd = f"tracks/{a['id']}/hd-{uuid.uuid4().hex}.wav"
        ap = f"tracks/{a['id']}/apercu-{uuid.uuid4().hex}.mp3"
        await _sql("UPDATE tracks SET r2_key = :hd, apercu_key = :ap, audio_url = :u WHERE id = :i",
                   hd=hd, ap=ap, u=f"/watt/stream/{ap}", i=o["track"])
        r = await client.get(f"/watt/stream/{hd}", follow_redirects=False)
        assert r.status_code == 404
        r = await client.get(f"/watt/stream/{ap}", follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].endswith(ap)

        # Page publique de l'Œuvre et catalogue : jamais la clé de l'original.
        r = await client.get(f"/watt/oeuvres/{o['image']}")
        assert r.status_code == 200 and hd not in r.text and ap in r.text
        r = await client.get("/watt/tracks-recent", params={"limit": 100})
        assert hd not in r.text
    finally:
        await _cleanup(a["id"])


def test_trackread_ecoute_la_version_legere():
    from datetime import datetime, timezone

    from app.schemas.track import TrackRead

    t = TrackRead(id=uuid.uuid4(), title="x", audio_url="/watt/stream/a/apercu-1.mp3",
                  r2_key="a/hd-secret.wav", apercu_key="a/apercu-1.mp3", color=None,
                  created_at=datetime.now(timezone.utc))
    d = t.model_dump()
    assert d["stream_url"] == "/watt/stream/a/apercu-1.mp3"
    assert "r2_key" not in d and "apercu_key" not in d


# ═══ 4. Rattrapage et publication ════════════════════════════════════════════

async def test_rattrapage_inscrit_chaque_son_une_seule_fois():
    from app.services.apercu_audio import programmer_protections_manquantes

    a = await _user()
    try:
        o = await _oeuvre(a["id"])
        async with SessionLocal() as db:
            await programmer_protections_manquantes(db)
            await db.commit()
        async with SessionLocal() as db:
            await programmer_protections_manquantes(db)
            await db.commit()
        rows = await _sql("SELECT count(*) AS n FROM fichiers_a_traiter WHERE cle = :k "
                          "AND action = 'proteger_audio' AND fait_le IS NULL", k=o["key"])
        assert rows[0].n == 1
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE action = 'proteger_audio' AND fait_le IS NULL")
        await _cleanup(a["id"])


async def test_publier_un_son_programme_sa_protection(client):
    from tests.test_lot_a_securite import _login

    a = await _user()
    try:
        h = await _login(client, a["email"])
        cle = f"tracks/{a['id']}/son-0123abcd.mp3"
        r = await client.post("/tracks/", headers=h, json={
            "title": "Son", "full_prompt": "deep house", "platform": "suno", "r2_key": cle,
            "cover_url": f"/watt/images/images/track-cover/{a['id']}/c.png"})
        assert r.status_code == 201, r.text
        rows = await _sql("SELECT action FROM fichiers_a_traiter WHERE cle = :k", k=cle)
        assert [x.action for x in rows] == ["proteger_audio"]
    finally:
        await _sql("DELETE FROM fichiers_a_traiter WHERE cle LIKE :m", m=f"%{a['id']}%")
        await _cleanup(a["id"])
