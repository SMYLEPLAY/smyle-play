---
title: Session 2026-05-04 — pivot écoute Sprint 1 + bugs prompt
type: session
tags: [session, recap, sprint1, pivot, ecoute, alpha, voix, prompt, p1-f4]
updated: 2026-05-04
---

# Session 2026-05-04 nuit — pivot écoute Sprint 1

> Session async marathon. Démarrée pour finir l'écosystème vente voix
> (suite du 2026-04-29), pivotée vers le pivot écoute (le track devient
> le produit visible, le prompt est le bonus premium).

---

## ✅ Livré en prod (15 PRs mergées)

| # | PR | Lignes |
|---|---|---|
| 17 | fix dashboard B11+B12 (toast + ADN guard) | +62 |
| 18 | feat backend voix complet (P1-F9) | +1043 |
| 19 | feat R2 delete + plays atomic (P1-F5+F8) | +198 |
| 20 | feat frontend dashboard voix | +357 |
| 21 | feat cellule profil voix /u/slug | +285 |
| 22 | feat onglet library voix unlockées | +130 |
| 23 | feat enriched payload artist (voix) | +152 |
| 24 | fix B10 token JWT cross-onglet | +38 |
| 25 | fix pipeline publication communauté (P1-F2) | +86 |
| 26 | feat pré-écoute voix avant achat | +51 |
| 27 | feat fiche prompt enrichie 5 réglages (P1-F4) | +366 |
| 28 | fix lyrics manquant dans PromptCreate | +60 |
| 29 | feat Sprint 1 PR1 — DB cover_url + prompt_id sur tracks | +206 |
| 30 | feat Sprint 1 PR2 — dashboard upload cover R2 + lien prompt | +114 |
| 31 | feat Sprint 1 PR3 — UI publique track + gating weirdness/influence | +244 |

**Total : ~3392 lignes** en 15 PRs sur une seule session.

---

## 🎯 Acquis structurants

### Écosystème vente voix (PRs #18-23, 26)
- Backend complet : table `voices_for_sale` + `owned_voices`, endpoints CRUD,
  unlock atomique calqué sur ADN/Prompt.
- Frontend complet : dashboard 1c câblé, cellule profil public /u/slug,
  onglet library voix unlockées.
- Pré-écoute publique (sample_url exposé dans VoicePublicRead) — résout
  le bug "achat à l'aveugle".
- Payload enrichi avec artist info (1 SELECT IN, pas de N+1).
- **Validé en prod** : achat voix bout-en-bout réussi (TL achète sur Smyle).

### Bug B10 cross-onglet fixé (PR #24)
- Token JWT bascule de localStorage vers sessionStorage par onglet.
- Migration douce pour les sessions existantes.
- Multi-comptes Chrome simultanés possibles (vendeur + acheteur).

### Pipeline publication communauté (PR #25)
- `injectCommunityPlaylist` lit maintenant `/watt/tracks-recent` au lieu
  de localStorage (qui ne contenait que les tracks de l'user courant).
- Filtre `profile_public=TRUE` côté backend (cohérent avec /watt/artists).

### Fiche prompt enrichie P1-F4 (PRs #27, 28)
- 5 champs réglages génération sur prompts (4 obligatoires + 1 optionnel) :
  platform, model_version, weirdness, style_influence, vocal_gender.
- Migration 0024 + bug fix lyrics dans PromptCreate (PR #28).
- Service create_prompt persiste tous les champs (avant : payload validé
  Pydantic mais ignoré silencieusement par le service — bug latent).

### Sprint 1 pivot écoute (PRs #29, 30, 31)
- Migration 0025 : `cover_url` + `prompt_id` FK sur tracks.
- Dashboard 1a : upload cover R2 + miroir FastAPI tracks + lien prompt
  via PATCH /tracks/{id}.
- /u/slug : refonte renderTracks avec cover + audio + bouton "Débloquer
  le prompt" si lié.
- Gating P1-F4 : `weirdness` et `style_influence` retirés du payload
  public artist, révélés uniquement après unlock dans /library.

---

## 🚨 Bloqueur restant identifié en fin de session

**Bug audio /u/smyle** : Tom ne peut PAS écouter ses morceaux en stream sur
son profil. Cause probable :

- **Hypothèse A (90% sûr)** : les tracks de Smyle sont dans `watt_tracks`
  (Flask legacy) mais pas dans `tracks` (FastAPI). Le profil public lit
  FastAPI → cellule "Sons publiés" cachée car payload `tracks: []`.
- **Hypothèse B** : tracks présents mais `audio_url` null (upload R2
  silencieusement raté).

Pas diagnostiqué côté payload réel — Cowork n'a pas accès à la prod
Railway depuis sa sandbox (proxy 403). Tom doit copier le JSON de
`/watt/artists/smyle` demain pour qu'on tranche.

→ **Plan de reprise** : voir [[2026-05-05_reprise_pivot_ecoute]].

---

## 🎛 Spec à valider demain

### Jauges Suno (révision spec P1-F4)

Tom note que sur Suno il y a 3 réglages distincts, pas 2 :
1. **Weirdness** : slider 0-100 (codé en texte 50 chars actuellement)
2. **Style Reference Weight** : slider 0-100 (PAS codé)
3. **Style description** : texte libre artistes/genres (codé comme
   `prompt_style_influence` actuellement)

À trancher avec Tom :
- `3 champs` → ajouter `prompt_style_weight` numérique en plus
- `juste jauge` → convertir `style_influence` en numérique et supprimer
  le texte artistes/genres

Migration 0026 prévue. Voir [[2026-05-05_reprise_pivot_ecoute]] Étape 2.

---

## 📝 Règles persistantes ajoutées en mémoire cette session

- [[project_playlist_visibility_toggle]] — toute UI playlist doit exposer
  un toggle public/privé explicite avant Enregistrer.
- [[project_prompt_visibility_rule]] mise à jour avec exception voix
  (sample_url public) et confirmation gating weirdness/style_influence
  (révélés uniquement après unlock dans /library).

---

## 🛠 Tooling appris cette session

- **Heredoc zsh** est piégeux avec `(`, `)`, `'`. Solution : tous les
  scripts de push utilisent `cat > /tmp/_smyle_msg.txt <<'COMMIT_MSG'`
  pour bypass total.
- **Stash + checkout main + stash pop** est fragile quand le stash
  contient des fichiers conflictuels (`.obsidian/workspace.json`,
  scripts untracked). Solution alternative : `git checkout stash@{0} --
  <fichiers>` pour récupération chirurgicale.
- **Sandbox Cowork = pas d'accès Railway prod** (proxy 403). Tom doit
  fournir les payloads JSON via copier-coller depuis Chrome.

---

## 🚦 Pour reprendre demain

Tom dit l'un de :
- `paste le JSON tracks` → Cowork diagnostique le bug audio (Étape 1)
- `3 champs` ou `juste jauge` → Cowork code la migration 0026 (Étape 2)
- `attaque la refonte UI track` → Cowork copie la mise en page voix sur
  les tracks (Étape 3)

Plan complet : [[2026-05-05_reprise_pivot_ecoute]].

---

**Signé** : Tom + Cowork · 2026-05-04 nuit · 15 PRs en une session
