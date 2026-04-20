# SMYLE PLAY — ÉTAT DU PROJET

> **Document de référence — 18 avril 2026**
> Synthèse consolidée de tout ce qui existe (Flask live, FastAPI backend, Next.js front, vault Obsidian, pipeline Suno, agents IA, assets audio) et de la direction à prendre.
> À lire avant toute reprise de travail. Ce fichier remplace `HANDOFF.md` comme point d'entrée unique.

---

## 1. TL;DR — où on en est

Il existe **deux projets Smyle Play en parallèle**, nés à des moments différents du concept :

- **Smyle Play v1** — app Flask déployée sur Railway (site HTML vanilla, pipeline Suno, agents IA macOS). Vision initiale : **plateforme musicale** avec playlists, artistes, collabs, WATT (classement artistes).
- **Smyle Play v2** — backend FastAPI (1618 tests OK) + front Next.js amorcé. Nouvelle vision : **marketplace créatif** autour des ADN (univers sonores) et des Prompts Suno vendables en crédits, avec achievements et économie.

Le **concept a évolué** : on est passé d'un Spotify-like à un marketplace de signatures sonores. La v1 a l'identité visuelle + le pipeline qui produit les sons, la v2 a le modèle économique + les données propres + les tests. Les deux doivent **fusionner en un seul produit v3**, pas coexister.

Cette session part sur **une refonte cohérente** : on garde ce qui a de la valeur (pipeline Suno, design WATT, assets audio, concept univers), on remodèle tout le reste autour du backend FastAPI qui est déjà solide.

---

## 2. Le concept aujourd'hui (v3)

### L'idée
Un artiste ne vend plus des pistes — il vend **son ADN créatif** : la recette qui produit ses sons. Sur Smyle Play :

