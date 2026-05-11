---
title: SMYLE PLAY — Vault Index
type: index
tags: [index, smyleplay]
updated: 2026-05-11
---

# SMYLE PLAY — Vault

Point d'entrée unique pour naviguer le projet **hors-code**.

> 🔴 **RÈGLE DE FER — 2026-04-22** : ouvrir [[01_PRODUIT/BACKLOG_SHIP]] **avant toute action code**. 1 chantier à la fois, dans l'ordre P0 → P1 → P2. Nouveau bug/feature → ligne ajoutée au backlog, pas traité à chaud. Voir aussi [[03_SESSIONS/2026-04-22_pivot_audit]].

## Règle de scope
- `OBSIDIAN/` = produit, stratégie, créatif, sessions, tâches, runbooks.
- `graphify-out/` = **code** (AST, architecture). Ouvrir : `graphify-out/graph.html`.
- **Jamais de duplication entre les deux.**

## Accès rapide
- [[05_TECH/Runbooks/Deploy|Runbooks techniques]]
- [[01_PRODUIT/Dette_technique|Dette technique]]
- [[04_TASKS/2026-04-21|Plan du jour]]

## Navigation

### 🧭 Aujourd'hui (2026-05-11)
- [[2026-05-11_handoff_smyleplay]] — **HANDOFF + cadrage 11 problématiques Smyleplay** (BACKLOG v3, Phase 0 → B8 en premier)
- [[BACKLOG_SHIP]] — **backlog priorisé v3** (Phase 0 quick wins → Phase 1 publication → Phase 2 achat → Phase 3 catalogue → Phase 4 recherche)

### 📅 Sessions précédentes
- [[2026-05-07_handoff_watt_dev_agent]] — handoff watt-dev-agent (en pause)
- [[2026-05-07_watt_dev_agent_sprint1]] — WATT DEV AGENT Sprint 1 livré (10 PRs, 160 tests verts)
- [[2026-05-05_reprise_pivot_ecoute]] — reprise étape par étape (bug audio /u/smyle + jauges Suno)
- [[2026-05-04_pivot_ecoute_session]] — récap session 15 PRs (pivot écoute Sprint 1 prod)
- [[2026-04-29_chantier_continuation]] — pré-saison nuit, chantiers vente
- [[2026-04-21]] — plan du jour (sprint stabilisation)
- [[2026-04-21_deploy-api]] — récap session déploiement API

### 📦 Produit
- [[BACKLOG_SHIP]] — **backlog priorisé actif v3 (2026-05-11)** — source de vérité
- [[Tarification_v1]] — note de travail pricing (sessions à tête reposée)
- [[Roadmap]]
- [[Dette_technique]] (D1 → D7)
- [[Bugs_connus]]

### 🤖 WATT DEV AGENT (chantier en cours, 2026-05-07)
- [[WATT_DEV_AGENT_ADR_001_durcissement]] — décision d'archi (durcir avant multi-agents)
- [[WATT_DEV_AGENT_Sprint1]] — backlog Sprint 1 chiffré (P0 → P2)
- [[WATT_DEV_AGENT_Roadmap_MultiAgents]] — vision Sprint 2+ (router + spécialistes)

### 🛠️ Technique
- Runbooks (procédures actionnables) : `05_TECH/Runbooks/`
  - [[Deploy]] · [[Suno_router]] · [[Watcher_setup]] · [[Mapping_Flask_to_FastAPI]] · [[Etape_1_runbook]] · [[DEV_PAIR_SESSION]]
- Legacy (lecture seule, ancien vault) : `05_TECH/Legacy/`
  - [[_INDEX|Index legacy]]
  - Hubs : [[HUB_AGENTS]] · [[HUB_AUTOMATION]] · [[HUB_PIPELINE]] · [[HUB_PLAYLISTS]] · [[HUB_SYSTEM]]
  - Master : [[SMYLEPLAY_MASTER]]

### 🎵 Créatif WATT
- [[Univers]]
- [[Prompts_Suno]]
- Artistes → `02_WATT/Artistes/`
- Tracks → `02_WATT/Tracks/`
  - [[low_light/_INDEX|Low Light]] (à classifier)

### 🗄️ Archives
- `99_ARCHIVE/` — handoffs, anciens états, snapshots zip
- Zips conservés :
  - `smyleplay-web_2026-04-19.zip` (ancien front Next.js)
  - `IA_SUNO_snapshot_2026-04-18.zip` (snapshot API phase_b)

## Tags principaux
`#produit` `#technique` `#watt` `#session` `#task` `#bug` `#dette` `#bloquant` `#legacy`

## État projet (2026-04-21)

| Couche | Outil | État |
|---|---|---|
| Code technique | `graphify-out/` + `smyleplay-api/` | ✅ en prod Railway |
| DB | Postgres Railway, Alembic | ✅ migrations OK |
| Produit / stratégie | ce vault | ✅ cartographié |
| Créatif WATT | `02_WATT/` + dossiers univers racine | 🟡 à structurer |
| CI / tests / monitoring | — | ❌ à faire ([[Roadmap#Sprint stabilisation]]) |

## URL prod
`https://web-production-e30c8c.up.railway.app`

## Liens externes
- Repo GitHub : [local `Smyleplay/.git`]
- Dashboard Railway : ouvrir via `railway` CLI
- Graphe code : `graphify-out/graph.html`
