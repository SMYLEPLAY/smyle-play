---
title: Brief session pair-programming — Smyleplay
type: runbook
tags: [runbook, onboarding, pair-programming, session]
updated: 2026-04-22
---

# Brief session pair-programming — Smyleplay

> Document destiné à un dev invité en pair-programming quelques heures.
> But de la session : sortir le **BACKLOG_SHIP** validé (carte des chantiers des 3 prochaines semaines), pas coder un feature en l'air.

---

## 1. Contexte en 5 lignes

- **Produit** : plateforme de musique générative (univers WATT). L'utilisateur crée un profil d'artiste, compose via prompts Suno, publie des morceaux, achète/vend des "smyles" (monnaie interne).
- **Prod** : https://web-production-e30c8c.up.railway.app
- **Moi (Tom)** : fondateur, **zéro compétence code**. Je pilote le produit et la direction, j'utilise Cowork (IA) pour exécuter.
- **Situation** : code fonctionnel, mais dette legacy Flask + patches accumulés. On attaque un **sprint nettoyage + ship de 3 semaines**.
- **Problème méthodologique identifié** : jusqu'ici on patchait au coup par coup → perte de fil, bugs qui rouvrent. **Nouvelle règle de fer : plus de patches isolés sans carte priorisée**.

---

## 2. Stack

- **Backend** : FastAPI (moderne) + Flask (legacy, encore monté en `/` via `a2wsgi`)
- **DB** : Postgres (Railway managed), migrations Alembic
- **Storage audio** : Cloudflare R2
- **Front** : vanilla JS (pas de framework) + HTML + CSS. Pages à la racine du repo.
- **Déploiement** : Railway (`railway.toml`)
- **CI** : minimal, 1 workflow (Alembic upgrade head fresh Postgres). **Pas de lint, pas de tests unitaires.** → dette visible.

---

## 3. Setup local en 4 commandes

```bash
git clone https://github.com/SMYLEPLAY/smyle-play.git
cd smyle-play
cp .env.example .env   # éditer DATABASE_URL, JWT_SECRET, R2_* si tu veux la prod-like
pip install -r requirements.txt
cd smyleplay-api && alembic upgrade head && cd ..
uvicorn main:app --reload
```

Serveur sur `http://localhost:8000`. Sans `DATABASE_URL` rempli, ça tombe en SQLite local (`smyle_local.db`).

---

## 4. Carte rapide du code

### Backend — `smyleplay-api/app/routers/` (FastAPI)

15 routers actifs, tous vivants :
- `auth` · `users` · `catalog` · `tracks` · `library` · `playlists`
- `search` · `follows` · `marketplace` · `unlocks`
- `credits` · `transactions` · `achievements`
- `watt_compat` (pont migration Flask → FastAPI)

Un Flask legacy (`flask_app.py` à la racine) sert encore `/` + quelques routes `/api/*`. **Ne pas supprimer tant qu'on n'a pas migré les dernières routes** — voir `OBSIDIAN/05_TECH/Runbooks/Mapping_Flask_to_FastAPI.md`.

### Front — `ui/` et HTML à la racine

```
ui/
├── core/         → events, state, dom, api, toast, storage (les primitives)
├── panels/       → watt-panel, mix, agent, playlist
├── modals/       → auth, premium, contact, save-mix, search
├── hub/          → community, marketplace
├── player/       → audio.js
├── topbar/       → topbar.js
├── session-guard.js
├── smyle-balance.js
└── app.js        → entry point
```

Pages HTML : `index.html`, `dashboard.html`, `library.html`, `artiste.html` (page publique `/u/<slug>`).

### Obsidian (pas le code)

Le dossier `OBSIDIAN/` est un vault Obsidian stratégique (produit / créatif / sessions). **Point d'entrée : `OBSIDIAN/00_INDEX.md`**. Tu peux l'ouvrir avec l'app Obsidian pour naviguer. Tout le code = repo, toute la strat = Obsidian.

---

## 5. Plan de la session (2-3h)

### Objectif unique : produire le **BACKLOG_SHIP**

Le BACKLOG_SHIP est un doc unique et priorisé avec 3 listes fermées :
- **Bugs** à corriger (avec criticité P0/P1/P2)
- **Features** manquantes (avec effort/impact)
- **Dette technique** à tuer (avec coût du statu quo)

