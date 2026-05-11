---
title: Note brief projet Smyleplay — à partager
type: session
tags: [session, onboarding, externe, brief]
updated: 2026-04-22
---

# Smyleplay — brief projet

## Projet
- Nom code : **Smyleplay** (nom commercial **WATT PLAY**).
- Pitch : marketplace de contenus musicaux IA — prompts de son, voix, ADN d'artistes IA complets.
- Modèle éco : acheteurs paient en **smyles** (crédits internes en euros). Vendeurs encaissent des smyles sur leurs ventes. Sortie fiat par Stripe (prévu, pas branché).
- Statut : déployé en prod sur Railway, URL active, premiers flows fonctionnels.

## Stack technique
- Backend : FastAPI (Python 3.11+), SQLAlchemy async, Alembic (20 migrations), Postgres.
- Auth : JWT maison (python-jose), email + password.
- Frontend : HTML + JavaScript vanilla, pas de framework. ~5-6 pages statiques.
- Stockage fichiers : Cloudflare R2 (S3-compatible) pour audio et images.
- Déploiement : Railway, auto-deploy sur push `main`.
- Legacy : un `flask_app.py` coexiste pour 2-3 endpoints upload R2 non encore migrés vers FastAPI. À tuer.

## Backend — ce qui marche
- Routers : `auth`, `users`, `catalog`, `tracks`, `playlists`, `marketplace`, `credits`, `transactions`, `unlocks`, `follows`, `achievements`, `search`, `library`, `watt_compat`.
- Modèles DB : `User`, `Track`, `Playlist`, `Prompt`, `PromptMemory`, `UnlockedPrompt`, `Transaction`, `DNA`, `OwnedADN`, `Achievement`, `UserFollow`.
- Flows live : signup minimal (email + password), login JWT, profil artiste unifié (édition `/dashboard`, vitrine `/u/<slug>`), slug auto depuis `artist_name`, bouton unifié Enregistrer+Publier (ADR-001), crédits smyles (stub grant manuel en attendant Stripe), catalog/playlists/tracks en lecture.

## Frontend — ce qui marche
- Topbar partagée (SMYLES / MY MIX / Avatar dropdown).
- Widget solde Smyles auto-injecté, rafraîchi toutes les 60s + cache stale pour sessions expirées.
- Dashboard édition profil avec accordéons (identité, visuels, réseaux, styles).
- Page publique `/u/<slug>` read-only.

## Bugs visibles (non bloquants mais nuisent à l'UX)
- Badge SMYLES dupliqué qui chevauche l'avatar sur `/u/<slug>` et `/library` (fix écrit, pas committé).
- 4 playlists WATT (Hit Mix, Jungle Osmose, Night City, Sunset Lover) n'apparaissent plus sur le profil.
- Profil de l'admin affiché en énorme sur la homepage au lieu d'une grille multi-profils.
- Accordéon "Identité publique" pas intuitif — l'utilisateur ne comprend pas qu'il faut cliquer pour éditer.
- Bloc PLUG WATT séparé du profil alors qu'il devrait être intégré (toggle publier/dépublier direct dans l'accordéon).
- "Titre en dessous du titre" (à localiser).

## Features manquantes pour ship
1. Stripe Checkout réel sur `/credits` (actuellement stub manuel).
2. Upload de sons par le vendeur → apparition sur son profil → vente.
3. Upload d'ADN d'artiste → en vente sur le profil.
4. Upload voix (fichier audio simple, pas de création sur site, on revend).
5. Traduction EN de toute l'interface.
6. Onboarding d'enregistrement "vrai" (vérification email, profil initial guidé).
7. Flow economy bout-à-bout : acheter smyles → acheter contenu → vendeur crédité.

## Dette technique à tuer
- Migrer derniers endpoints Flask vers FastAPI → supprimer `flask_app.py`.
- Supprimer doublons et orphelins : `mon-profil.html`, `artiste-demo.html`, `MOCKUP_profil_artiste.html`, scripts Python de dev à la racine (`scanner.py`, `watcher_pipeline.py`, `upload_to_r2.py` si non utilisés).
- Pas de CI, pas de tests automatisés, pas de monitoring. Risque connu.

## Contexte Tom
- 0 compétence code. Construit avec une IA comme co-pilote.
- Cherche à shipper vite (peur de se faire doubler sur le marché).
- Sprint Nettoyage + Ship 3 semaines validé comme plan courant.

## Pistes d'aide classées par valeur
1. Review d'archi globale (1h-2h) — FastAPI + vanilla JS tient-il pour scaler une marketplace, ou faut-il passer le front sur framework (Next.js / SvelteKit) avant de grossir.
2. Branchement Stripe sur `/credits` — goulot business, bloque la monétisation.
3. CI + tests minimum (pytest endpoints critiques, lint front).
4. Design du flow upload (voix / sons / ADN) — gros fichiers audio, previews, watermarks anti-piratage.
5. Pair-programming ponctuel 30 min sur blocages précis.

## Accès
- Repo GitHub (lecture) : à partager à la demande.
- Prod live : URL Railway à partager à la demande.
