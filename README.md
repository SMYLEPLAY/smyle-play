# WATT (watt.place)

Plateforme où des créateurs publient des **Œuvres** créées avec l'IA (un son et
une image, avec leur recette) et les vendent en **Smyles**.

- **Site** : https://watt.place
- **Backend** : FastAPI (`watt-api/`), qui sert **tout** : l'API, les pages HTML
  et les fichiers statiques (`watt-api/app/routers/pages.py`). Flask a été
  supprimé le 2026-07-30.
- **Base** : PostgreSQL, migrations Alembic (`watt-api/alembic/versions/`).
- **Fichiers** : Cloudflare R2 (sons, images, vidéos) — un bucket public, un
  bucket privé optionnel (`R2_PRIVATE_BUCKET`) pour les originaux payants et
  les contenus retirés par la modération.
- **Hébergement** : Railway (`railway.toml`), sonde `/health`.

## Structure du dépôt

```
.
├── main.py              # Point d'entrée uvicorn (importe watt-api/app/main.py)
├── watt-api/            # SEUL backend : API FastAPI, migrations, tests
│   ├── app/             # routers/ · services/ · models/ · schemas/ · core/ · auth/
│   ├── alembic/         # migrations (une seule tête, cf. /health → alembic_head)
│   ├── tests/           # suite pytest (Postgres réel)
│   ├── scripts/         # scripts ponctuels (ex. migrate_originals_to_private.py)
│   └── tools/           # outils d'exploitation (sauvegarde des médias, lien de secours…)
├── *.html · *.js · *.css  # pages et scripts du site (servis par FastAPI)
├── ui/                  # composants front partagés (api, modales, lecteur, PWA…)
├── e2e/                 # tests de bout en bout (Playwright)
├── ops/k6/              # test de charge (k6) — jamais contre la production
├── agents/              # agents Python (classement ADN, playlists, prompts)
├── data/                # données statiques (config/, seeds/ ; exports/ ignoré)
├── scripts/             # scripts shell/Python ponctuels
└── .github/workflows/   # CI, E2E, sauvegardes, restore drill
```

Pour les humains : ce `README.md`. Pour les agents IA : [`CLAUDE.md`](./CLAUDE.md).

## Démarrage local

PostgreSQL obligatoire (pas de SQLite : la chaîne Alembic utilise des types
Postgres).

```bash
# 1. Postgres local (Docker)
docker run -d --name watt-pg -e POSTGRES_USER=dev -e POSTGRES_PASSWORD=dev \
  -e POSTGRES_DB=smyleplay -p 5432:5432 postgres:16

# 2. Dépendances (requirements.txt est un lockfile, voir plus bas)
pip install -r requirements.txt

# 3. Variables d'environnement : partir de .env.example (à ADAPTER, ne pas
#    le copier tel quel — voir l'avertissement en tête du fichier)
cp .env.example .env

# 4. Migrations (toujours depuis watt-api/)
cd watt-api && alembic upgrade head && cd ..

# 5. Lancer
uvicorn main:app --reload --port 8080
```

## Vérifier ce qui tourne en production

`GET /health` renvoie notamment :

- `commit` : le commit servi ;
- `alembic_head` : la version de base attendue par le code ;
- `alembic_db` : la version réellement appliquée à la base (les deux doivent
  être égales après un déploiement réussi).

## Dépendances (lockfile)

`requirements.in` liste les dépendances voulues ; `requirements.txt` est le
lockfile installé partout (Railway, CI, e2e, local), généré, jamais édité à la
main.

```bash
uv pip compile requirements.in --python-version 3.11 -o requirements.txt
pip install -r requirements.txt && (cd watt-api && pytest -q)
```

Commiter `requirements.in` **et** `requirements.txt` dans le même commit.

## Tests et CI

Workflows dans [`.github/workflows/`](./.github/workflows/) :

- **`ci.yml`** : migrations Alembic sur une base vierge, sonde `/health`, suite
  pytest complète (`watt-api/tests/`), sécurité (`pip-audit`, `bandit`,
  `gitleaks`).
- **`e2e.yml`** : tests Playwright, en configuration « actuelle » et « jour J ».
- **`backup-db.yml`** / **`backup-media.yml`** : sauvegardes quotidiennes de la
  base et des fichiers.
- **`restore-drill.yml`** : chaque semaine, restaure la dernière sauvegarde
  (refusée si elle a plus de 26 h), vérifie les tables et applique les
  migrations du code sur la copie.

En local : `cd watt-api && pytest -q` (Postgres démarré, migrations appliquées).

## Documentation projet

Stratégie, produit et dette : vault `OBSIDIAN/` (local, non versionné).
