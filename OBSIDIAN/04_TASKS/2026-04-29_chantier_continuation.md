---
title: Continuation chantier — finir l'écosystème vente Smyleplay
type: task
tags: [task, sprint, alpha, vente, adn, prompt, voix]
updated: 2026-04-29
status: en-cours
---

# Continuation chantier — finir l'écosystème vente

> Tom commence sa saison 7j/7 nuit. Mode async + petites sessions.
> Objectif : finir l'écosystème **publication + vente + achat** d'ADN, prompts et voix sur les profils artistes.

---

## ✅ Acquis au 2026-04-29 (4 PRs mergées)

| Brique | État |
|---|---|
| Persistance profil + casquettes en DB | ✅ Livré (commit `a59d334`) |
| Modale d'achat de SMYLES (badge balance topbar) | ✅ Livré (commit `417e011`) |
| Marketplace affiche les artistes publics sans track | ✅ Livré backend (commit `c21524a`) + front (commit `6d8e2b3`) |
| Logout purge complet localStorage | ✅ Livré (commit `4f1acb0`) |
| Endpoint `/credits/grant` désactivé en prod publique (gating ENVIRONMENT) | ✅ Livré (commit `4f1acb0`) |
| **Achat ADN bout-en-bout validé** (TL → Smyle, 80 SMYLES → 64 crédités vendeur) | ✅ Validé en prod |

---

## ⚠️ Bug actuel non résolu (point de reprise)

### Création de prompt impossible — toast `prompt refusé : [object Object]`

**État du diagnostic au 2026-04-29 fin de session** :
- L'API `/watt/artists/smyle` retourne `adn:null` même en mode visiteur (test confirmé 2 fois)
- Tom a cliqué "Publier" sur la cellule ADN du dashboard, mais l'API renvoie toujours `null`
- **Cause confirmée** : `_adnState.adn` est `null` côté front (`loadAdn` au boot a reçu 404 du backend) → `toggleAdnPublish` fait un `return` silencieux. Le dashboard affiche "publié" via un état UI par défaut, **mais aucun ADN n'existe vraiment en DB**.
- → L'ADN n'a **jamais été créé** en DB ou a disparu. Cause de la disparition non investiguée (entre l'achat ADN réussi à 14h et le test prompt à 15h, il s'est passé ~1h sans action utilisateur côté Smyle, et 2 PRs frontend ont été mergées sans toucher à la DB).

### Si l'ADN est bien public en DB mais le prompt est toujours refusé

→ Bug d'affichage du toast (`[object Object]` au lieu du vrai message Pydantic). Code dans `dashboard.js:1188-1190` :
```javascript
const msg = (e && e.body && e.body.detail) || (e && e.message) || 'erreur inconnue';
dashToast(`⚠ Son publié, mais prompt refusé : ${msg}`);
```
Si `e.body.detail` est un array Pydantic, `String(array)` donne `[object Object]`.

**Fix à coder** : améliorer le parsing pour gérer array/object Pydantic. ~15 min.

---

## 🎯 Étapes pour finir l'écosystème (priorisées)

### Étape 1 — RECRÉER l'ADN en DB (priorité absolue, ~10 min Tom)

**Avant tout** : l'ADN n'existe pas en DB. Le formulaire de création doit être **rempli depuis zéro**, pas juste "publier" un cache local fantôme.

1. Sur Chrome (Smyle) → /dashboard → cellule ADN
2. **Hard reload** `⌘ + Shift + R` (force le re-fetch de `_adnState.adn` qui est null)
3. La cellule devrait afficher un **état "vide / créer un ADN"** (et non "publié")
4. **Si la cellule affiche encore "publié" malgré reload** → bug d'affichage (P1-B12). Cliquer le bouton "Modifier" ou "Recréer" si dispo, sinon ouvrir DevTools (F12) → Application → Local Storage → supprimer toutes les clés `smyle_*` puis reload
5. Remplir le formulaire :
   - Description : ≥ 200 chars (texte libre, ex le brief Smyle)
   - Prix : entre 30 et 500 SMYLES (ex 80)
   - Usage guide + example outputs : optionnel
6. Cliquer **Sauvegarder** → toast attendu : `ADN créé · prêt à publier`
7. Cliquer le bouton/toggle **Publier** → toast attendu : `ADN publié — visible sur ton profil 🎉`
8. Refaire test API : `"adn":{...}` au lieu de `null`

### Étape 2 — Débloquer le test prompt (~15 min Tom)

Une fois l'ADN bien en DB :
1. /dashboard → bloc Poster un morceau (1a) → mode "avec prompt vendable"
2. Remplir avec :
   - Texte prompt : `Synthwave neo-rétro 110 BPM, basses pulsées analogiques, nappes vintage, claps réverbérés, mood nocturne urbain Paris 2026.` (~120 chars)
   - Prix : 15 SMYLES
3. Toast attendu : `💎 Recette IA "..." publiée sur la marketplace`
4. Vérifier API : `"prompts":[{...}]` au lieu de `[]`
5. Vérifier sur `/u/smyle` : cellule prompts visible avec le nouveau prompt

