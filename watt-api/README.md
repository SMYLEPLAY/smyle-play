# Smyle Play API

Backend FastAPI du projet Smyle Play.

## Phase 1 — Fondation

Cette phase pose uniquement la base technique du projet. Aucune logique metier
n'est implementee volontairement. La structure doit rester intacte pour
accueillir les modules critiques des phases suivantes (auth, tracks, DNA,
marketplace, credits).

## Pre-requis

- Python 3.11
- Docker / docker-compose (optionnel pour le dev local)

## Installation locale

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -e .[dev]
```

## Lancer le serveur

```bash
uvicorn app.main:app --reload
```

Endpoints utiles :

- `GET /` -> health check (`{"status": "ok"}`)
- `GET /docs` -> Swagger UI auto-genere

## Structure

```
app/
  auth/        # authentification (Clerk, middleware)
  core/        # utilitaires transverses (errors, logging)
  models/      # modeles SQLAlchemy
  routers/     # endpoints HTTP
  schemas/     # schemas Pydantic (I/O)
  services/    # logique metier
alembic/       # migrations DB
tests/         # tests pytest
```

## Docker

```bash
docker compose up --build
```

## Regles de la Phase 1

- Pas de logique metier
- Pas de DB branchee
- Pas d'auth
- Pas d'endpoint avance
- Ne pas modifier l'arborescence

## Administration — crediter un testeur en Smyles

Trois etapes : se donner le role admin, trouver le compte, crediter. Le role
admin (`users.is_admin`) est distinct du compte vitrine « Smyle »
(`is_official`) : il n'a aucun effet d'affichage.

**1. Se donner le role admin** (sur la machine d'ops, une seule fois) :

```bash
cd watt-api && python tools/make_admin.py tom@example.com
# --revoke pour retirer, --list pour voir les admins
```

**2. Trouver le testeur** (`GET /admin/users`, reserve aux admins). Recherche
partielle et insensible a la casse sur l'email et le pseudo, y compris les
profils NON publies (`/watt/search/artists` ne montre que les profils publies :
c'est voulu, et ca rend un testeur fraichement inscrit invisible). `limit` :
20 par defaut, 100 maximum.

```bash
curl "https://<host>/admin/users?q=marie" -H "Authorization: Bearer <TOKEN_ADMIN>"
```

Chaque resultat porte : `id`, `email`, `artist_name`, `slug`,
`credits_balance`, `created_at`, `profile_public`, `is_banned`. Rien d'autre
(pas de hash de mot de passe, pas d'IP d'inscription).

**3. Crediter le testeur.** Deux formes equivalentes — par email (aucun UUID a
manipuler) ou par identifiant. Le token est celui d'un compte admin, recupere
via `POST /auth/login`.

```bash
# par email (recommande)
curl -X POST "https://<host>/admin/credits" \
  -H "Authorization: Bearer <TOKEN_ADMIN>" \
  -H "Content-Type: application/json" \
  -d '{"email": "marie@example.com", "credits": 500, "reason": "beta_tester"}'

# par identifiant (route historique K-02, inchangee)
curl -X POST "https://<host>/admin/users/<USER_UUID>/credits" \
  -H "Authorization: Bearer <TOKEN_ADMIN>" \
  -H "Content-Type: application/json" \
  -d '{"credits": 500, "reason": "beta_tester"}'
```

`POST /admin/credits` accepte exactement UN de `email` ou `user_id` (les deux,
ou aucun des deux : 422).

### « Je veux crediter 500 Smyles a Marie » — en deux commandes

Depuis la machine d'ops, sans HTTP ni SQL (`tools/grant_credits.py`) :

```bash
cd watt-api
python tools/grant_credits.py --find marie
python tools/grant_credits.py marie@example.com --credits 500 --reason "beta_tester"
```

La premiere commande liste les comptes correspondants (email, pseudo, solde,
date d'inscription, etat, identifiant). La seconde credite et imprime le solde
avant / apres et l'id de la transaction. `--reason` est obligatoire.
`--dry-run` montre la cible sans rien ecrire ; `--by <email admin>` trace
l'auteur au ledger. L'outil refuse un compte banni ou supprime. Attention :
un credit n'est pas idempotent, rejouer la commande credite une seconde fois.

Par HTTP, le meme parcours tient aussi en deux commandes :
`GET /admin/users?q=marie` puis `POST /admin/credits`.

Les Smyles sont credites dans le bucket `promo` (non encaissables, depenses en
premier), toujours via `grant_credits_atomic` et le ledger. `credits` va de 1 a
10000, `reason` est obligatoire (<= 500 car.). Reponses : 201 (ok), 403 (pas
admin), 404 (compte inconnu), 400 (compte suspendu ou supprime), 422 (bornes).

Relire les credits accordes (l'audit est la ligne `transactions`, append-only,
qui porte `granted_by` / `granted_by_email` / `source`) :

```bash
curl "https://<host>/admin/grants?limit=50" -H "Authorization: Bearer <TOKEN_ADMIN>"
```
