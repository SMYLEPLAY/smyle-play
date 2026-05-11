# Suno Router — Auto-routage des téléchargements

Dès que tu télécharges un WAV/MP3 depuis Suno, il arrive dans `~/Downloads` et en quelques secondes le Suno Router le déplace tout seul dans la bonne playlist (SUNSET LOVER / NIGHT CITY / JUNGLE OSMOSE / HIT MIX) — ou dans `A_CLASSER/` si l'ADN est ambigu.

Ensuite le LaunchAgent principal prend le relais : upload R2 → push GitHub → Railway redéploie.

## Les 3 niveaux de décision

| Priorité | Méthode | Quand elle s'applique |
|---|---|---|
| **1. Breadcrumb** | `pending_downloads.json` | Tu as pré-déclaré ton intention via `add_breadcrumb.py` ou le skill watt-prompt. Routage 100% fiable. |
| **2. DNA Classifier** | `agents/dna_classifier.py` | Pas de breadcrumb, mais le nom du fichier contient des mots-clés ADN (JUNGLE, NIGHT, CALM RAIN, etc.). Seuil minimum de confiance : **0.40**. |
| **3. Triage** | `A_CLASSER/` | Ni breadcrumb, ni confiance suffisante. Tu classes à la main en 2 secondes. |

## Workflow recommandé

### Option A — Avec watt-prompt (le plus fluide)

1. Tu demandes à Claude : *« génère-moi un prompt NIGHT CITY pour un morceau nommé Midnight Cruise »*
2. Le skill watt-prompt génère le prompt **et** enregistre le breadcrumb automatiquement
3. Tu colles le prompt dans Suno → Suno te donne un morceau nommé `Midnight Cruise.wav`
4. Tu cliques Download → le fichier arrive dans `~/Downloads`
5. Suno Router matche `Midnight Cruise` avec le breadcrumb → déplace dans `NIGHT CITY/`
6. Pipeline principal s'enchaîne → live en 2-3 min

### Option B — Sans breadcrumb (heuristique seule)

1. Tu génères n'importe quoi sur Suno et le nommes avec un mot-clé clair (ex: `Neon Canopy Drift.wav`)
2. Download → le classifier voit "neon canopy" → JUNGLE OSMOSE (confiance 0.7+)
3. Routage auto

### Option C — Breadcrumb manuel

Si tu crées un prompt Suno sans passer par le skill :

```bash
cd ~/Documents/Claude/IA\ SUNO\ PLAYLIST\ DEVELOPPEMENT
python3 add_breadcrumb.py "Midnight Cruise" NIGHT_CITY
```

Puis tu télécharges depuis Suno, le router matche le titre.

## Commandes `add_breadcrumb.py`

```bash
# Enregistrer une intention
python3 add_breadcrumb.py "Golden Hour" SUNSET_LOVER
python3 add_breadcrumb.py "Neon Canopy" JUNGLE_OSMOSE
python3 add_breadcrumb.py "Midnight Cruise" NIGHT_CITY
python3 add_breadcrumb.py "triste" HIT_MIX

# Lister les breadcrumbs actifs
python3 add_breadcrumb.py --list

# Vider tout
python3 add_breadcrumb.py --clear

# Retirer un titre précis
python3 add_breadcrumb.py --remove "Midnight Cruise"
```

Les breadcrumbs expirent automatiquement après **24h**.

## Quand lancer manuellement

Si le LaunchAgent n'est pas chargé ou si tu veux forcer un run :

```bash
python3 suno_router.py
```

Il scanne `~/Downloads`, route les fichiers audio récents (< 60 min), et affiche un JSON résumant ce qui a été fait.

## Logs

```bash
tail -f .watcher-logs/suno_router.log          # log humain
tail -f .watcher-logs/suno_router.launchd.log  # output du LaunchAgent
cat    .watcher-logs/pending_downloads.json    # breadcrumbs en attente
cat    .watcher-logs/suno_router_seen.json     # fichiers déjà traités
```

## Dossier `A_CLASSER/`

- Créé à la racine du projet
- Gitignoré (sauf `.gitkeep`)
- Reçoit les fichiers dont la confiance DNA < 0.40 et sans breadcrumb
- À vider régulièrement : déplace manuellement les fichiers dans la bonne playlist, le pipeline principal les uploadera automatiquement

## Comment le skill watt-prompt peut écrire un breadcrumb

Dans `SKILL.md` du skill `watt-prompt`, ajoute après la génération du prompt :

```markdown
Après avoir généré le prompt, appelle le helper pour enregistrer le breadcrumb :

    Bash(command=f'cd "/Users/tommio/Documents/Claude/IA SUNO PLAYLIST DEVELOPPEMENT " && python3 add_breadcrumb.py "{track_title}" {DNA_CIBLE}')

Où `DNA_CIBLE` est parmi : SUNSET_LOVER, NIGHT_CITY, JUNGLE_OSMOSE, HIT_MIX.
```

Ainsi le breadcrumb est posé au moment même où tu génères le prompt — aucun effort supplémentaire.

## Déclencheurs et timing

```
Tu cliques Download sur Suno
        │
        ▼
Fichier arrive dans ~/Downloads
        │
        │  (LaunchAgent détecte via WatchPaths — latence ~secondes)
        ▼
suno_router.py vérifie stabilité fichier (3s)
        │
        ├─ Breadcrumb match ?  ──► oui ──► move vers playlist  ─┐
        │                                                       │
        ├─ Classifier ≥ 0.40 ? ──► oui ──► move vers playlist  ─┤
        │                                                       │
        └─ sinon              ──────────► move vers A_CLASSER/  │
                                                                │
                                                                ▼
                                        com.smyleplay.watcher plist
                                        détecte le nouveau fichier dans
                                        SUNSET LOVER/ / etc.
                                                                │
                                                                ▼
                                        deploy.sh → upload R2 → push GitHub
                                                                │
                                                                ▼
                                        Railway rebuild (~2-3 min)
                                                                │
                                                                ▼
                                        Visible en ligne
```

## Debug

**Fichier resté dans `~/Downloads` au lieu d'être déplacé :**
1. `tail .watcher-logs/suno_router.launchd.log` → erreur ?
2. Vérifie que le LaunchAgent est chargé : `launchctl list | grep suno-router`
3. Lance manuellement : `python3 suno_router.py` et lis le JSON

**Fichier part toujours dans `A_CLASSER/` :**
- Le nom est trop générique (ex: `Suno AI 2025-04-16.wav`). Solution : soit renommer avec un mot-clé ADN, soit poser un breadcrumb juste avant le download.

**Breadcrumb qui ne matche pas :**
- Vérifie la casse et les accents — le matcher normalise tout, mais les mots doivent être identiques (substring). Ex: breadcrumb `"Neon Canopy"` matchera `NEON CANOPY Drift.wav` mais PAS `NeonCanopy.wav` (sans espace).

## Désactiver

```bash
launchctl unload ~/Library/LaunchAgents/com.smyleplay.suno-router.plist
```

Rien d'autre à faire — le reste du pipeline continue à fonctionner.
