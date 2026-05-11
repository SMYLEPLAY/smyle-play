# Mapping Flask → FastAPI — état d'audit (2026-04-18)

Ce document liste **tous** les appels `fetch()` du site Flask, la route FastAPI correspondante (si elle existe), et ce qu'il faut faire pour chaque cas.

> **MAJ 2026-04-18 (fin de session)** — La stratégie finale retenue est un
> **shim FastAPI `/watt/*`** qui renvoie la forme Flask exacte (pas de
> découpage schéma côté JS). Les lignes ⚠️ SCHÉMA / ❌ MANQUANT ci-dessous
> sont désormais **résolues** pour tous les reads + DELETE + POST plays.
> Voir `PLAN_EXTERNE.md` pour la suite (writes, auth JWT, Railway).

---

## 1. Vue d'ensemble

- **Appels `fetch()` réels dans le front** : 21 (hors bruit plugin Obsidian)
- **Routes FastAPI disponibles** : 30+ réparties sur 11 routers
- **Auth Flask actuel** : session cookie (`session['user_id']`)
- **Auth FastAPI** : JWT bearer (header `Authorization: Bearer <token>`)
- **Verdict** : majoritairement faisable sans toucher au FastAPI, mais ~7 endpoints Flask n'ont **pas d'équivalent** côté FastAPI — il faudra soit les porter, soit les garder temporairement sur Flask.

---

## 2. Table de correspondance complète

Légende :
- ✅ **DIRECT** : mapping 1-1, juste changer l'URL et adapter le parsing
- 🔁 **AUTH** : dépend du choix d'auth (voir §4)
- ⚠️ **SCHÉMA** : le format de réponse FastAPI diffère de Flask, adaptation JS nécessaire
- ❌ **MANQUANT** : pas d'équivalent FastAPI → à ajouter côté API ou garder côté Flask
- 🗑️ **OBSOLÈTE** : concept v1 abandonné (collabs, feedback)

| # | Fichier JS | Ligne | Appel Flask actuel | Équivalent FastAPI | Statut |
|---|------------|-------|--------------------|--------------------|--------|
| 1 | `watt.js` | 688 | `POST /api/watt/upload` (multipart) | `POST /tracks` + `POST /artist/me/prompts` | ⚠️ SCHÉMA (découpage nécessaire) |
| 2 | `watt.js` | 932 | `GET /api/artists` | `GET /artists` | ✅ DIRECT + ⚠️ SCHÉMA |
| 3 | `watt.js` | 1033 | `GET /api/tracks/recent` | `GET /tracks/` (pas de filtre "recent") | ⚠️ SCHÉMA (ordre/limit à ajouter) |
| 4 | `dashboard.js` | 647 | `DELETE /api/watt/tracks/{id}` | ❌ pas d'endpoint DELETE | ❌ MANQUANT |
| 5 | `dashboard.js` | 812 | `POST /api/watt/upload` | `POST /tracks` | ⚠️ SCHÉMA |
| 6 | `dashboard.js` | 828 | `POST /api/watt/tracks` | `POST /tracks` | ⚠️ SCHÉMA |
| 7 | `dashboard.js` | 924 | `GET/POST /api/watt/profile` | `GET /users/me` / `PATCH /artist/me/brand-color` | ⚠️ SCHÉMA (fusion champs artiste + user) |
| 8 | `ui/hub/community.js` | 32 | `GET /tracks.json` | `GET /tracks/` | ✅ DIRECT |
| 9 | `ui/hub/community.js` | 39 | `GET /api/tracks` | `GET /tracks/` | ✅ DIRECT |
| 10 | `ui/hub/community.js` | 132 | `GET /api/artists` | `GET /artists` | ✅ DIRECT |
| 11 | `artiste.js` | 53 | `GET /api/artists/{slug}` | `GET /artists/{artist_id}` | ⚠️ SCHÉMA (slug → id) |
| 12 | `artiste.js` | 162 | `GET /api/auth/me` (cookie session) | `GET /users/me` (JWT) | 🔁 AUTH |
| 13 | `artiste.js` | 360 | `POST /api/watt/plays/{id}` | ❌ pas d'endpoint | ❌ MANQUANT |
| 14 | `artiste.js` | 437 | `POST /api/collabs` | ❌ concept v1 | 🗑️ OBSOLÈTE |
| 15 | `ui/panels/agent.js` | 124 | `GET /api/artists` | `GET /artists` | ✅ DIRECT |
| 16 | `ui/panels/agent.js` | 186 | `GET /api/tracks/recent` | `GET /tracks/` | ⚠️ SCHÉMA |
| 17 | `ui/panels/agent.js` | 232 | `GET /api/collabs/inbox` | ❌ concept v1 | 🗑️ OBSOLÈTE |
| 18 | `ui/panels/agent.js` | 350 | `POST /api/agents/process-track` | ❌ pas d'endpoint | ❌ MANQUANT (à porter) |
| 19 | `ui/panels/watt-panel.js` | 599 | `GET /api/watt/stats` | ❌ pas d'endpoint | ❌ MANQUANT |
| 20 | `ui/panels/watt-panel.js` | 865 | `GET /api/watt/me/stats` | `GET /me/achievements` (proche) | ⚠️ SCHÉMA |
| 21 | *app.py* | 116/136 | `POST /api/auth/register/login/logout` | `POST /auth/register` / `POST /auth/login` | 🔁 AUTH |

