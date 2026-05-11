---
title: 2026-05-07 — WATT DEV AGENT Sprint 1 livré
type: session
tags: [session, watt-dev-agent, sprint-1]
updated: 2026-05-07
---

# 2026-05-07 — WATT DEV AGENT Sprint 1 livré (durcissement complet)

## TL;DR

Sprint 1 de durcissement de WATT DEV AGENT terminé : **10/10 items livrés, 160 tests verts, 7 PRs mergées sur GitHub**. L'agent dispose désormais de fondations solides (Postgres, audit log, gating, tests) pour empiler les agents spécialistes en Sprint 2+. **Phase D (déploiement Railway) et Phase E (Control Center web) reportées à la prochaine session** après le boulot — Tom doit upgrader Railway au Hobby Plan d'abord.

## Contexte de la session

Tom a transmis une archive `watt-dev-agent.zip` générée par un autre chat. Squelette FastAPI + Claude Agent SDK avec :
- 1 seul agent généraliste (system prompt large)
- Approval queue in-memory (perdue à chaque restart)
- Aucune règle métier Smyleplay injectée
- Bash brut autorisé (l'agent pouvait `git push` ou `rm -rf` sans tap)

Diagnostic : bonne base mais fragile, à durcir avant de cloner en multi-agents.

## Décisions prises

### ADR 001 — Durcir avant multi-agents
Cf. [[WATT_DEV_AGENT_ADR_001_durcissement]]

Rejeté : casser direct en multi-agents (multiplie les fragilités), tout réécrire (3 semaines pour rien).
Choisi : durcir l'agent unique en Sprint 1, puis empiler les spécialistes Sprint 2+.

### Vision long-terme validée par Tom (fin de session)
Équipe complète d'agents autonomes autour de Smyleplay :
- Dev (le watt-dev-agent actuel)
- Création prompts (Suno, ADN WATT, voix)
- Maintenance (monitoring, healthchecks)
- Modération (review prompts uploadés)
- Marketplace (Stripe, refunds, audit transactionnel)
- Analytics (KPI hebdo)
- Support (drafts réponses tickets)

Cf. [[WATT_DEV_AGENT_Roadmap_MultiAgents]] pour le détail.

## Livré ce soir — 10 PRs

| # | Item | PR | Stats |
|---|------|----|----|
| 1 | S1-01 — Règles métier injectées | [#1](https://github.com/SMYLEPLAY/watt-dev-agent/pull/1) | +408/−4, 9 tests |
| 2 | S1-02 — Approval queue Postgres | [#2](https://github.com/SMYLEPLAY/watt-dev-agent/pull/2) | +629/−44, 6 tests |
| 3 | S1-03 — Bash gating universel | [#3](https://github.com/SMYLEPLAY/watt-dev-agent/pull/3) | +489/−18, 95 tests |
| 4 | S1-04 — Audit log append-only | [#4](https://github.com/SMYLEPLAY/watt-dev-agent/pull/4) | +443/−5, 7 tests |
| 5 | S1-05 — Tasks Postgres | [#5](https://github.com/SMYLEPLAY/watt-dev-agent/pull/5) | +298/−12, 9 tests |
| 6 | S1-06 — Webhook retry exponentiel | [#6](https://github.com/SMYLEPLAY/watt-dev-agent/pull/6) | +208/−11, 4 tests |
| 7 | S1-07 — Outils GitHub étendus | [#7](https://github.com/SMYLEPLAY/watt-dev-agent/pull/7) | +225/−12, 4 tests |
| 8 | S1-09 — Web tools opt-in | (mergé) | +116/−21, 7 tests |
| 9 | S1-10 — Healthcheck riche | (mergé) | +241/−4, 10 tests |
| 10 | S1-08 — Tests E2E + 3 bugs corrigés | (mergé) | +282/−19, 9 tests |

**Bonus S1-08** : 3 vrais bugs du code original détectés et corrigés en écrivant les tests d'intégration (auth retournait 422 au lieu de 401, background task mal initialisé, on_event deprecated).

## Décisions techniques notables

- **UUID en `String(36)`** dans la couche DB pour portabilité Postgres + SQLite (tests).
- **Classifier safe_bash isolé dans son module** sans dépendance SDK pour testabilité (~95 tests paramétrés).
- **Audit log silent on DB failure** : une perte d'audit ne casse jamais l'action métier.
- **Stub `claude_agent_sdk` en conftest** pour les tests d'intégration (le SDK n'est pas une dépendance publique facile en CI).
- **Lifespan handler** au lieu de `@app.on_event` (FastAPI 0.115+).

## État sécurité

- Token GitHub `github_pat_11CB2FAYQ0...` collé en clair dans le chat puis utilisé tel quel (Tom a refusé l'option régénération immédiate). Marqué comme dette dans la mémoire `project_watt_dev_agent_chantier.md`. À régénérer post-Phase D.

## Reste à faire (prochaine session)

1. **Upgrader Railway au Hobby Plan** ($5/mois min) — Tom n'a plus que $1.94 de crédit Trial. Smyleplay risque de tomber bientôt sans cet upgrade. Hobby devient obligatoire.
2. **Phase D — Déploiement Railway** (~30 min)
   - Créer projet Railway depuis le repo `SMYLEPLAY/watt-dev-agent`
   - Ajouter add-on Postgres
   - Configurer les variables d'environnement (ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_OWNER=SMYLEPLAY, GITHUB_REPO=watt-dev-agent ou cible, CONTROL_CENTER_URL placeholder, CONTROL_CENTER_WEBHOOK_SECRET, AGENT_AUTH_TOKEN)
   - Vérifier que `/health` répond OK depuis l'URL Railway publique
3. **Phase E — Mini-Control-Center web** (~1-2h)
   - Page web simple (HTML/JS ou Next.js) hébergée Railway
   - Liste les pending approvals via GET /approvals/pending
   - Boutons approve/reject (POST sur l'agent)
   - Mobile-friendly, possible Service Worker pour notifs push
4. **Test bout en bout** : lancer une tâche fake, recevoir notif tel, taper approve, vérifier que ça marche
5. **Sprint 2** — Router + agent QA review (probablement, à confirmer)

## Liens

- [[WATT_DEV_AGENT_ADR_001_durcissement]] — décision d'archi
- [[WATT_DEV_AGENT_Sprint1]] — backlog Sprint 1
- [[WATT_DEV_AGENT_Roadmap_MultiAgents]] — vision Sprint 2+
- Repo : https://github.com/SMYLEPLAY/watt-dev-agent
