---
title: Bugs connus
type: bug-tracker
tags: [bug, produit]
updated: 2026-04-21
---

# Bugs connus

## Ouverts

### B1. Routes `/api/*` Flask → crash potentiel
- Cause racine : [[Dette_technique#D1. Modèles Flask legacy avec `INTEGER id`]]
- Statut : non reproductible tant que pas de trafic réel, mais bombe à retardement.
- Action : inventaire + décision migration vs réécriture.

### B2. Seed Smyle non-loginable
- Voir [[Dette_technique#D4. Seed Smyle non-loginable]]

## Résolus — session 2026-04-21
Voir [[2026-04-21_deploy-api]] pour le détail des 9 fixes :
1. Flask + FastAPI en 2 process → unifié via `a2wsgi`
2. Collision package `app/` vs `app.py` → renommé `flask_app.py`
3. `DATABASE_URL` mal formatée → normalisée `postgresql+asyncpg://`
4. Clerk vars obligatoires → optionnelles
5. Table `tracks` jamais créée → migration `0010b`
6. Bcrypt > 72 octets → truncate
7. Colonnes `users` manquantes → migration `0021b`
8. UUID `id` non fourni dans INSERT seed → fix
9. Flask `db.create_all()` écrasait le schéma → désactivé en prod

## Observabilité
Pas encore de Sentry → les bugs runtime ne remontent pas.
Voir [[Roadmap#Sprint stabilisation]].
