---
title: WATT DEV AGENT — Sprint 1 (Durcissement)
type: backlog
tags: [produit, backlog, sprint, watt-dev-agent, agent]
updated: 2026-05-07
status: proposed
---

# WATT DEV AGENT — Sprint 1 (Durcissement)

> Backlog priorisé du chantier "agent unique → solide", **avant** clonage multi-agents.
> Décision d'archi : [[WATT_DEV_AGENT_ADR_001_durcissement]]
> Vision après Sprint 1 : [[WATT_DEV_AGENT_Roadmap_MultiAgents]]
> **Périmètre = repo `watt-dev-agent`** (séparé du repo Smyleplay/`smyleplay-api`).

---

## Règle de fer (héritée du projet Smyleplay)

1. **1 chantier à la fois**, ordre P0 → P1 → P2
2. **1 chantier = 1 commit = 1 PR** (pas de PR fourre-tout)
3. **Pas de patch sans ligne de backlog correspondante**
4. **Tom valide chaque PR via le Control Center** avant merge

---

## 🎯 Objectif Sprint 1

À la fin du Sprint 1, l'agent doit être **un seul service stable**, capable de :

- Recevoir une tâche du Control Center
- Exécuter sans perdre l'état si Railway redémarre
- Gater **toutes** les actions mutantes (y compris Bash) derrière l'approval queue
- Écrire un audit log complet de chaque action
- Connaître les règles métier Smyleplay (mémoire injectée)
- Notifier Tom sur mobile sans perdre de notif (retry)

Métriques de sortie :
- 0 perte d'état après redémarrage Railway (testable)
- 100 % des actions mutantes passent par `request_approval` (auditable)
- 100 % des règles métier mémoire répliquées en `business_rules.py`

---

## 🔴 P0 — Sécurité + métier (semaine 1, ~2 jours)

### S1-01 — Injecter règles métier dans le system prompt
- **Pourquoi** : agent ignore tout des règles Smyleplay → reproduit en boucle les bugs déjà corrigés
- **Quoi** : créer `agent/business_rules.py` avec liste structurée (id, règle, raison, application). Concaténer au `SYSTEM_PROMPT` dans `_build_options`.
- **Règles à inclure (sources : memory MD)** :
  - `STOP_PATCHES_ISOLES` — backlog priorisé d'abord
  - `VOIX_SEPAREES` — voix jamais en shuffle/playlist/DNA
  - `PROMPTS_VERROUILLES` — prompts/ADN/voix invisibles sans achat
  - `PLAYLIST_TOGGLE_PUBLIC_PRIVE` — UI doit exposer le choix avant Enregistrer
  - `TRACK_RECETTE_UNIFIEE` — track = recette Suno = entité unique
  - `COPYWRITING_HONNETE` — pas d'arguments commerciaux non prouvés
  - `BRAND_DNA_WATT` — noir / chrome / bleu électrique / mauve
  - `URL_JAMAIS_TERMINAL` — toujours préciser "Chrome" pour les URLs (interaction Tom)
  - `LEGACY_USERS_CHAMPS_VIDES` — vérifier les données AVANT de chercher un bug code
- **Critère d'acceptation** : test unitaire prouve que chaque règle est dans le prompt généré
- **Effort** : **0.5 j**
- **Dépendances** : aucune

### S1-02 — Persister approval queue en Postgres
- **Pourquoi** : in-memory = perte si Railway redémarre = approbations Tom perdues, agent bloqué silencieusement
- **Quoi** :
  - Migration Alembic `approvals` (id uuid, task_id uuid, action text, summary text, payload jsonb, risk text, status text, created_at, decided_at, decided_by)
  - Réécrire `approvals/queue.py` pour persister, garder l'`asyncio.Event` pour le bloquage process
  - LISTEN/NOTIFY Postgres pour réveil cross-process (utile multi-workers Railway)
- **Critère d'acceptation** : test "kill -9 du process, redémarre, l'approbation est toujours en pending"
- **Effort** : **1 j**
- **Dépendances** : aucune

### S1-03 — Gating universel des outils mutants (Bash wrappé)
- **Pourquoi** : aujourd'hui Bash est libre → l'agent peut `rm -rf` ou `git push` sans tap. Inacceptable.
- **Quoi** :
  - Custom tool `safe_bash` qui remplace `Bash` dans `allowed_tools`
  - Classifier de commandes par regex : lecture (libre), mutation locale (risk=medium), réseau/push (risk=high)
  - `Bash` brut retiré de `allowed_tools`
- **Critère d'acceptation** : test "agent demande `rm -rf` → bloque sur request_approval"
- **Effort** : **0.5 j**
- **Dépendances** : aucune

---

## 🟠 P1 — Robustesse + traçabilité (semaine 2, ~2 jours)

