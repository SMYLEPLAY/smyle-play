# HANDOFF — Smyle Play (passation entre sessions Cowork)

> **À lire en priorité par la nouvelle instance Claude.**
> Cette session précédente a construit un backend complet + démarré un front Next.js
> SANS visibilité sur le projet existant dans `/Users/tommio/Desktop/WORK/Smyleplay/`.
> La nouvelle session DOIT inventorier ce qui existe avant d'ajouter quoi que ce soit.

---

## 👤 Utilisateur

- **Tom** (`tom.lecomte1@gmail.com`)
- Francophone, **aucun niveau de code** ("aucun niveau dans le domaine")
- Travaille avec Cowork sur Mac (macOS Sequoia, terminal zsh)
- A construit son concept Smyle Play / WATT (univers musicaux générés via Suno)

## 📐 Règles de travail établies (NON NÉGOCIABLES)

1. **À chaque étape on code**. Pas d'accumulation de code manuel à recopier en bloc.
   Une étape = un fichier (ou un ajout chirurgical) = une commande de copie = une vérif visuelle/test = on valide → étape suivante.
2. **On code dans le workspace Cowork**, puis on copie vers le vrai projet sur Mac via les variables `$SOURCE` (backend) et `$WEB` (front), définies dans `~/.zshrc`.
3. **Toujours utiliser `AskUserQuestion`** avant de démarrer un travail multi-étapes pour cadrer les choix structurants.
4. **Toujours utiliser `TaskCreate`/`TaskUpdate`** pour suivre la progression — Tom voit le widget en temps réel.
5. Tom préfère **1 commande à la fois** (pas de suite de 5 commandes chaînées). En cas d'erreur, on isole.
6. Tom fait du copier-coller depuis le chat → **éviter les emojis/caractères spéciaux dans les commandes shell**, et **jamais** de balises XML parasites.

---

## 🏗️ Backend `smyleplay-api/` — TERMINÉ jusqu'à Phase 9.6

### Localisation
- **Vrai projet (Docker)** : `/Users/tommio/Desktop/WORK/Smyleplay/smyleplay-api/`
- **Mirror Cowork** (sync bidirectionnel) : `/Users/tommio/Desktop/WORK/IA SUNO PLAYLIST DEVELOPPEMENT /smyleplay-api/`
  → variable `$SOURCE` dans `.zshrc` pointe vers ce mirror

### Stack
- **FastAPI** + **SQLAlchemy 2.0 async** + **asyncpg** + **Alembic** + **Pydantic v2**
- **PostgreSQL 15** (port `5433` mappé en local pour éviter conflit avec un Postgres système)
- **Docker Compose** (`smyleplay-api-api-1` sur :8000, `smyleplay-api-db-1` sur :5433)
- **pytest-asyncio 1.3** avec `loop_scope="session"` pour partage event loop

