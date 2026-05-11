---
title: Pivot stratégique — STOP patches, audit exhaustif d'abord
type: session
tags: [session, pivot, strategie, produit, bloquant]
updated: 2026-04-22
---

# Session 2026-04-22 — Pivot "STOP patches, on fait la carte d'abord"

> ⚠️ **À LIRE EN TOUT PREMIER AU DÉBUT DE CHAQUE PROCHAINE SESSION CLAUDE.** Cette note fixe une nouvelle règle de fer qui prime sur tout le reste.

## Contexte

Tom est frustré : impression de tourner en rond, on revient sans cesse sur des choses déjà faites, chaque nouveau chantier rouvre des bugs ailleurs. A envisagé un **rebuild from scratch** du projet. Claude l'en a dissuadé avec arguments business (cf. échange plus haut dans la session).

Tom a choisi l'**option B** : Sprint Nettoyage + Ship (3 semaines), pas de rebuild.

Puis a explicité la vraie douleur : trop de choses en suspens en même temps (badges, tuyauterie sons, ADN en vente sur profil, traduction EN, enregistrement réel, economy qui tourne, bugs UX accumulés : profil géant sur accueil, titre doublé, morceaux playlist inactifs, PLUG WATT mal placé…).

## Diagnostic — le vrai problème

**Ce n'est pas l'architecture. C'est la méthode de pilotage.**

On patche en miettes, sans carte d'ensemble. Résultat : Claude perd le fil entre sessions, Tom doit re-rappeler 10 choses à chaque fois, on en règle 1, les 9 autres reviennent.

## 🔴 NOUVELLE RÈGLE DE FER — À RESPECTER DANS TOUTES LES PROCHAINES SESSIONS

1. **Avant tout code**, lire `OBSIDIAN/01_PRODUIT/BACKLOG_SHIP.md` (à produire).
2. **Un chantier à la fois.** Dans l'ordre du backlog. Pas de parallèle. Pas de "pendant qu'on y est". Pas de déviation.
3. **Nouveau bug repéré en cours de route** → ajouté au backlog, **pas traité à chaud**.
4. **Chaque commit ferme exactement un chantier.** Le backlog est mis à jour.
5. **Pas de nouvelle feature tant que le backlog courant n'est pas vidé.**

Cette règle prime sur toute demande ad-hoc de Tom. Si Tom demande un patch isolé, Claude doit lui rappeler la règle et proposer de l'ajouter au backlog à la bonne position.

## Prochaine action (ce qui bloque tout le reste)

**Chantier #8 dans la task list** : Audit exhaustif du projet → 3 listes fermées :
- BUGS visibles (liste de tous les bugs connus, priorisés par impact business)
- FEATURES manquantes pour ship (upload sons, ADN en vente, traduction EN, enregistrement réel, Stripe, etc.)
- DETTE morte à supprimer (flask_app.py legacy, doublons HTML, fichiers orphelins)

**Chantier #9** (bloqué par #8) : Rédiger `OBSIDIAN/01_PRODUIT/BACKLOG_SHIP.md`. Un seul doc numéroté/priorisé. Chaque ligne = 1 chantier = 1 commit.

**Chantier #10** (bloqué par #9) : Tom relit, reclasse si besoin, valide.

Dès que #10 est validé → on exécute dans l'ordre. Commit/jour. Progrès visible chaque jour.

## Modifications locales non commitées (à intégrer au backlog, pas à committer isolé)

- `ui/smyle-balance.js` : fix race condition topbar/widget (badge SMYLES dupliqué qui chevauche l'avatar sur `/u/<slug>` et `/library`). Diagnostic complet fait, code patché localement, **pas encore committé**. À intégrer comme premier chantier du BACKLOG_SHIP dans la plupart des scénarios (P0 UX sur la page publique).

## Liste brute des sujets remontés par Tom aujourd'hui (matériel pour l'audit)

**Bugs UX visibles**
- Badge SMYLES dupliqué sur topbar (`/u/<slug>`, `/library`) — déjà patché local non commit
- Titre doublé (titre en dessous du titre — à localiser pendant l'audit)
- 4 playlists WATT (Hit Mix, Jungle Osmose, Night City, Sunset Lover) n'apparaissent plus sur le profil
- Profil de Tom affiché en énorme sur la page d'accueil, prend toute la place, pas de slot pour les autres futurs profils
- Accordéon "Identité publique" pas intuitif (on ne comprend pas qu'il faut cliquer)
- PLUG WATT séparé du profil — devrait être intégré dans la création du profil (toggle publier direct)
- Barre "déconnexion" qui apparaît sur `/u/<slug>` alors qu'elle ne devrait pas (lié au badge dupliqué ? à vérifier pendant audit)

**Features manquantes pour ship**
- Page d'achat smyles (Stripe remplace le stub /credits/grant)
- Tuyauterie upload de sons → apparaissent sur profil artiste
- Tuyauterie upload d'ADN artiste → en vente sur profil
- Upload de voix (Option W : marketplace de fichiers audio, pas de création sur site)
- Traduction EN du site
- Enregistrement utilisateur "pour de vrai" (à clarifier pendant l'audit — probablement : onboarding, vérification email, etc.)
- Economy qui tourne bout-à-bout (acheter smyles → acheter contenu → créditer vendeur)

**Dette à tuer**
- `flask_app.py` legacy — migrer derniers endpoints R2 upload vers FastAPI puis supprimer
- `mon-profil.html` — doublon de dashboard.html, à supprimer (ADR-001)
- Fichiers orphelins à identifier pendant l'audit

## Règle anti-frustration pour Claude

Tom a 0 compétence code et dépend 100% de Claude. Ça oblige à :
- **Une seule direction claire à la fois** (pas d'options floues, pas de parallèle)
- **Étapes minuscules, exactes, dans l'ordre** (où cliquer, quoi écrire)
- **Pas de jargon, ou jargon expliqué immédiatement**
- **Pousser à Terminal** pour toute opération git (sandbox Claude ne peut pas push)

## Liens vault

- [[01_PRODUIT/BACKLOG_SHIP]] (à créer après audit)
- [[00_INDEX]]
- [[05_TECH/Runbooks]]
