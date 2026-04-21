# Seeds DB

Scripts d'initialisation des données Postgres.

## Règles
- **Idempotent** : `ON CONFLICT DO NOTHING` ou check d'existence avant insert.
- Écrit en Python + SQLAlchemy async (cohérent avec `smyleplay-api/`).
- Exécutable standalone via `python -m data.seeds.<nom>`.
- **Ne contient jamais de secrets** (password, tokens) — utiliser `secrets.token_urlsafe()`.

## Convention de nommage
- `seed_<domaine>.py` — ex. `seed_artists.py`, `seed_tracks.py`, `seed_univers.py`.
- Utiliser `data/config/*.json` comme source des constantes (univers, styles).

## À créer
- [ ] `seed_univers.py` — lit `data/config/univers.json` → insère en DB si table existe.
- [ ] `seed_smyle_admin.py` — crée compte admin au password configurable (remplace le seed random actuel).

## Lien
- Seeds historiques Alembic : `smyleplay-api/alembic/versions/0022_seed_smyle_official.py`