- L'**artiste** crée un **ADN** (= signature sonore : couleur de marque, description, guide d'usage, exemples audio gated). Exemples existants : `Sunset Lover`, `Night City`, `Jungle Osmose`, `Hit Mix`.
- L'artiste publie des **Prompts** dérivés de son ADN → recettes Suno prêtes à générer des sons dans l'univers.
- Le **fan** peut **acheter un ADN** (OwnedAdn) → il devient collectionneur et obtient un **perk -30 %** sur tous les prompts de cet artiste.
- Le **fan** peut **débloquer un prompt** (UnlockedPrompt) → il voit le `prompt_text` complet et peut générer ses propres sons avec.
- L'économie tourne en **crédits** (Stripe prévu plus tard, Phase 6).
- Toute mutation passe par une **Transaction immutable** (ledger auditable).
- **13 achievements** seedés sur 3 axes : BUYER (collectionneur), FAN (découvreur d'ADN), ARTIST (créateur).

### Les univers actuels
| Univers | Couleur | Style |
|---|---|---|
| Jungle Osmose | vert néon `#00E676` | afrobeat, tropical |
| Night City | bleu néon `#2266FF` | lo-fi, jazz, soul |
| Sunset Lover | orange néon `#FF9500` | deep house, nu-disco |
| Hit Mix | violet néon `#AA00FF` | best-of, electro, crossover |

Dans la v3 ces 4 univers deviennent les 4 premiers **ADN** seedés, signés par Tom comme artiste fondateur.

---

## 3. Inventaire consolidé — ce qui existe

### 3.1 Backend FastAPI `smyleplay-api/` ✅ solide
- **Stack** : FastAPI + SQLAlchemy 2.0 async + asyncpg + Alembic + Pydantic v2 + PostgreSQL 15 (port 5433) + Docker Compose.
- **11 routers** : `/auth`, `/users`, `/tracks`, `/credits`, `/transactions`, `/marketplace`, `/unlocks`, `/catalog`, `/me/library`, `/achievements`, `/me/achievements`.
- **Modèles SQLAlchemy** : `User`, `Track`, `Adn`, `Prompt`, `OwnedAdn`, `UnlockedPrompt`, `Transaction`, `Achievement`, `UserAchievement` (+ `Dna`, `PromptMemory` à vérifier — possibles doublons à nettoyer).
- **1618 tests** au vert, end-to-end inclus (deadlock, race condition, perk -30 %, conservation crédits, CHECK strict UNLOCK/RESALE).
- **Migrations Alembic** jusqu'à 0010.
- **Pièges documentés** : enum case-sensitivity Postgres, trigger DELETE sur `transactions`, `loop_scope="session"` pytest-asyncio, hooks achievements post-commit.

> À nettoyer : fichiers `.bak` (`__init__.py.bak`, `transaction.py.bak`, `user.py.bak`, `docker-compose.yml.bak`) et potentiel doublon `adn.py` vs `dna.py` dans `app/models/`.

### 3.2 Front Next.js `smyleplay-web/` 🟡 amorcé
- Next.js 16.2.4 (Turbopack) + App Router + TypeScript + Tailwind v4 + shadcn/ui.
- **Existe** : `src/lib/api.ts` (client fetch typé + ApiError), 2 composants shadcn (button, card), page `/health` vérifiée OK, page `/feed` posée mais non vérifiée visuellement.
- **Manque** : tout le reste — layout final, identité visuelle, `/login`, `/library`, `/artist/[id]`, `/create`, état auth, token storage.

### 3.3 Site Flask live (racine `/Smyleplay/`) 🔵 v1 historique
- Déployé sur Railway, dépose les fichiers audio sur Cloudflare R2 CDN.
- **Pages** : `index.html` (29 Ko, avec logo SVG perles signature, meta iOS, hub WATT intégré), `watt.html` (espace artiste public + classement), `dashboard.html` (dashboard artiste), `artiste.html` (page artiste publique).
- **UI modulaire** dans `ui/` : `core/` (dom, state, storage), `hub/community`, `modals/` (auth, contact, premium, save-mix), `panels/` (agent, mix, playlist, watt-panel), `player/audio`.
- **Routes Flask** (`app.py`, 24 Ko) : `/`, `/watt`, `/dashboard`, `/artiste/<slug>`, plus 23 endpoints API (auth, watt/profile, watt/tracks, watt/upload, plays, artists, collabs, feedback, agents/process-track).
- **Modèles SQLAlchemy v1** (`models.py`) : `User`, `Artist`, `Track`, `Collab`, `PlayCount`, `SavedMix`, `Feedback`.
- **CSS** énorme (`style.css` 77 Ko, `watt.css` 46 Ko, `watt-panel.css` 21 Ko) — contient toute l'identité visuelle actuelle (hub WATT jaune néon, palettes par univers, canvas réseau électrique animé).
- **Identité WATT** : `--watt-gold #FFD700`, `--watt-electric #FFE737`, `--watt-deep #FF9500`. Hub WATT = 3 cellules (DNA violet, CONNECT rouge, ARTIST or).

### 3.4 Pipeline Suno 🟢 opérationnel localement
- **Flux** : `Skill WATT Prompt → Suno Router → Scanner → Add Breadcrumb → Upload R2 → Watcher Pipeline → tracks.json → Push GitHub → Deploy Railway`.
- **Scripts** : `suno_router.py`, `scanner.py`, `watcher_pipeline.py`, `upload_to_r2.py`, `add_breadcrumb.py`.
- **Daemons macOS** : `com.smyleplay.suno-router.plist`, `com.smyleplay.watcher.plist` (LaunchAgents).
- **Catalogue** : `tracks.json` (28 Ko) — indexé par univers, chaque piste a `id`, `file`, `name`, `duration`, `url` R2.
- **74 pistes audio** livrées dans `HIT MIX/` (10), `NIGHT CITY/` (20), `SUNSET LOVER/` (22), `JUNGLE OSMOSE/` (22 d'après l'historique).

### 3.5 Agents IA 🟢 fonctionnels
Dans `agents/` (Python) :
- `orchestrator.py` — chef d'orchestre, dispatch.
- `dna_classifier.py` — analyse émotionnelle → classe une piste dans un univers.
- `playlist_manager.py` — gestion dynamique des playlists.
- `suno_prompt_architect.py` — génération de prompts Suno optimisés.
- **Skill Claude** `watt-prompt.skill` (7 Ko) + copie dans `.claude/skills/watt-prompt/` — générateur de prompts Suno alignés ADN WATT.

### 3.6 Vault Obsidian `Smyle-play/` 🟢 bien structuré (mais v1)
~50 notes markdown :
- **Cockpit** : `SMYLEPLAY_MASTER.md` avec vues Dataview par priorité.
- **5 hubs** : SYSTEM, PLAYLISTS, AUTOMATION, AGENTS, PIPELINE — tous bien reliés.
- **Notes par module** (App Flask, App JS, Audio Player, etc.), par univers (Playlist Sunset Lover, etc.), par agent, par panel.
- **⚠️ Obsolète sur la v2** : le vault décrit exclusivement l'architecture Flask, pas le marketplace FastAPI. À retravailler après consolidation.

### 3.7 Graphify `graphify-out/` 🟢 indexé (mais v1 seulement)
- Indexe les 10 fichiers Python/JS du Flask : 301 nodes, 566 edges, 11 communautés, cohérence modérée.
- **God nodes** : `getEl()`, `Config`, `loadTrack()`, `uploadTrack()`, `getCurrentUser()`, `renderArtistCard()`.
- **⚠️ Ne couvre pas** : `smyleplay-api/`, `smyleplay-web/`, `ui/` modulaire. À ré-indexer sur le périmètre total après refonte.

---

## 4. Architecture cible unifiée (v3)

```
┌─────────────────────────────────────────────────────────────────┐
│                   FRONT — smyleplay-web/ (Next.js)              │
│    UI visuelle héritée du site Flask (WATT, SVG, palettes)      │
│    Pages : /feed /artist/[slug] /prompt/[id] /library /create   │
│            /login /signup /me (dashboard)                        │
└─────────────────────────────────────────────────────────────────┘
                               ↕  REST + JWT
┌─────────────────────────────────────────────────────────────────┐
│                  API — smyleplay-api/ (FastAPI)                  │
│  Routers : auth / users / tracks / catalog / marketplace /      │
│            unlocks / credits / transactions / library /         │
│            achievements                                          │
│  + (nouveau) ingestion : /admin/ingest (trigger pipeline Suno)   │
└─────────────────────────────────────────────────────────────────┘
                    ↕               ↕               ↕
       ┌────────────────────┐  ┌─────────────┐  ┌──────────────┐
       │   PostgreSQL 15    │  │ Cloudflare  │  │ Pipeline     │
       │   (users, adn,     │  │    R2       │  │ Suno (agents │
       │   prompts, tracks, │  │ (audio CDN) │  │ + watcher +  │
       │   transactions,    │  │             │  │  router +    │
       │   achievements)    │  │             │  │  scanner)    │
       └────────────────────┘  └─────────────┘  └──────────────┘
```

**Ce qui disparaît** : l'app Flask (`app.py`, `server.py`, `models.py`) — ses routes et ses modèles sont absorbés par FastAPI.
**Ce qui migre** : le pipeline Suno devient un module interne de `smyleplay-api/` (ex. `app/ingestion/`) déclenché soit par le watcher macOS, soit par endpoint admin.
**Ce qui se récupère** : l'identité visuelle (CSS, SVG, canvas réseau), les assets audio, le concept d'univers, les agents IA.

---

## 5. Zones à décider ou retravailler

> **MAJ 18 avril — décisions prises avec Tom** ✅ (voir §8 plus bas)

### 5.1 Doublons dans `smyleplay-api/app/models/` ✅ clarifié
- **Pas un doublon** : `Adn` (table `adns`) = signature créative de l'artiste (vendable marketplace, UNIQUE par artiste). `DNA` (table `dna`) = prompt Suno exact utilisé pour UNE piste (lié à `track_id`). Deux niveaux distincts et légitimes.
- `.bak` archivés dans `smyleplay-api/_archive_bak/` (vieilles versions pré-Phase 9, conservés par prudence). ✅

### 5.2 Routes Flask → FastAPI : correspondance
**Décision Tom** : on garde la dimension sociale v1 complète (collabs + plays + feedback). À porter progressivement dans FastAPI.


| Flask (v1) | FastAPI (v2) | Action |
|---|---|---|
| `/api/auth/*` | `/auth/*` | ✅ déjà porté |
| `/api/watt/profile` | `/users/me` (PATCH) | ✅ porté |
| `/api/watt/tracks` (GET/POST/DELETE) | `/tracks/*` | ✅ porté partiellement, à vérifier |
| `/api/watt/plays/<id>` | **manque** | ⏳ à porter (compteur plays) |
| `/api/artists` | `/catalog/artists` | ✅ porté |
| `/api/artists/<slug>` | `/catalog/artists/<slug>` ou `/users/<id>` | ⏳ à harmoniser |
| `/api/collabs` (POST/inbox/unread) | **manque** | 🟡 à porter ou à couper selon concept v3 |
| `/api/feedback` | **manque** | 🟡 nice-to-have |
| `/api/watt/upload` | **manque** | ⏳ à porter (upload audio → R2) |
| `/api/agents/process-track` | **manque** | ⏳ à porter (trigger DNA classifier) |
| `/api/plays/<id>` | **manque** | ⏳ à porter (compteur anonyme) |
| `/api/tracks/recent` | `/catalog/tracks/recent` | ⏳ à créer |

### 5.3 Pipeline Suno — comment l'intégrer ? ✅ tranché
**Décision Tom** : Option A — Watcher local + endpoint admin `/admin/ingest`. Le watcher macOS continue à tourner, il dépose les tracks sur R2 et appelle FastAPI pour rafraîchir la DB. Tom peut continuer à produire pendant qu'on code le front. Le portage complet dans FastAPI (option B) est repoussé en Phase 4 ou plus tard.

### 5.4 Rôle de Track vs Adn.example_outputs vs Prompt ⏳ reporté
**Décision Tom** : pas tranché maintenant, l'enjeu du terme reste flou. On laisse le modèle `Track` tel qu'il est et on y reviendra **le jour où on aura besoin d'afficher quelque chose qui est une Track** (typiquement quand on fera la page ADN avec les exemples audio, ou quand on branchera le watcher au feed). La décision viendra naturellement quand le besoin sera concret.

### 5.5 Vault Obsidian : on met à jour ? ✅ tranché
**Décision Tom** : Option B — on met à jour au fur et à mesure. Chaque fois qu'on touche un module, on met à jour la note Obsidian correspondante. Le vault reste vivant et à jour sans gros chantier de refonte.

### 5.6 Graphify : ré-indexer ? ✅ tranché (action Tom)
**Décision Tom** : oui, indexer tout le périmètre. L'outil `graphify` n'est pas disponible dans le sandbox Cowork, donc **Tom lance la commande sur son Mac** :

```
cd "/Users/tommio/Desktop/WORK/IA SUNO PLAYLIST DEVELOPPEMENT " && graphify init .
```

(ou équivalent selon le référent choisi). AST-only, gratuit, 2-3 min. Sortie dans `graphify-out/`.

---

## 6. Plan de migration proposé

Strictement aligné sur le plan Phase 1 → 8 donné par Tom dans le HANDOFF.

### Phase 0 — Consolidation (cette session)
- [x] Inventaire complet
- [x] Synthèse (ce document)
- [ ] Nettoyage `.bak` et doublons `adn.py`/`dna.py` dans `smyleplay-api/`
- [ ] Décisions structurantes sur §5 avec Tom
- [ ] Mise à jour `HANDOFF.md` pour pointer ici

### Phase 1 — Produit visible (ON EST ICI)
- [ ] **1D** Vérifier `/feed` Next.js connecté au backend (catalogue prompts)
- [ ] **1E** Importer l'identité visuelle WATT dans Next.js (palette, SVG logo, typo, fond réseau électrique)
- [ ] **1F** Page `/artist/[slug]` (branchée à `/catalog/artists/<slug>`)
- [ ] **1G** Page `/prompt/[id]` (branchée à `/catalog/prompts/<id>`) avec gating du `prompt_text`
- [ ] **1H** Landing `/` redesignée (reprend le spirit de `index.html` v1)

### Phase 2 — Flow complet
- [ ] Page `/signup` + `/login` (token JWT en cookie httpOnly)
- [ ] Page `/library` (branchée à `/me/library/*`)
- [ ] Achat ADN / Unlock prompt (branché à `/unlocks/*` et `/marketplace/*`)
- [ ] Dashboard artiste `/me` (création ADN + Prompts, branché à `/marketplace/adns` POST)

### Phase 3 — Test réel utilisateur
- [ ] QA walkthrough inconnu
- [ ] Corrections UX

### Phase 4 — Automation de base
- [ ] Port du pipeline Suno dans `smyleplay-api/app/ingestion/`
- [ ] Seed des 4 ADN existants avec les assets des dossiers univers
- [ ] Endpoint admin `/admin/ingest`

### Phase 5 — Stabilisation
- [ ] Perf, bugs UX, lisibilité

### Phase 6 — Monétisation
- [ ] Stripe checkout pour achat crédits

### Phase 7 — Automation avancée
- [ ] Agents IA réintégrés (reco, DNA classifier, playlist manager)

### Phase 8 — Long terme
- [ ] Mobile, P2P, branding, analytics

---

## 7. Règles de travail (rappel)

1. À chaque étape on code. Pas de gros bloc à recopier.
2. `AskUserQuestion` avant tout travail multi-étapes.
3. `TaskCreate`/`TaskUpdate` pour le suivi visible.
4. Une commande à la fois dans le terminal (pas de chaînages).
5. Pas d'emojis/XML dans les commandes shell (zsh parsing).
6. Vérification visuelle privilégiée (`ouvre l'URL et dis-moi ce que tu vois`).
7. Tom = francophone, non-dev : pas de jargon sans analogie.

---

## 8. Décisions actées (18 avril 2026)

Toutes les zones grises §5 ont été tranchées avec Tom. Synthèse :

| # | Sujet | Décision |
|---|---|---|
| 5.1 | `adn.py` vs `dna.py` | **Pas un doublon** — 2 modèles légitimes (Adn = signature marketplace, DNA = prompt complet d'une Track). `.bak` archivés dans `_archive_bak/`. |
| 5.2 | Routes Flask sociales | **On garde tout** : collabs, plays, feedback. À porter progressivement dans FastAPI. |
| 5.3 | Pipeline Suno | **Option A** — watcher local + endpoint admin `/admin/ingest`. Tom continue de produire pendant qu'on code. |
| 5.4 | Rôle de Track | **Reporté** — on décidera quand le besoin sera concret (page ADN avec exemples audio, branchement watcher/feed). |
| 5.5 | Vault Obsidian | **Mise à jour au fil de l'eau** — chaque module touché = note mise à jour. |
| 5.6 | Graphify | **Ré-indexer tout** — commande à lancer par Tom sur son Mac (cf. §5.6). |

## 9. Prochaine étape — Phase 1E : Identité visuelle WATT dans Next.js

**Objectif** : que la page d'accueil `smyleplay-web/` arrête d'afficher le template Next par défaut et ait le look Smyle Play — palette WATT jaune néon, logo SVG perles, typos, ambiance "réseau électrique" du site Flask.

**Décomposition pas-à-pas** (une commande / un fichier / une vérif visuelle chaque fois) :

1. **1E.1** Extraire les variables de couleur WATT du `style.css` v1 → créer `smyleplay-web/src/styles/watt-theme.css` avec les variables Tailwind v4.
2. **1E.2** Copier le SVG du logo perles (depuis `index.html` v1) → créer `smyleplay-web/src/components/SmylePlayLogo.tsx`.
3. **1E.3** Reprendre le fond canvas réseau électrique (WattNetwork) → composant React `smyleplay-web/src/components/ElectricBackground.tsx`.
4. **1E.4** Refondre `layout.tsx` : header avec logo + palette WATT globale.
5. **1E.5** Refondre `page.tsx` (home) : hero simple avec le logo, le slogan, bouton "Découvrir les ADN" → `/feed`.
6. **1E.6** Vérifier visuellement : `npm run dev` → ouvrir `http://localhost:3000` et comparer à l'esprit `index.html` v1.

Après validation 1E.6 → Phase 1F (page `/artist/[slug]`).

---

_Document rédigé en session Cowork, Claude Opus 4.7, 2026-04-18._
_MAJ 18 avril : toutes les décisions §5 tranchées. Prochaine MAJ : après validation Phase 1E.6._
