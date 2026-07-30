"""
SMYLE PLAY — Entry point UNIFIÉ (uvicorn)
─────────────────────────────────────────
Architecture :
  ┌───────────────── FastAPI (ASGI) ─────────────────┐
  │  /health                   → healthcheck Railway │
  │  /watt/*                   → WATT API (JSON)     │
  │  /api/auth/*  (FastAPI)    → auth JWT moderne    │
  │  /marketplace/*, /catalog/*, /tracks/*, ...      │
  │                                                   │
  │  /  ── mount ──► Flask (WSGI via a2wsgi)         │
  │                  • sert index.html + statiques  │
  │                  • /api/* legacy (Flask)         │
  └──────────────────────────────────────────────────┘

Lancement :
  uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2

IMPORTANT : l'ordre du sys.path est critique.
  - le dossier de l'API DOIT être avant le root pour que `from app.main`
    résolve le package FastAPI et non le module renommé flask_app.

UNIFICATION BACKEND (2026-07-20)
  Jusqu'ici le point d'entrée importait `smyleplay-api/`, alors que les
  migrations Alembic tournaient depuis `watt-api/` (cf. railway.toml). Deux
  backends divergeaient (47 fichiers), et tout le travail fait dans watt-api/
  n'avait AUCUN effet en production.

  On bascule sur `watt-api/`, qui est la version complète et celle que les
  migrations alimentent — les modèles correspondent enfin au schéma réel.

  Vérifié avant bascule : les deux apps s'importent sans erreur · aucun router
  perdu (33 → 36) · 3 routers gagnés (reports/DSA, telemetry, the_plan) ·
  aucune variable de configuration supplémentaire requise.

  NB (2026-07-30, Sprint 0) : smyleplay-api/ a été retiré du repo —
  le rollback documenté ici n'est plus possible ; watt-api/ est le seul backend.
"""

import os
import sys

# 1) Prioriser le dossier de l'API dans sys.path pour l'import du package FastAPI
_ROOT = os.path.dirname(os.path.abspath(__file__))
_API_DIR = os.path.join(_ROOT, "watt-api")
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)
if _ROOT not in sys.path:
    sys.path.insert(1, _ROOT)  # pour `import flask_app`, `import config`, etc.

# 2) Import FastAPI app (package `app` = watt-api/app/)
from app.main import app as fastapi_app  # noqa: E402

# 3) Import Flask app (module `flask_app` = ./flask_app.py)
from flask_app import app as flask_app  # noqa: E402

# 4) Bridge ASGI↔WSGI — mount Flask comme fallback universel
from a2wsgi import WSGIMiddleware  # noqa: E402

# Toutes les routes FastAPI (déjà enregistrées via create_app) prennent
# précédence sur le mount. Le mount "/" attrape tout le reste → Flask.
fastapi_app.mount("/", WSGIMiddleware(flask_app))

# Export uvicorn
app = fastapi_app
