"""Accès d'un ACHETEUR à l'audio d'un son retiré par son créateur.

Parcours V1 (règle de protection des acheteurs, décision Tom du 9/10/2026) :
masquer, changer le prix ou supprimer une Œuvre ne retire JAMAIS l'accès de
ceux qui l'ont payée. Or un son supprimé par son créateur ne s'écoute plus par
sa clé (Lot A, E3) — y compris pour ses acheteurs.

Le lecteur audio (balise <audio>) ne peut pas envoyer de jeton de connexion :
la bibliothèque de l'acheteur reçoit donc une adresse d'écoute SIGNÉE
(`/watt/stream/<clé>?acces=<expiration>.<signature>`). Le proxy audio sert un
son supprimé par son créateur uniquement avec une signature valide pour CETTE
clé. Un son retiré par la MODÉRATION reste coupé pour tout le monde.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote

from app.config import settings

DUREE_SECONDES = 7 * 24 * 3600
_PREFIXE = "/watt/stream/"


def _signature(cle: str, expiration: int) -> str:
    msg = f"acces-audio|{cle.lstrip('/')}|{expiration}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:32]


def signer(cle: str, *, maintenant: int | None = None) -> str:
    exp = int(maintenant if maintenant is not None else time.time()) + DUREE_SECONDES
    return f"{exp}.{_signature(cle, exp)}"


def verifier(cle: str, jeton: str | None, *, maintenant: int | None = None) -> bool:
    if not jeton or "." not in jeton:
        return False
    exp_txt, sig = jeton.split(".", 1)
    try:
        exp = int(exp_txt)
    except ValueError:
        return False
    if exp < int(maintenant if maintenant is not None else time.time()):
        return False
    return hmac.compare_digest(sig, _signature(cle, exp))


def url_acheteur(audio_url: str | None) -> str | None:
    """Ajoute la signature d'accès à une adresse d'écoute du proxy audio.
    Les autres adresses (stockage public direct, vide) sont rendues telles
    quelles."""
    if not audio_url or not audio_url.startswith(_PREFIXE) or "?" in audio_url:
        return audio_url
    from urllib.parse import unquote

    cle = unquote(audio_url[len(_PREFIXE):])
    return f"{audio_url}?acces={quote(signer(cle))}"
