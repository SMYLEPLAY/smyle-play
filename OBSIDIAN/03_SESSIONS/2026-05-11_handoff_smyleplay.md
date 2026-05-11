---
title: HANDOFF Smyleplay — Plan d'action pour reprise
type: handoff
tags: [handoff, session, smyleplay, plan, reprise]
updated: 2026-05-11
---

# HANDOFF — Reprise Smyleplay dans un chat propre

## Comment utiliser ce doc

Tom ouvre un nouveau chat Claude/Cowork et colle le **§ Prompt de reprise** ci-dessous. Le nouveau Claude aura immédiatement tout le contexte.

---

## § Prompt de reprise (à copier-coller dans le nouveau chat)

```
Tu es mon assistant d'exécution stratégique pour Smyleplay.
Posture : direct, structuré, orienté résultat. Tu me contredis si je vais dans la
mauvaise direction. Pas de chronologies/estimations de temps prématurées.

# État actuel (validé 2026-05-11)

Backlog priorisé existant : OBSIDIAN/01_PRODUIT/BACKLOG_SHIP.md
Ce backlog est la source de vérité. Le lire en premier avant toute action code.

WATT DEV AGENT : livré en prod (Phase D + Phase E + Sprint 2 push notifs) mais
PAUSÉ pour le moment. Utilité réelle = Phase F/G multi-agents, pas maintenant.
On reviendra dessus quand on aura besoin de paralléliser ou d'orchestrer.

Focus actuel = avancer Smyleplay direct.

# Plan d'action séquentiel validé v3 (mise à jour 2026-05-11)

Stratégie : construire la maison (tuyauterie) AVANT de la décorer (catalogue).
Pas l'inverse. Ajout d'une Phase 0 quick wins bugs en tête.

## Phase 0 — QUICK WINS BUGS (à attaquer en premier)
3 bugs critiques visibles en prod qui dégradent l'expérience d'achat.

- P1-B8 : Sons unlock pas écoutables depuis /library (bug critique conversion)
- P1-B11 : Slide déconnexion reste ouvert sur /u/<slug>
- P1-B12 : Contraste écritures violettes insuffisant (accessibilité WCAG)

## Phase 1 — TUYAUTERIE PUBLICATION (ex Bloc 1)
Sans ça, marketplace inutilisable. Les uploads ne sont pas visibles.

- P1-F2 : Publication cross-page (artist publie → /u/<slug> + accueil)
- P1-F5 : DELETE /api/watt/tracks/{id} Flask → FastAPI
- P1-F8 : POST /api/watt/plays/{id} Flask → FastAPI
- P1-F6a : Modèle Playlist + Like + auto-playlists Mes sons + Mes likes (backend)
- P1-F6b : Tab "Playlists" sur /u/<slug> (filtre visibility=public)
- P1-F6c : UI gestion playlists dans le dashboard + boutons like + (ajout playlist) globaux

## Phase 2 — TUYAUTERIE ACHAT + UX MARKETPLACE (ex Bloc 2)
Sans ça, pas de monétisation. Promesse "marketplace de prompts" non livrée.

- P1-F3 étendu : Cellule DNA vendable + unlock direct depuis accueil + modal preview
- P1-F4 étendu : Fiche vente prompt + jauges numériques 0-100 + DNA style + Mood
- P1-B10 : Page dédiée /track/<id> (SEO + partage)
- P1-B9 : Refonte affichage Top sons (nom à gauche de la bande)
- P1-B6 précisé : Cadenas + badge prix discret + covers sur /u/<slug>
- P1-C2a : Tarifs UI placeholder (montrer la vision pricing)
- P1-F9 backend : Vente voix complète (table voices_for_sale, endpoints, achat)

## Phase 3 — REMPLIR LE CATALOGUE (ex Bloc 3)
Une fois tuyauterie OK, on peut décorer.

- P1-PLAYLIST-1 : Champ `universe` formulaire upload
- P1-PLAYLIST-2 : Colonne `universe` DB tracks (migration Alembic)
- P1-PLAYLIST-3 : Transformer 4 cards accueil en filtres dynamiques
- P1-PLAYLIST-4 : Page "ADN global Smyle"
- P1-PLAYLIST-5 : Upload des 81 sons perso Tom

## Phase 4 — RECHERCHE + RESTE P1 (ex Bloc 4)
- P1-B7 : Casquettes sélectionnables Identité
- P1-SEARCH : Refonte accueil 3 barres recherche dépliables (DNA + Mood + Connect)
- P1-F7 : Réutiliser dispositif recherche DNA/Connect sur accueil
- P1-D10 : Audit migrations Alembic INTEGER vs UUID
- Tout P2 : dette code, migration Flask, tests, i18n, tarification

## Listes signature WATT figées 2026-05-11

DNA style (15) : Trap, Rap, RnB, Pop, Afro, Reggaeton, Dancehall, Deep House, Electro, House, Jazz, Soul, Classique, Rock, Autre.
Moods (10) : Joie, Triste, Fête, Zen, Voyage, Évasion, Travail, Sport, Soleil, Nuit.
DNA style obligatoire (1 choix) + Mood multi-select 1 à 3 max. Jamais fusionner.

# Hors sprint actuel (ne pas toucher)
- Stripe Checkout (après Tarification_v1)
- Stripe Connect cash-out vendeurs
- Abonnement récurrent
- Rewrite from scratch
- Migration framework front (React/Vue)
- Suppression flask_app.py avant F5/F6/F7/F8 complets
- Watt-dev-agent (en pause)

# Règles de fer (toujours actives)
- 1 chantier à la fois, dans l'ordre du plan
- 1 chantier = 1 commit = 1 PR
- Pas de patch sans ligne dans le backlog
- BACKLOG_SHIP.md est la source de vérité
- Nouveau bug/feature → ajouté au backlog, pas traité à chaud
- Voix séparées du flux musical (jamais shuffle/playlist/DNA)
- Prompts/ADN/voix verrouillés sans achat (teaser metadata only)
- Playlist toggle public/privé obligatoire avant Enregistrer
- Track = recette Suno unifiée
- Copywriting honnête (pas d'arguments commerciaux non prouvés)
- ADN visuel : noir / chrome / bleu électrique / mauve
- URL jamais dans Terminal — toujours préciser "dans Chrome"
- Comptes pré-migrations ont champs DB vides — vérifier les données AVANT de chercher un bug code
- Push systématique rappelé après chaque modif (Tom regarde la prod Railway)
- Pas de chronologies/estimations de temps prématurées (souvent mal évaluées)

# Posture importante
Tom n'est PAS développeur. Guidage clic par clic, sans jargon. Toujours
préciser "dans Chrome" quand URL donnée. Tom lit sur mobile pendant le service
de nuit, mais code sur Mac le matin.

# Démarrage de la nouvelle session

Tom dira "on attaque B8" ou "on reprend Smyleplay". Tu commences par :
1. Confirmer que prod Smyleplay est UP : https://web-production-e30c8c.up.railway.app
2. Lire BACKLOG_SHIP.md (v3) pour confirmer l'item à attaquer
3. Lire la section précise du backlog correspondante
4. Guider Tom étape par étape

Premier chantier Phase 0 = P1-B8 (diagnostic sons unlock biblio).

# Documents de référence à lire en début de session
- OBSIDIAN/01_PRODUIT/BACKLOG_SHIP.md (backlog priorisé v3, source de vérité)
- OBSIDIAN/01_PRODUIT/Dette_technique.md (D1 → D7)
- OBSIDIAN/01_PRODUIT/Bugs_connus.md
- OBSIDIAN/00_INDEX.md (point d'entrée vault)
- OBSIDIAN/03_SESSIONS/2026-05-11_handoff_smyleplay.md (ce doc — récap + cadrage 11 problématiques)
- graphify-out/wiki/index.md (navigation code)
- CLAUDE.md (règles projet)
```

