# SMYLE PLAY — Handoff mémoire conversationnelle

> Document passerelle pour reprendre la conversation dans un nouveau chat.
> Colle ce fichier (ou son contenu) au début du prochain chat comme contexte.
> Date export : 2026-04-20.

---

## 1. Stack & architecture

- **Flask** sur port **8080** — sert les HTML statiques + endpoints legacy `/api/*`
  - `static_folder=BASE_DIR, static_url_path=''` → tout le dossier `Smyleplay/`
    est accessible en statique (c'est comme ça que `/ui/modals/search.js`,
    `/dashboard.js`, etc. sont servis).
- **FastAPI** sur port **8000** — `smyleplay-api/app/` — endpoints modernes
  sous `/watt/...`, `/playlists/...`, `/auth/...`, etc.
- **PostgreSQL** partagé entre les deux.
- **Alembic** pour les migrations (numérotées, dernière posée : `0021_playlists`).
- **Racine projet** : `/sessions/relaxed-affectionate-turing/mnt/Smyleplay`.
- **Graphify** : un graphe de connaissance est dans `graphify-out/`. CLAUDE.md
  demande d'interroger `/graphify query "..."` avant de lire les fichiers
  bruts, et de lancer `graphify update .` après modif (CLI locale, pas dispo
  en sandbox — le user doit le faire).

## 2. Roadmap « profil public » — état par étape

| # | Étape | Statut |
|---|---|---|
| 1 | Gate profil publié avant publication d'un son | ✅ terminée |
| 2 | Couleur par morceau (track_color + fallback brand_color) | ✅ terminée |
| 3 | Modèle Playlist unifié (table + junction + seed wishlist) | ✅ terminée |
| 4a | My Mix recentré consommation (privé uniquement) | 🔜 pending |
| 4b | Dashboard Création 1c « Mes Playlists Publiques » | 🔜 pending |
| 5 | UI `/u/<slug>` : cellules playlists + tracks orphelins + clip 3s | 🔜 pending |
| — | Section Recherche globale (Connect + DNA, topbar) | ✅ terminée |
| — | Rework UX gate publication (form visible mais désactivé) | ✅ terminée |
| — | Texte ADN pédagogique précisé (BPM, notes, clés, styles) | ✅ terminée |

## 3. Ce qui a été livré dans les dernières sessions

### 3.1 — Étape 3 Playlists (backend FastAPI)

Fichiers créés / modifiés :

- `smyleplay-api/app/models/playlist.py` — modèles `Playlist` + `PlaylistTrack`
  (composite PK, visibility enum-like via CheckConstraint, `dna_description`
  forward-compat).
- `smyleplay-api/app/models/__init__.py` — export des modèles.
- `smyleplay-api/app/schemas/playlist.py` — Pydantic v2 avec
  `Visibility = Literal["public","private"]`, `extra="forbid"`.
- `smyleplay-api/app/services/playlists.py` — logique métier :
  `create_playlist`, `get_playlist`, `list_user_playlists`, `update_playlist`
  (avec assertion public owner), `delete_playlist`, `add_track` (idempotent),
  `remove_track`, `list_playlist_tracks`, `ensure_default_wishlist`.
  Exceptions typées : `PlaylistNotFound`, `PlaylistForbidden`,
  `PlaylistPublicOwnerMismatch`, `TrackNotFound`.
- `smyleplay-api/app/routers/playlists.py` — deux routeurs :
  `router = APIRouter(prefix="/playlists")` (auth) + `public_router = APIRouter(prefix="/watt")`.
  Endpoints : POST/GET/PATCH/DELETE `/playlists`, GET `/playlists/me`,
  GET `/playlists/wishlist`, POST/DELETE `/playlists/{id}/tracks/{track_id}`,
  GET `/watt/users/{slug}/playlists`.
- `smyleplay-api/app/routers/auth.py` — register wrappe
  `ensure_default_wishlist` (best-effort try/except).
- `smyleplay-api/tests/test_playlists.py` — TestPlaylistCRUD, TestPlaylistTracks,
  TestWishlistSeed, TestPlaylistAuth.

**Règles métier importantes** :
- Playlist publique ⇒ ne peut contenir QUE des tracks de son owner (vérifié
  au service, pas au DB, pour garder la flexibilité).