---

## 3. Endpoints FastAPI sans équivalent Flask (fonctionnalités v3 nouvelles)

Ces endpoints existent côté FastAPI mais ne sont pas encore appelés par le front. Il faudra leur construire une UI plus tard (dans des nouvelles pages/modals greffées sur le site Flask) :

- `GET /credits/packs` — packs de crédits à l'achat
- `POST /credits/grant` — créditer un user
- `GET /users/me/transactions` — ledger immutable
- `GET/POST/PATCH /artist/me/adn` — ADN marketplace de l'artiste
- `GET/POST/GET/PATCH /artist/me/prompts` — prompts de l'artiste
- `PATCH /artist/me/brand-color` — couleur de marque
- `GET /prompts` / `GET /prompts/{id}` — catalogue public
- `GET /adns` / `GET /adns/{id}` — catalogue ADN public
- `POST /unlocks` — déblocage d'un prompt (perk -30% si tu possèdes un ADN)
- `GET /me/library/prompts` / `GET /me/library/adns` — bibliothèque user
- `GET /achievements` / `GET /me/achievements` — 13 badges

**Liste de nouvelles pages/panels à créer progressivement** :
1. Page marketplace ADN (liste + fiche ADN)
2. Page "acheter des crédits"
3. Panel "Ma library" (ADN possédés + prompts débloqués)
4. Page "Mes achievements"
5. Dashboard artiste : onglets "Mon ADN" + "Mes prompts"

---

## 4. Auth — le point le plus délicat

**Flask actuel (cookie-session)** :
- `POST /api/auth/login` → `session['user_id'] = user.id` (cookie envoyé automatiquement)
- `GET /api/auth/me` → lit `session['user_id']`
- Pas de token côté JS

**FastAPI actuel (JWT bearer)** :
- `POST /auth/login` → retourne `{access_token, token_type}`
- Routes protégées → exigent `Authorization: Bearer <token>`
- Pas de session cookie

**Conséquence** : on ne peut **pas** faire cohabiter les deux auth sur les mêmes cookies. Deux options :