Chaque ligne du backlog = 1 chantier = 1 commit = 1 PR. On shipe dans l'ordre, sans parallèle.

### Découpage proposé

| Temps | Tâche | Qui fait quoi |
|-------|-------|---------------|
| 0-20 min | Tour du propriétaire | Tom fait la démo en prod (ce qui marche / ce qui coince visuellement) |
| 20-60 min | Scan backend à 2 | Ami ouvre `smyleplay-api/app/routers/*`, checke cohérence, note les endpoints non câblés au front |
| 60-90 min | Scan front à 2 | Ami ouvre `ui/*` + HTML racine, note les handlers morts, les doublons, les bugs visibles |
| 90-150 min | Rédaction BACKLOG_SHIP | À 4 mains dans `OBSIDIAN/01_PRODUIT/BACKLOG_SHIP.md` |
| 150-180 min | Priorisation | Tom tranche l'ordre d'exécution, ami challenge |

Output final : **un fichier `BACKLOG_SHIP.md` validé** + un accord sur le chantier #1 à ship en semaine prochaine.

---

## 6. Warm-up optionnel (30 min)

Si tu veux toucher du code avant l'audit, il y a un fix **déjà diagnostiqué et prêt** dans `ui/smyle-balance.js` (modifications non committées, dispo en `git status`).

**Bug** : double affichage du badge SMYLES (flottant + topbar) sur `artiste.html` et `library.html`.
**Diagnostic** : race condition entre `ui/topbar/topbar.js` (boot tardif) et `ui/smyle-balance.js` (boot DOMContentLoaded).
**Fix en place** : 3 hunks dans `ui/smyle-balance.js` (helper `getOrCreateContainer` + `_removeFloatingOrphans` + early returns).

Action proposée :
1. `git diff ui/smyle-balance.js` → review le fix
2. Si OK → commit sur branche dédiée (`fix/smyle-balance-duplicate-badge`), push, PR
3. Test visuel sur `/u/<tom-slug>` + `/library`

Livrable : 1 PR mergée = première contribution + tu as testé le workflow complet.

---

## 7. Conventions du repo

### Branches
- `main` = prod (merge déclenche un déploiement Railway)
- Features : `feat/<scope>-<short-desc>`
- Fixes : `fix/<scope>-<short-desc>`
- Chores : `chore/<scope>-<short-desc>`

### Commits (conventional commits obligatoires)
```
<type>(<scope>): <sujet en minuscules, impératif présent>

[body optionnel]

Co-Authored-By: ... (si pair-programming)
```

Types : `feat` / `fix` / `chore` / `refactor` / `docs` / `test`

### Pull Requests
- 1 PR = 1 chantier du BACKLOG_SHIP (pas de PR fourre-tout)
- Description structurée : Objectif / Changements / Vérifications / Hors scope
- CI doit passer au vert avant merge
- Squash-merge recommandé

---

## 8. Si on collabore à distance après cette session

Si la session matche bien, Tom peut te donner un accès collaborateur GitHub en écriture. Dans ce cas :
- Tu prends un ticket du BACKLOG_SHIP, tu ouvres une branche, tu fais ta PR
- Tom review/merge (ou tu mets un humain IA dessus si Tom est pas dispo)
- Tu ne patches jamais en dehors du backlog — si tu vois un bug en chemin, tu l'**ajoutes** au backlog, tu ne le corriges pas à chaud.

---

## 9. Ce qui NE doit PAS sortir de la session

- Pas de refactor anticipatif
- Pas de migration Flask lancée sans audit complet (gros chantier, impact prod, on ne s'y attaque qu'après le BACKLOG_SHIP)
- Pas de suppression de `tracks.json` (encore utilisé par la migration en cours)
- Pas de decision "on réécrit tout" — on a déjà tranché : pas de rewrite from scratch

---

## 10. Liens utiles

- Repo : https://github.com/SMYLEPLAY/smyle-play
- Prod : https://web-production-e30c8c.up.railway.app
- README projet : `README.md`
- Instructions IA (à lire pour comprendre le contexte Cowork) : `CLAUDE.md`
- Mapping migration Flask → FastAPI : `OBSIDIAN/05_TECH/Runbooks/Mapping_Flask_to_FastAPI.md`
- Dette technique connue : `OBSIDIAN/01_PRODUIT/Dette_technique.md`

---

**Signé :** Tom + Cowork (IA) · 2026-04-22
