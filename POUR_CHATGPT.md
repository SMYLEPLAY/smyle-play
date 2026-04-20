# Contexte Smyle Play — demande d'avis extérieur

## Ce que j'ai

Je suis Tom, non-développeur. J'ai un projet qui s'appelle **Smyle Play** : un marketplace où des artistes vendent leur "ADN créatif" (signature sonore) et des "prompts Suno". Les fans achètent ces ADN en crédits et débloquent les prompts pour générer leurs propres sons dans l'univers de l'artiste.

Aujourd'hui j'ai **trois choses** qui coexistent sur ma machine, et c'est ça le problème :

### 1. Un site complet déjà fait (Flask + HTML/CSS/JS)
Localisation : `/Users/tommio/Desktop/WORK/Smyleplay/` (racine).

Techno : **Python Flask** comme serveur, **HTML/CSS/JS vanilla** côté navigateur, déployé sur **Railway**, avec **Cloudflare R2** comme CDN audio.

Contenu :
- `index.html` (29 Ko) — page d'accueil avec header logo SVG perles, hub WATT intégré
- `watt.html` — espace artiste public avec classement par écoutes
- `dashboard.html` (25 Ko) — dashboard artiste (upload de sons, édition profil)
- `artiste.html` — page artiste publique
- `style.css` (77 Ko), `watt.css` (46 Ko), `watt-panel.css` (21 Ko) — toute l'identité visuelle (palette néon, fond canvas "réseau électrique" animé doré, palettes par univers)
- `watt.js` (42 Ko), `dashboard.js` (47 Ko), `artiste.js`, `app.js` — logique front
- Dossier `ui/` avec modules : `core/`, `hub/`, `modals/`, `panels/`, `player/`
- Dossier `agents/` : 4 agents Python IA (orchestrator, dna_classifier, playlist_manager, suno_prompt_architect)
- Pipeline Suno automatisé : `suno_router.py`, `scanner.py`, `watcher_pipeline.py`, `upload_to_r2.py`
- Daemons macOS (LaunchAgents) pour l'auto-ingestion
- `tracks.json` (28 Ko) — catalogue de ~74 pistes audio déjà produites
- 4 dossiers d'univers musicaux avec les fichiers .wav : SUNSET LOVER (22), NIGHT CITY (20), HIT MIX (10), JUNGLE OSMOSE (22)

Ce site **est en production** sur Railway. Il marche. J'ai passé 3 jours à le construire.

Modèles SQLAlchemy v1 (Flask) : User, Artist, Track, Collab, PlayCount, SavedMix, Feedback.

### 2. Un nouveau backend FastAPI (séparé)
Localisation : `/Users/tommio/Desktop/WORK/Smyleplay/smyleplay-api/`.

Techno : **FastAPI** + **SQLAlchemy 2.0 async** + **PostgreSQL 15** (Docker), **Alembic** pour les migrations, **Pydantic v2**, tourne en local via Docker Compose sur le port 8000.

Contenu :
- **11 routers REST** : `/auth`, `/users`, `/tracks`, `/credits`, `/transactions`, `/marketplace`, `/unlocks`, `/catalog`, `/me/library`, `/achievements`, `/me/achievements`
- **Modèles** : User, Track, Adn (signature créative de l'artiste), Prompt, OwnedAdn, UnlockedPrompt, Transaction (ledger immutable), Achievement, UserAchievement, DNA (prompt complet d'une Track)
- **1618 tests qui passent** (unitaires + intégration + end-to-end)
- Le concept économique complet : crédits, achat d'ADN, unlock de prompts avec perk -30% si tu possèdes déjà un ADN de l'artiste, transactions auditables, 13 badges d'achievements sur 3 axes

### 3. Un front Next.js démarré (vide)
Localisation : `/Users/tommio/Desktop/WORK/Smyleplay/smyleplay-web/`.

Techno : **Next.js 16** App Router + **TypeScript** + **Tailwind v4** + **shadcn/ui**.

