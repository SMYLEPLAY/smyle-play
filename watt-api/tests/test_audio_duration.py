"""P2 durée audio — test DB-free du calcul de durée à l'upload."""

import io
import struct
import wave

from app.routers.watt_compat import _audio_duration_seconds


def _make_wav(seconds: float, framerate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        n = int(seconds * framerate)
        w.writeframes(struct.pack("<" + "h" * n, *([0] * n)))
    return buf.getvalue()


def test_duration_wav_2s():
    d = _audio_duration_seconds(_make_wav(2.0))
    assert d is not None
    assert abs(d - 2.0) < 0.1


def test_duration_donnees_invalides():
    # Bytes non-audio → None, jamais d'exception (best-effort strict).
    assert _audio_duration_seconds(b"pas de l'audio du tout") is None


def test_duration_vide():
    assert _audio_duration_seconds(b"") is None
