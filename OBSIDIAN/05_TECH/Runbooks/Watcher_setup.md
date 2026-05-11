# WATT Deploy Watcher — Setup

Pipeline automatique complet : dépose un audio → upload R2 → catalogue regénéré → commit/push GitHub → Railway redéploie → visible en ligne. Le tout en 2-5 min, sans ouvrir le Terminal.

## Ce qu'il te reste à faire (une seule fois)

### Étape unique — lance le setup interactif

Double-clique sur **`setup_watcher.sh`** depuis le Finder (ou lance-le dans le Terminal).

Il va :
1. Vérifier Python 3
2. Te demander tes clés R2 (copie-les depuis Railway → Variables) et créer `.env`
3. Installer `boto3` et `python-dotenv`
4. Tester le pipeline (`watcher_pipeline.py`)
5. Proposer d'installer la détection instantanée (LaunchAgent macOS)

Si tu préfères faire manuellement, lis la section **Setup manuel** plus bas.

## Comment ça marche à l'usage

```
1. Tu déposes sw-001 — NEW TRACK Drift.wav dans NIGHT CITY/
2. LaunchAgent le détecte en quelques secondes → lance ./deploy.sh
   (filet : scheduled task toutes les 15min)
3. deploy.sh :
   - nettoie les .DS_Store / .asd / ._*
   - valide l'ADN (warn si Drift ressemble plus à JUNGLE OSMOSE)
   - upload sur R2 (bucket smyle-play-audio)
   - regenere tracks.json avec la nouvelle entrée
   - git add + commit + push sur main (retry ×3 si échec réseau)
4. Railway détecte le push → rebuild l'app (~1-3 min)
5. Le morceau apparaît sur la playlist en ligne
```

**Total : ~1-3 minutes** avec LaunchAgent actif (vs 2-5 min avec cron seul).

## Les 2 couches de détection

| Couche | Déclencheur | Latence | Rôle |
|---|---|---|---|
| **LaunchAgent macOS** | WatchPaths sur les 4 dossiers | ~secondes | Détection instantanée quand le Mac est allumé |
| **Scheduled task Claude** | Cron `*/15 * * * *` | 15 min max | Filet de sécurité (Mac endormi, plist déchargé, etc.) |

Les deux appellent **`./deploy.sh`** qui a un verrou anti-double-run.

## Commandes utiles

**Forcer un run immédiat depuis Claude :**
> Lance watt-deploy-watcher maintenant

**Lancer le pipeline en local :**
```bash
./deploy.sh                # détection + push si changements
./deploy.sh --dry-run      # simule sans écrire ni pousser
./deploy.sh --cleanup-r2   # supprime les fichiers R2 orphelins (absents en local)
```

**Voir les logs :**
```bash
tail -f .watcher-logs/deploy.log       # logs du deploy
tail -f .watcher-logs/launchd.out.log  # logs du LaunchAgent
```

**Désactiver temporairement :**
- LaunchAgent : `launchctl unload ~/Library/LaunchAgents/com.smyleplay.watcher.plist`
- Scheduled task : dans Claude, dis-moi « désactive watt-deploy-watcher »

**Réactiver :**
- LaunchAgent : `launchctl load ~/Library/LaunchAgents/com.smyleplay.watcher.plist`
- Scheduled task : « réactive watt-deploy-watcher »

## Setup manuel (si tu préfères ne pas lancer setup_watcher.sh)

### 1. Créer `.env` à la racine du projet

```bash
# ── Cloudflare R2 (copie depuis Railway → Variables) ──
R2_ACCOUNT_ID=...
R2_ACCESS_KEY=...
R2_SECRET_KEY=...
R2_BUCKET=smyle-play-audio
CLOUD_AUDIO_BASE_URL=https://pub-5d7696b1acd74214b3314fdcab40121f.r2.dev
```

### 2. Installer les dépendances

```bash
pip3 install boto3 python-dotenv
```

### 3. Tester manuellement

```bash
python3 watcher_pipeline.py
```

Sortie attendue :
```json
{
  "mode": "full",
  "uploaded": [],
  "skipped_count": 81,
  "catalog_changed": false,
  "track_count": 81,
  "dna_warnings": [],
  "cleanup_local": {"deleted": [], "errors": []},
  "cleanup_r2": {"skipped": true},
  "errors": []
}
```

### 4. Installer le LaunchAgent (optionnel mais recommandé)

```bash
cp com.smyleplay.watcher.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.smyleplay.watcher.plist
```

## Debug

**Pipeline en échec ?**
1. Vérifie que `.env` contient les 5 variables R2
2. `pip3 list | grep -E "boto3|dotenv"` → les deux doivent être présents
3. `python3 watcher_pipeline.py` → lis le JSON / les erreurs
4. `git push origin main` en manuel → credentials GitHub OK ?
5. Sur Railway, vérifie que le deploy auto depuis `main` est activé

**LaunchAgent ne déclenche rien ?**
1. `launchctl list | grep smyleplay` → doit montrer le label
2. `tail .watcher-logs/launchd.err.log` → regarde les erreurs
3. Vérifie que les 4 dossiers existent et sont dans le plist
4. Les chemins dans le plist ont un espace devant ` JUNGLE OSMOSE` — c'est normal

**Une track apparaît dans le mauvais dossier ?**
Le pipeline renvoie un warning dans `dna_warnings` mais ne bloque pas le push. Déplace le WAV à la main dans le bon dossier → au run suivant le catalogue se corrigera.

## Fichiers impliqués

- `setup_watcher.sh` — installation interactive (une fois)
- `deploy.sh` — orchestrateur appelé par LaunchAgent + scheduled task + à la main
- `watcher_pipeline.py` — logique : scan + cleanup + DNA + upload R2 + regen tracks.json
- `com.smyleplay.watcher.plist` — LaunchAgent macOS (détection instantanée)
- `upload_to_r2.py` — script d'upload R2 standalone (toujours utilisable séparément)
- `scanner.py` — scan des playlists (utilisé par app.py au runtime)
- `agents/dna_classifier.py` — classification ADN (SUNSET / NIGHT CITY / JUNGLE OSMOSE)
- `tracks.json` — catalogue statique commité, lu en fallback par Railway
- `.gitignore` — exclut audios, `.env`, `.claude/`, `HIT MIX/`, `.watcher-logs/`
- Tâche Claude `watt-deploy-watcher` — filet de sécurité, cron `*/15 * * * *`