Une session précédente a bootstrappé ce front **sans voir mon site Flask existant**. Elle a créé des pages `/health` et `/feed` branchées au FastAPI. Ce matin j'ai passé une heure avec une autre session à essayer d'y réinjecter mon logo SVG perles, mon fond électrique, ma palette WATT — alors que tout ça existe déjà à l'état fini dans mon site Flask. Le résultat visible sur `localhost:3001` est une page rudimentaire comparée à ce que j'avais déjà.

---

## Ma question

**Pourquoi on ne peut pas juste brancher mon site Flask existant au nouveau backend FastAPI ?**

Concrètement, ma logique de non-dev :

- Côté visuel j'ai déjà tout : design néon, fond canvas électrique, logo SVG, pages artiste + dashboard + hub WATT + modals, player audio persistant, panels.
- Le backend FastAPI a tout le concept v3 (ADN, prompts, crédits, achievements, transactions).
- **Il devrait suffire de modifier les fichiers JavaScript de mon site Flask** pour que leurs appels `fetch('/api/...')` aillent interroger le FastAPI au lieu du Flask — et au fur et à mesure on étend l'interface Flask avec les nouvelles pages pour l'achat d'ADN, la library, le déblocage de prompts.

Au lieu de ça, on est parti sur un Next.js repart-de-zéro qui va me demander des semaines pour retrouver le niveau visuel que j'ai déjà.

---

## Ce que j'aimerais savoir de ChatGPT

1. **Est-ce que mon raisonnement tient la route techniquement ?** Peut-on garder un front HTML/CSS/JS vanilla + Flask (purement routeur/serveur de fichiers statiques) et faire en sorte que tous les appels API partent vers un FastAPI séparé ? Y a-t-il des pièges CORS, d'authentification (cookies vs JWT), ou de sessions à anticiper ?

2. **Quelle est la meilleure architecture de transition** entre :
   - Option A : Flask reste devant (sert les HTML), les JS appellent FastAPI via CORS ou via un proxy Flask
   - Option B : FastAPI sert directement les fichiers statiques HTML/CSS/JS (on vire Flask)
   - Option C : Nginx ou autre devant qui route `/api/*` vers FastAPI et le reste vers les fichiers statiques
   - Option D : Continuer sur Next.js (ce que font les sessions Cowork actuelles — je ne comprends pas pourquoi)

3. **Mes 3 modèles Flask (User, Artist, Track, Collab, PlayCount, SavedMix, Feedback)** — comment les réconcilier avec les modèles FastAPI (User, Track, Adn, Prompt, Transaction, Achievement) ? On migre quoi, on supprime quoi, on fusionne quoi ?

4. **Mon pipeline Suno** (watcher macOS qui scanne un dossier, upload R2, régénère tracks.json, commit+push GitHub → déploie Railway) — comment il s'intègre proprement dans une archi FastAPI ? Faut-il le laisser tourner à part et lui ajouter un appel à FastAPI à la fin, ou le porter à l'intérieur de FastAPI ?

5. **Est-ce une erreur stratégique d'avoir démarré un Next.js** alors que j'avais déjà un site HTML/CSS/JS fonctionnel et stylisé ? Est-ce que remettre Next.js de côté et brancher mon site Flask existant au FastAPI est le bon move pour gagner des semaines ?

---

## Informations utiles

- Je ne suis **pas développeur**. Je comprends les concepts mais je ne peux pas écrire ni lire du code à vitesse de dev.
- Je travaille avec l'outil **Cowork** (Claude Code en interface chat, Claude écrit les fichiers chez moi).
- Mon Mac tourne macOS Sequoia, Docker Desktop installé, Node 25, Python 3.11 via Docker.
- Le backend FastAPI tourne sur http://localhost:8000 via `docker-compose up -d` dans `smyleplay-api/`.
- Le site Flask tournait sur Railway en production, localement il est lancable via `python app.py` à la racine.
- L'objectif court terme : un site qui montre les ADN disponibles, permet de s'inscrire/se connecter, d'acheter un ADN, de débloquer un prompt, de voir sa library. Le tout avec le visuel que j'ai déjà passé 3 jours à construire.

Merci pour ton avis franc. J'ai besoin de trancher avant de perdre plus de temps.
