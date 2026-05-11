---
title: Reprise pivot écoute — étape 2
type: task
tags: [task, sprint1, pivot, ecoute, alpha, audio, prompt, p1-f4]
updated: 2026-05-05
status: a-faire
---

# Reprise pivot écoute — étape 2 (2026-05-05)

> Suite directe de la session async 2026-05-04 nuit. 15 PRs livrées en prod
> dont les 3 du Sprint 1 (DB tracks + dashboard cover + UI publique
> tracks + gating P1-F4). Bloqueur restant : **les tracks ne sont pas
> écoutables sur /u/smyle**.

---

## ⚠️ Règle d'engagement demain

1. **Tom envoie le payload JSON AVANT que Cowork code quoi que ce soit.**
   Sans le payload réel, on diagnostique à l'aveugle et on perd 1h.

2. **1 chantier = 1 commit = 1 PR.** Règle de fer (cf [[BACKLOG_SHIP]]).

3. **Ordre strict** : bug audio d'abord, jauges après, refonte UI track après ça.

---

## 🚨 Étape 1 — Bug audio /u/smyle — DIAGNOSTIC FAIT (2026-05-04 nuit)

### Confirmation : **Cas A**

Payload `/watt/artists/smyle` reçu de Tom 2026-05-04 23h+ :
```json
"trackCount": 0, "plays": 0, "tracks": [], "adn": null, "prompts": []
```

**Smyle a ZÉRO track et ZÉRO prompt en DB FastAPI.** Tous les uploads
historiques sont dans la table `watt_tracks` (Flask legacy) — perdus
pour /u/slug qui lit FastAPI uniquement.