### S1-04 — Audit log structuré (table append-only)
- **Pourquoi** : traçabilité (qui a tapé approve, quand, payload exact), debug, base future "marketplace multi-créateurs"
- **Quoi** : table `audit_log` (append-only), wrapper qui logge à chaque appel `request_approval`, decide, github call, safe_bash mutant
- **Critère d'acceptation** : exécuter une tâche complète → log montre toutes les étapes mutantes
- **Effort** : **0.5 j**
- **Dépendances** : S1-02 (table approvals d'abord)

### S1-05 — Persister tâches en Postgres
- **Pourquoi** : `_tasks: dict` perd les tâches au redémarrage. Pareil que la queue.
- **Quoi** : table `tasks` (id, prompt, status, context jsonb, result, error, timestamps), routes `/tasks` migrées
- **Critère d'acceptation** : créer une tâche, redémarrer le service, GET `/tasks/{id}` répond toujours
- **Effort** : **0.5 j**
- **Dépendances** : S1-02

### S1-06 — Webhook Control Center signé + retry
- **Pourquoi** : aujourd'hui notif perdue = tap manqué = agent bloqué jusqu'au timeout (1h)
- **Quoi** : retry exponentiel (3 essais, 1s/4s/16s), log final si échec, métrique `webhook_failed_total`
- **Critère d'acceptation** : tester avec Control Center down → 3 tentatives + log + approbation reste consultable via `/approvals/pending`
- **Effort** : **0.5 j**
- **Dépendances** : aucune

### S1-07 — Outils GitHub étendus
- **Pourquoi** : aujourd'hui l'agent peut écrire localement mais ne peut ni push ni vérifier les checks → cycle PR incomplet
- **Quoi** : ajouter `git_push_branch`, `git_fetch_origin`, `github_get_pr_status`, `github_get_check_runs`. Tous gated `request_approval`.
- **Critère d'acceptation** : agent termine un cycle code → push → PR → wait checks → reporter le status, en autonomie (avec taps de Tom)
- **Effort** : **0.5 j**
- **Dépendances** : S1-03 (gating en place)

---

## 🟢 P2 — Finition (semaine 2 fin, ~1 jour)

### S1-08 — Tests d'intégration sur sandbox repo
- **Pourquoi** : valider le flow bout-en-bout avant prod
- **Quoi** : repo GitHub vide `watt-dev-agent-sandbox`, suite pytest qui pousse une tâche fake et vérifie le flow complet (tâche → approval → PR fake)
- **Critère d'acceptation** : `pytest tests/integration/` vert
- **Effort** : **1 j**
- **Dépendances** : S1-01 à S1-07

### S1-09 — Restreindre les outils par défaut
- **Pourquoi** : `WebFetch` / `WebSearch` activés = surface d'exfil potentielle. À activer en opt-in par tâche.
- **Quoi** : retirer de `allowed_tools` par défaut, ajouter `task.allow_web: bool` dans `TaskRequest`
- **Critère d'acceptation** : tâche sans `allow_web` → outil indisponible côté SDK
- **Effort** : **0.25 j**
- **Dépendances** : aucune

### S1-10 — Healthcheck riche
- **Pourquoi** : Railway redémarre dès que le check est rouge → utile que ça reflète vraiment l'état
- **Quoi** : `/health` renvoie `{db, github, anthropic, version}` avec OK/KO par dépendance
- **Critère d'acceptation** : couper la DB → `/health` répond 503 avec `db=ko`
- **Effort** : **0.25 j**
- **Dépendances** : S1-02

---

## 📊 Récap effort

| Bloc | Items | Effort cumulé |
|------|-------|---------------|
| P0 — Sécurité + métier | S1-01, S1-02, S1-03 | **2 j** |
| P1 — Robustesse + traçabilité | S1-04, S1-05, S1-06, S1-07 | **2 j** |
| P2 — Finition | S1-08, S1-09, S1-10 | **1.5 j** |
| **Total** | 10 items | **~5.5 j-homme** |

> Avec un dev-agent fonctionnel qui code à ta place, le calendrier réel est plus court (mais chaque PR demande ton tap).

---

## ✅ Definition of Done — Sprint 1

- [ ] L'archive zippée est dépoussiérée et déployée Railway en branche `sprint-1`
- [ ] 0 action mutante sans `request_approval` (Bash compris)
- [ ] Approbations + tâches persistées en Postgres, redémarrage propre
- [ ] Audit log présent et lisible
- [ ] System prompt enrichi des règles métier mémoire
- [ ] Webhook Control Center fiable (retry)
- [ ] `/health` riche, observabilité minimale
- [ ] Tests d'intégration passent sur sandbox

Une fois ces 8 cases cochées → on passe à [[WATT_DEV_AGENT_Roadmap_MultiAgents]].

---

## 🚫 Hors Sprint 1 (sortis volontairement)

- ❌ Routeur multi-agents → Sprint 2
- ❌ Spécialistes (review, marketplace, modération, etc.) → Sprint 2+
- ❌ App mobile Control Center elle-même (UI iOS/Android) → projet séparé, pas dans ce backlog
- ❌ Stripe / paiement / support utilisateur → relèvent de Smyleplay, pas du dev-agent
- ❌ Brancher Railway MCP pour les déploiements → Sprint 2 (gating risk=critical déjà prévu en archi)

---

## Liens

- [[WATT_DEV_AGENT_ADR_001_durcissement]] — décision d'archi
- [[WATT_DEV_AGENT_Roadmap_MultiAgents]] — Sprint 2+
- [[BACKLOG_SHIP]] — backlog Smyleplay côté plateforme (séparé)
