---
title: Dette technique
type: dette
tags: [technique, dette, bloquant]
updated: 2026-04-21
---

# Dette technique

> Source : session [[2026-04-21_deploy-api]] + `SMYLEPLAY_STATE_2026-04-18.md` (archivé).

## Stratégie long terme

**Objectif** : éliminer Flask à terme. La coexistence FastAPI + Flask via `a2wsgi` est une étape de transition, pas une cible.

**Entry point production** : `main.py` (uvicorn) → monte FastAPI + mount Flask sur `/`. Documentation dans [[Deploy]].

Tant que Flask existe, les points D1, D2, D7, D8 sont actifs. La séquence de résolution cible est : D3 (CI) → D5 (tests) → D6 (staging) → D1/D8 (migration complète FastAPI) → suppression Flask.

## Critique — à traiter avant toute nouvelle feature

### D1. Modèles Flask legacy avec `INTEGER id`
- **Impact** : incompatible avec le schéma FastAPI (`UUID id`). Routes `/api/*` qui manipulent `artists`, `watt_tracks`, etc. vont crasher au runtime.
- **Options** :
  1. Migrer les modèles Flask en UUID (migration Alembic + adaptation modèles).
  2. Réécrire les routes `/api/*` concernées en FastAPI → route la plus propre long terme.
- **Décision à prendre** : voir [[2026-04-21#3. Dette Flask legacy]].
- Tags : `#bloquant` `#flask` `#uuid`

### D2. Table `artists` Flask-only inexistante en prod
- Routes Flask qui querient `artists` → 500 garanti.
- Bloquer les routes concernées tant que D1 non traité.

### D3. ~~Pas de CI sur migrations~~ ✅ Résolu 2026-04-21
- **Impact initial** : chaque push était une roulette russe (cf. 9 fixes en une soirée).
- **Solution livrée** : `.github/workflows/ci.yml` avec 2 jobs (migrations + smoke test `/health`).
- **Validation** : premier run vert sur `main` 2026-04-21 (commit `cf0fa48`).
- **Branch protection** : active sur `main` avec 2 status checks requis.
- **Runbook** : [[CI_migrations]]

## Moyen — à planifier

### D4. Seed Smyle non-loginable
- Compte `smyle@smyleplay.com` a un password random inconnu (token_urlsafe 48).
- Créer script `admin_set_password.py` utilitaire.

### D5. Pas de tests automatisés
- Smoke test minimum : `/health`, login, upload track.
- Pytest + FastAPI TestClient.

### D6. Pas d'env staging
- Tout est testé en prod actuellement → risqué.
- Dupliquer service Railway en `staging` avec Postgres séparé.

### D7. Flask `ensure_schema()` résiduel
- Désactivé sur Postgres en prod mais encore présent dans le code.
- À supprimer complètement une fois D1 traité.

### D8. Refactor backend → `backend/{api,flask,agents}/`
- **Contexte** : la racine contient `smyleplay-api/`, `flask_app.py`, `agents/`, `main.py`, `models.py`, `config.py` → mélange API / Flask / agents / config.
- **Impact d'un refactor non préparé** :
  - Imports Python cassés (`from smyleplay_api.app.*`, `from flask_app import ...`, `from agents.*`)
  - `railway.toml` : `preDeployCommand = "cd smyleplay-api && alembic upgrade head"` → chemin à adapter
  - `main.py` : `from flask_app import app as flask_app` → à adapter
  - Graphify à rebuild (chemins changent)
  - Historique git : renames massifs → blame/log dégradés si pas `git mv`
- **Plan de migration (branche `refactor/backend-layout`)** :
  1. Créer `backend/` avec `api/` (ex-`smyleplay-api/`), `flask/` (ex-`flask_app.py` + `models.py` + `config.py`), `agents/` (ex-`agents/`).
  2. `git mv` systématique pour préserver l'historique.
  3. Adapter `main.py` (imports) + `railway.toml` (preDeployCommand).
  4. Adapter les `import` internes (sed global).
  5. Lancer full test suite + migration Alembic dry-run.
  6. Deploy sur env **staging** (cf D6) → smoke test.
  7. Merge main + deploy prod.
  8. Rebuild graphify.
- **Prérequis** : D3 (CI migrations) + D5 (smoke tests) + D6 (staging env) opérationnels avant.
- **Estimation** : 1/2 journée + 1/2 journée validation staging.
- **Ne pas faire tant que** la prod est le seul environnement testé.
- Tags : `#refactor` `#backend` `#non-bloquant` `#nécessite-staging`

## Décisions architecturales gravées

### ADR-001 — Profil artiste : édition sur /dashboard, vue sur /u/<slug>
- **Date** : 2026-04-21 (confirme Phase 5 du 2026-04-20)
- **Contexte** : le code a hésité entre 2 architectures (édition inline sur `/u/<slug>` vs édition sur `/dashboard`). Les deux surfaces ont coexisté pendant une période → dette UX + risque de désync.
- **Décision** :
  - **`/dashboard#sec-identity`** = **UNIQUE** lieu d'édition/création du profil (atelier). Section en accordéon dérouleable.
  - **`/u/<slug>`** = vue publique 100% lecture seule (boutique). Aucune édition inline.
  - **`/u/<slug>` owner sans nom** → redirect auto vers `/dashboard#sec-identity`.
  - **`/u/<slug>` owner avec nom mais !publié** → preview + bouton "Publier mon profil" (POST `/watt/me/profile/publish`).
- **Conséquences** :
  - `artiste.js` : mode édition inline neutralisé (`toggleOwnerEdit` redirige).
  - Bouton "Modifier" sur `/u/<slug>` → renommé "Éditer dans le dashboard" + redirige.
  - `dashboard.js` : seul détenteur du PATCH `/users/me` pour les champs profil.
- **Signal de régression** : si un PATCH `/users/me` apparaît dans `artiste.js`, on reprend la dette.
- Tags : `#adr` `#profil` `#ux`

## Liens
- [[Bugs_connus]]
- [[Roadmap#Sprint stabilisation]]
- [[2026-04-21_deploy-api]]
