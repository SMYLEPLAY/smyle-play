---
title: WATT DEV AGENT — Roadmap Multi-agents (Sprint 2+)
type: roadmap
tags: [produit, roadmap, agent, watt-dev-agent, marketplace]
updated: 2026-05-07
status: blueprint
---

# Roadmap Multi-agents (Sprint 2+)

> Vision d'ensemble de la flotte d'agents Smyleplay, **après** le durcissement Sprint 1.
> Pré-requis : [[WATT_DEV_AGENT_Sprint1]] coché en entier.
> Décision d'archi : [[WATT_DEV_AGENT_ADR_001_durcissement]]
> **Ce doc est un blueprint, pas un backlog implémentable. Chaque sprint suivant aura son propre doc chiffré.**

---

## Pourquoi multi-agents

Un agent généraliste = un prompt dilué = couverture moyenne sur tous les sujets. Une marketplace musicale a 4 dimensions critiques qu'un seul cerveau gère mal :

1. **Tech** — coder le produit (backend, frontend, DB, devops)
2. **Marketplace business** — paiement, modération, transactionnel, support
3. **Créatif WATT** — qualité prompts, ADN, voix, marketing honnête
4. **Pilotage** — analytics, KPI, alertes, decisions data-driven

→ Un spécialiste par dimension = prompts étroits, outils minimaux, règles métier ciblées, audit clair.

---

## Architecture cible

```
            WATT CONTROL CENTER (mobile)
                       │
                       ▼
            ┌──────────────────────┐
            │   ROUTER (Haiku)     │  ← classifie, dispatche, ne mute rien
            └──────┬───────────────┘
                   │
   ┌──────────┬────┴────┬───────────┬────────────┐
   ▼          ▼         ▼           ▼            ▼
[CODE]   [MARKET]   [CREA]      [QA/SEC]     [SUPPORT]
 Sonnet   Sonnet    Sonnet      Sonnet        Haiku

Chaque spécialiste hérite de l'infra Sprint 1 :
  - approval queue Postgres
  - audit log
  - safe_bash gating
  - business_rules.py partagé
  - system prompt étroit + outils sur-mesure
```

Tous les agents tournent dans le **même service `watt-dev-agent`**, partagent la même base, mais chaque tâche route vers une `AgentSpec` différente (système prompt + outils + risk policy).

---

## Sprint 2 — Spécialiste Code + Router (~3-4 j)

**But** : sortir le mono-agent en passant à 2 agents (router + code) sans casser l'API existante.

- **Router** (Haiku, peu coûteux) : reçoit la tâche, classifie en `code | marketplace | crea | qa | support`, retourne le slug du spécialiste à appeler
- **Code agent** (Sonnet) : équivalent du DEV AGENT actuel, system prompt resserré sur "écrire et tester du code Smyleplay"
- **Pas encore** d'autres spécialistes — on valide le pattern avec 2 agents avant d'empiler

Critères de sortie :
- Une tâche `"refactor le module players"` est dispatché vers `code` automatiquement
- Une tâche `"comment va la conversion ce mois-ci ?"` est dispatché vers `analytics` (et échoue gracieusement avec "agent pas encore disponible")
- L'API publique du dev-agent ne change pas (compat Control Center)

---

## Sprint 3 — Agent QA / Security review (~2 j)

**But** : avant chaque merge, un agent indépendant relit la PR.

- Hook : Control Center notifie l'agent QA dès qu'une PR est créée par l'agent code
- Outils : `github_get_pr_diff`, `github_post_review_comment`, `safe_bash` (read-only)
- System prompt étroit : "tu cherches N+1, injections, secrets en clair, edge cases manqués, breaking changes, régressions"
- **Ne merge jamais** lui-même → propose une review en commentaires + verdict (approve/changes_requested)
- Tom décide en taps depuis le Control Center

Pourquoi tôt ? Parce que l'agent code en autonomie nocturne sans QA = dette technique exponentielle.

---

## Sprint 4 — Agent Marketplace (~3-4 j)

**But** : flux Stripe + transactionnel, séparé du code généraliste.

