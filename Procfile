# Doublon de `startCommand` dans railway.toml, qui PRIME sur Railway (F-04,
# 2026-09-02). Conservé pour les hébergeurs/outils qui lisent un Procfile ;
# toute modification de la commande de démarrage se fait dans railway.toml
# ET ici, à l'identique. (Le supprimer toucherait le déploiement = 🟠.)
web: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2 --access-log
