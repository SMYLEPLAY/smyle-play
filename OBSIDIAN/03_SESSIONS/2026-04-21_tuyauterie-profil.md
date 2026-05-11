---
title: Session tuyauterie profil — 2026-04-21
type: session
date: 2026-04-21
tags: [session, tuyauterie, profil, ux]
status: en-cours
---

# 2026-04-21 — Tuyauterie profil (handoff nouvelle conv)

> **But du handoff** : reprendre la conv sans réexpliquer le contexte.
> Suite de [[2026-04-21_deploy-api]] et [[2026-04-21]].

---

## État actuel (à l'heure du handoff)

### Code poussé mais **PR pas encore mergée**
- **Branche** : `fix/signup-minimal`
- **Commits** :
  - `d600065` — signup minimal (retrait champ nom)
  - `5cd67d1` — profil unifié sur /dashboard (ADR-001)
- **PR** : https://github.com/SMYLEPLAY/smyle-play/compare/main...fix/signup-minimal?expand=1
- **Bloqueur** : Tom doit merger via UI GitHub (branch protection active, CI doit être verte)

### Prod
- Tourne encore sur l'**ancien code** (PR pas mergée)
- Test accordéon KO pour Tom → **c'est normal**, prod pas encore redéployée

---

## Décisions gravées cette session

### ADR-001 — Édition profil unifiée sur /dashboard
- `/dashboard#sec-identity` = **UNIQUE** lieu d'édition (atelier). Accordéon fermé par défaut.
- `/u/<slug>` = vue publique 100% read-only (boutique).
- Owner sans nom sur `/u/<slug>` → redirect `/dashboard#sec-identity`.
- Owner avec nom mais !publié → bouton "Publier mon profil" (Option B, déjà câblé).
- `artiste.js::toggleOwnerEdit` neutralisé (redirige).
- Bouton "Modifier" → "Éditer dans le dashboard".
- Voir [[Dette_technique#ADR-001]].

### Signup minimal
- 2 champs uniquement : email + password.
- Plus de champ nom/display_name.
- La création de profil se fait **après** connexion, depuis le dashboard.

### Git / Infra
- CI verte sur main (commit `cf0fa48`), branch protection stricte active.
- Repo passé en **public** (Tom refuse le plan Team pour branch protection).
- `*.sql` et `*.dump` ajoutés au `.gitignore` (dumps jamais commit).
- `backup.sql` supprimé du workspace local (contenait password DB).

---

## ⚠️ Chantier suivant validé par Tom — PAS encore implémenté

### Simplification "1 bouton unifié"

**Problème UX remonté par Tom** :
> "pour quoi plug watt n'est pas directement integrer a la creation de profil et ne remplace pas le bouton enregistrer ? cest dur de comprendre la manip, sa serait plus simple de publier directement le profil non ?"

**Décision** : éliminer la distinction Enregistrer / Publier pour le premier cas.

| État profil | Bouton dashboard | Action |
|---|---|---|
| `profile_public=false` (1re fois) | **"Publier mon profil"** | PATCH /users/me + POST /watt/me/profile/publish en séquence |
| `profile_public=true` | **"Enregistrer"** | PATCH /users/me seulement (déjà live) |

**Conséquences** :
- `/u/<slug>` avec `profile_public=false` ET non-owner → **404**
- `/u/<slug>` avec `profile_public=false` ET owner → redirect dashboard
- Plus de bouton "Publier" sur `/u/<slug>` (supprime Option B devenue caduque)
- Dépublication reste gérée via PLUG WATT (toggle de visibilité, cas rare)

**Référence design** : Vinted, Airbnb, LinkedIn — 1 action "Mettre en ligne" la 1re fois.

---

## ⚠️ Question ouverte non traitée

**Dernier message de Tom (non répondu)** :
> "pour quoi y a encore toujours le slug en mode creation de profil ? modifie sa"

**À clarifier avec Tom** avant d'agir :
- Le champ slug est-il éditable en mode création → veut-il qu'il soit auto-généré depuis artist_name ?
- Ou veut-il simplement retirer le champ visible à ce stade ?
- Piste probable : auto-slug à partir de `artist_name` (slugify côté back, champ en lecture seule ou édition avancée plus tard).

---

## Fichiers touchés (non committés pour le chantier suivant)

Aucun. Tout est clean côté git. Le chantier "1 bouton unifié" n'a pas commencé.

**Fichiers qui seront probablement touchés** pour le chantier suivant :
- `dashboard.js` (handler save → logique conditionnelle publish/patch)
- `dashboard.html` (label bouton dynamique)
- `artiste.js` (suppression Option B preview, renforcement du 404/redirect)
- `smyleplay-api/app/routers/users.py` (si slug auto-gen backend)

---

## Dette tech toujours ouverte (non-bloquante mais à savoir)

- **D1** : modèles Flask legacy en INTEGER id (incompatibles UUID FastAPI)
- **D4** : compte `smyle@smyleplay.com` non-loginable (password random inconnu)
- **D5** : pas de smoke tests (/health seulement via CI)
- **D6** : pas d'env staging (tout testé en prod → risqué)
- **Secrets prod** : Tom a leak DATABASE_URL/R2/SECRET_KEY en chat, **refuse la rotation**. Risque connu, assumé.
- **Backup Postgres** : script `scripts/backup_db.sh` présent mais cassé (DATABASE_PUBLIC_URL pas activé + railway link pointe sur `web` pas Postgres).

Voir [[Dette_technique]] complet.

---

## Comportement Claude attendu (rappel pour la nouvelle conv)

Format Tom :
- Analyse rapide
- Problème identifié
- Solution recommandée
- Étapes concrètes

Principes :
- Direct, pas de blabla, pas de validation automatique.
- Contredire si mauvaise direction avec argument.
- Priorité business/produit/user > technique pure.
- **Ne pas repartir dans des détours infra** (Tom a été explicite : "j'en ai marre des détours, je veux bosser sur le projet").
- Ne pas proposer de rotation secrets sans qu'il demande.
- Respecter convention Obsidian : tout doc stratégique dans `OBSIDIAN/`, jamais à la racine.

---

## Prochaine action immédiate

1. **Tom merge la PR** https://github.com/SMYLEPLAY/smyle-play/compare/main...fix/signup-minimal?expand=1
2. **Attend Railway redeploy** (~2 min)
3. **Test accordéon en navigation privée** → si OK, valide
4. **Clarifier la question slug** (auto-gen ou suppression)
5. **Démarrer chantier "1 bouton unifié"**

---

## Liens
- [[2026-04-21_deploy-api]] — session déploiement initial
- [[2026-04-21]] — plan du jour
- [[Dette_technique]]
- [[Roadmap]]
