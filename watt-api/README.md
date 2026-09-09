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

## Administration — un testeur a perdu son mot de passe

Dispositif de **beta interne** (ticket B2). Tant que le domaine WATT n'est pas
depose et verifie chez Resend, aucun email transactionnel ne part vers un
testeur : sans `RESEND_API_KEY` le module email est desactive, et avec une cle
mais sans domaine verifie Resend n'accepte que l'adresse du proprietaire du
compte. Le jeton de reinitialisation n'existant qu'en empreinte SHA-256 en
base, il est irrecuperable a posteriori — d'ou cet outil.

Sur la machine d'ops, contre la base pointee par `watt-api/.env` :

```bash
cd watt-api
python tools/reset_link.py testeur@example.com --base-url https://<host>
# --base-url facultatif si PUBLIC_BASE_URL est pose dans l'environnement
```

Le script affiche **une seule fois** un lien `https://<host>/reset#token=...`
a transmettre au testeur par un canal direct. Il produit exactement le meme
jeton que `POST /auth/forgot-password` (meme fonction
`app/services/password_reset.py` : 32 bytes urlsafe, empreinte SHA-256,
60 minutes, usage unique, invalidation du lien precedent). Sortie 1 et aucun
lien si le compte est inconnu, supprime ou banni. Chaque emission ecrit une
ligne WARNING dans le journal applicatif (`app.services.password_reset` +
`watt.tools.reset_link`, avec l'operateur et la machine) : un usage abusif est
visible.

> **Impact.** Un lien emis ici permet de changer le mot de passe d'un compte
> sans rien connaitre de l'ancien : l'outil donne a son porteur le pouvoir de
> prendre la main sur **n'importe quel compte**. Il est donc reserve a Tom,
> sur sa machine, et n'a **aucune route HTTP** — un endpoint de
> reinitialisation administrative serait une porte derobee.

**A retirer** au profit de l'envoi automatique des que le domaine sera
verifie chez Resend : poser `RESEND_API_KEY` + `EMAIL_FROM` sur le domaine
officiel, verifier que `POST /auth/forgot-password` ne logge plus
`lien de reinitialisation NON DELIVRE`, puis rendre l'outil inutile au
quotidien (il reste un secours d'exploitation).

### Quand l'email ne part pas

`POST /auth/forgot-password` repond **toujours** `200 {"ok": true}`, qu'un
compte existe ou non (anti-enumeration) — cette reponse ne change jamais,
meme quand l'envoi echoue. En revanche l'echec n'est plus silencieux : il
ecrit un `ERROR` (`[auth] lien de reinitialisation NON DELIVRE pour
user_id=...`) et, si `SENTRY_DSN` est pose, envoie un evenement Sentry.
Ni le jeton ni le lien ne sont journalises.

## Administration — crediter un testeur en Smyles

Deux etapes. Le role admin (`users.is_admin`) est distinct du compte vitrine
« Smyle » (`is_official`) : il n'a aucun effet d'affichage.

**1. Se donner le role admin** (sur la machine d'ops, une seule fois) :

```bash
cd watt-api && python tools/make_admin.py tom@example.com
# --revoke pour retirer, --list pour voir les admins
```

**2. Crediter un testeur** (`user_id` = UUID du compte cible ; le token est
celui d'un compte admin, recupere via `POST /auth/login`) :

```bash
curl -X POST "https://<host>/admin/users/<USER_UUID>/credits" \
  -H "Authorization: Bearer <TOKEN_ADMIN>" \
  -H "Content-Type: application/json" \
  -d '{"credits": 500, "reason": "beta_tester"}'
```

Les Smyles sont credites dans le bucket `promo` (non encaissables, depenses en
premier). `credits` va de 1 a 10000, `reason` est obligatoire (<= 500 car.).
Reponses : 201 (ok), 403 (pas admin), 404 (compte inconnu), 400 (compte
suspendu ou supprime), 422 (bornes).

Relire les credits accordes (l'audit est la ligne `transactions`, append-only,
qui porte `granted_by` / `granted_by_email` / `source`) :

```bash
curl "https://<host>/admin/grants?limit=50" -H "Authorization: Bearer <TOKEN_ADMIN>"
```