### Étape 2 — Si toast `[object Object]` persiste (~30 min code)

**Cowork à coder** :
- Dans `dashboard.js:1188-1190`, parser correctement `e.body.detail` (gérer array Pydantic, object validation, fallback string)
- Push + PR
- Tom valide depuis mobile

Code suggéré :
```javascript
let msg = 'erreur inconnue';
if (e?.body?.detail) {
  const d = e.body.detail;
  if (typeof d === 'string') msg = d;
  else if (Array.isArray(d)) msg = d.map(x => x.msg || JSON.stringify(x)).join(' · ');
  else if (typeof d === 'object') msg = d.message || JSON.stringify(d);
} else if (e?.message) msg = e.message;
dashToast(`⚠ Son publié, mais prompt refusé : ${msg}`);
```

### Étape 3 — Tester l'achat de prompt bout-en-bout (~30 min Tom batch)

Une fois le prompt visible sur `/u/smyle` :
1. Sur Safari (compte TL) : aller sur `/u/smyle`
2. Cellule prompts → click "Débloquer" sur le prompt à 15 SMYLES
3. Vérifier débit acheteur (TL : -15) + crédit vendeur (Smyle : +12 = 80% × 15)
4. Sur `/library` (TL) : onglet Prompts → prompt visible avec `prompt_text` complet (gated avant unlock, complet après)

**Si OK → écosystème vente prompt 100% fonctionnel.**

### Étape 4 — Vente de voix (backend, ~2-3 jours)

Le bloc 1c "Vendre une voix" est livré en aperçu visuel localStorage. **Backend manquant** :

- **Migration Alembic** : table `voices_for_sale`
  ```
  id (UUID PK), user_id (FK users), name (str 40), style (str 80),
  genres (JSON array), sample_url (str 500 — R2), license (enum personnel/commercial/exclusif),
  price_smyles (int 50-5000), is_published (bool), created_at, updated_at
  ```
- **Endpoints FastAPI** : POST/GET/PATCH/DELETE `/api/voices`
- **Upload sample audio** : pipeline Cloudflare R2 (réutiliser celui des tracks)
- **Affichage `/u/<slug>`** : cellule dédiée "Voix à vendre", chips genres, bouton Débloquer
- **Flux d'achat** : endpoint `POST /unlocks/voices/{voice_id}` (calqué sur unlock_adn / unlock_prompt)
- **Page `/library`** : onglet Voix avec liste des voix unlockées + lien téléchargement sample

### Étape 5 — Pricing v1 (session dédiée, ~2-4h, hors code)

Voir `OBSIDIAN/01_PRODUIT/Tarification_v1.md` (déjà cadré, section 11 enrichie 2026-04-28).

**Sujets à trancher** :
- Ratio EUR ↔ SMYLES (pack 200 = 120€ donne 0,60€/SMYLE)
- Répartition vendeur / plateforme (actuel 80/20 — confirmer)
- Fourchettes ADN (actuelle 30-500, proposition Tom 3-8 prompt simple / 8-20 avancé)
- Système d'exclusivité (1 acheteur, N places limitées avec prix qui monte)
- Ajustement DB CHECK constraints si fourchettes changent

---

## 🐛 Backlog bugs détectés (à fixer post-alpha sauf urgence)

| ID | Bug | Effort | Critique ? |
|---|---|---|---|
| **P1-B10** | Token JWT partagé entre onglets/fenêtres Chrome (auth cross-onglet) | 2-3h refactor sessionStorage | Non (workaround = navigateurs séparés) |
| **P1-B11** | Toast `[object Object]` au lieu du détail Pydantic | 15 min | Oui (couvert par Étape 2) |
| **P1-B12** | Désync dashboard cellule ADN (affiche "publié" alors que `is_published=false` en DB) | 30 min — re-fetch /artist/me/adn au boot dashboard et caser sur la valeur DB pas localStorage | Non bloquant, mais source de confusion utilisateur |
| **P1-B13** | À investiguer : pourquoi l'ADN de Smyle a disparu de la DB entre l'achat ADN réussi et le test prompt (~1h plus tard) | À diagnostiquer | À voir si reproductible |

---

## 🚀 Mode opératoire async — Tom + Cowork

### Côté Cowork
- Code en autonomie chaque chantier (1 chantier = 1 PR — règle de fer)
- Push avec test plan court dans la PR
- Notification GitHub mobile envoyée à Tom

### Côté Tom
- **Mode rapide (5 min mobile)** : approve + merge depuis l'app GitHub pendant pauses service
- **Mode batch (1h jour off)** : tests bout-en-bout cumulés, retour en lot

### Cadence cible
- 2-3 PRs / semaine côté code
- 1 batch test / semaine côté Tom
- **Alpha publique testable = 2-3 semaines** si cadence tenue

---

## 🔑 Pour reprendre — message d'ouverture session

Quand Tom revient, il dit simplement :

```
go étape 1
```
ou
```
go étape 2
```
ou
```
test batch
```

Cowork relit ce doc et reprend exactement où c'était. **Pas de recap à refaire.**

---

**Signé** : Tom + Cowork · 2026-04-29 · session prep avant saison nocturne
