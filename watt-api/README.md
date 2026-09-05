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

## Administration — crediter un testeur en Smyles

Deux etapes. Le role admin (`users.is_admin`) est distinct du compte vitrine
« Smyle » (`is_official`) : il n'a aucun effet d'affichage.

**1. Se donner le role admin** (sur la machine d'ops, une seule fois) :

```bash
cd watt-api && python tools/make_admin.py tom@example.com
# --revoke pour retirer, --list pour voir les admins
```

**2. Crediter un testeur** (`user_id` = UUID du compte cible ; le token est
celui d'un compte admin, recupere via `POST /auth/login`) :

```bash
curl -X POST "https://<host>/admin/users/<USER_UUID>/credits" \
  -H "Authorization: Bearer <TOKEN_ADMIN>" \
  -H "Content-Type: application/json" \
  -d '{"credits": 500, "reason": "beta_tester"}'
```

Les Smyles sont credites dans le bucket `promo` (non encaissables, depenses en
premier). `credits` va de 1 a 10000, `reason` est obligatoire (<= 500 car.).
Reponses : 201 (ok), 403 (pas admin), 404 (compte inconnu), 400 (compte
suspendu ou supprime), 422 (bornes).

Relire les credits accordes (l'audit est la ligne `transactions`, append-only,
qui porte `granted_by` / `granted_by_email` / `source`) :

```bash
curl "https://<host>/admin/grants?limit=50" -H "Authorization: Bearer <TOKEN_ADMIN>"
```