### Architecture
```
smyleplay-api/
├── alembic/                    # Migrations (10 fichiers)
├── app/
│   ├── auth/                   # JWT (sub=user_id) + dependencies
│   ├── config.py               # Settings pydantic
│   ├── database.py             # Engine async + get_db + SessionLocal
│   ├── main.py                 # FastAPI app + include 11 routers
│   ├── models/                 # SQLAlchemy 2.0 models (User, Track, Adn, Prompt, OwnedAdn, UnlockedPrompt, Transaction, Achievement, UserAchievement)
│   ├── schemas/                # Pydantic schemas
│   ├── services/               # Business logic (atomic patterns FOR UPDATE)
│   └── routers/                # Endpoints REST
├── tests/                      # 1618 tests qui passent ✅
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

### Phases livrées
| Phase | Contenu | Tests |
|---|---|---|
| 1-7 | Setup, auth, users, tracks, credits, transactions | ~1500 |
| 8 | Smoke tests statiques | inclus |
| 9.1 | Migration 0009 marketplace + modèles Adn/Prompt/Owned/Unlocked + brand_color | inclus |
| 9.2 | Endpoints catalogue artiste (POST/PATCH ADN+Prompt) | inclus |
| 9.3 | Endpoints unlock atomic (Prompt + ADN) avec perk -30% si user possède un ADN de l'artiste | inclus |
| 9.4 | Endpoints découverte publique (`/catalog/*`) + library (`/me/library/*`) | inclus |
| 9.5 | Tests d'intégration end-to-end (deadlock, race, perk, conservation crédits) + migration 0010 (CHECK strict UNLOCK/RESALE) | +intégration |
| 9.6 | **Système trophées** : 13 badges seedés sur 3 axes (BUYER, FAN, ARTIST), hooks auto dans unlock_*_atomic, BONUS transactions, endpoints `/achievements` et `/me/achievements` | +4 tests |
| **Total** | | **1618 passed** |

### Endpoints REST (11 routers)
- `/` (health), `/auth/*` (register, login), `/users/me` (GET/PATCH)
- `/tracks/*`, `/credits/*`, `/transactions/*`
- `/marketplace/*`, `/unlocks/*`
- `/catalog/{artists,prompts,adns}` + `/catalog/{prompts,adns}/{id}` (publics)
- `/me/library/*`, `/me/effective-price/prompts/{id}`
- `/achievements` (catalog public, 13 badges), `/me/achievements` (progression user)

### ⚠️ Pièges connus
1. **Enum case-sensitivity Postgres** : tous les SQLEnum doivent avoir `values_callable=lambda x: [e.value for e in x]` sinon Postgres reçoit le NAME (uppercase) au lieu de la VALUE (lowercase) → corrigé sur `Transaction.type`, `Transaction.status`, `Achievement.axis`.
2. **Trigger DELETE sur `transactions`** : la table est immutable. Pour cleanup en tests : `SET session_replication_role = 'replica'` avant le DELETE, `'origin'` après.
3. **pytest-asyncio** : besoin de `loop_scope="session"` à la fois en config (`asyncio_default_fixture_loop_scope`) ET sur les markers de tests (`@pytest.mark.asyncio(loop_scope="session")` + `pytestmark = pytest.mark.asyncio(loop_scope="session")` au niveau module).
4. **Hooks achievements** placés APRÈS le commit du savepoint principal d'unlock — un échec de grant n'invalide pas l'unlock.

### Commandes courantes (backend)
```bash
# Lancer
cd /Users/tommio/Desktop/WORK/Smyleplay/smyleplay-api && docker-compose up -d

# Tests
docker-compose exec api pytest                          # all (1618 tests, ~5s)
docker-compose exec api pytest tests/test_xxx.py -v     # un fichier
docker-compose exec api pytest -k "achievement"         # filtre

# DB
docker exec smyleplay-api-db-1 psql -U postgres -d smyleplay -c "SELECT ..."

# OpenAPI
curl -s http://localhost:8000/openapi.json | jq '.paths | keys'
```

---

## 🎨 Front `smyleplay-web/` — DÉMARRÉ ce matin (Phase 1A-1D en cours)

### ⚠️ ALERTE : à fusionner avec l'existant
Tom a confirmé qu'il a **déjà un site/front, des docs/maquettes, et des assets média** dans `/Users/tommio/Desktop/WORK/Smyleplay/`.
La nouvelle session doit **inventorier ce qui existe** avant de continuer le front Next.js. Décision à prendre : on garde l'existant et on le branche au backend ? on remplace ? on fusionne sélectivement ?

### Localisation
- **Vrai projet** : `/Users/tommio/Desktop/WORK/Smyleplay/smyleplay-web/`
- **Mirror Cowork** : `/Users/tommio/Desktop/WORK/IA SUNO PLAYLIST DEVELOPPEMENT /smyleplay-web/`
  → variable `$WEB` dans `.zshrc`

### Stack choisie (à confirmer avec l'existant)
- **Next.js 16.2.4** (Turbopack par défaut), **App Router**, TypeScript, src/ layout, alias `@/*`
- **Tailwind v4** + **shadcn/ui** (button, card déjà ajoutés)
- **Node 25.9.0** installé via Homebrew

### Fichiers créés
```
smyleplay-web/
├── .env.local                          # NEXT_PUBLIC_API_URL=http://localhost:8000
├── src/
│   ├── lib/
│   │   ├── api.ts                      # ✅ Client fetch typé + ApiError
│   │   └── utils.ts                    # shadcn (cn helper)
│   ├── components/ui/
│   │   ├── button.tsx                  # shadcn
│   │   └── card.tsx                    # shadcn
│   └── app/
│       ├── layout.tsx                  # default Next
│       ├── page.tsx                    # default Next (page d'accueil pas touchée)
│       ├── globals.css                 # Tailwind v4 + variables shadcn
│       ├── health/page.tsx             # ✅ Smoke test backend (Server Component)
│       └── feed/page.tsx               # ✅ Catalogue public prompts (Server Component, grille shadcn)
```

### État
- ✅ **Étape 1A** — Bootstrap (`create-next-app`) : Done
- ✅ **Étape 1B** — Init shadcn/ui : Done
- ✅ **Étape 1C** — Helper API + page `/health` : Done, vérifié ("status ok" affiché)
- 🟡 **Étape 1D** — Page `/feed` : Code copié, **vérif visuelle interrompue** par Tom qui a réalisé qu'on ignorait son projet existant.

### Commandes courantes (front)
```bash
cd /Users/tommio/Desktop/WORK/Smyleplay/smyleplay-web && npm run dev
# → http://localhost:3000 (page Next default)
# → http://localhost:3000/health (smoke test backend)
# → http://localhost:3000/feed (catalogue prompts)
```

---

## 🗺️ Plan global Smyle Play (donné par Tom)

```
PHASE 1 — Produit visible (front, navigation, données affichées)   ← ON EST ICI
PHASE 2 — Flow complet (signup, achat, library, retour)
PHASE 3 — Test réel (utilisateur inconnu)
PHASE 4 — Automation base (génération + publication contenu)
PHASE 5 — Stabilisation (bugs UX, lisibilité, vitesse)
PHASE 6 — Monétisation (Stripe achat crédits)
PHASE 7 — Automation avancée (agents, reco, optimisation)
PHASE 8 — Évolution long terme (mobile, P2P, branding, analytics)
```

Règle non négociable : **front d'abord**, puis flow complet, puis test, puis automation. Pas l'inverse.

---

## 🛠️ Setup Mac (déjà configuré)

### Variables `.zshrc` (ajoutées ce matin)
```zsh
# Smyle Play — Cowork mirrors (auto-généré)
export SOURCE="/Users/tommio/Desktop/WORK/IA SUNO PLAYLIST DEVELOPPEMENT /smyleplay-api"
export WEB="/Users/tommio/Desktop/WORK/IA SUNO PLAYLIST DEVELOPPEMENT /smyleplay-web"
```

### Outils installés
- Docker Desktop (containers `smyleplay-api-api-1`, `smyleplay-api-db-1` running)
- Node 25.9.0 + npm + npx (via brew)
- Python 3.11 (dans le container Docker, pas sur le host)
- Homebrew 5.1.6

### À noter pour la nouvelle session
- Le path `IA SUNO PLAYLIST DEVELOPPEMENT ` contient un **espace en fin** (très important pour les `cp`).
- Le workspace Cowork actuel est `IA SUNO PLAYLIST DEVELOPPEMENT/`. La nouvelle session aura **`Smyleplay/`** comme workspace → adapter les chemins en conséquence.

---

## 📋 Tâches Cowork actives (à reporter dans la nouvelle session)

| # | Statut | Sujet |
|---|---|---|
| 76 | ✅ done | Phase 1A — Bootstrap Next.js |
| 77 | ✅ done | Phase 1B — Init shadcn/ui |
| 78 | ✅ done | Phase 1C — Helper API + page /health |
| 79 | 🟡 in_progress | Phase 1D — Page /feed (vérif visuelle interrompue) |
| 80 | ⏳ pending | Phase 2 — Page /login + auth front (token storage) |
| 81 | ⏳ pending | Phase 3 — Page /library |
| 82 | ⏳ pending | Phase 4 — Page /artist/[id] |
| 83 | ⏳ pending | Phase 5 — Page /create (artiste) |

**Backend (toutes terminées)** : tasks #1-75 + Phase 9.6 (#73). Voir `git log` pour le détail.

---

## 🚦 Action immédiate pour la nouvelle session

1. **Saluer Tom et reconnaître la passation** ("OK, je vois le HANDOFF, je vais d'abord inventorier ce qui existe").
2. **Inventorier `/Users/tommio/Desktop/WORK/Smyleplay/`** (son nouveau workspace) :
   ```bash
   ls -la /Users/tommio/Desktop/WORK/Smyleplay/
   find /Users/tommio/Desktop/WORK/Smyleplay/ -maxdepth 2 -type f | head -50
   ```
3. **Identifier** : techno du front existant (HTML statique ? Next ? React ? autre ?), pages présentes, assets, docs concept.
4. **Demander à Tom via `AskUserQuestion`** :
   - Quelle est la techno actuelle du site ?
   - Veut-il garder l'existant et le brancher au backend, ou tout migrer vers le nouveau Next.js qu'on a démarré ?
   - Le front `smyleplay-web/` qu'on a commencé ce matin doit-il être conservé, déplacé, ou supprimé ?
5. **Décider de la suite** avec Tom (sans coder avant que ce soit clair).

---

## 🧠 Contexte produit — l'ADN du projet (ce que j'ai compris sans voir le projet existant)

**Smyle Play** est un marketplace musical où :
- Des **artistes** créent des **univers** (`Adn`) — une signature sonore avec sa propre `brand_color`, sa description, son `usage_guide`, ses `example_outputs` (gated).
- Des **fans** peuvent acheter ces ADN (devenir collectionneurs : `OwnedAdn`) → ça leur donne un perk -30% sur tous les prompts du même artiste.
- Les artistes publient des **`Prompt`** dérivés de leur ADN, vendables en crédits.
- Les **buyers** débloquent un prompt (`UnlockedPrompt`) → accès au `prompt_text` complet (qui est gated avant achat).
- Économie en **crédits** (pas encore Stripe). Toute mutation passe par des `Transaction` immutables (audit ledger).
- 3 axes de progression avec **trophées** (BUYER = collectionneur, FAN = découvreur d'ADN, ARTIST = créateur). 13 badges seedés. Hooks auto.

**Univers musicaux mentionnés** (skill `watt-prompt`) :
JUNGLE OSMOSE, NIGHT CITY, SUNSET LOVER, HIT MIX, dancehall, reggaeton, jazz, soul, deep house, electro, tropical, jersey, afro, house.

---

## 📞 Communication avec Tom

- **Tutoiement** systématique
- **Réponses concises** (Tom n'est pas dev, surcharge = bruit)
- **Jamais** de jargon non expliqué — toujours analogie ou démo visuelle
- **Toujours** lui dire **où** (terminal 1 ou 2 ?) et **quoi** taper
- **Vérification visuelle** privilégiée ("ouvre cette URL et dis-moi ce que tu vois")
- Si une commande peut planter (zsh dquote, parsing, espace dans path) → la **simplifier** plutôt que la rendre robuste

Bonne session 🚀
