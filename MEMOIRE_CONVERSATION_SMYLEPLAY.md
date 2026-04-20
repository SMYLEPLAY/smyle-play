# 🧠 MÉMOIRE CONVERSATION — SMYLE PLAY / WATT

**Date export** : 2026-04-20
**Projet** : SMYLE PLAY — marketplace musique IA (SUNO) avec hub artiste WATT
**Propriétaire** : Tom (tom.lecomte1@gmail.com)
**Chemin projet** : `/Users/tommio/Desktop/WORK/Smyleplay`

---

## 🏗️ STACK TECHNIQUE

- **Backend** : FastAPI (Docker Compose, uvicorn) sur `localhost:8000`
- **DB** : PostgreSQL 15 port **5433** (user=smyle, db=smyleplay)
- **Front** : Flask `localhost:8080` (`server.py`)
- **Auth** : JWT bridge Flask → FastAPI
- **Migrations** : Alembic (dernière = `0017_profile_colors`)
- **ORM** : SQLAlchemy async + Pydantic v2
- **Graphify** : graphe de connaissance dans `graphify-out/` (à requêter via `/graphify query` avant d'attaquer du code)

---

## 🎯 CHANTIER EN COURS — "Profil artiste type"

### Étapes complétées (sur cette conv)

| # | Étape | État |
|---|---|---|
| 46 | Migration 0017 + 2 couleurs profil (`profile_bg_color` + `profile_brand_color`) | ✅ |
| 47 | Dashboard : 2 color pickers + mini preview dans l'onglet Artiste | ✅ |
| 48 | Page artiste applique bg/brand + texture néon WATT | ✅ |
| 49 | CTA redirect profil vierge vers dashboard (sur `/artiste/<slug>`) | ✅ |
| 13 | Couleurs noms artistes dans classement WATT (podium + rang 4+) | ✅ |
| 43 | Stats publiques (plays/tracks/followers/rank) sur page artiste | ✅ partiel |
| 50 | Bulle profil dashboard → dropdown cliquable avec contenu | ✅ |

### Reste à faire sur #43 (Profil artiste type — Événements)

- Migration DB table `user_events` (id, user_id, title, date, location, url, created_at)
- Endpoints CRUD dans `watt_compat.py`
- UI dashboard pour ajouter/éditer ses événements
- Affichage public sur `/artiste/<slug>` (section après stats)

---

## 📁 FICHIERS MODIFIÉS (cette conv)

### Front (tous dans `/Smyleplay/`)

**`dashboard.html`**
- Color pickers (bg + brand) dans section profil
- `#dashUserChip` transformé en `<button>` avec dropdown `#dashUserDrop`
- Dropdown contient : header (avatar + nom + @slug), état vierge (CTA "Créer mon profil"), état rempli (liens public/édition), Déconnexion
- Bouton `.dash-logout-btn` retiré de la topbar (rapatrié dans dropdown)

**`dashboard.css`**
- `.dash-profile-theme*` (color pickers + preview violet WATT)
- `.dash-user-wrap` + `.dash-user-drop*` (popover complet, animation `dashDropIn`, responsive mobile pleine largeur)
- `.dash-user-caret` (chevron rotation 180°)

**`dashboard.js`**
- `_PT_DEFAULTS = { bg: '#070608', brand: '#8800FF' }`
- `_normalizeHex()`, `setProfileThemePickers()`, `resetProfileTheme()`
- `_deriveArtistSlug(user, profile)` — miroir front de `_derive_artist_slug` backend
- `renderUserDropdown()` + `_initUserDropdown()` (toggle, click extérieur, Escape)
- `renderArtistCard()` : cascade initiales élargie (artistName → artist_name → name → email local-part)
- `loadPublishStatus()` : hydrate `profileBgColor` / `profileBrandColor`
- `saveProfile()` : envoie NULL quand valeur = defaults (pas de perso)

**`artiste.html`**
- `#ap-empty-cta` (banner owner, redirige `/dashboard#profile`)
- `<section class="ap-stats">` 4 tuiles (plays, tracks, followers, rank)

**`artiste.css`**
- `:root { --bg: #070608 }` + body utilise `var(--bg, var(--ap-bg))`
- `body::before` : cyber grid 64x64 + 6 points scintillants teintés `--brand` (animation `apGridPulse` 8s, `mix-blend-mode: screen`)
- `body::after` : CRT scanline (animation `apScanline` 9s)
- `.ap-artist-name` : drop-shadow + keyframes `apNeonName` (flicker 17/19/21/50/52%)
- `.ap-empty-cta*` (gradient brand-tinted + neon shadow)
- `.ap-stats` grid 4-col (2 mobile) + tuiles `.ap-stat` avec glow brand

**`artiste.js`**
- `THEME_DEFAULTS` + `hexToRgbTriplet()` + `applyArtistTheme(artist)`
- `renderEmptyProfileCTA(artist)` (3 variantes : vierge / prêt-à-publier / publié-mais-vide)
- `formatCount()` (k/M abréviations)
- `renderStats(artist)` (masque section si `trackCount === 0`)

**`watt.js`**
- `.wpr-rest-item` rendu avec `--wpr-brand` inline + classe `wpr-has-brand` (rang 4+, parity avec podium)

**`watt.css`**
- `.wpr-card.wpr-has-brand .wpr-card-name` + `.wpr-rest-item.wpr-has-brand .wpr-rest-name` : `color: var(--wpr-brand)` + text-shadow neon via `color-mix()`

### Backend (`/Smyleplay/smyleplay-api/`)

- **Migration 0017** (`alembic/versions/0017_profile_colors.py`) : ajoute `profile_bg_color` + `profile_brand_color` sur `users`
- **Modèle `User`** : champs ajoutés (SQLAlchemy)
- **Schéma Pydantic** : `profile_bg_color`/`profile_brand_color` acceptés via `PATCH /users/me` (`exclude_unset=True`)
- **`watt_compat.py`** : `/watt/artists/<slug>` retourne `isSelf`, `profilePublic`, `brandColor`, `profileBgColor`, `profileBrandColor`, `plays`, `trackCount`, `followersCount`, `rank`. Gate 404 si profil non publié ET pas self-view.

---

## ⚠️ CONVENTIONS & DIRECTIVES TOM

1. **Ton** : "essai des concis et efficace dans toute tes reponses" → réponses courtes, pas de blabla
2. **Navigation code** : TOUJOURS `graphify query` en premier, pas lecture brute sauf demande explicite
3. **Graphify** : `graphify update .` après modifs pour maintenir le graphe
4. **Jamais de `.md` docs sauf demande explicite** (convention Claude)
5. **Path projet** : `/Users/tommio/Desktop/WORK/Smyleplay` (pas `~/Smyleplay`)

---

## 🐛 BUGS / PIÈGES CONNUS

- **Port 8080 déjà en use** → Flask déjà lancé ailleurs, `lsof -i :8080` pour vérifier
- **Sandbox Claude ne peut pas curl localhost** → validation délégée à Tom
- **Bulle profil "?" persistante** (bug #37) : la cascade `profile.artistName || '?'` retombait sur `?` dès que `profile` existait sans nom, même si `user.name` était en mémoire → corrigé dans cette conv avec cascade élargie
- **isSelf 404 gate** : les visiteurs tiers ne voient JAMAIS les profils non-publiés → CTA owner jamais leaké

---

## 📋 TASKS RESTANTES (après compaction)

### Pending / Backlog
- **#21** Renommer classes CSS `.agent-suno-*` / `.dna-suno-*` (cosmétique)
- **#11** Remplir table `dna` pour les 82 tracks historiques
- **#12** UI édition prompt par l'artiste
- **#18** Phase 6 — NO DNA = NO TRACK
- **#32** Chantier 2 — Page achat Smyles (Stripe réel)
- **#24** [backlog futur] Pack Mystère — loot box prompts rares

### In progress
- **#43** Profil artiste type — **Événements** (stats déjà OK, events à faire)
- **#42** Profil artiste type — Section **Actualités** (feed de posts)

---

## 🔑 POINTS D'ENTRÉE / URLS

- Dashboard artiste : `http://localhost:8080/dashboard`
- Page artiste publique : `http://localhost:8080/artiste/<slug>`
- Classement WATT : `http://localhost:8080/watt`
- API FastAPI : `http://localhost:8000`
- Endpoints clés : `/users/me`, `/watt/artists/<slug>`, `/watt/ranking`

---

## 💡 DERNIÈRE MODIF (session #50 — bulle profil)

Clic sur la bulle en haut à droite du dashboard → dropdown :
- **Profil vierge** (pas de nom OU pas de bio) → CTA "Créer mon profil" (scroll `#sec-profile`)
- **Profil rempli** → "Voir mon profil public" (ouvre `/artiste/<slug>`) + "Éditer mon profil"
- Déconnexion en bas (séparée par une ligne)
- Ferme sur click extérieur / Échap / click interne
- Slug dérivé front avec `_deriveArtistSlug()` (miroir de `_derive_artist_slug` backend)

---

## 🚀 REPRISE DE CONV — QUELS PROMPTS POSSIBLES

- **"Attaque les événements (#43 suite)"** → migration `user_events` + endpoints + UI dashboard + affichage public
- **"Fais la section actualités #42"** → feed de posts artiste
- **"Renomme les classes suno #21"** → cosmétique
- **"Remplir table dna #11"** → backfill 82 tracks historiques

---

**Fin de l'export. Colle ce fichier en début de la nouvelle conv pour que Claude récupère le contexte sans tout relire.**
