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
  - smyleplay-api/ DOIT être avant le root pour que `from app.main`
    résolve le package FastAPI et non le module renommé flask_app.
"""

import os
import sys

# 1) Prioriser smyleplay-api/ dans sys.path pour l'import du package FastAPI
_ROOT = os.path.dirname(os.path.abspath(__file__))
_API_DIR = os.path.join(_ROOT, "smyleplay-api")
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)
if _ROOT not in sys.path:
    sys.path.insert(1, _ROOT)  # pour `import flask_app`, `import config`, etc.

# 2) Import FastAPI app (package `app` = smyleplay-api/app/)
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