### Option A — Passer tout en JWT (recommandé)
- Au login, le JS stocke `access_token` dans `localStorage`
- Un helper `authFetch(url, opts)` ajoute automatiquement le header Bearer
- Le Flask devient purement serveur de HTML statique (plus d'auth côté Flask)

### Option B — Garder Flask pour l'auth et proxyer le reste
- Flask garde sa session cookie
- Les autres appels passent par un proxy Flask `/api/*` qui forward vers FastAPI en ajoutant un JWT côté serveur
- Plus complexe à maintenir, pas recommandé

**Ma recommandation** : Option A. On perd la "session magique" Flask mais on gagne une archi propre.

---

## 5. Endpoints à porter dans FastAPI (priorité)

Ces 4 endpoints Flask n'ont pas d'équivalent FastAPI et sont utilisés par le front :

| Endpoint Flask | Usage | Priorité | Porting suggéré |
|----------------|-------|----------|-----------------|
| `POST /api/watt/plays/{track_id}` | Incrément compteur plays | P1 | À ajouter dans `routers/tracks.py` comme `POST /tracks/{id}/plays` |
| `DELETE /api/watt/tracks/{id}` | Suppression track artiste | P1 | À ajouter dans `routers/tracks.py` comme `DELETE /tracks/{id}` |
| `GET /api/watt/stats` | Stats globales WATT (home) | P2 | Nouveau endpoint `GET /stats/global` |
| `POST /api/agents/process-track` | Lance les 4 agents IA | P3 | Nouveau endpoint `POST /agents/process-track` ou via pipeline CLI |

**Obsolètes (à supprimer)** :
- `/api/collabs`, `/api/collabs/inbox`, `/api/collabs/unread` → concept v1 non repris en v3
- `/api/feedback` → remplacé par les achievements

---

## 6. Pipeline Suno — où il s'insère

Aujourd'hui :
```
WAV local → watcher_pipeline.py → scanner.py → upload_to_r2.py
         → tracks.json commit+push GitHub → Railway re-déploie
```

Après refactor :
```
WAV local → watcher_pipeline.py → scanner.py → upload_to_r2.py
         → POST http://localhost:8000/tracks (avec JWT admin)
         → FastAPI persiste en Postgres + renvoie l'URL R2
```

Le `tracks.json` disparaît de la boucle. Le front lit `GET /tracks/` directement depuis FastAPI.

---

## 7. Plan d'exécution proposé (commits séparés)

Chaque étape = un commit, testable indépendamment, réversible.

1. **Migration data** : script Python qui lit `tracks.json` + les SQLite Flask, écrit dans Postgres FastAPI. *→ zéro risque pour le site actuel*
2. **CORS côté FastAPI** : ajouter le middleware avec `allow_origins=["http://localhost:5000", "http://localhost:3000"]`. *→ zéro risque*
3. **Helper `apiFetch()`** dans `ui/core/api.js` : centralise `API_BASE`, gère le token JWT. *→ zéro risque (fichier nouveau, pas utilisé tant qu'on ne migre pas un appel)*
4. **Mapping READ-ONLY** (les 6 ✅ DIRECT + les 4 ⚠️ SCHÉMA simples) : tracks, artists listing, community hub. *→ risque faible*
5. **Auth JWT** : login, register, me. Ici on bascule en mode JWT. *→ risque moyen (toucher à l'auth)*
6. **Endpoints WRITE** : profil artiste (PATCH), upload track. *→ risque moyen*
7. **Porter les 4 endpoints manquants** dans FastAPI : plays, delete track, stats, process-track. *→ risque faible (ajout côté API, le front ne change pas)*
8. **Brancher pipeline Suno** sur `POST /tracks` au lieu de `tracks.json`. *→ risque faible*
9. **Désactiver routes Flask `/api/*`** une par une, garder seulement les routes HTML. *→ cleanup*
10. **Supprimer `smyleplay-web/`** (Next.js abandonné). *→ cleanup*

---

## 8. Ce que je propose maintenant

Si tu valides ce mapping, je commence par l'étape 1 (script de migration data, zéro risque), puis l'étape 2 (CORS), puis l'étape 3 (helper). À chaque étape je te livre le commit et tu peux tester que ton site continue de marcher.

**Je ne touche à rien tant que tu n'as pas dit OK.**
