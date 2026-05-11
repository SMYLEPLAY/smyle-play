---
title: Runbook — CI migrations Alembic
type: runbook
tags: [technique, ci, alembic, runbook]
updated: 2026-04-21
---

# CI migrations Alembic

> Workflow : `.github/workflows/ci.yml`
> Déclencheurs : PR sur `main`, push sur `main`, manuel (`workflow_dispatch`).

## Objectif
Bloquer un merge si une migration Alembic casse sur une DB vierge, ou si l'app ne démarre pas.

## Ce que fait la CI

### Job 1 — `migrations`
1. Spawn Postgres 16 (service container).
2. `pip install -r requirements.txt`.
3. `alembic upgrade head` dans `smyleplay-api/`.
4. Dump `alembic current` + `alembic history`.
5. Vérifie que les tables critiques existent (`users`, `tracks`, `transactions`).

### Job 2 — `smoke-test`
1. Migrations (idem).
2. Start `uvicorn main:app` en background.
3. Poll `/health` pendant 30 s.
4. Upload `uvicorn.log` en artefact en cas d'échec.

## Pourquoi
- Reproduit le bug qu'on a eu 9 fois le 2026-04-20 : migration qui passe en local mais explose en prod.
- Attrape les imports cassés, les env vars manquantes, les packages collisions.
- Zéro accès au vrai Postgres prod.

## Activer la protection de branche

**Actions côté GitHub (une fois, à faire après merge du workflow)** :

1. Repo → Settings → Branches → Add branch protection rule.
2. Branch name pattern : `main`.
3. Cocher :
   - ✅ Require a pull request before merging
   - ✅ Require status checks to pass before merging
     - Rechercher et ajouter : `Alembic upgrade head (fresh Postgres)` + `Smoke test (/health)`
   - ✅ Require branches to be up to date before merging
4. Save.

→ Après ça, **impossible de merge en main sans CI verte**.

## Limitations connues
- Ne teste pas Sentry, R2, auth Clerk (vars absentes volontairement → l'app doit démarrer sans).
- Ne teste pas les routes authentifiées (pas de smoke test login → à ajouter plus tard [[../../01_PRODUIT/Dette_technique#D5. Pas de tests automatisés]]).
- Base de test éphémère → pas de test de backfill sur données réelles.

## Troubleshooting

### CI rouge sur `migrations`
1. Aller dans Actions → run échoué → job `migrations` → étape en erreur.
2. Si erreur sur `alembic upgrade head` : migration cassée ou chaînée à un revision inexistant.
3. Reproduire localement :
   ```bash
   docker run -d --rm --name pg-ci -e POSTGRES_USER=ci -e POSTGRES_PASSWORD=ci \
     -e POSTGRES_DB=smyleplay_ci -p 5432:5432 postgres:16
   DATABASE_URL=postgresql://ci:ci@localhost:5432/smyleplay_ci \
     bash -c 'cd smyleplay-api && alembic upgrade head'
   ```

### CI rouge sur `smoke-test`
1. Télécharger l'artefact `uvicorn-log`.
2. Chercher l'exception au démarrage.
3. Cas fréquents :
   - Env var manquante → compléter le bloc `env:` du job.
   - Import cassé → corriger le code.
   - DB locale vs prod : `_normalize_async_url` doit transformer `postgresql://` en `postgresql+asyncpg://`.

## Évolutions prévues
- [ ] Ajouter tests pytest (`smyleplay-api/tests/`).
- [ ] Smoke test endpoints auth (login/signup).
- [ ] Lint (ruff) + format (black) en pré-étape.
- [ ] Coverage minimum sur PR.

## Liens
- [[Deploy]] — runbook déploiement Railway
- [[../../01_PRODUIT/Dette_technique#D3. Pas de CI sur migrations]]
