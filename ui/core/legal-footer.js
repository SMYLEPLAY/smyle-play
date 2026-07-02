/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY / WATT — ui/core/legal-footer.js
   Pack légal v1 (2026-06-10). Injecte un footer discret et identique sur
   toutes les pages qui incluent ce script : liens vers /legal (CGU,
   confidentialité, mentions, contenu). Zéro dépendance, zéro impact layout
   (simple bloc en fin de body).
   ───────────────────────────────────────────────────────────────────────── */
(function injectLegalFooter() {
  'use strict';
  if (typeof document === 'undefined' || document.getElementById('sp-legal-footer')) return;

  function inject() {
    if (document.getElementById('sp-legal-footer')) return;
    var f = document.createElement('footer');
    f.id = 'sp-legal-footer';
    f.setAttribute('role', 'contentinfo');
    f.style.cssText =
      'margin:48px 0 0;padding:18px 20px 26px;text-align:center;' +
      'border-top:1px solid rgba(255,255,255,.08);' +
      'font-family:inherit;font-size:11px;line-height:2;' +
      'color:rgba(255,255,255,.45);position:relative;z-index:5;';
    var l = 'color:rgba(255,255,255,.55);text-decoration:none;margin:0 10px;';
    f.innerHTML =
      '<span style="letter-spacing:.1em;">⚡ WATT · bêta</span><br>' +
      '<a href="/legal#cgu" style="' + l + '">CGU / CGV</a>' +
      '<a href="/legal#confidentialite" style="' + l + '">Confidentialité</a>' +
      '<a href="/legal#mentions" style="' + l + '">Mentions légales</a>' +
      '<a href="/legal#contenu" style="' + l + '">Signaler un contenu</a>';
    document.body.appendChild(f);
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    inject();
  } else {
    document.addEventListener('DOMContentLoaded', inject);
  }
})();
