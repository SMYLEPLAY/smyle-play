---
title: BACKLOG_SHIP — Sprint 3 semaines
type: backlog
tags: [backlog, produit, sprint, priorise]
updated: 2026-05-11
version: 3
---

# BACKLOG_SHIP — Sprint 3 semaines (v3 — ajouts 2026-05-11)

> Document unique et priorisé. **Chaque ligne = 1 chantier = 1 commit = 1 PR.**
> V1 : audit brut. V2 : cadrage Tom 2026-04-22 (C1-C4 + découpage C2 + posture pricing).
> V3 : ajout 2026-05-11 — 5 nouveaux items UX (B8 → B12), extensions F3/F4/F6 (unlock direct, jauges numériques, like + playlists publiques/privées), listes moods/genres figées.
> Voir aussi : [[Tarification_v1]] pour le chantier pricing à part, [[DEV_PAIR_SESSION]] pour l'onboarding dev externe, [[2026-05-11_handoff_smyleplay]] pour le contexte de la session de reprise.

---

## ⚠️ RÈGLE DE FER — à lire avant toute action

1. **1 chantier à la fois**, dans l'ordre P0 → P1 → P2
2. **Nouveau bug en cours de route** → ajouté à ce backlog, **pas traité à chaud**
3. **1 chantier = 1 commit = 1 PR** (pas de fourre-tout)
4. **Pas de patch sans ligne de backlog correspondante**
5. **Ce backlog est la source de vérité** — les sessions Claude doivent le lire en premier

---

## 🚫 Hors sprint (sortis volontairement — ne pas toucher)

- ❌ **Pricing final** → chantier dédié dans [[Tarification_v1]], sessions à tête reposée. Pas avant fin de sprint.
- ❌ **Stripe Checkout** (C2b) → arrive après validation de Tarification_v1.
- ❌ **Stripe Connect cash-out vendeurs** (C2d) → 2-3 semaines pleines, pas dans ce sprint.
- ❌ **Abonnement récurrent** (C2e) → arrive avec Stripe.
- ❌ **DNA playlist** (Q4a) → 1 DNA général par profil suffit pour MVP.
- ❌ **Rewrite from scratch** (tranché 2026-04-22, voir [[2026-04-22_pivot_audit]])
- ❌ **Migration framework front** (React/Vue) — vanilla JS reste
- ❌ **Supprimer `flask_app.py`** avant exécution complète de F5/F6/F7/F8

---

## 🔴 P0 — BLOQUANTS / WARM-UP (semaine 1, ~1-2 jours)

