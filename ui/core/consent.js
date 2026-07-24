/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/core/consent.js
   Consentement mesure d'audience (RGPD / ePrivacy) — OPT-IN.

   WATT n'utilise PAS de cookies publicitaires ni de traceurs tiers. La seule
   mesure est une télémétrie de funnel anonyme (sans PII), qui ne s'active
   QUE si l'utilisateur l'accepte ici. Le choix est stocké dans
   localStorage['smyle_consent'] = 'granted' | 'denied' et lu par
   ui/core/telemetry.js. Do-Not-Track => refus automatique, aucune bannière.

   API : window.SmyleConsent.granted() / .choiceMade() / .set('granted'|'denied')
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (typeof window === 'undefined') return;

  var KEY = 'smyle_consent';
  function get() { try { return localStorage.getItem(KEY); } catch (_) { return null; } }
  function set(v) { try { localStorage.setItem(KEY, v); } catch (_) {} }

  window.SmyleConsent = {
    granted: function () { return get() === 'granted'; },
    choiceMade: function () { var v = get(); return v === 'granted' || v === 'denied'; },
    set: function (v) { if (v === 'granted' || v === 'denied') set(v); }
  };

  // Do-Not-Track → refus automatique, pas de bannière.
  var dnt = (navigator.doNotTrack === '1' || window.doNotTrack === '1' ||
             navigator.msDoNotTrack === '1');
  if (dnt) { if (!get()) set('denied'); return; }

  if (window.SmyleConsent.choiceMade()) return;  // choix déjà fait

  function show() {
    if (document.getElementById('smyle-consent')) return;
    var bar = document.createElement('div');
    bar.id = 'smyle-consent';
    bar.setAttribute('role', 'dialog');
    bar.setAttribute('aria-label', 'Consentement mesure d\'audience');
    bar.style.cssText = [
      'position:fixed', 'left:16px', 'right:16px', 'bottom:16px', 'z-index:2147483000',
      'max-width:520px', 'margin:0 auto', 'padding:14px 16px',
      'background:linear-gradient(180deg,#120a20,#0a0712)',
      'border:1px solid rgba(170,0,255,.32)', 'border-radius:14px',
      'box-shadow:0 18px 50px rgba(0,0,0,.55)',
      'color:#e8e4f0', 'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif',
      'font-size:13px', 'line-height:1.5'
    ].join(';');
    bar.innerHTML =
      '<div style="margin-bottom:10px">On utilise une <strong>mesure d\'audience anonyme</strong> ' +
      '(sans publicité ni traceur tiers) pour améliorer WATT. Tu peux refuser — ' +
      'le site fonctionne pareil. <a href="/legal#confidentialite" style="color:#b98bff">En savoir plus</a>.</div>' +
      '<div style="display:flex;gap:8px;justify-content:flex-end">' +
        '<button type="button" data-consent="no" style="cursor:pointer;background:rgba(255,255,255,.06);' +
          'color:#cdc7db;border:1px solid rgba(255,255,255,.14);border-radius:9px;padding:7px 14px;font-size:13px">Refuser</button>' +
        '<button type="button" data-consent="ok" style="cursor:pointer;background:#6c4cf0;' +
          'color:#fff;border:1px solid #7d5cff;border-radius:9px;padding:7px 14px;font-size:13px;font-weight:600">Accepter</button>' +
      '</div>';
    document.body.appendChild(bar);

    bar.querySelector('[data-consent="ok"]').addEventListener('click', function () {
      set('granted'); bar.remove();
      // Compte la visite en cours maintenant que c'est accepté.
      try { if (window.SmyleTrack && SmyleTrack.pageView) SmyleTrack.pageView(); } catch (_) {}
    });
    bar.querySelector('[data-consent="no"]').addEventListener('click', function () {
      set('denied'); bar.remove();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', show);
  } else {
    show();
  }
})();