- Périmètre : webhooks Stripe (paiement réussi, refund, dispute), réconciliation, gestion crédits, idempotence
- Outils : `stripe_get_event`, `stripe_create_refund` (gated risk=critical), `db_query_readonly`, accès table `transactions`
- System prompt : "tu es responsable de la cohérence financière de Smyleplay. Aucune action sans audit. Tout refund > N€ → risk=critical."
- **Règle d'or supplémentaire** : `payment-agent` ne peut pas modifier le code, seulement les données transactionnelles

Pré-requis Smyleplay : Stripe Checkout livré côté plateforme (cf. [[BACKLOG_SHIP]] hors-sprint Smyleplay actuel — donc Sprint 4 dev-agent dépend de l'avancée Smyleplay).

---

## Sprint 5 — Agent Modération créa (~2-3 j)

**But** : review automatique des prompts/voix/tracks uploadés par les créateurs avant publication.

- Outils : lecture table `tracks` + `prompts` + `voices`, accès Cloudflare R2 (read-only sur l'audio), `db_set_status` (gated)
- System prompt : "tu vérifies la cohérence ADN, le copywriting honnête, l'absence de contenu protégé/offensant. Tu produis un verdict + justification."
- Règle de fer : **prompts/ADN/voix verrouillés publiquement** (memory) — l'agent modération les voit, le visiteur non
- Decisions : `approved | needs_changes | rejected` → notif au créateur via Control Center

---

## Sprint 6 — Agent Analytics (~2 j)

**But** : digest hebdo automatique pour Tom + alertes anomalies.

- Outils : `db_query_readonly`, accès aux vues materialisées `mv_kpi_*`, génération markdown
- System prompt : "tu es l'analyste de Smyleplay. Pas de bullshit, pas d'arrondis flatteurs. Si une métrique baisse, tu le dis."
- Trigger : cron hebdo (Railway scheduled task) + on-demand via Control Center
- Output : doc markdown dans `OBSIDIAN/03_SESSIONS/` avec tag `#analytics-weekly`

KPIs à suivre (à valider Sprint 6) :
- Conversion visiteur → member
- Conversion member → WATT Creator
- Top prompts vendus
- Churn créateurs (inactivité > 30 j)
- Revenue net (post-frais Stripe)
- Coût Claude API (à pondérer vs revenue)

---

## Sprint 7 — Agent Support (~2 j)

**But** : pré-rédige les réponses aux tickets utilisateurs, Tom valide.

- Outils : `helpdesk_get_ticket`, `helpdesk_post_draft_reply` (gated, jamais auto-send)
- Modèle : Haiku (volume + simplicité)
- System prompt : "tu es la voix de WATT. Direct, honnête, jamais commercial sur ce qui n'est pas prouvé."
- **Ne répond jamais** sans tap de Tom

---

## Sprint 8+ — À cadrer plus tard

- Agent **growth** (idées de campagnes, drafts SoMe — mais respect de [[Tarification_v1]] et copywriting honnête)
- Agent **A/B test designer** (génère hypothèses, propose variantes UI)
- Agent **trade-prompt** (échange d'ADN entre artistes — feature future memory `prompt_trading_feature`)

---

## Règles partagées par tous les agents

1. **Aucune action mutante sans `request_approval`** — règle d'or dev-agent étendue à toute la flotte
2. **Audit log universel** — tout agent loggue dans `audit_log` avec son `agent_slug`
3. **Business rules injectées** — chaque agent reçoit `business_rules.py` + ses règles spécifiques
4. **Outils minimaux** — un agent ne reçoit QUE les outils nécessaires à son rôle (principe du moindre privilège)
5. **Risk policy par agent** — un agent peut avoir un seuil `auto_approve_below` différent (ex : analytics = pas d'action mutante du tout)

---

## Ce que ce doc N'EST PAS

- ❌ Pas un backlog implémentable — chaque Sprint aura son doc chiffré dédié
- ❌ Pas un engagement de delivery — l'ordre peut bouger selon les priorités Smyleplay
- ❌ Pas une archi figée — c'est un cap, pas une carte routière

---

## Liens

- [[WATT_DEV_AGENT_Sprint1]] — pré-requis avant ce roadmap
- [[WATT_DEV_AGENT_ADR_001_durcissement]] — décision d'archi initiale
- [[Roadmap]] — roadmap Smyleplay côté plateforme
- [[BACKLOG_SHIP]] — backlog Smyleplay côté plateforme
- [[Tarification_v1]] — pré-requis pour Sprint 4 (marketplace)
