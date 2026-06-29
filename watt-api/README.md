# Smyle Play API

Backend FastAPI du projet Smyle Play.

## Phase 1 — Fondation

Cette phase pose uniquement la base technique du projet. Aucune logique metier
n'est implementee volontairement. La structure doit rester intacte pour
accueillir les modules critiques des phases suivantes (auth, tracks, DNA,
marketplace, credits).

## Pre-requis

- Python 3.11
- Docker / docker-compose (optionnel pour le dev local)

## Installation locale

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -e .[dev]
```

## Lancer le serveur

```bash
uvicorn app.main:app --reload
```

Endpoints utiles :

- `GET /` -> health check (`{"status": "ok"}`)
- `GET /docs` -> Swagger UI auto-genere

## Structure

```
app/
  auth/        # authentification (Clerk, middleware)
  core/        # utilitaires transverses (errors, logging)
  models/      # modeles SQLAlchemy
  routers/     # endpoints HTTP
  schemas/     # schemas Pydantic (I/O)
  services/    # logique metier
alembic/       # migrations DB
tests/         # tests pytest
```

## Docker

```bash
docker compose up --build
```

## Regles de la Phase 1

- Pas de logique metier
- Pas de DB branchee
- Pas d'auth
- Pas d'endpoint avance
- Ne pas modifier l'arborescence
