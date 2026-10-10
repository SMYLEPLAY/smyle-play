# Test de charge WATT (k6)

Le script `watt.js` simule trois parcours en même temps :

| Parcours  | Ce qu'il fait                                                        |
|-----------|----------------------------------------------------------------------|
| accueil   | visiteur anonyme : page d'accueil, catalogue, artistes, sons récents |
| connexion | connexion d'un compte existant, puis lecture du profil               |
| achat     | achat d'une recette à 3 Smyles, puis lecture de la bibliothèque      |

Au démarrage, il crée lui-même ses comptes de test : un vendeur avec 4 recettes et 40 acheteurs, qui ont chacun 10 Smyles de bienvenue. Les réponses « solde insuffisant » (402) et « déjà acheté » (409) sont normales.

## Règle n° 1 : jamais contre la production

Le test crée de vrais comptes et de vrais achats. Le script refuse toute adresse autre que `localhost` / `127.0.0.1`. Pour viser une **pré-production** (copie du site avec une base jetable), il faut ajouter `K6_CIBLE_AUTORISEE=oui`.

## Préparer le serveur testé

- `REQUIRE_EMAIL_VERIFIED=false` et `FEATURE_SELL_GATE=false`, sinon les comptes de test ne peuvent ni se connecter ni vendre.
- Relever les limites anti-abus : le test part d'une seule adresse IP et serait bloqué (429) au bout de quelques connexions. Par exemple :
  `RATE_LIMIT_LOGIN=10000/minute RATE_LIMIT_REGISTER=10000/minute RATE_LIMIT_PURCHASE=10000/minute`
  (en local, `ENVIRONMENT=test` les désactive toutes).
- Lancer le serveur comme en prod : `uvicorn main:app --workers 2`.

## Lancer

```bash
# 1. essai rapide (20 s, 4 utilisateurs) — pour vérifier que tout marche
PROFIL=fumee K6_NO_USAGE_REPORT=true k6 run ops/k6/watt.js

# 2. charge normale (~4 min, jusqu'à 80 utilisateurs simultanés)
K6_NO_USAGE_REPORT=true k6 run ops/k6/watt.js

# 3. pic (~4 min, jusqu'à 260 utilisateurs simultanés)
PROFIL=pic K6_NO_USAGE_REPORT=true k6 run ops/k6/watt.js

# autre adresse (pré-production uniquement)
BASE_URL=https://preprod.exemple K6_CIBLE_AUTORISEE=oui k6 run ops/k6/watt.js
```

Variables : `BASE_URL` (par défaut `http://localhost:8000`), `PROFIL` (`fumee`, `charge` ou `pic`), `NB_ACHETEURS` (par défaut 40).

## Lire le résultat

Le test est **réussi** si, en fin de rapport, toutes les lignes marquées ✓ sont vertes :

- `erreurs_techniques` < 1 % (erreurs 5xx, délais dépassés, connexions refusées) ;
- 95 % des requêtes de l'accueil en moins de 0,8 s ;
- 95 % des requêtes de connexion et d'achat en moins de 1,5 s (le contrôle du mot de passe est volontairement lent).

Une ligne ✗ rouge indique ce qui ne tient pas. Le parcours concerné (`scenario:accueil`, etc.) est indiqué sur la ligne.
