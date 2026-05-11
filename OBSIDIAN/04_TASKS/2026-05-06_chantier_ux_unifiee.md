---
title: Chantier UX unifiée — étape par étape
type: task
tags: [task, sprint, ux, profil, marketplace, playlists, voicestar]
updated: 2026-05-06
status: a-faire
---

# Chantier UX unifiée + playlists (2026-05-06)

> Suite directe session 2026-05-05 nuit. Pivot écoute fonctionnel
> bout-en-bout (tracks jouables sur profil + marketplace + library).
> Bouton supprimer track OK. Reste cohérence visuelle + playlists.

---

## ⚠️ Règle cohérence design bande (validée Tom 2026-05-06)

**Une fois le design final des bandes "Sons publiés" arrêté sur le
profil, le MÊME design doit apparaître sur la devanture marketplace
(vitrine de l'accueil).** Pas de design divergent entre profil et
accueil — cohérence totale.

**Bonus** : unlock de la recette doit être possible **directement
depuis la devanture marketplace** (pas seulement depuis le profil
artiste). Click sur 🔓 sur la card marketplace → POST /unlocks/prompts
sans rediriger.

---

## 📋 Plan étape par étape

### Étape 1 — Réorganisation profil + ADN gating renforcé (20 min)
**Ordre cible sur `/u/<slug>`** :
```
Header artiste (avatar, bio, stats)
   ↓
ADN — bouton "Débloquer l'ADN · X SMYLES" (description complète jamais affichée)
   ↓
Sons publiés (bande, JUSTE en dessous de l'ADN)
   ↓
… autres cellules …
   ↓
Voix à vendre (toujours en bas de la page)
```
**Fichiers** : `artiste.html` (ordre des sections) + `artiste.js` (ADN
ne doit pas révéler le contenu, juste prix + bouton + "verrouillé").

### Étape 2 — Boutons 🗑 voix + ADN + infos surface tracks (40 min)
- Bouton 🗑 sur cellule **Voix à vendre** quand `isSelf` (DELETE
  /api/voices/{id}, déjà existant côté backend).
- Bouton 🗑 sur cellule **ADN** quand `isSelf` (vérifier endpoint
  DELETE /api/adns/{id} ou créer).
- Améliorer infos sur card track : badges plateforme + modèle +
  vocal_gender visibles plus clairement (actuellement dans
  `promptMetaLine`, à rendre plus contrasté).

### Étape 3 — Fix bug 400 upload-image (30 min)
Sans cover, l'expérience visuelle est moche (fallback couleur). Le
bug 400 de `/api/watt/upload-image` bloque tous les uploads de cover
depuis le dashboard. À diagnostiquer côté Flask (probablement champ
FormData manquant ou mauvais nom).

### Étape 4 — UI dashboard playlists (1h30)
Cellule sur le dashboard pour :
- Créer une playlist (titre + cover + toggle public/privé)
- Éditer / renommer / supprimer
- Ajouter / retirer ses propres tracks
- Drag-drop pour réordonner

Backend déjà OK (table `playlists` migration 0021, endpoints
`/playlists` à vérifier).

### Étape 5 — "My Mix" playlists mixtes (1h)
Permettre à l'artiste d'ajouter dans ses playlists des tracks
**d'autres artistes** (qu'il a achetés via /unlocks/prompts ou pas —
à trancher selon la logique sociale voulue).

### Étape 6 — Affichage playlists publiques sur profil (1h)
Nouvelle cellule sur `/u/<slug>` "Mes playlists" :
- Cards-bannières avec cover + nb de tracks + brand color
- Click → ouvre la playlist en lecture enchaînée
- Cohérent avec les 4 univers WATT du compte officiel Smyle

### Étape 7 — Marketplace bandes unifiées + unlock direct (1h)
**Cohérence design** : la card "Sons publiés" du profil devient le
composant unique réutilisé sur l'accueil (Top Sons + Grille Tous
Sons). Mêmes éléments (cover + audio + bouton 🔓 Débloquer la
recette + nom artiste cliquable).

**Unlock direct** : depuis la card marketplace, click 🔓 → POST
/unlocks/prompts immédiat (sans rediriger vers le profil).

### Étape 8 (post-alpha) — VoiceStar integration
Voir section dédiée plus bas. **Pas avant l'alpha publique.**

---

## 🎙 VoiceStar — réflexion business à valider

**Question Tom** : peut-on récupérer des voix d'autres artistes via
VoiceStar pour les vendre sur Smyleplay ?

**Réponse stratégique en 3 cas** :

| Cas | Implication | Risque |
|---|---|---|
| **A.** Récupérer voix d'artistes externes (sans leur accord) | Vendre des voix tierces | ⚠️ Contrefaçon vocale, illégal sans licence |
| **B.** Workflow consentement : artistes Smyleplay clonent leur voix sur VoiceStar puis exposent l'instance ici | Modèle propre | ✅ OK si workflow signé |
| **C.** Repackaging du catalogue VoiceStar | Dépend du modèle commercial VoiceStar | Royalties à négocier |

**Reco** : option B uniquement. VoiceStar comme fournisseur tech (clone-
as-a-service), pas comme catalogue d'artistes externes.

**Workflow proposé pour option B** :
1. Smyleplay propose à l'artiste : "Veux-tu cloner ta voix sur
   VoiceStar et la vendre ici ?"
2. L'artiste suit le tunnel VoiceStar (consentement enregistré chez eux)
3. Smyleplay reçoit via API VoiceStar un identifiant de voix clone
4. L'artiste publie cette voix-instance sur sa cellule "Voix à vendre"
5. L'acheteur paie sur Smyleplay → reçoit l'accès à la voix-instance
   pour générer ses propres morceaux sur Suno (qui supporte les
   "Personas" de voix custom)

**Effort estimé** : 1-2 semaines (intégration API + workflow
consentement + storage instance + workflow acheteur).

**Décision** : **post-alpha publique**. Pas avant que les fondations
soient validées en condition réelle.

---

## 🚦 Ordre exécution demain

1. Étape 1 (réorganisation) — 20 min
2. Étape 2 (boutons supprimer + infos) — 40 min
3. Étape 3 (fix cover upload) — 30 min
4. Étape 4 (UI playlists dashboard) — 1h30
5. Étape 5 (My Mix mixte) — 1h
6. Étape 6 (affichage playlists profil) — 1h
7. Étape 7 (marketplace bandes unifiées + unlock direct) — 1h

**Total : ~5h30** = session demain.

---

## 🔑 Phrase d'ouverture demain

Tom dit `go étape 1`. Cowork relit ce doc et démarre.
Pas de récap à refaire.
