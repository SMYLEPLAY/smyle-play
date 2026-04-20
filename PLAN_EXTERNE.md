# PLAN EXTERNE — ce qu'il te reste à faire, étape par étape

Tout ce que j'ai pu automatiser est fait. Ce document liste **uniquement** les
actions qui nécessitent soit ton terminal, soit une décision de ta part, soit
un accès à des services externes (Railway, Cloudflare, R2…) que je n'ai pas.

Fais les étapes **dans l'ordre**. Chaque étape a :

- `Objectif` — pourquoi cette étape existe
- `Commandes` — à coller tel quel dans ton terminal
- `Vérification` — comment savoir que c'est OK avant de passer à la suivante

---

## Étape A — Appliquer la migration 0012 (legacy_id sur tracsk)

### Objectif

La migration 0012 ajoute une colonne `legacy_id` à la table `tracks`. Cette
colonne conserve les IDs historiques du catalogue WATT (ex :
`sl-sw001amberdrivedriftwav`) qu'utilise le JS existant pour :

- les URLs publiques (`/artiste/<slug>?track=<id>`)
- les compteurs de plays en localStorage (`smyle_plays_<id>`)
- les panneaux playlist (attribut `data-id`)

Sans cette migration, `/watt/plays/<id>` renverra 404 pour les tracks seedées
depuis `tracks.json`.

### Commandes

```bash
cd ~/Desktop/WORK/Smyleplay/smyleplay-api

# Appliquer la migration
docker-compose run --rm api alembic upgrade head
```

### Vérification

Tu dois voir dans la sortie quelque chose comme :

```
INFO  [alembic.runtime.migration] Running upgrade 0011_extend_tracks -> 0012_add_track_legacy_id
```

Puis vérifier la colonne :

```bash
docker-compose exec db psql -U postgres -d smyleplay \
  -c "\d tracks" | grep legacy_id
```

Doit afficher une ligne du type :
```
 legacy_id        | character varying(100) |           |          |
```

---

## Étape B — Re-run du seed pour backfill `legacy_id`

### Objectif

Le seed a été lancé **avant** la migration 0012. Les 82 tracks ont donc un
`legacy_id = NULL`. Le code du seed a été mis à jour pour remplir `legacy_id`
en mode "upsert" : il va mettre à jour les tracks existantes (match par
`r2_key`) sans créer de doublons.

### Commandes

```bash
cd ~/Desktop/WORK/Smyleplay/smyleplay-api

docker-compose run --rm \
  -v ~/Desktop/WORK/Smyleplay/tracks.json:/tmp/tracks.json:ro \
  api python tools/seed_from_tracks_json.py --tracks-json /tmp/tracks.json
```

### Vérification

Tu dois voir à la fin :

```
Créés   : 0
MAJ     : 82
Ignorés : 0
Total   : 82
```

Puis confirmer que tous les `legacy_id` sont remplis :

```bash
docker-compose exec db psql -U postgres -d smyleplay \
  -c "SELECT COUNT(*) AS total, COUNT(legacy_id) AS with_legacy FROM tracks;"
```

Doit afficher `total=82, with_legacy=82`.

---

## Étape C — Redémarrer l'API (pour charger le router `/watt/*`)

### Objectif

J'ai ajouté `app.include_router(watt_compat_router)` dans
`smyleplay-api/app/main.py`. Ça ne sera pris en compte qu'après un restart.

### Commandes

```bash
cd ~/Desktop/WORK/Smyleplay/smyleplay-api

docker-compose restart api
# Attends 3-4 secondes puis vérifie que ça a démarré proprement :
docker-compose logs --tail=30 api
```

### Vérification

Les logs doivent afficher :

```
Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
Application startup complete.
```

Aucune ligne `ImportError` ou `Traceback`. Si tu vois une erreur, copie-la
moi et je corrige.

Puis teste l'endpoint :

```bash
curl -s http://localhost:8000/watt/artists | head -c 300
```

Doit retourner un JSON type `{"artists": [...]}` avec les 4 univers.

---

## Étape D — Lancer Flask et tester les pages dans le navigateur

### Objectif

Vérifier que le JS (désormais branché sur `apiFetch('/watt/*')`) discute bien
avec le FastAPI sans erreur CORS et sans 404.

### Commandes

```bash
# Terminal 1 — FastAPI doit tourner (déjà fait via docker-compose)
cd ~/Desktop/WORK/Smyleplay/smyleplay-api
docker-compose up

# Terminal 2 — Flask
cd ~/Desktop/WORK/Smyleplay
python app.py  # ou ta commande habituelle pour lancer Flask sur :8080
```

Ouvre **http://localhost:8080** dans le navigateur.

### Vérification

Dans la console du navigateur (F12 → Console), tu NE dois voir :

- **aucune erreur CORS** (de type `Access-Control-Allow-Origin`)
- **aucun 404** sur `/watt/artists`, `/watt/tracks-catalog`, `/watt/tracks-recent`

Pages à tester :

1. `/` (home) — les playlists doivent s'afficher (chargement via `/watt/tracks-catalog`)
2. `/watt` — le classement public doit s'afficher (via `/watt/artists`)
3. `/watt` — les derniers sons doivent s'afficher (via `/watt/tracks-recent`)
4. `/artiste/sunset-lover` — la fiche artiste doit s'afficher (via `/watt/artists/sunset-lover`)