### ✅ P0-B1. Fix badge SMYLES dupliqué — LIVRÉ 2026-04-22
- **Où** : `/u/<slug>` + `/library`
- **Cause** : race condition entre `ui/smyle-balance.js` (boot DOMContentLoaded) et `ui/topbar/topbar.js` (boot tardif injectant `#smyle-balance`)
- **PR** : [#5](https://github.com/SMYLEPLAY/smyle-play/pull/5) mergée le 2026-04-22, commit `7a1d551`

### ✅ P0-F1. Persistance profil complète en DB — LIVRÉ 2026-04-28 (PR #13, commit `a59d334`)
**État réel post-audit 2026-04-28** : le backend (modèle User, schemas Pydantic, migrations 0016/0017/0018, endpoint `PATCH /api/users/me`) couvrait DÉJÀ tous les champs prévus. Le bouton Sauvegarder de la cellule 01 Identité câblait DÉJÀ presque tout. Seul gap réel : `roles` (casquettes) absent du payload + liste JS `DASH_ID_ROLES` divergente de `ROLE_CODES` backend → casquettes restaient en localStorage uniquement.
**Fix livré** : alignement liste JS sur les 12 codes backend, ajout `roles` au payload `dashIdentitySave`, hydratation `roles` depuis `me.roles` dans `loadPublishStatus`. +29 / −12 lignes (1 fichier).
**Champs hors-scope volontaire** : `slug` (géré par `/api/watt/profile` Flask, à migrer plus tard), `country` (pas dans schéma backend), `language` (pas exposé dans la cellule 01).

### P0-F1-archive. Cadrage initial (avant audit)
- **Quoi** : bouton "Sauvegarder" du WATT BOARD persiste TOUS les champs profil en Postgres (pas en localStorage)
- **Champs à persister** (confirmés par Tom + enrichissement) :
  1. `artist_name` (nom d'artiste)
  2. `bio` (description)
  3. `avatar_url` (upload → R2)
  4. `banner_url` (image de bannière → R2)
  5. `genres` (array, multi-select)
  6. `brand_color` (déjà partiellement câblé)
  7. `slug` (URL publique `/u/<slug>`)
  8. `social_links` (Instagram, YouTube, SoundCloud, Spotify, TikTok, site perso)
  9. `country`, `city`
  10. `locale` (langue préférée)
  11. **`roles` (array enum)** — casquettes : `auditeur`, `beatmaker`, `dj`, `topliner`, `producteur`, `ghostwriter`, `compositeur`, `interprete`, `inge_son`, `designer_sonore` (min 1, max libre)
- **Étape** : au clic du bouton Sauvegarder du WATT BOARD (option A validée)
- **Backend** : `PATCH /api/users/me` côté FastAPI, migration Alembic pour nouveaux champs
- **Frontend** : câblage du bouton + feedback visuel (toast "Profil sauvegardé ✓")
- **Effort** : 1 journée (migration + backend + front + tests manuels)

### ✅ P0-D6. Garde-fou SECRET_KEY en production — LIVRÉ 2026-04-22
- **Quoi fait** : `get_config()` crash explicitement au boot si `SECRET_KEY` absente ou encore à la valeur dev par défaut en prod. Fallback dev conservé pour local/tests.
- **PR** : [#6](https://github.com/SMYLEPLAY/smyle-play/pull/6) mergée le 2026-04-22, commit `939b112`
- **Prérequis Railway validé** : `SECRET_KEY` + `FLASK_ENV=production` présents avant merge (confirmé par Tom).

### P0-S1. Finaliser `DEV_PAIR_SESSION.md` pour ami codeur
- **Statut** : doc rédigé, Tom doit relire + décider timing
- **Voir** : [[DEV_PAIR_SESSION]]
- **Effort** : 10 min de relecture Tom

---

## 🟠 P1 — MAJEURS (semaine 2, ~4-5 jours)

### 🆕 P1-BUGS-V3 — Quick wins UX (ajouts 2026-05-11)
Ces 5 items remontés par Tom le 2026-05-11. Ils passent **AVANT** F2/F3/F4 dans l'ordre d'exécution parce que 3 sont des bugs visibles en prod qui dégradent l'expérience d'achat.

- [ ] **P1-B8. Lecture sons unlock cassée depuis `/library`** (bug critique conversion)
  - **Symptôme** : un son acheté/débloqué n'est pas écoutable depuis la bibliothèque.
  - **Diagnostic préalable requis** : ouvrir prod avec compte test, console DevTools (Console + Network) au clic Lecture, identifier si endpoint renvoie pas l'URL audio OU si le player ne se monte pas.
  - **Hypothèse** : `GET /api/library/tracks` retourne les tracks mais pas l'`audio_url` signed R2, OU le composant player attend un champ différent de ce que renvoie l'endpoint.
  - **Critère de sortie** : test reproductible OK en prod, lecture fluide sur ≥3 tracks unlock différents.

- [ ] **P1-B11. Slide déconnexion reste ouvert en haut à droite sur `/u/<slug>`** (bug visuel)
  - **Symptôme** : panneau de déconnexion reste affiché sur la page profil public alors qu'il devrait être fermé par défaut.
  - **Action** : repérer le composant (probablement `ui/topbar/topbar.js` ou un drawer), forcer l'état `closed` au mount de la page artiste.
  - **Critère de sortie** : panneau fermé par défaut sur `/u/<slug>`, ouverture uniquement au clic explicite.

- [ ] **P1-B12. Contraste écritures violettes insuffisant** (accessibilité)
  - **Symptôme** : textes violet sur fond sombre quasi illisibles.
  - **Action** : audit WCAG du ratio de contraste sur tous les textes violet du theme (rechercher `--color-violet*` ou équivalent dans CSS). Augmenter la luminosité jusqu'à ratio ≥ 4.5:1 (AA normal).
  - **À NE PAS faire** : changer la teinte au hasard. Outil : devtools accessibilité Chrome ou contrast-checker.com.
  - **Critère de sortie** : tous les textes violet du theme passent AA, ADN visuel préservé.

- [ ] **P1-B9. Affichage Top sons — nom à gauche de la bande** (UX marketplace)
  - **Symptôme** : sur la vision marketplace "Top sons", la présentation n'est pas claire.
  - **Spec Tom** : nom du morceau à gauche de la bande (cover/visuel), titre lisible en premier.
  - **Composant concerné** : probablement Banner (P1-B5) — vérifier si extension du Banner ou nouveau variant.
  - **Effort estimé** : 2-3h (CSS layout + ajustement Banner).

- [ ] **P1-B10. Page détail track `/track/<id>`** (refonte UX majeure — point 6 Tom)
  - **Spec validée Tom 2026-05-11** : **page dédiée** (PAS modal). Raison : SEO + partage de lien direct = vecteur d'acquisition gratuit.
  - **Comportement** : clic sur n'importe quel item track (accueil, profil, biblio) → ouvre `/track/<id>` avec : cover en grand, titre, artiste, prix, ADN vendable, bouton Unlock, bouton Like, bouton + (ajout playlist), métadonnées (genre, mood, plateforme, weirdness).
  - **Côté SEO** : balises Open Graph + Twitter Card avec cover + titre + artiste.
  - **Routing** : nouvelle route Flask/FastAPI + template ou rendu front.
  - **Dépendances** : nécessite F4 (champs métadonnées) + F6 (like + playlist) en partie pour être complet, mais la page peut exister en MVP sans ces dépendances complètes.
  - **Effort estimé** : 1-1,5 jour (route + template + composants réutilisés).
  - **Critère de sortie** : URL partageable, balises OG OK, tous les boutons fonctionnels OU stub explicite "bientôt".

### P1-F2. Tuyauterie publication cross-page (C3)
- **Quoi** : quand user publie depuis dashboard (son, voix, ADN), ça apparaît automatiquement sur :
  - `/u/<slug>` (profil public de l'artiste)
  - Interface principale (`index.html` — probablement section "Communauté" ou équivalent)
- **Diagnostic préalable requis (1-2h)** : tester en prod avec un compte test, identifier précisément quels endpoints ne sont PAS alimentés après publication. Très probablement :
  - `POST /api/tracks` crée la track mais `GET /api/artists/{slug}/tracks` ne la retourne pas (problème de filtrage `published_at`)
  - `GET /api/tracks/recent` (flux accueil) ne récupère pas les nouvelles publications
- **Effort** : 1 à 2 jours selon complexité du diagnostic

### P1-F3. Cellule DNA vendable sur profil public (C4)
- **Quoi** : 1 DNA "général" par profil peut être publié à la vente depuis le profil
- **Flow utilisateur (MVP)** :
  1. Dans le dashboard → section "Mes DNA" → bouton `Publier sur mon profil`
  2. Modale : sélection du DNA + prix en smyles (placeholder, voir Tarification_v1) + confirmer
  3. Sur `/u/<slug>` → cellule DNA s'affiche : image DNA + nom + prix + bouton Acheter
  4. Clic Acheter (visiteur connecté) → paie en smyles → DNA unlock dans son espace "Mes achats"
- **Produit livré à l'acheteur** : un prompt Suno haut niveau, plus travaillé et détaillé, de même nature que ceux générés par le skill `watt-prompt`. Livré sous forme de page "Mes achats" avec le prompt copiable + téléchargeable `.txt`
- **Backend** :
  - Nouvel endpoint `POST /api/dna/{id}/publish-for-sale {price}`
  - Adapter `GET /api/artists/{slug}` pour renvoyer le DNA publié
  - Endpoint `POST /api/dna/{id}/unlock` (débite smyles de l'acheteur, crédite vendeur, marque unlock)
- **Frontend** :
  - Bouton publication dans dashboard
  - Cellule sur `artiste.html` (emplacement : sous la bio, avant la liste tracks)
  - Page "Mes achats" pour l'acheteur
- **🆕 Extension 2026-05-11 (point 4 Tom) — Unlock direct depuis l'accueil** :
  - Sur l'accueil, les items track exposent un **bouton Unlock direct** + une **modal preview rapide** (cover + titre + prix + extrait écoutable + CTA "Unlock" + CTA "Voir l'artiste").
  - Raison stratégique : permettre la conversion sans forcer le détour par `/u/<slug>`, tout en gardant le pont vers le profil (cross-sell sur l'écosystème vendeur).
  - **À NE PAS faire** : supprimer le lien vers le profil artiste — il reste indispensable pour la découverte de l'écosystème vendeur (ADN global, autres sons, voix).
  - **Comportement** : modal s'ouvre sur clic preview, Unlock direct possible depuis la modal OU depuis la page `/track/<id>` (P1-B10).
- **Effort** : 2-3 jours (cellule profil) + 1 jour (modal preview + bouton unlock accueil)

### P1-F5. `DELETE /api/watt/tracks/{id}` — porter Flask → FastAPI
- **Quoi** : artistes ne peuvent pas supprimer leurs sons depuis la nouvelle UI car endpoint FastAPI absent
- **Action** : copier logique R2 delete Flask → `smyleplay-api/app/routers/tracks.py`, retirer shim de `watt_compat.py`
- **Effort** : 2h (code + test)

### P1-F8. `POST /api/watt/plays/{id}` — porter Flask → FastAPI
- **Quoi** : incrémenter les écoutes. Absent en FastAPI.
- **Effort** : 1h

### P1-C2a. Tarifs crédits affichés en UI (placeholder, non fonctionnel)
- **Quoi** : créer page / section "Acheter des crédits" avec grille de packs (valeurs placeholder)
- **Comportement** : bouton "Acheter" désactivé avec tooltip "Disponible bientôt"
- **Raison** : pouvoir montrer la vision aux premiers users sans déployer Stripe en rush
- **Valeurs réelles** : à injecter depuis [[Tarification_v1]] quand ce doc sera finalisé (hors sprint)
- **Effort** : 4h (grille UI + texte placeholder)

### P1-UX. Bugs UX profil remontés par Tom
Ces 3 items attendent tous **un screenshot + un test reproductible en prod**. Je refuse de les estimer tant que je n'ai pas vu le symptôme.

- [x] **P1-B3. Fusionner PLUG WATT dans Identité** ✅ LIVRÉ 2026-04-22 (commit `af20c02` → merge sur `main` `8345592`). Voir [[2026-04-22_spec_merge_01_04]].
  - Cellule 04 PLUG WATT supprimée, switch + preview + lien boutique intégrés dans la cellule 01 Identité.
  - Gate `#dashCreationGate` simplifié à 1 CTA, pill "PLUG WATT" retirée de la sous-nav.
  - Label "Publier mon profil" remplacé par un "Enregistrer" figé + switch ON/OFF explicite.
  - Net : +134 / −186 lignes (3 fichiers : dashboard.html, dashboard.js, artiste.html).
  - **Note prérequis** : livré SANS P0-F1 (persistance profil). Décision Tom (2026-04-22) = prioriser architecture visuelle avant connectique. Le "Enregistrer" sauvegarde toujours via PATCH /users/me existant ; le câblage complet des champs ADN / casquettes viendra avec P0-F1 / P1-F4.
- [ ] **P1-B4. Morceaux playlist inactifs au clic** — envoyer console DevTools (Console + Network) au clic
- [x] **P1-B5. Composant Banner unifié** (livré 2026-04-23, commit `6788cb4`). Spec Option B validée par Tom : un seul composant réutilisable pour vitrine accueil, classements, grille "tous les artistes", résultats recherche. Fichiers créés : `banner-card.css`, `banner-card.js`, `banner-demo.html`. **Reste à faire** : intégrer dans `index.html` pour remplacer les classements `.mp-ranking-row` + la grille `.mp-grid-artists` + la grosse card Smyle vitrine (étape 2, ~3h, planifiée 2026-04-24).
- [x] **P1-NAV1. Bouton 📚 BIBLIOTHÈQUE dans header** (livré 2026-04-23 sur index.html, commit `c3ebc01`). **Reste à faire** : propager sur dashboard.html + topbar partagée (artiste.html, library.html) pour cohérence cross-pages.

### P1-SEARCH. Refonte accueil — 3 barres de recherche dépliables côte à côte (spec Tom 2026-04-23)
- **Structure** : 3 barres horizontales au même niveau (DNA · CONNECT · VOICE), jamais empilées verticalement.
- **Chaque barre** = icône + label + flèche ▾ + input texte. Clic flèche → la barre concernée se déplie vers le bas avec ses filtres avancés. Les 2 autres restent repliées à leur place (pas d'empilement).
- **Filtres par barre** :
  - DNA : style musical, mood, tempo, plateforme, fourchette prix
  - CONNECT : style dominant profil, tags univers
  - VOICE : type vocal, genre vocal, genres compatibles, langue, licence, fourchette prix
- **Résultats** : affichés sous la barre dépliée en Banner compact (réutilise P1-B5).
- **Responsive mobile** : sur écran étroit, empilement vertical 1 par ligne, chacune gardant sa flèche.
- **État par défaut** : toutes repliées. But : interface propre, déploiement à la demande.
- **Estimation** : ~1,5 jour visuel (UI des 3 barres + dépliage + filtres stub + branchement Banner).
- **Priorité** : APRÈS intégration Banner dans index.html (P1-B5 étape 2). Les résultats utilisent le Banner → il doit être intégré d'abord.

### P1-PLAYLIST. Pré-lancement — remplir les 4 univers WATT avec catalogue Smyle signature (spec Tom 2026-04-23)
- **Vision produit** : AVANT mise en ligne publique, les 4 playlists hardcodées (Jungle Osmose, Night City, Hit Mix, Sunset Lover) doivent être remplies par le catalogue signature Smyle, avec prompts + prix + ADN vendable pour CHAQUE son.
- **Architecture décidée — modèle hybride à 2 niveaux** :
  - **Niveau 1** : les 4 univers WATT = **collections signature Smyle, verrouillées**. Seul le compte Smyle officiel peut y tagger des sons (protège la direction artistique, évite la dilution par self-tagging).
  - **Niveau 2** : genres musicaux ouverts (afro, jazz, reggaeton, deep house, etc.) = zone communautaire ouverte à tous les artistes.
- **ADN dual (choix C) — vendus en parallèle** :
  - *ADN par son* : 50-200 SMYLES, recette exacte pour reproduire CE son précisément (déjà en place).
  - *ADN global Smyle* : 500-2000 SMYLES, signature stylistique générale (mots-clés, influences, palette émotionnelle, genres dominants). Permet de créer *dans la vibe* sans reproduire un son précis.
  - *Différenciation anti-cannibalisation* : ADN global = style durable / ADN individuels = recettes one-shot. Marchés complémentaires.

**Chantiers techniques découpés** :
1. **P1-PLAYLIST-1. Champ `universe` formulaire upload** (~1h) — select 5 options (4 univers + `autre`), visible UNIQUEMENT pour compte Smyle (rôle admin ou feature flag).
2. **P1-PLAYLIST-2. Colonne `universe` DB tracks** (~30 min backend) — migration Alembic.
3. **P1-PLAYLIST-3. Transformer 4 cards accueil en filtres dynamiques** (~1h30) — clic → `/search?artist=smyle&universe=xxx`, résultats en Banner cards (réutilise P1-B5).
4. **P1-PLAYLIST-4. Page "ADN global Smyle"** (~2h) — nouvelle section vendable sur `/u/smyle`, séparée des ADN individuels.
5. **P1-PLAYLIST-5. Upload des 81 sons perso Tom** (temps variable côté Tom) — rassembler prompts + prix + univers + genre pour chacun, upload progressif via WATT BOARD.

**Pré-requis côté Tom (hors code)** :
- Inventaire des 81 sons (titre, prompt Suno, prix, univers, genre, mood).
- Décider grille pricing cohérente (voir [[Tarification_v1]]).
- Rédiger l'ADN global Smyle (mots-clés signature, influences, palette).

**Angle mort anticipé** : pendant la transition où les playlists sont vides, options → A. cacher les 4 cards, B. état "collection en cours", C. upload minimum avant visibilité. À trancher avec Tom.

**Critère de sortie** : 4 univers alimentés avec minimum 5 sons chacun, ADN global Smyle rédigé et publié, au moins 1 transaction test réussie.
- [ ] **P1-B2. "Titre en dessous du titre"** — screenshot + page concernée

**Action Tom** : envoyer les 4 screenshots + bref descriptif pour ces 4 bugs, je les intègre ensuite avec estimations précises.

### P1-B6. Problèmes d'affichage sur `/u/<slug>` (précisé 2026-05-11 — point 7 Tom)
- **Quoi** : page artiste publique `/u/<slug>` — refonte UX de la cellule track.
- **🆕 Spec validée 2026-05-11** :
  - **Covers tracks** doivent apparaître sur les items publiés du slug (actuellement non affichées).
  - **Remplacer la bande jaune "Unlock"** par un design plus discret : **petit cadenas + badge prix** intégré dans la card, pas en bandeau.
  - **Clic sur la card track** → ouverture page dédiée `/track/<id>` (P1-B10) avec toutes les infos + bouton Unlock + bouton Like + bouton + (ajout playlist).
  - **À NE PAS faire** : virer complètement l'info "verrouillé + prix" — elle doit rester visible mais intégrée, pas envahissante. Sinon perte du rappel de conversion.
- **Action préalable Tom** : envoyer URL d'un slug test + screenshots (desktop + mobile) pour valider l'agencement final avant code.
- **Dépendances** : P1-B10 (page `/track/<id>`) pour que le clic ouvre quelque chose d'utile.
- **Effort estimé** : 4-6h (CSS card + nouveau composant cadenas-prix + câblage clic vers /track/<id>).

### P1-F4. Fiche vente prompt complète (items 1 + 6 + 7 groupés, spec Tom 2026-04-22, étendu 2026-05-11)
- **Quoi** : enrichir l'upload d'un morceau (dashboard `1a` dans cellule 02 Création) + la fiche de vente publique pour que l'acheteur ait toutes les infos utiles avant d'acheter.
- **Contenu à ajouter sur la fiche upload** :
  1. **Plateforme d'origine du prompt** — enum select : `Suno` / `Udio` / `Riffusion` / `Stable Audio` / `Autre` (un seul choix, champ obligatoire). Affiché en clair sur la fiche de vente publique.
  2. **🆕 Réglages de génération** (point 1 Tom 2026-05-11) — **2 jauges numériques 0-100** style Suno :
     - `weirdness` : slider 0-100 avec valeur affichée à droite (pas texte libre).
     - `style_influence` : slider 0-100 avec valeur affichée à droite (pas texte libre).
     - Stockés en `INTEGER 0-100`, restitués en clair sur la fiche.
  3. **🆕 Case DNA style** (point 10 Tom 2026-05-11) — **1 select obligatoire** parmi la liste fermée signature WATT (15 genres, voir bas du doc).
  4. **🆕 Case Mood** (point 10 Tom 2026-05-11) — **multi-select 1 à 3 max** parmi la liste fermée signature WATT (10 moods, voir bas du doc).
     - Raison stratégique : DNA style + Mood = **2 taxonomies séparées qui se combinent pour la recherche** (ex: "deep house triste"). Ne JAMAIS fusionner les listes.
  5. **Disclaimer auto injecté** sur chaque fiche de vente (morceau + ADN), non modifiable par le vendeur :
     > « L'achat d'un prompt ne reproduit jamais à 100% le son exact. Il permet de s'approcher d'un résultat très similaire, surtout si les réglages indiqués sont respectés et si l'IA d'origine est utilisée. Si l'ADN du profil a été acheté, les variantes cohérentes du morceau sont plus faciles à générer tout en gardant la même identité. »
- **Backend** : champs `prompt_platform` (enum), `prompt_weirdness` (int 0-100), `prompt_style_influence` (int 0-100), `dna_style` (enum genre), `moods` (array enum, max 3) sur `tracks` + migration Alembic. Disclaimer = texte statique frontend.
- **Frontend** : formulaire upload enrichi + affichage sur `/u/<slug>` cellule track + sur fiche ADN en vente + sur page `/track/<id>` (P1-B10).
- **Effort** : 1,5 journée (migration + 5 champs UI dont 2 sliders + 2 selects + texte disclaimer + tests).
- **Prérequis** : aucun technique.

### P1-B7. Casquettes sélectionnables dans l'Identité (item 2 Tom — visuel Sprint 1)
- **Quoi** : dans la cellule 01 Identité, sous-bloc 1a ou 1b, ajouter un champ "Casquettes" avec chips multi-select.
- **Liste** : Artiste/Interprète, Producteur/Beatmaker, Topliner/Songwriter, DJ, Ingé son, Visuel, Manager/Label, A&R, Auditeur, Autre.
- **Règle** : chips individuels (pas de chip hybride). User coche plusieurs → le système sait qu'il cumule plusieurs compétences. Sert pour futur Connect (matching complémentaire).
- **Visuel only** pour Sprint 1 : le bouton Enregistrer désactivé sur ce champ tant que le backend ne stocke pas, OU banner "Aperçu — sera persisté avec P0-F1". À trancher au moment du code.
- **Effort** : 2h (HTML + CSS chips + petit JS de toggle).

### P1-F9. Vente de l'identité vocale sous un track — recette B (Tom 2026-04-22)
- **Statut** : ✅ **Bloc 1c "Vendre une voix" LIVRÉ en aperçu visuel** (dashboard.html + dashboard.js). Persistance backend restant à faire.
- **Spec retenue (2026-04-22, recette B)** : vente d'un **sample audio a cappella** (30s-2min .mp3/.wav/.m4a) + métadonnées. Pas de clone IA (rejet recette A Suno — export voix impossible ; recette C ElevenLabs — reportée, dépend d'un partenariat).
- **Fiche saisie (dashboard > cellule 02 Création > sous-bloc 1c)** :
  1. Nom de la voix (max 40 chars)
  2. Style de voix (texte libre, max 80 chars)
  3. Genres compatibles (chips multi : RnB, Pop, Trap, Rap, Electro, House, Afro, Jazz, Soul, Rock, Autre)
  4. Sample audio (upload .mp3/.wav/.m4a)
  5. Type de licence (radio : Personnel / Commercial / Exclusif)
  6. Prix en SMYLES (50-5000)
- **Aperçu visuel uniquement** : données stockées dans `localStorage.wattVoiceDraft`. Banner explicite "Aperçu — persistance à venir".
- **Reste à faire (backend)** :
  - Modèle `voices_for_sale` (id, user_id, name, style, genres[], sample_url R2, license, price_smyles, status, created_at).
  - Endpoints `POST/GET/PATCH/DELETE /api/voices`.
  - Upload sample → Cloudflare R2 (même pipeline que les tracks).
  - Affichage sur `/u/<slug>` (cellule dédiée) + sous le player d'un track généré avec cette voix.
  - Flux d'achat (débit SMYLES, génération licence PDF, lien de téléchargement sample).
- **Effort restant** : 2-3 jours pour le backend complet + l'affichage côté acheteur.

### P1-F7. Réutiliser le dispositif de recherche DNA/Connect sur l'accueil (item 4 Tom)
- **Quoi** : Tom veut qu'un composant de recherche existant (du flow DNA ou Connect) soit réutilisé discrètement sur l'accueil pour améliorer la découverte.
- **Statut** : **composant source à identifier avec Tom** avant estimation. Candidats : `ui/modals/search.js`, recherche Connect, filtre artiste.html.
- **Action Tom** : confirmer "le champ de recherche de la page X / du flow Y".
- **Effort** : 3-5h selon composant (re-mount + styling discret sur accueil). Pas de backend nouveau.

### P1-F6. Playlists sur profils + auto-playlist + likes (item 8 Tom, spec étendue 2026-05-11)
- **Contexte** : Tom proposait d'interdire la publication d'un morceau sans playlist pour l'accueillir. **Contre-proposition retenue** : auto-playlist par défaut, zéro friction à l'onboarding.
- **Principe** : à la 1ʳᵉ publication d'un morceau, création automatique (backend) d'une playlist `"Mes sons"` rattachée à l'utilisateur ; le morceau y est ajouté. L'utilisateur peut ensuite renommer, créer d'autres playlists, déplacer les sons.
- **🆕 Extensions 2026-05-11 (point 3 Tom)** :
  - **2e playlist auto : `"Mes likes"`** créée au 1er like. Tout son liké atterrit dedans. Like = entité globale (toggle ❤️), distinct de l'ajout en playlist nommée.
  - **Action "ajout playlist"** : bouton `+` sur chaque item track → modale sélection playlist existante OU "Créer une nouvelle playlist" (titre + toggle public/privé obligatoire).
  - **Login obligatoire** pour : like, création/édition playlist, ajout track playlist, unlock. Visiteur anonyme peut UNIQUEMENT écouter les previews et naviguer.
  - **Toggle public/privé obligatoire** sur toute création/édition playlist (déjà règle de fer projet). Default suggéré : `privé`.
  - **Affichage sur `/u/<slug>`** : seules les playlists `public` apparaissent dans le tab Playlists du profil public. Les playlists `private` restent visibles uniquement dans le dashboard du propriétaire.
  - **Cas particulier** : `"Mes sons"` créée par défaut en `public` (cohérent avec l'objectif de tuyauterie publication F2). `"Mes likes"` créée par défaut en `private`.
- **Découpage en 3 sous-items** :

  - [ ] **P1-F6a. Modèle Playlist + Like + auto-playlists** (backend, étendu 2026-05-11)
    - Table `playlists` (id, user_id, title, slug, cover_url, **visibility ENUM('public','private') NOT NULL DEFAULT 'private'**, created_at, updated_at).
    - Table pivot `playlist_tracks` (playlist_id, track_id, position).
    - **🆕 Table `likes` (user_id, track_id, created_at)** — clé composite, unique.
    - Hook sur `POST /api/watt/tracks` : si user n'a aucune playlist → créer `"Mes sons"` (`public`) + y ajouter le track.
    - **🆕 Hook sur `POST /api/likes` : si pas de playlist `"Mes likes"` → la créer (`private`) + y ajouter le track liké automatiquement**.
    - Endpoints playlists : `GET/POST/PATCH/DELETE /api/playlists`, `POST /api/playlists/{id}/tracks`, `DELETE /api/playlists/{id}/tracks/{track_id}`.
    - **🆕 Endpoints likes : `POST /api/likes {track_id}`, `DELETE /api/likes/{track_id}`, `GET /api/me/likes`**.
    - **Auth obligatoire** sur tous les endpoints ci-dessus (401 si visiteur anonyme).
    - Migration Alembic (2 nouvelles tables + 1 colonne `visibility`).
    - **Effort** : 2 jours (au lieu de 1.5 — extension likes + visibility).

  - [ ] **P1-F6b. Tab "Playlists" sur `/u/<slug>`** (front profil public, étendu 2026-05-11)
    - Nouveau tab à côté de "Tracks" / "ADN" sur la page artiste.
    - **🆕 Filtre serveur : seules les playlists `visibility='public'` sont renvoyées par `GET /api/artists/{slug}/playlists`**. Les private restent invisibles côté public.
    - Affichage en grille : cover + titre + nb de sons.
    - Clic → vue détail de la playlist (liste des tracks, lecteur).
    - **Effort** : 1 jour.

  - [ ] **P1-F6c. UI gestion playlists dans le dashboard** (étendu 2026-05-11)
    - Nouvelle sous-section dans la cellule 02 Création (sous-bloc `1c` par ex).
    - Créer / renommer / réorganiser / supprimer playlist. Ajouter/retirer un track depuis sa liste.
    - **🆕 Toggle public/privé obligatoire** sur création ET édition. Bouton Enregistrer désactivé tant que la valeur n'est pas explicite (cf. règle de fer projet `project_playlist_visibility_toggle`).
    - Drag & drop pour réordonner.
    - **🆕 Bouton like (❤️) + bouton + (ajout playlist) sur chaque item track** dans toutes les listes (accueil, profil, bibliothèque, page `/track/<id>`).
    - **Effort** : 2 jours (au lieu de 1.5 — extension toggle + boutons like/+).
    - **Ordre d'exécution** : F6a → F6b → F6c (pas d'UI de gestion avant que ça existe en DB et soit visible public).

**Total P1-F6** : ~5 jours (au lieu de 4 — extensions likes + visibility + boutons globaux).

### P1-D10. Audit migrations Alembic INTEGER vs UUID FK
- **Quoi** : Flask `models.py` en INTEGER ids, FastAPI en UUID. Une mauvaise migration peut casser la cohabitation.
- **Action** : lire toutes les migrations, tester sur base fresh
- **Effort** : 2-3h

---

## 🟡 P2 — STRUCTURANTS (semaine 3, ~5-7 jours)

### Dette code

- [ ] **P2-D2. Refactor `dashboard.js` monolithique (121 KB, 66 fonctions)**
  Scinder en `dashboard-upload.js` + `dashboard-stats.js` + `dashboard-identity.js`. **Risque** : casser des handlers inter-fichiers. Tests manuels requis. **Effort** : 1 jour.

- [ ] **P2-D3. Dédup CSS** (style 88KB + artiste 97KB + dashboard 99KB + watt 51KB)
  Factoriser styles communs en `shared.css`. **Effort** : 1 jour. Gain estimé : -40 KB.

- [ ] **P2-D5. Setup pre-commit hooks** (ruff, mypy, pytest)
  Empêcher merge de code non formaté ou cassé. `.pre-commit-config.yaml` + doc README. **Effort** : 2h.

### Migration Flask legacy

- [ ] **P2-F6. Porter `POST /api/agents/process-track` → FastAPI** (agents autonomes bloqués en Flask). **Effort** : 3h.
- [ ] **P2-F7. Porter `GET /api/watt/stats` → FastAPI**. **Effort** : 1h.
- [ ] **P2-D1. Planifier le kill total de `flask_app.py`** (liste fermée des routes Flask restantes, prep + exécution). **Effort** : 2 jours. **Prérequis** : D10, monitoring OK.

### Organisation repo

- [ ] **P2-D7. Archiver `upload_to_r2.py` et `add_breadcrumb.py` dans `scripts/`** (scripts batch hors-ligne). **Effort** : 15 min.
- [ ] **P2-D8. Migrer `scanner.py` → `smyleplay-api/services/scanner.py`** (critique, 246 lignes). **Effort** : 2h.
- [ ] **P2-D11. Clarifier ou supprimer `server.py`** (222 lignes, fantôme ?). **Effort** : 30 min investigation.
- [ ] **P2-D9. Statuer sur `tracks.json`** (28 KB, fallback legacy). **Effort** : 1h.
- [ ] **P2-D12. Variabiliser les paths dans `.plist` launchd** (hardcodés `/Users/tommio/...`). **Effort** : 30 min.

### Tests

- [ ] **P2-D4. Tests agents autonomes + upload R2 + auth mixte Flask/FastAPI**. **Effort** : 1 jour.

### Features secondaires / nice to have

- [ ] **P2-F3. Traduction anglaise** (i18n). **Prérequis** : UX stabilisée. **Effort** : 2-3 jours.
- [ ] **P2-TARIF. Session de travail Tarification** — remplir `Tarification_v1.md` (personas + benchmark Splice + grille packs + répartition). **Effort** : 4 × 1-2h sur plusieurs jours. **Livrable** : pricing finalisé, prêt à injecter quand Stripe arrivera.

---

## 🎨 Listes signature WATT — figées 2026-05-11

> Listes fermées validées Tom le 2026-05-11. **Source de vérité unique** pour tous les selects (upload track, recherche, ADN). Toute modification = décision produit explicite + commit dédié.

### DNA style (genres musicaux) — 15 options
1. Trap
2. Rap
3. RnB
4. Pop
5. Afro
6. Reggaeton
7. Dancehall
8. Deep House
9. Electro
10. House
11. Jazz
12. Soul
13. Classique
14. Rock
15. Autre *(soupape — à éviter, à reclasser si volume significatif)*

### Moods (états émotionnels) — 10 options
1. Joie
2. Triste
3. Fête
4. Zen
5. Voyage
6. Évasion
7. Travail
8. Sport
9. Soleil
10. Nuit

### Règles d'usage
- **DNA style** = champ obligatoire, 1 seul choix (radio/select).
- **Mood** = champ multi-select, 1 à 3 max.
- **Combinaison DNA × Mood** = clé de la recherche fine (ex: "Deep House + Triste + Nuit").
- **Ne JAMAIS fusionner** les deux listes dans un même champ.
- Les 2 listes doivent être stockées dans `data/config/` (JSON statique) pour réutilisation côté seed DB, frontend, et skill `watt-prompt`.

---

## 📊 Vue d'ensemble v3 (mise à jour 2026-05-11)

| Priorité | Items | Effort cumulé estimé |
|----------|-------|----------------------|
| P0 | 4 (livrés sauf S1) | ~1-2 jours |
| P1 | 15 (10 v2 + 5 v3 ajouts) | ~7-8 jours |
| P2 | 14 | ~5-7 jours |
| **Total** | **33** | **~3 semaines code pur** (hors pricing + hors Stripe) |

### Ordre d'exécution v3 — Bloc par Bloc

**Phase 0 — Quick wins bug (à attaquer en premier)**
1. P1-B8 (lecture sons unlock biblio)
2. P1-B11 (slide déconnexion /slug)
3. P1-B12 (contraste violet)

**Phase 1 — Tuyauterie publication (Bloc 1)**
4. P1-F2 → P1-F5 → P1-F8 → P1-F6a → P1-F6b → P1-F6c

**Phase 2 — Tuyauterie achat + UX marketplace (Bloc 2)**
5. P1-F3 (étendu) → P1-F4 (étendu) → P1-B10 (page /track/<id>) → P1-B9 (Top sons) → P1-B6 (cadenas + cover slug) → P1-C2a

**Phase 3 — Catalogue (Bloc 3)**
6. P1-PLAYLIST-1 → 2 → 3 → 4 → 5

**Phase 4 — Recherche + reste P1 (Bloc 4)**
7. P1-B7 → P1-SEARCH → P1-F7 → P1-D10 → P1-F9 backend

**Phase P2 — dette code + i18n + pricing** (semaine 3).

---

## 🚦 Protocole d'exécution

1. Tom valide ce backlog v2 (dit `validé` ou corrige).
2. On attaque **P0-B1** (fix smyle-balance, 30 min, warm-up parfait).
3. Puis dans l'ordre : P0-F1 → P0-D6 → P1-F2 → P1-F3 → etc.
4. À chaque session Claude : **ouvrir ce fichier en premier**, identifier le prochain item, exécuter, cocher.
5. Nouveau bug/feature → ligne ajoutée ici.
6. En parallèle des sessions code : sessions dédiées pour remplir `Tarification_v1.md` (sans rush).

---

**Signé** : Tom + Cowork · cadrage 2026-04-22, v3 2026-05-11
**Prochaine révision** : après ship Phase 0 (B8 + B11 + B12)
**Premier chantier code** : P1-B8 — diagnostic lecture sons unlock depuis `/library` en prod
