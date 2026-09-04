"""
S-09 sécurité (2026-09-02) — garde-fou SECRET_KEY (audit A §M1).

Le JWT est signé HS256 avec `SECRET_KEY` : qui la connaît forge un jeton pour
n'importe quel compte, compte officiel compris. L'ancienne garde de
`main.py` ne refusait QUE la valeur littérale
`dev-secret-change-in-production` — donc `cp .env.example .env`
(`SECRET_KEY=change-this-to-a-long-random-string`) démarrait le serveur, et la
CI signait avec `ci-flask-secret` (15 octets, sous le seuil PyJWT de 32).

Tests DB-free : ils portent sur la fonction pure `assert_secret_key_strong`
et sur le contenu du `.env.example` livré.
"""
from pathlib import Path

import pytest

from app.config import (
    SECRET_KEY_MIN_BYTES,
    _WEAK_SECRETS,
    assert_secret_key_strong,
)


@pytest.mark.parametrize(
    "weak",
    [
        "",
        "   ",
        None,
        "dev-secret-change-in-production",
        "change-this-to-a-long-random-string",   # .env.example d'avant S-09
        "CHANGE-THIS-TO-A-LONG-RANDOM-STRING",   # insensible à la casse
        "ci-flask-secret",                       # clé CI d'avant L-01
        "changeme",
        "secret",
        # Assez longue (≥ 32 octets) mais contient "change" → placeholder.
        "please-change-me-before-going-to-prod-0123456789",
    ],
)
async def test_rejette_placeholder(weak):
    with pytest.raises(RuntimeError):
        assert_secret_key_strong(weak)


@pytest.mark.parametrize("n", [1, 8, 15, SECRET_KEY_MIN_BYTES - 1])
async def test_rejette_moins_de_32_octets(n):
    with pytest.raises(RuntimeError) as exc:
        assert_secret_key_strong("a" * n)
    assert "32" in str(exc.value)


async def test_compte_en_octets_pas_en_caracteres():
    """31 caractères non-ASCII font > 32 octets : la mesure est en octets."""
    # 20 caractères é = 40 octets en UTF-8 → accepté.
    assert_secret_key_strong("é" * 20)
    # 20 caractères ASCII = 20 octets → refusé.
    with pytest.raises(RuntimeError):
        assert_secret_key_strong("a" * 20)


@pytest.mark.parametrize(
    "strong",
    [
        "a" * SECRET_KEY_MIN_BYTES,
        "wY3n_QoVbz8kx2-JhP1sRt5UfA7dLmEc9NgZvB0iXqKw",   # token_urlsafe(32)
        "  " + "b" * 40 + "  ",                            # espaces rognés
    ],
)
async def test_accepte_cle_forte(strong):
    assert assert_secret_key_strong(strong) is None


async def test_env_example_ne_livre_plus_de_placeholder():
    """`cp .env.example .env` ne doit plus produire une clé qui démarre."""
    env_example = Path(__file__).resolve().parents[2] / ".env.example"
    lines = [
        ln.strip() for ln in env_example.read_text(encoding="utf-8").splitlines()
        if ln.strip().startswith("SECRET_KEY=")
    ]
    assert lines == ["SECRET_KEY="], lines
    value = lines[0].split("=", 1)[1]
    with pytest.raises(RuntimeError):
        assert_secret_key_strong(value)


async def test_liste_des_placeholders_est_normalisee_en_minuscules():
    """Garde-fou : la comparaison se fait sur key.lower()."""
    assert all(w == w.lower() for w in _WEAK_SECRETS)


async def test_avertissement_pyjwt_est_promu_en_erreur():
    """Le filtre de pytest.ini doit pointer une classe qui existe vraiment.

    `jwt.warnings.InsecureKeyLengthWarning` (pas `jwt.exceptions.*`) : un
    chemin erroné fait échouer pytest au parsing de sa configuration.
    """
    import configparser
    import jwt.warnings

    assert issubclass(jwt.warnings.InsecureKeyLengthWarning, Warning)

    cfg = configparser.ConfigParser()
    cfg.read(Path(__file__).resolve().parents[1] / "pytest.ini")
    filters = cfg["pytest"]["filterwarnings"].split()
    assert "error::jwt.warnings.InsecureKeyLengthWarning" in filters, filters
