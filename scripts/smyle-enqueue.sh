#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# SMYLE ENQUEUE — (sandbox) DÉCLARE une tâche de déploiement.
#
# ⚠️ AUCUNE opération git ici. Le dossier monté interdit au sandbox de
# supprimer/renommer des fichiers (donc git en écriture est impossible côté
# sandbox). C'est le RELAIS (Mac) qui committe, pousse et merge.
# Ce script écrit seulement un descripteur que le relais lira.
#
# Usage :
#   scripts/smyle-enqueue.sh <branche> "<titre>" <fichier...> [-- "<corps PR>"]
#
# Exemple :
#   scripts/smyle-enqueue.sh feat/img-del "feat: suppression image owner" \
#       artiste.js artiste.html index.html -- "Recupere le travail non deploye."
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
RELAY="$(pwd)/.relay"
mkdir -p "$RELAY/queue"

BR="${1:-}"; TITLE="${2:-}"
if [ -z "$BR" ] || [ -z "$TITLE" ]; then
  echo "Usage: scripts/smyle-enqueue.sh <branche> \"<titre>\" <fichier...> [-- \"<corps>\"]"; exit 2
fi
shift 2

BODY=""; FILES=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--" ]; then shift; BODY="${1:-}"; break; fi
  FILES="$FILES $1"; shift
done
FILES="${FILES# }"
if [ -z "$FILES" ]; then echo "✗ Indique au moins un fichier à committer."; exit 3; fi

# Anti-casse pour le fichier sourcé en bash.
TITLE=${TITLE//\'/}; BODY=${BODY//\'/}
QF="${BR//\//-}"

cat > "$RELAY/queue/$QF" <<EOF
BRANCH='$BR'
TITLE='$TITLE'
BODY='$BODY'
FILES='$FILES'
CREATED='$(date -u +%Y-%m-%dT%H:%M:%SZ)'
PR=''
EOF

echo "✓ Tâche déclarée → .relay/queue/$QF"
echo "  branche : $BR"
echo "  fichiers: $FILES"
echo "  Le relais (Mac) committera ces fichiers, poussera et mergera si la CI est verte."
