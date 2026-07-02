#!/bin/bash
# ── SMYLE PLAY Launcher ──────────────────────────────────────────────────────
# Double-clique sur ce fichier pour lancer SMYLE PLAY dans ton navigateur.
# Nécessite Python 3 (installé par défaut sur macOS 12+).
# ─────────────────────────────────────────────────────────────────────────────

# Aller dans le dossier de ce script (où se trouve index.html)
cd "$(dirname "$0")"

# Trouver un port libre à partir de 8080
PORT=8080
while lsof -i :$PORT &>/dev/null; do
  PORT=$((PORT + 1))
done

# Ouvrir le navigateur après 1 seconde
(sleep 1 && open "http://localhost:$PORT") &

# Démarrer le serveur SMYLE PLAY (scan automatique des dossiers audio)
python3 server.py $PORT
