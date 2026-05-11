---
title: Session 2026-04-21 — Déploiement API
type: session
date: 2026-04-21
tags: [session, deploy, api, railway]
status: done
---

# Session 2026-04-21 — Déploiement API

> Récap complet de la soirée de mise en prod. Source originale : `SESSION_2026-04-21_deploy-api.md` à la racine du projet.

## État final
- **URL prod** : https://web-production-e30c8c.up.railway.app
- **Stack** : FastAPI + Flask unifiés via `a2wsgi` (WSGIMiddleware), `uvicorn` sur Railway
- **DB** : Postgres Railway (service persistant)
- **Healthcheck** `/health` : 200 OK
- **Alembic** : chaîne complète, migrations passent de zéro

## Architecture

```
uvicorn main:app (port $PORT, 2 workers)
  └── main.py
      ├── FastAPI app (/health, /watt/*, /catalog/*, /auth/*)
      └── Flask app (monté sur "/" via a2wsgi.WSGIMiddleware)
              └── routes legacy: /api/*, /, /dashboard, /u/<slug>, static
```

**Règle** : Alembic gère tout le schéma. Flask ne touche plus aux tables en prod.

## 9 fixes appliqués
| # | Problème | Fix |
|---|---|---|
| 1 | Flask + FastAPI en 2 process | Unifié via `a2wsgi.WSGIMiddleware` |
| 2 | Collision package `app/` vs `app.py` | Renommé `flask_app.py` |
| 3 | `DATABASE_URL` mal formatée | Helper `_normalize_async_url()` |
| 4 | Clerk vars obligatoires | `CLERK_SECRET_KEY: str \| None = None` |
| 5 | Table `tracks` jamais créée | Migration `0010b` |
| 6 | Bcrypt > 72 octets | `token_urlsafe(48)[:72]` |
| 7 | Colonnes `users` manquantes | Migration `0021b` |
| 8 | UUID `id` non fourni INSERT seed | `uuid.uuid4()` bind param |
| 9 | Flask `db.create_all()` écrasait schéma | Désactivé en prod Postgres |

## Chaîne Alembic finale
```
34003a80bc2b → 4856b7981481 → b2fe0db4906d → 0009 → 0010 → 0010b (NEW)
→ 0011 → 0012 → 0013 → 0014 → 0015 → 0016 → 0017 → 0018 → 0019 → 0020
→ 0021 → 0021b (NEW) → 0022
```

## Config Railway retenue

`railway.toml` :
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2 --access-log"
preDeployCommand = "cd smyleplay-api && alembic upgrade head"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

Variables d'env :
- `DATABASE_URL` → `${{Postgres.DATABASE_URL}}`
- `JWT_SECRET` / `SECRET_KEY`
- `R2_ACCOUNT_ID` (ID seul, pas l'URL complète)
- `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET`, `R2_PUBLIC_URL`
- `CORS_ALLOWED_ORIGINS`

## Problèmes ouverts → [[Dette_technique]]
Voir spécifiquement :
- [[Dette_technique#D1. Modèles Flask legacy avec `INTEGER id`|D1 — Flask UUID]]
- [[Dette_technique#D3. Pas de CI sur migrations|D3 — CI migrations]]
- [[Dette_technique#D4. Seed Smyle non-loginable|D4 — Seed non-loginable]]

## Suite → [[2026-04-21]]
Plan du jour = sprint stabilisation.
