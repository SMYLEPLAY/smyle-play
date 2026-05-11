---
title: 2026-05-07 — HANDOFF WATT DEV AGENT (pour reprise dans un chat propre)
type: handoff
tags: [handoff, session, watt-dev-agent, reprise]
updated: 2026-05-07
---

# HANDOFF — Reprise du chantier WATT DEV AGENT dans un chat propre

> **Mode d'emploi** : Tom, copie-colle l'ensemble du **§ Prompt de reprise** ci-dessous au début d'un nouveau chat Claude. Le nouveau Claude aura immédiatement tout le contexte. Pas besoin de lui reraconter 200 messages.

---

## § Prompt de reprise (à copier-coller dans le nouveau chat)

```
Tu es mon assistant d'exécution stratégique pour Smyleplay / WATT.
Posture : direct, structuré, orienté résultat. Tu me contredis si je vais
dans la mauvaise direction.

# Mission en cours

Construire une équipe complète d'agents autonomes autour de Smyleplay :
1. WATT DEV AGENT (code) — Sprint 1 LIVRÉ, à déployer
2. Agent QA review
3. Agent création prompts (Suno, ADN WATT, voix)
4. Agent marketplace (Stripe, refunds)
5. Agent modération (review prompts uploadés)
6. Agent analytics (KPI hebdo)
7. Agent support (drafts tickets)

# État actuel (2026-05-07 fin de session)

WATT DEV AGENT — Sprint 1 (durcissement) : 10/10 items LIVRÉS sur GitHub.
- Repo : https://github.com/SMYLEPLAY/watt-dev-agent
- 160 tests verts
- 7 PRs mergées sur main
- Code complet : approval queue Postgres, audit log, safe_bash gating,
  outils GitHub étendus, healthcheck riche, tests E2E

L'agent ne tourne PAS encore en prod. Il est juste sur GitHub.

# Plan d'action séquentiel à reprendre

PHASE D — Déployer watt-dev-agent sur Railway (~30 min Tom + moi)
  1. Tom doit upgrader Railway de Trial → Hobby Plan ($5/mois min) car
     il ne reste que ~$1.94 de crédit, Smyleplay risque de tomber.
  2. Créer projet Railway depuis le repo SMYLEPLAY/watt-dev-agent
  3. Ajouter add-on Postgres
  4. Configurer variables d'env (cf. .env.example du repo)
  5. Vérifier que /health répond depuis l'URL Railway publique

PHASE E — Mini Control Center web (~1-2h)
  Page web mobile-friendly où Tom tape approve/reject sur les pending
  approvals via son téléphone. Sans ça, l'agent reste bloqué sur chaque
  action mutante et ne peut pas faire de cycle dev complet.
  Suggéré : 1 page HTML+JS hébergée Railway, lit GET /approvals/pending,
  expose 2 boutons par item. Possible PWA pour notifs push.

PHASE F — Test bout en bout
  Tom envoie une tâche fake ("ajoute un commentaire dans README"),
  reçoit notif tel, swipe approve, vérifie que ça marche.

SPRINT 2 — Démarrer la flotte multi-agents
  Premier ajout : agent QA review (relit les PRs avant merge).
  Cf. roadmap : OBSIDIAN/01_PRODUIT/WATT_DEV_AGENT_Roadmap_MultiAgents.md

# Règles de fer Smyleplay (déjà injectées dans le prompt de l'agent)

- STOP_PATCHES_ISOLES : backlog priorisé d'abord, 1 chantier = 1 PR
- VOIX_SEPAREES : voix jamais en shuffle/playlist/DNA
- PROMPTS_VERROUILLES : prompts/ADN/voix invisibles sans achat
- PLAYLIST_TOGGLE_PUBLIC_PRIVE : choix exposé avant Enregistrer
- TRACK_RECETTE_UNIFIEE : track avec prompt vendable EST la recette
- COPYWRITING_HONNETE : pas d'arguments commerciaux non prouvés
- BRAND_DNA_WATT : noir / chrome / bleu électrique / mauve
- LEGACY_USERS_CHAMPS_VIDES : check données AVANT bug code
- URL_JAMAIS_TERMINAL : toujours préciser "dans Chrome" pour les URLs
- RAPPEL_PUSH_SYSTEMATIQUE : Tom regarde la prod Railway

# Posture importante

Je (Tom) ne suis PAS développeur. Tu dois me guider clic par clic, sans
jargon. Toujours préciser "dans Chrome" quand tu donnes une URL.
Je travaille de nuit en service, je lis sur mobile.

# Documents de référence à lire en début de session

OBSIDIAN/01_PRODUIT/WATT_DEV_AGENT_Sprint1.md            (backlog complet)
OBSIDIAN/01_PRODUIT/WATT_DEV_AGENT_Roadmap_MultiAgents.md (vision Sprint 2+)
OBSIDIAN/05_TECH/Runbooks/WATT_DEV_AGENT_ADR_001_durcissement.md (ADR)
OBSIDIAN/03_SESSIONS/2026-05-07_watt_dev_agent_sprint1.md (récap session)
OBSIDIAN/03_SESSIONS/2026-05-07_handoff_watt_dev_agent.md (ce doc)

# Dette de sécurité connue (non bloquante)

Le token GitHub `github_pat_11CB2FAYQ0...` a été collé en clair dans
l'ancien chat. À régénérer après Phase D : Chrome →
https://github.com/settings/tokens?type=beta → revoke ancien + nouveau.
Risque concret faible (repo privé, perms ultra-limitées au seul repo
watt-dev-agent).

# Commande de démarrage

Tom dira "on reprend" ou "phase D". Tu commences par confirmer Smyleplay
toujours up (https://web-production-e30c8c.up.railway.app), puis tu
guides l'upgrade Hobby Plan.
```

