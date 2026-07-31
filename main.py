"""
SMYLE PLAY — Entry point (uvicorn)
──────────────────────────────────
P0-c « Sortie Flask » (2026-07-30) : Flask est SUPPRIMÉ. FastAPI (watt-api/)
sert tout : API, pages, statiques (cf. app/routers/pages.py).
Historique : l'unification backend (2026-07-20) puis la bascule flaggée
SERVE_STATIC_FROM_FASTAPI (P0-b) sont documentées dans
OBSIDIAN/01_PRODUIT/Dette_technique.md et dans l'historique git de ce fichier.

Lancement :
  uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
"""

import os
import sys

# Prioriser watt-api/ dans sys.path pour que `from app.main` résolve le
# package FastAPI. Le root reste accessible (config.py utilisé par les
# scripts locaux watcher/scanner).
_ROOT = os.path.dirname(os.path.abspath(__file__))
_API_DIR = os.path.join(_ROOT, "watt-api")
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)
if _ROOT not in sys.path:
    sys.path.insert(1, _ROOT)

from app.main import app  # noqa: E402, F401
