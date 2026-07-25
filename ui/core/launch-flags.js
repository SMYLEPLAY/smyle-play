/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/launch-flags.js  (FALLBACK STATIQUE)
   Filet de sécurité du MODE LANCEMENT : si l'endpoint dynamique généré par
   Flask (GET /ui/core/launch-flags.js, VRAIE source de vérité issue des
   settings backend) ne répond pas, on retombe sur « tout masqué ».
   L'endpoint dynamique est chargé EN PREMIER dans le <head> ; ce fichier ne
   fait qu'installer un défaut si window.WATT_LAUNCH n'existe pas déjà.
   RIEN n'est supprimé côté produit : ces drapeaux ne font que masquer des
   points d'entrée, et tout est rallumable par item côté backend.
   ───────────────────────────────────────────────────────────────────────── */
window.WATT_LAUNCH = window.WATT_LAUNCH || {
  paliers: false,
  resale: false,
  packs: false,
  voix: false,
  troc: false,
  thePlan: false,
};
