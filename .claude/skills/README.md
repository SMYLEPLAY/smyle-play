# Skills installées pour Smyleplay

Source : [sickn33/antigravity-awesome-skills](https://github.com/sickn33/antigravity-awesome-skills) (MIT)
Date mise à jour : 2026-05-12
Sélection ciblée : **32 skills** sur les 1444 du repo source.

## Inventaire complet (32)

### Produit & Stratégie (4)
- **product-manager-toolkit** — RICE prioritization, PRD templates
- **launch-strategy** — planning lancement WATT
- **competitive-landscape** — analyse Suno / Udio / Riffusion
- **competitor-alternatives** — pages "alternative à X" pour SEO

### Marketing & Growth (7)
- **copywriting** — copy conversion (⚠ filtrer avec règle "honnête uniquement")
- **seo-audit** — santé SEO Smyleplay
- **programmatic-seo** — pages à grande échelle (artistes, univers, prompts)
- **content-creator** — blog SEO
- **email-sequence** — onboarding utilisateurs WATT
- **analytics-tracking** — GA4 / PostHog setup propre
- **churn-prevention** — cancel flows, save offers, dunning, win-back

### IA / WATT (5)
- **prompt-engineering** — alimente le skill `watt-prompt` natif
- **agent-orchestrator** — Phase F : orchestrateur multi-agents
- **multi-agent-architect** — design systèmes multi-agents (LangGraph)
- **agent-memory-systems** — short-term / long-term / vector stores
- **agent-evaluation** — test/benchmark agents AVANT prod (anti-bug Sprint 1)

### Dev Stack Smyleplay (5)
- **fastapi-pro** — cœur de stack
- **postgres-best-practices** — préparation migration SQLite → Postgres
- **database-migration** — stratégies migration + zero-downtime (legacy users)
- **stripe-integration** — paiements WATT (intégration de base)
- **payment-integration** — couvre PayPal, dunning, webhooks, PCI compliance
- **pricing-strategy** — packaging, monétisation WATT (crédits, prompts, trade ADN)
- **docker-expert** — containers pour Railway prod

### Infra / Observabilité (3)
- **deployment-procedures** — CI deploy manquant (cause des 5 bugs Sprint 1)
- **observability-engineer** — monitoring/logging/tracing agent Railway prod
- **sentry-automation** — ⚠ **RISK: CRITICAL** — exécute des actions destructives via Composio MCP. À utiliser uniquement en mode lecture/analyse sans autoriser actions.

### Tests (1)
- **e2e-testing-patterns** — corrige le trou Sprint 1 (tests SQLite ne détectaient pas les bugs prod)

### Sécurité (4)
- **api-security-best-practices** — FastAPI public exposé
- **auth-implementation-patterns** — JWT/OAuth, anciens comptes legacy mal migrés
- **top-web-vulnerabilities** — OWASP baseline (obligatoire repo public)
- **secrets-management** — Vault, AWS Secrets Manager (adresse "Tom colle régulièrement des secrets en clair")

### Communication / Bot (1)
- **telegram-bot-builder** — Phase E live : étoffer pilotage Telegram agent

## Comment les invoquer

Selon l'outil utilisé :
- **Claude Code (CLI)** : `>> /skill-name aide-moi à...`
- **Cursor (IDE)** : `@skill-name` dans le chat
- **Cowork (cette session)** : pas chargé auto. Demander explicitement :
  *"applique la skill `agent-orchestrator` du dossier `.claude/skills/`"*

## Skills à manier avec précaution

- **sentry-automation** — risk:critical, exécute via Composio MCP. Lire d'abord, exécuter ensuite.
- **copywriting** — règle "copywriting honnête uniquement" prime toujours
- **secrets-management** — règle "jamais coller secrets dans le chat" prime

## Skills natives Cowork déjà disponibles (rappel)

Inutile de dupliquer :
- `engineering:debug` ↔ ne pas ajouter `systematic-debugging` / `error-detective`
- `engineering:code-review` ↔ ne pas ajouter `code-review-checklist`
- `engineering:system-design` ↔ ne pas ajouter `senior-architect`
- `engineering:testing-strategy` ↔ couvre l'essentiel hors E2E spécifique
- `engineering:deploy-checklist` ↔ complémentaire à `deployment-procedures`
- `engineering:incident-response` ↔ couvre postmortem et triage

## Évolutions futures possibles

Skills repérées mais non installées (à considérer plus tard) :
- `mcp-builder` — si on construit un plugin MCP custom Smyleplay
- `voice-agents` — quand voix WATT seront priorité Sprint
- `react-best-practices` / `nextjs-best-practices` — quand frontend sera défini
- `onboarding-cro`, `ux-audit`, `ux-flow` — phase optimisation conversion
