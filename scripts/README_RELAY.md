# Commandes du framework de dev autonome

⚠️ Le sandbox ne peut faire AUCUN git en écriture (le dossier monté interdit la
suppression des fichiers .lock). Donc : le sandbox **déclare** une tâche, le **Mac**
fait tout le git.

## Côté sandbox (lancé par Claude — aucune op git, juste un descripteur)

```bash
scripts/smyle-enqueue.sh <branche> "<titre>" <fichier...> [-- "<corps PR>"]
#   ex : scripts/smyle-enqueue.sh fix/like-notif "fix: notif like" artiste.js -- "Ferme B3."
```

## Côté Mac (installé une fois, tourne en fond — fait 100 % du git)

```bash
scripts/smyle-relay.sh --once   # un cycle (utilisé par le LaunchAgent)
scripts/smyle-relay.sh          # boucle continue (debug manuel)
scripts/smyle-sync.sh           # dépannage : recale main sur origin/main (Mac)
```

Le relais committe les fichiers déclarés (sans checkout), pousse les branches,
ouvre les PR, et **merge seulement si la CI est verte**. Railway déploie au merge.

## Installation du relais (une seule fois)

```bash
cp com.smyleplay.relay.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.smyleplay.relay.plist
```

## Contrôles

```bash
touch .relay/PAUSE     # met le relais en pause
rm .relay/PAUSE        # reprend
tail -f .relay/relay.log   # suivre l'activité
```

Détails : `.relay/README.md` et `OBSIDIAN/05_TECH/Runbooks/2026-06-22_systeme-dev-autonome.md`.
