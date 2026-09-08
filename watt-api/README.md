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

## Administration — tableau de bord de la beta

Un seul appel repond aux questions que l'on se pose vraiment pendant la beta.
**Tous les chiffres d'activite viennent du registre des transactions et des
tables metier, jamais de la telemetrie** : une vente est un fait comptable,
elle ne depend ni du consentement cookies, ni d'un bloqueur, ni de JavaScript.

```bash
curl "https://<host>/admin/beta?days=7&limit=20" \
  -H "Authorization: Bearer <TOKEN_ADMIN>"
```

`days` (1..365, defaut 7) est la fenetre glissante des compteurs « sur la
fenetre » ; `limit` (1..100, defaut 20) borne la liste des ventes et des
createurs. Reponses : 200, 403 (pas admin), 422 (bornes). Lecture seule.

### Ce que veut dire chaque chiffre

**`comptes`** — source : table `users`.

| Champ | Sens |
|---|---|
| `total` | Nombre de comptes existants, tous etats confondus. |
| `nouveaux_sur_la_fenetre` | Comptes crees pendant les `days` derniers jours. |
| `ont_publie` | Comptes ayant au moins une publication visible (prompt, ADN, ADN visuel ou voix publie, ou morceau depose). C'est le vrai taux d'activation createur. |
| `ont_achete_au_moins_une_fois` | Comptes apparaissant comme acheteur d'au moins une transaction `unlock`/`resale` terminee. |
| `ont_vendu_au_moins_une_fois` | Idem cote vendeur : combien de createurs ont vraiment encaisse quelque chose. |
| `bannis`, `supprimes_rgpd` | Comptes suspendus, et comptes anonymises par la purge RGPD (comptes, jamais l'e-mail). |
| `pct_qui_publient`, `pct_qui_achetent` | Part du total. `null` si aucun compte — pas `0`, qui se lirait comme un echec mesure. |

**`publications`** — `total` et `sur_la_fenetre` : combien d'objets sont
publies, et combien l'ont ete recemment. `perimetre` rappelle ce qui est compte.

**`ventes`** — source : `transactions` (`unlock` = vente primaire,
`resale` = revente entre membres), statut `completed` uniquement.

| Champ | Sens |
|---|---|
| `total`, `smyles_echanges` | Nombre de ventes et volume total en Smyles depuis le debut. |
| `part_reversee_aux_createurs` | Ce que les vendeurs ont reellement touche (`montant - commission`). |
| `commission_plateforme` | La part prise par la plateforme — elle sort de la circulation (voir `masse_smyles`). |
| `sur_la_fenetre` | Les deux memes chiffres, restreints aux `days` derniers jours. |
| `panier_moyen_smyles` | Prix moyen d'une vente. `null` s'il n'y a eu aucune vente. |
| `dernieres` | Les `limit` dernieres ventes : `date`, `acheteur`, `vendeur` (pseudos), `objet_type`, `objet_titre`, `montant_smyles`, `part_createur`, `commission`, `nature`. `vendeur` peut etre `null` si le compte a ete supprime. |

**`masse_smyles`** — la monnaie interne, et si elle reconcilie.

| Champ | Sens |
|---|---|
| `crees.bonus_bienvenue_et_recompenses` | Smyles emis par les bonus (bienvenue, streak, trophees, parrainage). |
| `crees.credits_administratifs` | Smyles emis a la main via `POST /admin/users/{id}/credits`. |
| `crees.achats_de_packs` | Smyles achetes en euros (0 tant que Stripe n'est pas branche). |
| `crees.gains_credites_directement`, `crees.remboursements` | Types `earning` / `refund` du ledger. |
| `depenses_par_les_acheteurs` | Total debite aux acheteurs sur les ventes. |
| `redistribues_aux_createurs` | Ce que les vendeurs ont recu en retour : ces Smyles ont change de poche, ils n'ont pas disparu. |
| `detruits_en_commission` | Les seuls Smyles reellement detruits par une vente. |
| `en_circulation` | Solde total detenu par les comptes, ventile par origine (`achetes` non encaissables, `gagnes` encaissables = dette, `promo` offerts, `dont_gagnes_geles` sous sequestre). |
| `reconciliation.attendu` | `crees.total - detruits_en_commission` : ce que la circulation devrait valoir. |
| `reconciliation.constate` | Ce qu'elle vaut vraiment (somme des soldes). |
| `reconciliation.ecart` | `constate - attendu`. **Doit valoir 0.** Un ecart non nul signale des Smyles bouges hors ledger (SQL manuel, chemin de code qui oublie une transaction). |
| `reconciliation.comptes_aux_sous_soldes_incoherents` | Canari A1.2 : comptes ou `achetes + gagnes + promo != credits_balance`. Doit rester a 0. |

Ecart connu sur une base fraiche : **+10**. Le compte vitrine officiel
`smyle@smyleplay.com`, insere par la migration `0022_seed_smyle_official`,
a recu 10 Smyles via l'ancien `server_default` de `users.credits_balance`,
sans ligne au ledger (la migration `0066` a depuis supprime ce defaut, mais
la ligne existe deja). C'est exactement ce que ce chiffre doit rendre visible :
tant qu'il vaut 10 et pas davantage, rien de nouveau ne fuit hors du ledger.

**`createurs`** — les `limit` comptes les plus actifs : `pseudo`,
`publications`, `ventes_realisees`, `smyles_gagnes` (cumul exact
`credits_earned_total`, tous chemins de vente confondus) et `palier`
(commission appliquee : standard / premium / mythique).

**`conversion_fiche_vers_deblocage`** — « parmi ceux qui ont vu une fiche,
combien ont debloque ? ». Aujourd'hui `mesurable: false` et `taux_pct: null` :
la vue d'une fiche n'a **aucune trace en base**, et l'evenement telemetrie
`product_view` n'est emis par aucune page du front. Le champ `pourquoi` le dit
dans la reponse, et `pour_l_obtenir` indique quoi brancher. Le jour ou la vue
sera emise, le taux apparaitra avec son `avertissement` : numerateur comptable
et denominateur telemetrique, donc **plafond** et non conversion reelle.

### `/admin/funnel` : ce qui a change

`GET /admin/funnel?days=30` existe toujours (page `analytics.html`) mais ne
ment plus. Les marches « Inscrits » et « 1er achat » comptaient les evenements
telemetrie `signup` et `purchase`, **que le front n'emet nulle part** : elles
valaient 0 quoi qu'il se passe sur le site. Elles sont desormais lues dans
`users` et `transactions` et portent `source: "comptable"`. « Visiteurs » et
« Reviennent » restent telemetriques (`source: "telemetrie"`) : une visite
anonyme n'a pas de trace en base — ils sous-comptent, car la telemetrie est
soumise au consentement et a Do-Not-Track. Le champ `avertissements` de la
reponse l'explique, y compris le fait que les taux melangeant les deux
(Visite -> Inscription) divisent des comptes par des sessions.

Aucun evenement `signup` / `purchase` n'est emis cote serveur : les sources
comptables repondent deja a la question, exactement et sans consentement.
Dupliquer le fait dans `analytics_events` produirait deux chiffres destines a
diverger, pour zero information nouvelle.
