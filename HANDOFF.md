# HANDOFF Smyleplay — État global & trajectoire

> Document de transmission · 2026-05-14
> Lecture estimée : 8 minutes

---

## 1. Le projet en 3 lignes

**Smyleplay** est une marketplace musicale où des artistes vendent leurs créations (sons, prompts IA, voix, ADN créatifs) contre une monnaie interne (les Smyles). L'univers créatif s'appelle **WATT**. Le créateur unique est **Tom** (toi).

Stratégie de monétisation : achat one-shot de packs de crédits Smyles (via Stripe), puis utilisation de ces crédits pour débloquer des prompts / ADN / voix / morceaux. Abonnement récurrent prévu en phase 2.

---

## 2. Architecture technique

| Composant | Stack |
|---|---|
| **API moderne** | FastAPI + SQLAlchemy async + asyncpg |
| **Flask legacy** | Monté sur `/` via a2wsgi (WSGIMiddleware) |
| **DB** | PostgreSQL (Railway) |
| **Migrations** | Alembic (chaîne 0009 → 0033) |
| **Storage audio/image** | Cloudflare R2 (boto3) |
| **Frontend** | Vanilla JS pur (pas de framework), Tailwind-like CSS custom |
| **Déploiement** | Railway (nixpacks, auto-deploy sur merge main) |
| **CI** | Pre-deploy command : `alembic upgrade head` |
| **URL prod** | `https://web-production-e30c8c.up.railway.app` |
| **Repo** | `github.com/SMYLEPLAY/smyle-play` (public, OBSIDIAN/ whitelist privée) |

---

## 3. Ce qu'on a accompli (résumé)

### Phase 1 (avril 2026) — fondations

- Tables marketplace (`adns`, `prompts`, `tracks`, `voices_for_sale`, `owned_*`, `transactions`)
- Système crédits atomique avec savepoints (anti-deadlock)
- Auth JWT + Flask legacy bridge
- Upload R2 (sons + cover images)
- Playlists DB
- Likes via wishlist
- Bot Telegram pilote agent

### Phase 2 (mai 2026) — features marketplace

- Profil artiste public `/u/<slug>` avec ADN + prompts + voix + follow
- Marketplace home avec sections "Top sons", "Tous les sons"
- Player principal marketplace + queue auto
- WATT BOARD : interface vendeur, sections pliables (Création / Mes posts)
- Validation Pydantic stricte (extra=forbid, str_strip_whitespace)
- Lock contenu après vente (description ADN, prompt_text figés)

### Sessions récentes (2026-05-12 / 13 / 14)

- ✅ Voice metadata (origin: personal/ai/known_artist, linked_track_id)
- ✅ **Chantier voice preview 30s** (full gated + preview public via pydub/ffmpeg)
- ✅ **ADN rareté 4 tiers auto** (Mythic / Legendary / Limited / Open)
- ✅ Plafond max_supply ADN retiré (INT32 max)
- ✅ Plafond prix ADN retiré (min 30 seul)
- ✅ Équivalence euros côté vendeur dashboard (0.70€/crédit)
- ✅ Soft-delete prompts & tracks
- ✅ Endpoint admin backfill voice previews

**~15 PRs mergées sur 2 jours**, prod stable.

---

## 4. Règles métier validées (LOIS du projet)

> Ces règles sont **non-négociables**. Toute modif doit les respecter.

