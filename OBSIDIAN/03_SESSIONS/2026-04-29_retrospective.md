---
title: Rétrospective session 2026-04-29 — pré-saison nocturne
type: session
tags: [session, retrospective, sprint, alpha]
updated: 2026-04-29
---

# Rétrospective session 2026-04-29

**Contexte** : dernière session avant saison de service 7j/7 nuit. Tom passe en mode async fatigué.

## État global du projet — bilan factuel

**Ce qui FONCTIONNE en prod (validé bout-en-bout)** :
- Inscription / login / persistance profil + casquettes en DB
- Marketplace : artistes publics visibles (officiel Smyle + autres)
- Modale d'achat de SMYLES (badge balance topbar) avec stub V1 `/credits/grant`
- **Achat ADN bout-en-bout** : acheteur débité, vendeur crédité 80%, ADN unlock dans `/library`
- Logout purge complet localStorage (pas de fuite entre comptes)
- Endpoint `/credits/grant` gating prod via `ENVIRONMENT` env var

**Ce qui N'A PAS pu être validé dans cette session** :
- Test bout-en-bout achat de prompt (bloqué sur ADN absent en DB côté Smyle — cause inconnue)

## Bugs détectés non résolus

| ID | Bug | Statut | Effort |
|---|---|---|---|
| **B10** | Token JWT partagé entre onglets/fenêtres Chrome | Workaround = navigateurs séparés | 2-3h refactor |
| **B11** | Toast `[object Object]` au lieu détail Pydantic | Fix codé, pas pushé | 0 (prêt) |
| **B12** | Désync dashboard ADN (cache vs DB) | Fix codé, pas pushé | 0 (prêt) |
| **B13** | ADN de Smyle disparu de la DB entre 14h et 15h sans action user | Non investigué (pas accès DB Railway) | 30 min logging |

## PRs livrées dans cette session

1. `feat/identity-roles-persist` (commit `a59d334`) — persistance casquettes
2. `feat/credits-buy-modal` (commit `417e011`) — modale achat SMYLES
3. `fix/marketplace-empty-tracks` (commit `c21524a`) — OUTER JOIN backend marketplace
4. `fix/marketplace-vitrine-smyle` (commit `6d8e2b3`) — extraction artist côté front
5. `fix/alpha-ready-security` (commit `4f1acb0`) — logout purge + gating prod /credits/grant
6. `fix/dashboard-error-rendering` — fix B11+B12 ✅ codé, **pas encore pushé**

## Mode opératoire async (à activer)

### Auto-merge GitHub (en cours de configuration)
Tom est sur `https://github.com/SMYLEPLAY/smyle-play/settings`, en train de cocher :
- ✅ "Autoriser la fusion automatique"
- ✅ "Suppression automatique des branches principales"
- (Étape suivante) Branch protection sur `main` avec approvals à 0 si Tom veut éviter d'avoir à approuver lui-même

Une fois activé : Tom clique 1× **"Activer la fusion automatique"** sur chaque PR depuis mobile → GitHub merge tout seul quand CI verte.

### Cadence cible
- Cowork : 2-3 PRs/semaine en autonomie max
- Tom : valide les PRs depuis mobile (~30 sec/PR), batch testing 1×/semaine sur jour off
- Alpha publique testable : 2-3 semaines si cadence tenue

## Reprise — ordre des chantiers

Voir `OBSIDIAN/04_TASKS/2026-04-29_chantier_continuation.md` pour le détail step-by-step.

**Résumé prioritaire** :

1. **Étape 1** — Tom recrée son ADN en DB (logout/login d'abord pour purger cache, puis dashboard cellule ADN → Sauvegarder + Publier)
2. **Étape 2** — Tom retest la création de prompt (texte ≥ 100 chars, prix 3-500)
3. **Étape 3** — Test bout-en-bout achat prompt (Safari pour TL, Chrome pour Smyle)
4. **Étape 4** — Backend vente voix (table `voices_for_sale` + endpoints + R2) — Cowork en autonomie 2-3 j
5. **Étape 5** — Pricing v1 — session dédiée 2-4h tête reposée

## Règles permanentes (à respecter dans toute nouvelle session)

- **Règle de fer Smyleplay** : 1 chantier = 1 commit = 1 PR. Pas de patches isolés.
- **URL = Chrome barre d'adresse**, JAMAIS Terminal.
- **Tom regarde uniquement la prod Railway**, rappeler le push après chaque modif.
- **Copywriting honnête** : pas d'arguments commerciaux non prouvés.
- **Voix séparées** : voix jamais en shuffle/playlist/DNA, table et endpoints séparés.
- **Prompts/ADN/voix verrouillés publiquement** : teaser métadonnées uniquement.
- **Anciens comptes pré-migrations** : profil DB FastAPI quasi vide, vérifier les données AVANT de chercher un bug code.

## Contraintes Tom à connaître

- Saison de service **7j/7 horaires de nuit** depuis 2026-04-30
- Énergie basse, peu de plages disponibles
- **Aucune compétence en code** : guider chaque manip étape par étape, mots simples
- Préfère **réponses courtes, structurées** (analyse rapide / problème / solution / étapes)
- Demande à être contredit si direction sous-optimale
- Ne mélange pas les chantiers — backlog priorisé d'abord

## Format de reprise dans nouvelle session

Tom dira simplement :
- `go étape 1` → cowork relit `OBSIDIAN/04_TASKS/2026-04-29_chantier_continuation.md` et reprend
- `attaque tâche backend voix` → cowork commence en autonomie

Cowork **NE doit PAS** demander à Tom de re-raconter. Tout est dans les docs Obsidian + auto-memory.