**Si une page casse**, garde la console ouverte, fais un screenshot et envoie-moi :
- l'URL qui a foiré
- le code d'erreur (4xx/5xx)
- le message dans la console JS

---

## Étape E — Purger le dossier Next.js `smyleplay-web/`

### Objectif

Le dossier `smyleplay-web/` contient un scaffold Next.js abandonné (783 Mo,
principalement du `node_modules`). Il n'est plus utilisé dans la nouvelle
architecture (Flask front + FastAPI back). Il reste des **changements
non-committés** dans ce dossier, donc je ne l'ai pas supprimé automatiquement
par sécurité.

### Commandes

Si tu es sûr de ne rien vouloir récupérer :

```bash
cd ~/Desktop/WORK/Smyleplay
rm -rf smyleplay-web
```

Si tu veux archiver au cas où :

```bash
cd ~/Desktop/WORK
mv Smyleplay/smyleplay-web ./smyleplay-web.archived-2026-04-18
```

### Vérification

```bash
ls ~/Desktop/WORK/Smyleplay | grep -i web
# ne doit rien retourner
```

---

## Étape F — Décisions à prendre pour la suite (ordre conseillé)

Ces étapes dépendent de ce que tu veux prioriser. Fais-les **après** A–E.

### F.1 — Auth JWT côté Flask (remplacement de `session['user_id']`)

**Pourquoi** : aujourd'hui, `apiFetch()` ne transmet pas encore de JWT parce
que le login Flask crée une session cookie, pas un token. Résultat : tous les
endpoints `/watt/me/*` renvoient 401.

**Ce qu'il faut faire** (1 session de travail avec moi) :
1. Sur la page `/login` de Flask, après le POST vers `/login`, faire un
   `apiFetch('/auth/login', { method: 'POST', body: { email, password }})`
   pour récupérer un JWT
2. Stocker le JWT avec `setAuthToken(token)` (déjà dispo dans `ui/core/api.js`)
3. Mêmes modifs sur `/register` et le logout

Une fois ça fait, `/watt/me/stats` (stats artiste sur la page `/watt`) se
remplira automatiquement pour les users connectés.

### F.2 — Écriture : upload / delete / profile

Les endpoints write ne sont pas encore dans le shim :

- `POST /api/watt/upload` → garde Flask pour l'instant (R2 multipart)
- `POST /api/watt/tracks` → idem
- `PUT /api/watt/profile` → idem
- `POST /api/collabs`, `GET /api/collabs/inbox` → idem (logique collab pas portée)
- `POST /api/agents/process-track` → idem (pipeline agents pas porté)
- `GET /api/auth/me` → idem (tant que l'auth JWT n'est pas faite, on garde la session Flask)

Ce sera l'**étape suivante** après l'auth JWT. On portera un endpoint à la
fois, en gardant Flask comme fallback.

### F.3 — Déploiement Railway

Quand les endpoints read marchent bien en local, on passera à :

1. Créer un service FastAPI sur Railway (avec Postgres attaché)
2. Ajouter `CORS_ALLOWED_ORIGINS=https://smyleplay.com,https://www.smyleplay.com`
3. Configurer `API_BASE` côté JS pour pointer sur la prod Railway
4. Déployer en mode "shadow" : Flask reste le front officiel, FastAPI répond
   uniquement aux routes `/watt/*`

### F.4 — Pipeline Suno (plus tard)

Pas couvert ici. On verra quand WATT v1 tournera stable en prod.

---

## Rappel : ce qui a été fait automatiquement (tu n'as rien à refaire)

- ✅ Migration Alembic 0011 (universe, duration_seconds, r2_key, plays)
- ✅ Migration Alembic 0012 (legacy_id) — **doit être appliquée** (étape A)
- ✅ Seed des 82 tracks + 4 users univers depuis `tracks.json`
- ✅ Modèle SQLAlchemy `Track` mis à jour
- ✅ CORS configuré sur FastAPI (localhost:8080 autorisé)
- ✅ Helper JS `ui/core/api.js` créé et intégré dans `index.html`,
      `dashboard.html`, `artiste.html`, `watt.html`
- ✅ Router `watt_compat` créé avec 8 endpoints Flask-compat
- ✅ `app.include_router(watt_compat_router)` ajouté dans `main.py`
- ✅ JS branché sur `/watt/*` :
  - `watt.js` : classement + derniers sons
  - `artiste.js` : fiche artiste + POST plays
  - `ui/hub/community.js` : catalogue playlists + hub community
  - `ui/panels/agent.js` : cockpit + monitoring
  - `ui/panels/watt-panel.js` : stats connect + stats artiste
  - `dashboard.js` : delete track

## Ce qui reste volontairement sur Flask (à migrer plus tard)

- Uploads (`POST /api/watt/upload`, `POST /api/watt/tracks`)
- Profile update (`PUT /api/watt/profile`)
- Avatar upload (Flask only)
- Collabs (`/api/collabs/*`)
- Agents pipeline (`/api/agents/*`)
- Auth session (`/api/auth/me`, `/login`, `/register`, `/logout`)

Ces routes continuent de marcher comme avant. Elles seront portées une par
une quand on attaquera les étapes F.1 et F.2.