- PlaylistTrack a une PK composite (playlist_id, track_id) → pas de doublon.
- Wishlist (titre "Ma Wishlist") est une playlist privée seed auto à l'inscription.

### 3.2 — Rework UX gate publication (dashboard)

Quand le profil public n'est pas encore créé, le formulaire d'upload de son
RESTE VISIBLE mais est désactivé (opacité .45 + grayscale .3 + pointer-events
via ::after), et une bannière flashe en haut pour inciter à créer le profil.
Un clic sur le formulaire gated fait scroll + flash + toast.

Fichiers touchés :
- `dashboard.js` — `renderCreationGate()` (classe `.is-gated` au lieu de
  `display:none`), `handleGatedLayoutClick(ev)` (capture-phase), `gotoMyProfile()`
  (ajoute `?edit=1` à l'URL).
- `dashboard.html` — titres et copy du bloc gate, bouton « Créer mon profil ».
- `dashboard.css` — `.dash-creation-gate.is-flash`, `@keyframes dash-gate-flash`,
  `.dash-upload-layout.is-gated`.
- `artiste.js` — `_hasEditIntentParam()` lit `?edit=1`/`true`/`yes`,
  `maybePromptFirstEdit()` force le mode édition + scroll vers identité et
  nettoie l'URL via `history.replaceState`.

### 3.3 — Recherche globale (topbar)

Backend :
- `smyleplay-api/app/routers/search.py` — router `/watt/search` avec
  `/artists` et `/tracks`. ILIKE sur colonnes textuelles, gate
  `profile_public=true`, max 30 résultats, tri `plays desc, followers desc,
  created_at desc` pour artistes et `plays desc, created_at desc` pour tracks.
- `smyleplay-api/app/main.py` — import + `app.include_router(search_router)`.

Frontend :
- `ui/modals/search.js` (IIFE, guard `window.__smyleSearchInstalled`) —
  auto-injecte un bouton loupe dans la topbar (détection multi-classes :
  `.dash-topbar-right`, `.ap-topbar-right`, `.lib-topbar-right`,
  `.topbar-right`), ouvre un modal avec onglets **Connect** (artistes) /
  **DNA** (tracks), fetch debouncé 280 ms, fermeture ESC + click-outside,
  API publique `window.SmyleSearch = { open, close, setTab }`.
- Inclusion dans `dashboard.html`, `index.html`, `library.html`, `watt.html`,
  `artiste.html` via `<script src="/ui/modals/search.js" defer></script>`.

### 3.4 — Texte ADN pédagogique (dashboard Création → Mon ADN)

Bloc `#dashAdnEmpty` dans `dashboard.html` ligne ~537 — réécrit pour préciser
les ingrédients techniques d'un ADN :

> Ton ADN est le prompt de ta trame créative complète qui décrit ton univers
> musical : influences, atmosphères, références, BPM, notes et clés
> généralement utilisés, styles d'influence et guide d'utilisation. Les fans
> peuvent l'acheter pour composer dans ton style ; le posséder leur déclenche
> automatiquement un bonus -30 % sur tous tes morceaux promptés mis en vente
> sur ton profil.

## 4. Incident en cours / non résolu

L'utilisateur dit « sur le site je n'ai pas accès à ces modifs ».

Diagnostic posé :
- Fichier `ui/modals/search.js` sur disque = propre, 533 lignes, `node --check` passe.
- HTML (`dashboard.html` lignes 537 + 821) contient bien le nouveau texte ADN
  et l'inclusion `<script src="/ui/modals/search.js" defer></script>`.
- Le « fichier traduit en français » que l'utilisateur voyait = Google Translate
  auto-déclenché sur l'onglet brut du JS (commentaires FR en tête ⇒ Chrome
  traduit même les mots-clés). Pas un vrai problème, c'est cosmétique sur la
  vue brute.

**Ce qu'il faut vérifier au prochain échange** — demander à l'utilisateur de
faire sur `http://localhost:8080/dashboard` (F12 ouvert, Disable cache coché,
Ctrl+Shift+R) :

1. Console : `typeof window.SmyleSearch` → attendu `"object"`.
2. Network : filtrer `search.js` → attendu status 200 ou 304.
3. Œil : loupe ronde visible dans la topbar (à côté du solde Smyle).

Si `undefined` en console, le script n'est pas chargé → regarder le status
Network. Si 404, vérifier que Flask tourne bien depuis `/sessions/.../mnt/Smyleplay`.