**Pourquoi le miroir FastAPI Sprint 1 PR2 n'a pas marché lors des
re-uploads de Tom** : hypothèse forte = bug d'auth. Le frontend
dashboard utilise l'auth Flask (cookies de session). Le miroir FastAPI
appelle `apiFetch('/tracks/')` qui exige le JWT en sessionStorage.
Si le JWT FastAPI n'est pas présent, le miroir échoue silencieusement
(`console.warn` mais pas de toast à l'utilisateur).

### Plan fix demain

**Approche recommandée — refactor complet POST track Flask → FastAPI**

Au lieu d'un double-write fragile, on supprime le POST Flask `/api/watt/tracks`
et on fait TOUT côté FastAPI :

1. Frontend `dashboard.js uploadTrack` : POST direct sur FastAPI `/tracks/`
   avec audio_url + r2_key + cover_url + color + title (le full_prompt
   placeholder reste obligatoire pour l'instant).
2. Backend FastAPI `tracks` accepte déjà tous ces champs (Sprint 1 PR2
   a étendu TrackCreate).
3. Si le JWT FastAPI manque côté front → toast d'erreur explicite + ne
   pas créer le track Flask non plus (cohérence : zéro upload si l'auth
   est cassée plutôt qu'orphelin).

**Effort** : 1 PR ~1h Cowork (modifier dashboard.js, retirer fetch
`/api/watt/tracks` Flask, garder uniquement le POST FastAPI).

**Alternative plus prudente** : garder le double-write mais ajouter un
toast d'erreur explicite si le miroir FastAPI rate, pour que Tom sache
qu'il y a un problème d'auth à fixer manuellement (re-login).

**Recommandation Cowork** : refactor complet (option 1). Le code Flask
`watt_tracks` devient legacy et sera décommissionné progressivement.

---

## 🎛 Étape 2 — Spec jauges Suno — VALIDÉE 2026-05-04 nuit

Tom : « je veux une chose sur 100 comme le weirdness mais avec style
influence , tu peux garder le texte libre de style en plus si tu veux »

### Spec finale (à coder demain)

| Champ | Type | Plage | Obligatoire ? |
|---|---|---|---|
| `prompt_platform` | enum | Suno/Udio/Riffusion/Stable Audio/Autre | ✅ |
| `prompt_model_version` | texte | max 50 chars | ⚪ |
| `prompt_weirdness` | numérique | 0-100 (slider) | ✅ |
| `prompt_style_weight` | numérique | 0-100 (slider) NEW | ✅ |
| `prompt_style_influence` | texte | max 500 chars (artistes/genres) | ⚪ optionnel (bonus) |
| `prompt_vocal_gender` | enum | Masculin/Féminin/Instrumental | ✅ |

→ **3 champs distincts** côté style :
- 1 jauge `style_weight` (poids 0-100)
- 1 texte `style_influence` (artistes/genres en bonus optionnel)

### Migration 0026 nécessaire

- Convertir `prompt_weirdness` VARCHAR(50) → INT (0-100, NULL accepté
  pour rétro-compat des anciens prompts)
- Convertir `prompt_style_influence` reste VARCHAR(500) NULLable
  (passe d'obligatoire à optionnel)
- AJOUTER `prompt_style_weight` INT NULL (CHECK 0-100)
- Schemas Pydantic : PromptCreate exige `prompt_style_weight` (au lieu
  de style_influence), `style_influence` devient optionnel
- Frontend dashboard 1a : remplacer textarea `dashPromptStyleInfluence`
  par un slider 0-100 `dashPromptStyleWeight` + garder le textarea
  comme champ optionnel
- Frontend artiste.js : badges affichent `weirdness` et `style_weight`
  côte à côte
- Frontend library.js : idem côté révélation après unlock

**Effort** : 1 PR ~2h.

---

## 🎨 Étape 3 — Refonte UI track façon voix

Tom : « copie la mise en page de publication de voix ».

**Cellule voix actuelle** (qui marche) :
- Sample audio direct (lecteur `<audio controls>` toujours visible)
- Nom + style + badges licence
- Bouton "Débloquer" si visiteur

**Cellule track actuelle** (cassée) :
- Cover image (parfois)
- Audio player conditionnel (caché si streamUrl null)
- Bouton débloquer prompt si linked

**Refonte cible** :
- Identique aux voix : audio TOUJOURS visible (avec fallback "Audio en
  cours d'upload" si null)
- Cover en grand
- Métadonnées en dessous (titre, plateforme, date)
- Bandeau bas : bouton "🔓 Débloquer le prompt" si lié, sinon vide

**Effort** : 1 PR ~1h après bug audio fixé.

---

## 📋 Récap toutes les actions ouvertes

### Critique (alpha publique bloquée tant que pas fait)
- [ ] **Bug audio /u/smyle** (Étape 1) — diagnostic Tom + fix Cowork
- [ ] **Test bout-en-bout achat prompt** complet (jamais validé en prod)
- [ ] **Migration watt_tracks → tracks** (Cas A1) si tracks legacy à conserver

### Important (avant alpha)
- [ ] **Spec jauges Suno** (Étape 2) — Tom valide
- [ ] **Refonte UI track façon voix** (Étape 3)
- [ ] **Pricing v1** ([[Tarification_v1]]) — session dédiée
- [ ] **Catalogue Smyle min viable** (4 sons × 4 univers = 16 sons)
- [ ] **Bug B10 cross-onglet** — ✅ FIX en prod, à valider en condition réelle
- [ ] **Bug B13 ADN disparu** — toujours non investigué

### Sprint 2-3 (après alpha publique)
- [ ] **Sprint 2** : player enchaîné (auto-queue tracks artiste)
- [ ] **Sprint 3 PR1** : UI dashboard création playlists (modèle DB déjà
      en place via migration 0021, cf [[project_playlist_visibility_toggle]])
- [ ] **Sprint 3 PR2** : ajouter/retirer tracks dans une playlist
- [ ] **Sprint 3 PR3** : affichage playlists publiques sur /u/slug
      + univers playlists ouvertes aux users
- [ ] **Stripe Checkout V1** — achat SMYLES réel

---

## 🗂 Bilan session 2026-05-04 nuit

15 PRs livrées en prod, ~3392 lignes ajoutées. Voir [[2026-05-04_pivot_ecoute_session]].

---

## 🔑 Mode opératoire demain

Diagnostic + spec FAITS hier soir. Cowork peut attaquer directement.

### Ordre des PRs demain

**PR A (priorité absolue) — `feat/track-fastapi-only-post`**
- Refactor `dashboard.js uploadTrack` : retire le POST Flask `/api/watt/tracks`,
  fait UNIQUEMENT POST FastAPI `/tracks/`. Toast d'erreur explicite si
  l'auth FastAPI manque (au lieu de fail silencieux).
- Test : Smyle re-publie un track → /u/smyle voit la cellule Sons publiés
  avec audio jouable + cover.

**PR B (après PR A mergée) — `feat/prompt-style-weight-jauge`**
- Migration 0026 : convertir weirdness en INT, ajouter style_weight INT,
  rendre style_influence optionnel.
- UI dashboard : sliders 0-100 pour weirdness et style_weight, textarea
  optionnel pour style_influence.
- UI artiste.js + library.js : badges weirdness + style_weight, texte
  style_influence si rempli.

**PR C (optionnelle, si temps) — `feat/track-card-voice-style`**
- Refonte card track sur /u/slug pour copier la mise en page voix
  (audio toujours visible, cover en grand, métadonnées en dessous).

### Phrases d'ouverture pour Tom

- `attaque PR A` → Cowork code la migration POST track Flask → FastAPI uniquement
- `attaque PR B` → Cowork code la migration 0026 + jauge style_weight
- `attaque les 3` → Cowork enchaîne A puis B puis C en autonomie
- `change la spec` → Tom modifie la spec ci-dessus avant code

---

**Signé** : Tom + Cowork · 2026-05-04 nuit · pré-saison test alpha
