# SMYLE PLAY

Plateforme de musique générative WATT — backend FastAPI (`watt-api/`), front statique, Postgres, stockage R2.

**Prod** : https://web-production-e30c8c.up.railway.app

## Structure du repo

```
smyle-play/
├── main.py                  # Entry point uvicorn — FastAPI + mount Flask legacy (a2wsgi)
├── flask_app.py             # Flask legacy : statiques + routes pages (suppression en cours, cf. dette « Sortie Flask »)
├── config.py · models.py    # Config & modèles legacy Flask (partent avec flask_app.py)
├── watt-api/                # ✅ SEUL backend actif : API FastAPI + migrations Alembic + tests
│   └── app/                 # routers/ · models/ · services/ · schemas/
├── agents/                  # Agents Python (classifier ADN, playlist, prompt Suno)
├── ui/                      # Assets front (les pages HTML/JS/CSS vivent à la racine)
├── data/                    # Données statiques (config/, seeds/, exports/ gitignoré)
├── scripts/                 # Scripts shell/Python de déploiement & one-shots
├── e2e/ · tests/            # Tests end-to-end & racine (la suite principale est dans watt-api/tests/)
├── graphify-out/            # Cartographie AST du code (gitignoré, rebuild à la demande)
└── OBSIDIAN/                # Vault Obsidian — stratégie / produit / dette (gitignoré)
```

⚠️ `smyleplay-api/` (ancien backend, débranché le 2026-07-20) a été retiré du repo.

## Conventions

Pour les humains : ce `README.md`.
Pour les agents IA (Claude Code / Cowork) : voir [`CLAUDE.md`](./CLAUDE.md).

## Stack

- **Backend** : FastAPI (`watt-api/app`), servi par `uvicorn`. Flask legacy encore monté en fallback via `a2wsgi` pour les statiques et les pages — sa suppression est le chantier P0 en cours.
- **DB** : Postgres (Railway managed), migrations Alembic — chaîne unique dans `watt-api/` (`preDeployCommand` Railway).
- **Storage** : Cloudflare R2 (audio, images, covers).
- **Auth** : JWT (HS256) côté FastAPI.
- **Deploy** : Railway (`railway.toml`), healthcheck `/health`.

## Démarrage local (Postgres-only)

Le dev local utilise Postgres, comme la prod. Pas de mode SQLite : la chaîne Alembic
utilise des types Postgres (UUID, enums) et ne tourne pas sur SQLite.

```bash
# 1. Postgres 16 local (Docker)
docker run -d --name smyle-pg -e POSTGRES_USER=dev -e POSTGRES_PASSWORD=dev \
  -e POSTGRES_DB=smyleplay -p 5432:5432 postgres:16

# 2. Deps
pip install -r requirements.txt

# 3. Variables d'env
cp .env.example .env
# éditer DATABASE_URL=postgresql://dev:dev@localhost:5432/smyleplay, JWT_SECRET, R2_*, etc.

# 4. Migrations (toujours depuis watt-api/)
cd watt-api && alembic upgrade head && cd ..

# 5. Run
uvicorn main:app --reload
```

## Tests & CI

CI GitHub Actions active — 4 workflows dans [`.github/workflows/`](./.github/workflows/), tous bloquants sur PR :

- **`ci.yml`** : migrations Alembic sur Postgres 16 vierge · smoke test `/health` · suite pytest complète (`watt-api/tests/`, ~469 tests, Postgres réel) · sécurité (`pip-audit`, `bandit -ll -ii`, `gitleaks`).
- **`e2e.yml`** : tests end-to-end.
- **`backup-db.yml`** : backup automatisé de la base.
- **`restore-drill.yml`** : drill de restauration.

Lancer la suite en local : `cd watt-api && pytest -q` (Postgres démarré + migrations appliquées).

## Documentation projet

- **Cartographie produit/stratégie** : ouvrir `OBSIDIAN/` dans Obsidian (local, non versionné).
- **Cartographie code** : `graphify-out/graph.html` (rebuild à la demande).
- **Dette technique** : `OBSIDIAN/01_PRODUIT/Dette_technique.md` — chantier actif : **Sortie Flask** (plan P0 a/b/c).