---

## Récapitulatif détaillé du Sprint 1 livré

### Architecture du WATT DEV AGENT

```
WATT CONTROL CENTER (à fabriquer en Phase E)
        │ HTTPS + Bearer token
        ▼
┌─────────────────────────────────────┐
│   WATT DEV AGENT (FastAPI)          │
│   - Approval queue (Postgres)       │  ← S1-02
│   - Audit log append-only           │  ← S1-04
│   - Tasks store (Postgres)          │  ← S1-05
│   - safe_bash classifier            │  ← S1-03
│   - business_rules (memory)         │  ← S1-01
│   - retry webhook exponentiel       │  ← S1-06
│   - GitHub PR / push / status       │  ← S1-07
│   - Web tools opt-in                │  ← S1-09
│   - Healthcheck DB/GH/Anthropic     │  ← S1-10
│   - Tests E2E + integration         │  ← S1-08
└─────────────────────────────────────┘
        │
        ▼
   GitHub (PRs sur Smyleplay)
   Postgres Railway (state + audit)
   Anthropic API (Claude SDK)
```

### Stack technique

- Python 3.11+ / FastAPI / pydantic v2 / SQLAlchemy 2 async / asyncpg / Alembic
- Claude Agent SDK (claude-agent-sdk)
- Hébergement : Railway (Dockerfile + railway.json)
- DB : PostgreSQL (Railway add-on)
- Tests : pytest + pytest-asyncio + aiosqlite (in-memory)

### Liste des PRs Sprint 1

Toutes mergées sur `main` :
1. `feat(s1-01)` — Inject Smyleplay business rules into system prompt
2. `feat(s1-02)` — Persist approval queue in Postgres
3. `feat(s1-03)` — Wrap Bash with classifier-gated safe_bash
4. `feat(s1-04)` — Structured append-only audit log
5. `feat(s1-05)` — Persist tasks in Postgres
6. `feat(s1-06)` — Exponential retry on Control Center webhook
7. `feat(s1-07)` — Extended GitHub tools (push, pr_status, check_runs)
8. `feat(s1-08)` — End-to-end integration tests + 3 bugs fixed
9. `feat(s1-09)` — WebFetch/WebSearch opt-in par tâche
10. `feat(s1-10)` — Rich /health probe (DB, GitHub, Anthropic)

### Variables d'environnement requises (à coller dans Railway en Phase D)