### Voix
- **Pré-écoute 30s public** (preview_url, clip généré à l'upload via pydub)
- **Full sample gated** — accessible UNIQUEMENT à :
  - L'owner (artist_id = user.id)
  - Acheteur (OwnedVoice existe)
  - Acheteur du track lié (UnlockedPrompt sur voice.linked_track_id)
- **Jamais "bloque DL via UI"** — c'est du wishful thinking, le streaming HTTP ne bloque pas le download sans DRM

### ADN
- **4 tiers de rareté auto** : 1=Mythic, 2-10=Legendary, 11-10000=Limited, 10001+=Open
- Prix : min 30 crédits, pas de plafond ressenti (INT32 max)
- Description figée après 1ère vente
- ai_reference déclaratif (chatgpt/claude/grok/gemini/mistral/perplexity/autre)

### Visibilité produits
- **Avant achat** : streaming OK, download NO, vision details NO
- **Après achat** : tout OK (download, vision, etc.)
- Métadonnées publiques : titre, prix, longueur, IA, rareté, badges

### Économie
- Taux indicatif **0.70€/crédit** (pack_50 médian)
- Équivalence euros affichée UNIQUEMENT côté vendeur (saisie dashboard)
- Côté acheteur : crédits only (préserve l'effet "monnaie de jeu" type V-Bucks)

### Voix séparées du flux musical
- Voix jamais en shuffle / playlist / DNA
- Table dédiée `voices_for_sale`
- Endpoints séparés

### Track = recette Suno (entité unifiée)
- Un track avec prompt vendable EST une recette
- Audio écoutable partout
- Click track → fiche déblocage

### Acheteur garde toujours son unlock
- Soft-delete côté vendeur ≠ révocation côté acheteur
- `OwnedAdn` / `OwnedVoice` / `UnlockedPrompt` survivent à un DELETE du produit

---

## 5. État actuel des features

| Feature | État | Note |
|---|---|---|
| Auth JWT | ✅ Prod | Stable |
| Marketplace home | ✅ Prod | Player principal OK |
| Profil artiste public | ✅ Prod | ADN + prompts + voix + follow |
| Upload son + cover | ✅ Prod | Flask `/api/watt/upload` |
| Upload voix + preview 30s | ✅ Prod | Flask `/api/watt/upload-voice` |
| Mes prompts (création + édition) | ✅ Prod | Lock prompt_text après vente |
| Mon ADN (création + édition + rareté + IA) | ✅ Prod | 4 tiers auto |
| Mes voix (création + édition + métadonnées) | ✅ Prod | preview 30s auto |
| Playlists | ✅ Prod | Public/privé toggle |
| Wishlist (likes) | ✅ Prod | Via table playlists |
| Unlock prompts / ADN / voix | ✅ Prod | Atomic ACID, perks 30% ADN holder |
| Follow utilisateurs | ✅ Prod | Pas de follow-back inline (à venir) |
| Soft-delete prompts/tracks | ✅ Prod | PR #94 |
| Soft-delete ADN/voix | ❌ À faire | Chantier #1 demain |
| DELETE/EDIT côté UI WATT BOARD | ❌ À faire | Chantier #1 demain |
| Cover playlist | ❌ À faire | Chantier #2 demain |
| Compte officiel Smyle | 🟡 Existe séparé | Chantier #3 : fusionner avec slug Tom |
| Trophées avec récompense crédits | ❌ Backend OK, frontend câblage | Chantier #4 |
| Centre notifications catégorisées | ❌ À faire | Chantier #5 |
| Messagerie 1:1 | ❌ À faire | Phase 3 |
| Trade ADN | ❌ À faire | Phase 3 (type TCG Pocket) |
| Stripe Checkout (achat packs) | ❌ À faire | Monétisation, chantier dédié |
| Stripe Connect (payer artistes) | ❌ À faire | Dépend de Checkout |
| Abonnement récurrent | ❌ À faire | Dépend de Connect |
| Trophées complets (Phase 4) | ❌ Partiel | Achievements existent, à étoffer |

---

## 6. Roadmap restante — trajectoire

### 📅 Court terme (cette semaine — 1-2 jours)

1. **CHANTIER #1 — DELETE/EDIT + conservation achats** (½ journée)
   - Soft-delete ADN + voix (mirror PR #94)
   - UI bouton Éditer/Supprimer sur chaque cellule WATT BOARD
   - Audit cascade `Owned*` (survie après soft-delete)

2. **CHANTIER #2 — Cover playlist** (1h30)
   - Migration + upload R2 + UI + fallback gradient

3. **CHANTIER #3 — Compte officiel Smyle = slug Tom** (2h)
   - Flag `is_official` sur user Tom
   - Vitrine accueil pointe vers ton slug
   - Badge ⭐ Officiel sur cards

4. **CHANTIER #4 — Trophées débloquent crédits** (1h30)
   - Câbler achievements → grant_credits_atomic
   - 5-10 règles (1er son = 10 Smyles, 1ère vente ADN = 200, etc.)

### 📅 Semaine suivante (2-3 jours)

5. **CHANTIER #5 — Centre notifications + follow back inline** (1-2 jours)
   - Table notifications, 6 catégories (💸❤️👤✉️🔄⚙️)
   - Cloche unread + dropdown
   - Bouton Follow back inline sur ligne type=follow

6. **Backfill preview voix legacy** (1h, script ops)
   - Déjà fait pour 1 voix, refaire si nouvelles voix legacy apparaissent

### 📅 Monétisation (semaine dédiée, 5-7 jours)

7. **Stripe Checkout** (2-3 jours) — achat packs Smyles one-shot
8. **Stripe Connect** (2 jours) — redistribuer aux artistes vendeurs
9. **Abonnement récurrent** (2 jours) — Découverte gratuit / Pro mensuel / Studio annuel

### 📅 Phase 3 — Social (après compte officiel)

10. **Messagerie 1:1** (2 jours)
11. **Trade ADN** (2-3 jours, type TCG Pocket avec crédits)

### 📅 Phase 4 — Engagement avancé

12. **Système de trophées complet** (challenges quotidiens, classements, badges)
13. **Curation éditoriale** (playlists officielles Smyle, mises en avant)

---

## 7. Dette technique à régler

| Dette | Sévérité | Action |
|---|---|---|
| 5 bugs Sprint 1 jamais retraités | 🟡 Moyenne | Audit + tests E2E SQLite à fixer |
| WATT DEV AGENT déployé mais pas opérationnel | 🟡 Moyenne | Soit réactiver, soit retirer le code |
| Migrations alembic chaîne complexe (3 merges nécessaires) | 🟢 Réglée | Mais surveiller pour les futures PRs (1 head only) |
| Tests E2E sur SQLite, prod sur PG = écart | 🔴 Critique | Idéalement CI avec test deploy |
| Pas de monitoring erreurs (Sentry mentionné mais non activé) | 🟡 Moyenne | Activer Sentry Prod |
| Frontend vanilla JS pur, pas de build = pas de transpilation | 🟢 OK | C'est un choix, fait gagner du temps |

---

## 8. Comment travailler ensemble — méthodologie validée

### Format de réponse attendu
- Analyse rapide
- Problème identifié
- Solution recommandée
- Étapes concrètes

### Posture IA
- Direct, structuré, orienté action
- Contredit Tom si direction sous-optimale (argumenter, ne pas valider à l'aveugle)
- Identifie angles morts, incohérences
- Raisonne business / produit / utilisateur prioritairement
- Privilégie le meilleur ratio effort/résultat

### Règles de fer Smyleplay
- ❌ STOP patches isolés → tout en chantier cohérent
- ❌ Jamais de revert de PR pour description manquante (éditable post-merge)
- ❌ Jamais coller de secrets en chat (recadrer Tom systématiquement)
- ✅ Rappel push systématique (Tom regarde uniquement la prod Railway)
- ✅ URLs : toujours expliciter "Chrome, pas Terminal" avant chaque URL
- ✅ Auditer le backend existant AVANT de coder (grep app/models/, app/routers/)
- ✅ Tom n'a aucune compétence code → guider click-by-click, sans jargon

### Workflow PR
1. Je code dans `/tmp/sp-<feature>/` via script bash autonome
2. Le script clone main fresh, applique patches Python anchor-based, commit + push
3. Tom lance le script dans Terminal
4. Tom merge la PR dans Chrome (GitHub UI)
5. Railway auto-deploy → vérifier vert
6. Tom recharge sa page avec Cmd+Shift+R

### Sandbox Cowork limites
- Le sandbox peut clone + commit + push (sauf 502 occasionnel)
- Si push 502 → fallback base64 + gunzip + bash inline
- Le sandbox ne peut PAS atteindre Railway prod en HTTP direct (proxy 403)

---

## 9. Outils & accès

| Outil | Lien | Usage |
|---|---|---|
| GitHub repo | `github.com/SMYLEPLAY/smyle-play` | Code source, PR, merges |
| Railway dashboard | `railway.app/dashboard` | Deploy, env vars, logs |
| Prod URL | `web-production-e30c8c.up.railway.app` | Site live |
| Cloudflare R2 | console.cloudflare.com | Storage audio + images |
| Stripe (à venir) | dashboard.stripe.com | Monétisation |

### Variables d'env critiques sur Railway
- `DATABASE_URL` (Postgres Railway)
- `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `CLOUD_AUDIO_BASE_URL`
- `JWT_SECRET`
- `ADMIN_BACKFILL_TOKEN` (configuré 2026-05-14 pour backfill voix)

---

## 10. Notes critiques pour la reprise

### Mémoires persistantes
Tout ce qui est validé en termes de règles métier, méthodes, décisions est stocké dans `MEMORY.md` à charger automatiquement chaque nouvelle session. **À ne jamais oublier** :
- `project_voice_strict_no_dl_rule.md` — règle voix stricte
- `project_visibility_rule_revised.md` — streaming OK, DL/details NO
- `project_chantier_messagerie_notifs.md` — spec centre notifs
- `feedback_no_isolated_patches.md` — méthode chantiers cohérents
- `project_vision_phases.md` — phases 1-4 vision

### Pièges connus (déjà rencontrés)
1. **Alembic revision_id ≤ 32 chars** — sinon crash `value too long for character varying(32)`
2. **Multiple heads alembic** — toute PR avec migration doit checker la chaîne avant push
3. **PLAYLISTS lexical scope** — `let PLAYLISTS` n'est PAS sur `window.PLAYLISTS`
4. **Cache Railway nixpacks** — peut se coincer → bump fichier pour forcer rebuild
5. **ffmpeg vs ffmpeg-headless** — nixpacks auto-installe headless via pydub, ne pas demander ffmpeg explicitement
6. **Sandbox ne peut pas atteindre Railway prod** — pour tester, demander à Tom de vérifier

### Conventions repo
- `data/config/` : constantes statiques JSON (univers, styles WATT)
- `data/seeds/` : scripts Python init DB (idempotents)
- `OBSIDIAN/` : vault docs stratégiques (whitelist Git, créatif WATT)
- `assets_audio/` : audio brut par univers, gitignored, R2 hébergé
- `.claude/skills/` : skills antigravity installées (32 skills)

---

## 11. Ordre d'attaque demain — résumé exécutable

```
🌅 MATIN   (4h)   → CHANTIER #1 DELETE/EDIT + conservation achats
🌇 13h-15h (2h)   → CHANTIER #3 Compte officiel Smyle = slug Tom
🌇 15h-17h (2h)   → CHANTIER #2 Cover playlist + CHANTIER #4 Trophées crédits
🌙 SOIR    (opt)  → Démarrer #5 Notifications si énergie
```

---

**Fin du handoff.** Bonne suite.