---

## Récap de ce qui a été décidé (2026-05-11)

### Pause watt-dev-agent
Livré en prod (Phase D Railway + Phase E bot Telegram + Sprint 2 push notifs auto).
Mis en pause parce que :
- Surcoût ~$10-20/mois (API Anthropic + Railway)
- Utilité réelle MVP solo limitée (Cowork sur Mac suffit pour 1 agent)
- 12h d'investissement pour zéro valeur business immédiate
Réactivable en 5 min quand vraie utilité arrivera (voyage, parallélisme, Phase F/G).

### Réorientation focus → Smyleplay
Backlog Smyleplay sprint v2 défini le 22 avril, stagnait depuis 1 semaine
(watt-dev-agent a aspiré la productivité). Reprise du sprint, dans l'ordre.

### Correction stratégie remplissage catalogue
Initial : "remplir les playlists Smyle signature en priorité".
Corrigé par Tom : "d'abord la tuyauterie (publication + achat), ensuite décorer".
Raison : marketplace vide mais fonctionnelle vaut mieux que vitrine pleine qui plante.

---

## Liens externes
- Repo : (local `Smyleplay/.git`)
- Prod : https://web-production-e30c8c.up.railway.app
- Vault Obsidian : `OBSIDIAN/`
- Graph code : `graphify-out/graph.html`
- Watt-dev-agent (en pause) : https://watt-dev-agent-production.up.railway.app/docs
- Repo agent : https://github.com/SMYLEPLAY/watt-dev-agent

