/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY / WATT — ui/core/legal-footer.js
   Pack légal v1 (2026-06-10), complété au Lot D. Injecte un pied de page
   discret et identique sur toutes les pages qui incluent ce script :
   Mentions légales, CGU, Confidentialité, Cookies / mesure d'audience (rouvre
   le choix de consentement), Contact, Signaler un contenu.
   Zéro dépendance, zéro impact layout (simple bloc en fin de body).
   ───────────────────────────────────────────────────────────────────────── */
(function injectLegalFooter() {
  'use strict';
  if (typeof document === 'undefined' || document.getElementById('sp-legal-footer')) return;

  var CONTACT = 'smyletheplan@gmail.com';

  function ouvrirCookies() {
    if (window.SmyleConsent && window.SmyleConsent.reopen) { window.SmyleConsent.reopen(); return; }
    // Page sans consent.js : on le charge, puis on rouvre le choix.
    var s = document.createElement('script');
    s.src = '/ui/core/consent.js?v=20261010lotd';
    s.onload = function () { if (window.SmyleConsent && window.SmyleConsent.reopen) window.SmyleConsent.reopen(); };
    document.head.appendChild(s);
  }

  function ouvrirContact() {
    if (typeof window.openContactModal === 'function') { window.openContactModal(); return; }
    window.location.href = 'mailto:' + CONTACT;
  }

  function inject() {
    if (document.getElementById('sp-legal-footer')) return;
    var f = document.createElement('footer');
    f.id = 'sp-legal-footer';
    f.setAttribute('role', 'contentinfo');
    f.style.cssText =
      'margin:48px 0 0;padding:18px 16px 26px;text-align:center;' +
      'border-top:1px solid rgba(255,255,255,.08);' +
      'font-family:inherit;font-size:11px;line-height:2;' +
      'color:rgba(255,255,255,.45);position:relative;z-index:5;' +
      'display:block;width:100%;box-sizing:border-box;clear:both;';
    var l = 'color:rgba(255,255,255,.6);text-decoration:none;margin:0 8px;display:inline-block;' +
            'background:none;border:none;padding:0;font:inherit;cursor:pointer;';
    f.innerHTML =
      '<span style="letter-spacing:.1em;">⚡ WATT</span><br>' +
      '<nav aria-label="Informations légales">' +
        '<a href="/legal#mentions" style="' + l + '">Mentions légales</a>' +
        '<a href="/legal#cgu" style="' + l + '">CGU</a>' +
        '<a href="/legal#confidentialite" style="' + l + '">Confidentialité</a>' +
        '<button type="button" data-sp-cookies style="' + l + '">Cookies / mesure d’audience</button>' +
        '<button type="button" data-sp-contact style="' + l + '">Contact</button>' +
        '<a href="/legal#contenu" style="' + l + '">Signaler un contenu</a>' +
      '</nav>';
    f.querySelector('[data-sp-cookies]').addEventListener('click', ouvrirCookies);
    f.querySelector('[data-sp-contact]').addEventListener('click', ouvrirContact);
    document.body.appendChild(f);
  }

  window.SmyleLegalFooter = { cookies: ouvrirCookies, contact: ouvrirContact };

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    inject();
  } else {
    document.addEventListener('DOMContentLoaded', inject);
  }
})();
