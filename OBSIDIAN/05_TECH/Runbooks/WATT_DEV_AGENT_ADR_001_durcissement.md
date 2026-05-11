---
title: ADR 001 — Durcissement WATT DEV AGENT (Sprint 1) avant multi-agents
type: adr
tags: [technique, adr, watt-dev-agent, agent, sprint]
updated: 2026-05-07
status: proposed
---

# ADR 001 — Durcissement de WATT DEV AGENT (Sprint 1)

> Source code de l'agent : repo `watt-dev-agent` (FastAPI + Claude Agent SDK), déployé sur Railway, piloté depuis le futur WATT CONTROL CENTER mobile.
> Ce doc est la décision d'architecture **avant code**.
> Voir aussi : [[WATT_DEV_AGENT_Sprint1]] (backlog chiffré), [[WATT_DEV_AGENT_Roadmap_MultiAgents]] (vision Sprint 2+).

## Contexte

L'archive `watt-dev-agent.zip` contient un agent FastAPI mono-rôle :

- 1 seul `SYSTEM_PROMPT` généraliste ("code, teste, doc, PR sur le repo Smyleplay")
- Approval queue **in-memory** (perdue à chaque redémarrage Railway)
- Store `_tasks` **in-memory** également
- 2 outils custom MCP exposés : `request_approval`, `github_create_pull_request`
- Outils SDK built-in : `Read / Write / Edit / Bash / Grep / Glob` — **non gated par `request_approval`**
- Webhook Control Center **fire-and-forget** (échec silencieux)
- Aucune règle métier Smyleplay injectée (mémoire de Tom non répliquée dans le prompt)

## Décision

**Sprint 1 = durcir l'agent unique avant de le cloner en multi-agents.**

Raison principale : cloner un agent fragile produit N agents fragiles. La duplication amplifie les défauts. Tant que les fondations (persistance, audit, gating mutant, prompts métier) ne sont pas saines, ajouter des spécialistes augmente la surface de bug sans réelle valeur.

## Choix techniques retenus pour Sprint 1

### 1. Approval queue → Postgres (au lieu d'in-memory)

- Table `approvals` avec colonnes `id, task_id, action, summary, payload (jsonb), risk, status, created_at, decided_at, decided_by`
- L'agent **bloque** sur `asyncio.Event` côté process, mais la décision et l'audit vivent en DB
- `LISTEN/NOTIFY` Postgres pour réveiller l'agent même après redémarrage (recovery propre)
- Conséquence : un crash Railway ne détruit plus la file d'attente. Les approbations restent visibles dans le Control Center.

### 2. Audit log structuré

- Table `audit_log` (append-only) : `id, ts, task_id, actor (agent|user|auto|timeout), action, payload, outcome`
- Toute action mutante (request_approval, decide, github call, bash mutant) écrit une ligne
- Format compatible avec une exfiltration future vers un SIEM ou un dashboard interne
- Conséquence : traçabilité complète, base pour les futures features "qui a fait quoi" et conformité.

### 3. Gating universel des outils mutants

- Aujourd'hui `Bash` est libre → l'agent peut `rm -rf`, `git push`, `npm publish` sans approbation. Risque inacceptable même en sandbox.
- Décision : **wrapper `Bash` derrière un classifier de commandes**.
  - Lecture (`ls, cat, grep, git log, git status, pytest`) → libre
  - Mutation locale (`git commit, git checkout, mv, rm`) → `request_approval` risk=`medium`
  - Réseau / push (`git push, curl POST, pip install`) → `request_approval` risk=`high`
- `WebFetch` et `WebSearch` désactivés par défaut au Sprint 1 (réactivables avec opt-in par tâche).

### 4. Prompts métier injectés

- Le system prompt reçoit en injection les règles métier issues de la mémoire Smyleplay :
  - Pas de patches isolés (backlog d'abord)
  - Voix séparée du flux musical (table + endpoints distincts)
  - Prompts jamais visibles sans achat (teaser métadonnées uniquement)
  - Playlist : toggle public/privé obligatoire dans l'UI de création/édition
  - Track = recette Suno (entité unifiée, prompt vendable inclus)
  - Copywriting honnête uniquement
  - Brand DNA WATT (noir / chrome / bleu électrique / mauve)
- Implémentation : fichier `agent/business_rules.py` avec liste structurée. Injecté en post-fix du `SYSTEM_PROMPT` à chaque tâche.
- Conséquence : un dev-agent qui ne re-casse pas les règles que Tom a déjà imposées dix fois.

### 5. Webhook Control Center signé + retry

- Aujourd'hui : `httpx.post` avec `try/except: pass`. Une notif perdue = un tap manqué = agent bloqué silencieusement.
- Nouveau : signature HMAC déjà OK, ajouter retry exponentiel (3 tentatives, backoff 1s/4s/16s), et logger l'échec final.
- Fallback : `/approvals/pending` reste consultable (déjà le cas).

### 6. Outils GitHub étendus

- Ajouter en Sprint 1 : `git_push_branch`, `git_fetch`, `github_get_pr_status`, `github_get_check_runs`
- Tous gated derrière `request_approval` avec risk approprié
- Conséquence : l'agent peut boucler un cycle complet code → push → PR → vérifier les checks, sans Tom devoir intervenir entre chaque étape

### 7. Healthcheck riche

- `/health` renvoie aujourd'hui `{"status": "ok"}` — Railway ne sait pas si la DB ou la clé Anthropic sont KO
- Nouveau : check DB (SELECT 1), check GitHub (`/rate_limit`), check Anthropic (HEAD `/v1/messages`)

## Conséquences

**Positives**
- Fondations saines pour empiler les agents Sprint 2+ sans dette
- Audit log = base obligatoire pour ouvrir un jour la marketplace à plusieurs créateurs (traçabilité légale)
- Règles métier centralisées en code = source unique de vérité

**Négatives / coûts**
- ~5–6 jours-homme (estimation détaillée dans [[WATT_DEV_AGENT_Sprint1]])
- Durcir avant cloner = pas de "wow effect multi-agents" en Sprint 1
- Migration in-memory → Postgres demande Alembic + tests (mais Postgres déjà disponible Railway)

**Neutres**
- L'API exposée au Control Center reste **identique** (compatibilité ascendante préservée pour la future app mobile)

## Alternatives écartées

### Alt A — Casser direct en multi-agents
Plus rapide visuellement, mais multiplie les fragilités (queue in-memory × N agents = N fois plus de fragilité). Rejeté.

### Alt B — Tout réécrire from scratch
Aligne avec l'envie de propre, mais coûte ~3 semaines. L'archive zippée est correcte, on garde et on durcit. Rejeté.

### Alt C — Externaliser approval queue (Redis / SQS)
Sur-ingénierie pour un MVP solo. Postgres est déjà là, suffisant jusqu'à plusieurs dizaines de tâches/jour. Rejeté pour Sprint 1, à réévaluer Sprint 5+.

## Statut

**Proposé** — en attente de validation de Tom.

Une fois validé, j'attaque le code dans le repo `watt-dev-agent` (séparé de Smyleplay), branche `sprint-1-hardening`, 1 PR par item du backlog.

## Liens

- [[WATT_DEV_AGENT_Sprint1]] — backlog chiffré, ordre P0→P1→P2
- [[WATT_DEV_AGENT_Roadmap_MultiAgents]] — vision Sprint 2+ (router + spécialistes)
- [[BACKLOG_SHIP]] — backlog Smyleplay côté plateforme (séparé)
- Mémoire : "STOP patches isolés", "URL jamais dans Terminal", "Comptes pré-migrations champs vides"