```
ANTHROPIC_API_KEY=sk-ant-...                  (la clé Claude de Tom)
GITHUB_TOKEN=github_pat_...                   (à régénérer plus tard)
GITHUB_OWNER=SMYLEPLAY
GITHUB_REPO=watt-dev-agent                    (repo de l'agent lui-même)
TARGET_REPO_OWNER=SMYLEPLAY
TARGET_REPO_NAME=smyle-play                   (le vrai repo Smyleplay à modifier)
DATABASE_URL=                                 (auto-fourni par Railway Postgres)
CONTROL_CENTER_URL=https://...                (placeholder en attendant Phase E)
CONTROL_CENTER_WEBHOOK_SECRET=                (générer une string aléatoire)
AGENT_AUTH_TOKEN=                             (générer une string aléatoire forte)
WORKSPACE_DIR=/tmp/watt-workspace
ENV=prod
```

Pour générer un secret aléatoire : dans Chrome, va sur `https://generate-secret.vercel.app/64` ou utilise un gestionnaire de mots de passe.

### Endpoints API exposés par l'agent

| Méthode | Route                     | Auth  | Usage                                   |
|---------|---------------------------|-------|-----------------------------------------|
| GET     | `/health`                 | non   | Healthcheck riche (DB/GH/Anthropic)     |
| POST    | `/tasks`                  | bearer| Lance une nouvelle tâche                |
| GET     | `/tasks`                  | bearer| Liste toutes les tâches                 |
| GET     | `/tasks/{id}`             | bearer| Détail d'une tâche                      |
| GET     | `/approvals/pending`      | bearer| Liste les approvals en attente          |
| GET     | `/approvals/{id}`         | bearer| Détail d'un approval                    |
| POST    | `/approvals/{id}/approve` | bearer| TAP APPROVE depuis le Control Center    |
| POST    | `/approvals/{id}/reject`  | bearer| TAP REJECT depuis le Control Center     |

### Modèle de données (3 tables Postgres)

- **approvals** : id, task_id, action, summary, payload (jsonb), risk, status, created_at, decided_at, decided_by
- **tasks** : id, prompt, status, context (jsonb), auto_approve_below, result, error, created_at, updated_at
- **audit_log** : id, ts, actor (agent/user/auto/timeout/system), action, outcome, payload (jsonb), task_id

---

## Mini-spec Phase E — Control Center web

> Pour le prochain Claude qui prendra ce chantier.

### Objectif
Une page web mobile-friendly qui permet à Tom de taper approve/reject depuis son téléphone sur les pending approvals de l'agent.

### Specs minimales
- 1 fichier HTML/JS (ou Next.js si on veut PWA + notifs push)
- Hébergé Railway dans le même projet que watt-dev-agent (ou projet séparé)
- Auth simple : bearer token saisi 1 fois, stocké localStorage (Tom = utilisateur unique)
- 3 vues :
  - Liste des pending approvals (auto-refresh toutes les 5s)
  - Détail d'une approval (action, summary, risk, payload pretty-print)
  - Boutons Approve / Reject (call POST /approvals/{id}/approve|reject)
- Mobile-first : boutons gros, swipeable
- Notifications : Service Worker + Push API si on veut être réveillé. Sinon notification email/SMS/Telegram suffit pour MVP

### Décisions à prendre (à valider avec Tom au prochain chat)
- Vanilla HTML/JS vs Next.js ? Recommandation : Next.js pour PWA + déploiement Railway facile
- Notifications push natives vs Telegram bot ? Telegram bot est ultra-rapide à mettre en place pour MVP
- Hébergement : projet Railway séparé ou même service que l'agent ?

---

## Liens externes

- Repo agent : https://github.com/SMYLEPLAY/watt-dev-agent
- Smyleplay prod : https://web-production-e30c8c.up.railway.app
- Railway dashboard : https://railway.app/dashboard
- Anthropic console : https://console.anthropic.com

---

## Prochaine session

- Date prévue : dans ~2 jours puis une semaine de pause Tom (= disponibilité large)
- Première action : ouvrir un chat propre, coller le **§ Prompt de reprise** ci-dessus
- Premier message attendu de Tom : "on reprend" ou "phase D"

Bonne pause de boulot.