Pour le texte ADN : il n'apparaît QUE dans l'état vide (`#dashAdnEmpty`). Si
l'utilisateur a déjà un ADN en base, c'est le résumé qui s'affiche à la place
(`#dashAdnSummary`), et le texte pédagogique n'est pas visible — c'est voulu.

## 5. Pending tasks à reprendre

- **#47** — Étape 4b : Dashboard Création ajouter bloc 1c « Mes Playlists
  Publiques » (collection de playlists publiques de l'artiste, gérables
  depuis le dashboard, consommables sur `/u/<slug>`).
- **#46** — Étape 4a : My Mix recentré consommation privée uniquement
  (Library → My Mix ne manipule plus que des playlists privées ; les
  publiques sont gérées depuis Création).
- **#48** — Étape 5 : UI `/u/<slug>` cellules playlists + tracks orphelins
  (tracks non rattachés à une playlist publique) + clip audio 3s au hover.

## 6. Conventions de code importantes

- **Pas de frontend bundler** : vanilla JS classique, fichiers inclus via
  `<script>`, exposition via `window.X = X` pour handlers inline onclick.
- **API_BASE** : `window.API_BASE` (injecté par `/ui/core/api.js`), fallback
  `http://localhost:8000` côté JS frontend.
- **Auth JWT** : headers `Authorization: Bearer <token>` côté FastAPI ; côté
  Flask session legacy pour les vieilles routes.
- **SQLAlchemy async** : Mapped/mapped_column + `postgresql.UUID(as_uuid=True)`,
  AsyncSession via `Depends(get_db)`.
- **Pydantic v2** : `model_config = ConfigDict(extra="forbid")` sur tous les
  update schemas, Literal types pour enums, patterns regex pour couleurs hex.
- **Commentaires en français** dans le code (préférence utilisateur).

## 7. Perspective utilisateur (contexte stratégique)

L'utilisateur Tom veut maintenant **créer son propre premier profil artiste**
pour calibrer les interfaces avec du contenu réel. Ça va aider à :
- mesurer les frictions du parcours création → publication ;
- combler les vides visuels sur `/u/<slug>` (pertinent pour étape 5) ;
- ajuster les libellés qui résonnent vraiment pour un artiste qui arrive.

Le prochain pas logique : soit il remplit son profil pendant qu'on attaque
#48, soit on regarde ensemble son profil rempli pour trancher.

## 8. Commandes utiles

```bash
# Backend FastAPI (port 8000)
cd smyleplay-api && uvicorn app.main:app --reload --port 8000

# Frontend Flask (port 8080)
python app.py

# Migrations Alembic
cd smyleplay-api && alembic upgrade head
cd smyleplay-api && alembic revision -m "..." --autogenerate

# Tests backend
cd smyleplay-api && pytest tests/test_playlists.py -v

# Graphify (à lancer en local, pas dispo en sandbox)
graphify update .
```

## 9. Fichiers clés à connaître

- `app.py` — Flask monolithe (toutes les routes HTML + API legacy)
- `dashboard.html` + `dashboard.js` + `dashboard.css` — cockpit artiste
  (Création + Analytique en 2 pills)
- `artiste.html` + `artiste.js` — page publique `/u/<slug>` (mode owner + viewer)
- `library.html` + `library.js` — My Mix / wishlist viewer
- `watt.html` + `watt.js` — homepage WATT (artistes + tracks)
- `smyleplay-api/app/main.py` — entrée FastAPI, liste des routers montés
- `smyleplay-api/app/routers/*.py` — tous les endpoints modernes
- `smyleplay-api/app/models/*.py` — modèles SQLAlchemy async
- `smyleplay-api/alembic/versions/` — migrations numérotées
- `ui/modals/search.js` — modal recherche globale (auto-inject topbar)
- `ui/smyle-balance.js` — widget solde Smyle (auto-inject topbar, modèle suivi
  par search.js)
- `ui/core/api.js` — constantes API_BASE + helpers fetch
- `ui/session-guard.js` — redirect logic session expirée
- `CLAUDE.md` — instructions projet (interroger graphify avant fichiers bruts)

---

**Fin du handoff.** Ouvre le nouveau chat, colle ce document (ou pointe
Claude vers ce fichier), et dis « reprend là où on s'est arrêté ».
