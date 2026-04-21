# SMYLE PLAY

Plateforme de musique générative WATT — API FastAPI + Flask legacy, Postgres, stockage R2.

**Prod** : https://web-production-e30c8c.up.railway.app

## Structure du repo

```
Smyleplay/
├── main.py                  # Entry point (uvicorn)
├── flask_app.py             # App Flask legacy
├── config.py · models.py    # Config & modèles globaux
├── smyleplay-api/           # API FastAPI + Alembic
├── agents/                  # Agents Python (classifier, orchestrator, ...)
├── ui/                      # Assets front
│
├── data/                    # Données statiques
│   ├── config/              # univers.json, styles.json
│   ├── seeds/               # scripts d'init DB
│   └── exports/             # dumps temporaires (gitignored)
│
├── scripts/                 # Scripts shell (.sh) de déploiement / setup
├── assets_audio/            # Audio brut par univers (gitignored, ~2 Go)
├── graphify-out/            # Cartographie AST du code (rebuild à la demande)
├── OBSIDIAN/                # Vault Obsidian — stratégie / produit / créatif
└── A_CLASSER/               # Dossier de triage temporaire
```

## Conventions

Pour les humains : ce `README.md`.
Pour les agents IA (Claude Code / Cowork) : voir [`CLAUDE.md`](./CLAUDE.md) — règles projet, routage des docs, navigation graphify + Obsidian.

## Stack

- **Backend** : FastAPI + Flask legacy unifiés via `a2wsgi`, servis par `uvicorn`.
- **DB** : Postgres (Railway managed), migrations Alembic.
- **Storage** : Cloudflare R2 (audio) + assets locaux (`ui/`).
- **Deploy** : Railway (`railway.toml`), preDeployCommand `alembic upgrade head`.

## Démarrage local

```bash
# 1. Deps
pip install -r requirements.txt

# 2. Variables d'env
cp .env.example .env
# éditer DATABASE_URL, JWT_SECRET, R2_*, etc.

# 3. Migrations
cd smyleplay-api && alembic upgrade head && cd ..

# 4. Run
uvicorn main:app --reload
```

## Tests & CI

⚠️ Pas encore de CI. Voir [`OBSIDIAN/01_PRODUIT/Dette_technique.md`](./OBSIDIAN/01_PRODUIT/Dette_technique.md) (dette D3).

## Documentation projet

- **Cartographie produit/stratégie** : ouvrir `OBSIDIAN/` dans Obsidian.
- **Cartographie code** : ouvrir `graphify-out/graph.html` dans un navigateur.
- **Runbooks** : `OBSIDIAN/05_TECH/Runbooks/`.
- **Dette technique** : `OBSIDIAN/01_PRODUIT/Dette_technique.md`.