---

## 🆕 Mise à jour — Suite de session 2026-05-11 — Cadrage 11 problématiques

Cette mise à jour suit la 1ʳᵉ partie du doc. Tom a relancé une session pour faire un point UX sur Smyleplay et a remonté 11 problématiques visibles en prod. Cadrage fait avant tout code.

### Les 11 problématiques remontées

1. Jauge "style influence" pas en numéro sur 100 comme Suno.
2. Sons unlock pas écoutables depuis `/library`.
3. Pas de like sur les sons → impossible de les ajouter dans `My Mix` ou créer des playlists.
4. Pas d'unlock direct depuis l'accueil → obligation d'aller sur le profil artiste = perte de conversion.
5. Présentation des morceaux dans "Top sons" pas claire → nom du morceau à gauche de la bande demandé.
6. Covers pas affichées dans "Tous les sons" → besoin d'une page card-détail au clic.
7. Covers absentes sur le slug + bande jaune "Unlock" pas esthétique, trop envahissante.
8. Bug : slide déconnexion reste ouvert en haut à droite sur `/u/<slug>`.
9. Écritures violettes trop sombres, illisibles.
10. Finir connectique recherche DNA avec moods + brancher Connect avec profils.
11. Intégrer plus tard un système d'échange de cardsong (trade entre users, brûle des crédits).

### Décisions structurantes

- **Phase 0 inséré avant Bloc 1** : 3 bugs critiques (B8 + B11 + B12) passent **AVANT** les features de tuyauterie.
- **Point 3** : like → playlist auto **"Mes likes"** (créée au 1er like, default `private`). Bouton `+` séparé pour playlist nommée. Login obligatoire pour like + playlist + unlock.
- **Point 4** : double dispositif — modal preview accueil + bouton Unlock direct + lien profil artiste préservé.
- **Point 6** : **page dédiée `/track/<id>`** (pas modal). Raison : SEO + lien partageable.
- **Point 7** : cadenas + badge prix discret intégré dans la card (pas bande jaune). Clic card → `/track/<id>`.
- **Point 10** : refus de la fusion moods/genres → **2 taxonomies séparées**, listes fermées signature WATT figées.

### Listes signature WATT figées 2026-05-11

**DNA style (15 genres)** : Trap, Rap, RnB, Pop, Afro, Reggaeton, Dancehall, Deep House, Electro, House, Jazz, Soul, Classique, Rock, Autre.

**Moods (10)** : Joie, Triste, Fête, Zen, Voyage, Évasion, Travail, Sport, Soleil, Nuit.

→ DNA style = obligatoire (1 choix). Mood = multi-select 1 à 3 max. Combinaison = clé recherche fine.

### Conséquences backlog

[[BACKLOG_SHIP]] passé en **v3** :
- 5 nouveaux items P1 : B8, B9, B10, B11, B12.
- Extensions F3 (unlock direct), F4 (jauges numériques + DNA style + Mood), F6 (likes + visibility), B6 (cadenas + cover slug).
- Nouvelle section "Listes signature WATT figées 2026-05-11".
- Nouveau récap "Ordre d'exécution v3" en 4 phases.

### Ordre d'exécution v3 (à jour 2026-05-11)

- **Phase 0** : B8 → B11 → B12 (quick wins bug, **on commence ici**)
- **Phase 1** : F2 → F5 → F8 → F6a → F6b → F6c (tuyauterie publication)
- **Phase 2** : F3 → F4 → B10 → B9 → B6 → C2a (tuyauterie achat + UX marketplace)
- **Phase 3** : PLAYLIST-1 à 5 (remplir catalogue)
- **Phase 4** : B7 → SEARCH → F7 → D10 → F9 backend (recherche + reste P1)

### Premier chantier code : P1-B8

Diagnostic en prod du bug "sons unlock pas écoutables depuis `/library`".

Étapes :
1. Confirmer prod UP sur https://web-production-e30c8c.up.railway.app
2. Tom ouvre `/library` **dans Chrome** (PAS Terminal), connecté avec un compte qui a au moins 1 son unlock.
3. Console DevTools ouverte (Console + Network) au clic Lecture sur un son unlock.
4. Tom partage les logs Console + Network → on identifie la cause.
5. Fix ciblé → 1 commit dédié → push → vérif prod.

---

## Prochaine session

Tom ouvre un nouveau chat, colle le **§ Prompt de reprise** ci-dessus, dit
"on attaque B8" ou "on reprend Smyleplay". Le nouveau Claude a tout en main.
