# Étape 1 — Migration data Flask → FastAPI (runbook)

**Objectif** : importer les 82 tracks du catalogue WATT (tracks.json côté Flask)
dans la base Postgres du backend FastAPI, sans rien toucher au site Flask
existant.

**Risque pour le site Flask actuel** : **aucun**. Le script lit uniquement
`tracks.json` en mode lecture seule et écrit dans la base FastAPI (isolée).

---

## Ce qui a été livré

1. `smyleplay-api/alembic/versions/0011_extend_tracks_for_flask_migration.py`
   → ajoute 4 colonnes au modèle `Track` : `universe`, `duration_seconds`,
   `r2_key`, `plays`. Plus une CHECK constraint sur les valeurs d'univers
   autorisées et un index sur `universe`.

2. `smyleplay-api/app/models/track.py` (modifié)
   → le modèle SQLAlchemy reflète les nouveaux champs.

3. `smyleplay-api/tools/seed_from_tracks_json.py`
   → script idempotent qui :
   - crée 4 "users-univers" (SUNSET LOVER, JUNGLE OSMOSE, NIGHT CITY, HIT MIX)
     avec la bonne `brand_color` et un password hash impossible (pas de login)
   - importe les 82 tracks, chacune rattachée à son user-univers
   - supporte `--dry-run` pour vérifier sans écrire

---

## Comment lancer ça chez toi (sur le Mac)

Tout se passe dans `~/Desktop/WORK/Smyleplay/smyleplay-api/`.

### 1. Démarrer la base Postgres FastAPI

```bash
cd ~/Desktop/WORK/Smyleplay/smyleplay-api
docker-compose up -d db
```

### 2. Appliquer la migration 0011

```bash
docker-compose run --rm api alembic upgrade head
```

Tu devrais voir dans les logs :
```
INFO  [alembic.runtime.migration] Running upgrade 0010_strict_unlock_check -> 0011_extend_tracks, ...
```

### 3. (Optionnel) Dry-run pour vérifier

**Important** : `tracks.json` est dans `~/Desktop/WORK/Smyleplay/` (dossier
parent), pas dans `smyleplay-api/`. Le container ne voit que `smyleplay-api/`
monté sur `/app`. Il faut donc monter `tracks.json` à la volée avec `-v`.
Toute la commande doit tenir sur **une seule ligne** (pas de `\` qui ouvre
sur une ligne de commentaire — zsh n'aime pas ça).

```bash
docker-compose run --rm -v ~/Desktop/WORK/Smyleplay/tracks.json:/tmp/tracks.json:ro api python tools/seed_from_tracks_json.py --tracks-json /tmp/tracks.json --dry-run
```

Sortie attendue :
```
▸ sunset-lover : 22 tracks à traiter
   [dry-run] would create user sunset-lover@smyleplay.local
▸ jungle-osmose : 30 tracks à traiter
   [dry-run] would create user jungle-osmose@smyleplay.local
▸ night-city : 20 tracks à traiter
   ...
==================================================
Créés   : 82
MAJ     : 0
Ignorés : 0
==================================================
```

### 4. Lancer le seed pour de vrai

```bash
docker-compose run --rm -v ~/Desktop/WORK/Smyleplay/tracks.json:/tmp/tracks.json:ro api python tools/seed_from_tracks_json.py --tracks-json /tmp/tracks.json
```

### 5. Vérifier en base

```bash
docker-compose exec db psql -U smyle -d smyleplay -c \
  "SELECT universe, COUNT(*) FROM tracks GROUP BY universe ORDER BY universe;"
```

Tu dois voir :
```
   universe    | count
---------------+-------
 hit-mix       |    10
 jungle-osmose |    30
 night-city    |    20
 sunset-lover  |    22
```

Et les 4 users-univers :
```bash
docker-compose exec db psql -U smyle -d smyleplay -c \
  "SELECT artist_name, brand_color FROM users WHERE email LIKE '%@smyleplay.local';"
```

---

## Ce que ça ne fait pas encore (à venir dans les étapes suivantes)

- **Pas de migration des vrais users Flask** (comptes créés via le dashboard).
  Raison : je n'ai trouvé aucune DB Flask locale (`*.db`, `*.sqlite`) sur
  ton disque. Les comptes étaient probablement sur Railway Postgres. À voir
  ensemble si on les récupère depuis Railway (pg_dump), ou si on repart
  clean et les gens se réinscrivent.

- **Pas de migration des playlists sauvegardées (SavedMix)** ni des Collabs
  (concept v1 qu'on abandonne en v3 de toute façon).

- **Pas encore de branchement front** : ton site Flask continue de taper sur
  lui-même et lire `tracks.json`. Le front ne verra les données FastAPI que
  quand on aura fait l'étape 3 (helper `apiFetch()`) + étape 4 (mapping des
  appels read-only).

---

## Si quelque chose se passe mal

**Cas 1 : la migration 0011 échoue.** On peut rollback proprement avec
`alembic downgrade 0010_strict_unlock_check` — les 4 colonnes ajoutées sont
nullables (sauf `plays` avec default 0), donc pas de perte de données.

**Cas 2 : le seed s'arrête au milieu.** Relance-le. Il est idempotent
(match par `r2_key`), donc tu ne crées jamais de doublon.

**Cas 3 : les URLs R2 ne sont plus valides.** Ce n'est pas un problème pour
l'étape 1 : on stocke simplement ce qui est dans `tracks.json`. Si tu
changes de bucket plus tard, un simple `UPDATE tracks SET audio_url = ...`
suffira.

---

## Une fois que c'est fait

Dis-le-moi, je passe à **l'étape 2** (CORS côté FastAPI) puis **étape 3**
(helper `apiFetch()` côté JS Flask). Ces deux étapes aussi sont zéro risque
pour ton site actuel — on ajoute sans rien casser.
