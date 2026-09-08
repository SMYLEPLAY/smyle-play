"""Hygiène de configuration — `.env.example` ne doit jamais dériver du code.

D20 (2026-09-08). Trois réglages réellement lus par l'application vivaient
hors de `.env.example` : `PUBLIC_BASE_URL` (garde-fou S-10 contre
l'empoisonnement du lien de réinitialisation via l'en-tête `Host`),
`SHOW_ACHAT_SMYLES` et `SHOW_EUROS` (drapeaux du MODE LANCEMENT). Une variable
non documentée est une variable qu'on oublie de poser sur Railway : le défaut
du code s'applique en silence, et personne ne voit passer la régression.

Ce test compare donc ce que l'app LIT à ce que `.env.example` DOCUMENTE, dans
un seul sens : tout ce qui est lu doit être documenté. L'inverse n'est PAS
exigé — une clé de commodité (alias legacy, réglage d'un script hérité) peut
rester documentée sans être lue par `watt-api/app/`, et faire échouer le test
là-dessus pousserait à supprimer de la documentation utile.

Même modèle que `test_repo_public_hygiene.py` : on parcourt des fichiers du
dépôt, aucun accès base ni réseau.
"""

import re
from pathlib import Path

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
APP_DIR = REPO_ROOT / "watt-api" / "app"

# Variables INJECTÉES par la plateforme d'hébergement : elles n'ont rien à
# faire dans un `.env` local et ne sont donc pas exigées dans `.env.example`.
_FOURNIES_PAR_LA_PLATEFORME = {"RAILWAY_GIT_COMMIT_SHA"}

# `os.getenv("X")` / `os.environ.get("X")`, y compris derrière un import local
# aliasé (`import os as _os` dans app/routers/reports.py).
_LECTURE_ENV = re.compile(
    r"\b_?os\.(?:getenv|environ\.get)\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']"
)
# Une clé documentée est une ligne `CLE=` — commentée ou non : les alias
# legacy R2 sont volontairement documentés en commentaire.
_CLE_DOCUMENTEE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", re.MULTILINE)


def _cles_documentees() -> set[str]:
    assert ENV_EXAMPLE.is_file(), ".env.example introuvable à la racine du dépôt"
    return set(_CLE_DOCUMENTEE.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def test_les_reglages_de_settings_sont_documentes():
    """`app/config.py` est la source de vérité des réglages : chaque champ de
    `Settings` doit apparaître dans `.env.example`, sinon le réglage n'est
    connu que de celui qui l'a écrit."""
    documentees = _cles_documentees()
    manquantes = sorted(set(Settings.model_fields) - documentees)
    assert not manquantes, (
        "réglages de app/config.py absents de .env.example : "
        f"{manquantes} — documente-les (nom, rôle, valeur par défaut)."
    )


def test_les_variables_lues_par_le_code_sont_documentees():
    """Tout ce que `watt-api/app/` lit par `os.getenv` doit être documenté :
    ces variables-là échappent à `Settings`, donc à la relecture."""
    documentees = _cles_documentees()
    manquantes: dict[str, str] = {}
    for chemin in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in chemin.parts:
            continue
        for nom in _LECTURE_ENV.findall(chemin.read_text(encoding="utf-8")):
            if nom in documentees or nom in _FOURNIES_PAR_LA_PLATEFORME:
                continue
            manquantes.setdefault(nom, str(chemin.relative_to(REPO_ROOT)))
    assert not manquantes, (
        "variables lues par l'app mais absentes de .env.example : "
        f"{manquantes}"
    )
