/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/refonte/profil.js · refonte, lot 4 (page profil).

   Chargé par le serveur UNIQUEMENT quand l'interrupteur `refonte` est ouvert
   et que la page est un profil (#ap-profile). Il ne fait qu'une chose :
   marquer la page du compte officiel SMYLE (classe rf-officiel sur <body>),
   pour que son masque s'affiche dans le rond quand il n'a pas de photo.
   Tout l'habillage est dans ui/pwa/refonte.css.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (!(window.WATT_LAUNCH && window.WATT_LAUNCH.refonte)) return;
  var m = /^\/(?:@|u\/|artiste\/)([^\/?#]+)/.exec(location.pathname || '');
  var slug = m ? decodeURIComponent(m[1]).toLowerCase() : '';
  function marquer() { if (slug === 'smyle') document.body.classList.add('rf-officiel'); }
  if (document.body) marquer(); else document.addEventListener('DOMContentLoaded', marquer);
})();
