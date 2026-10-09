/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/core/visitor-gate.js  ·  window.SmyleGate
   Parcours V1 (9/10/2026) — le visiteur sans compte.

   1. BANDEAU d'inscription en haut de l'accueil (et de /o/…) :
      « Crée ton compte gratuit — 30 Smyles offerts ». Se monte dans
      l'élément #smyle-visitor-banner s'il existe, disparaît une fois connecté.
   2. Toute ACTION (débloquer, acheter, suivre, aimer, publier, commenter,
      signaler, ajouter en playlist…) ouvre l'INSCRIPTION (la connexion reste
      en lien secondaire). Après la création du compte (ou la connexion), le
      visiteur revient EXACTEMENT sur la page d'où il venait : paramètre
      `return=`, validé pour n'accepter qu'un chemin interne commençant par
      « / » (pas de redirection ouverte).
        - SmyleGate.requireAccount()  → true si connecté, sinon ouvre
          l'inscription et renvoie false.
        - Filet de sécurité : toute requête d'action (POST/PUT/PATCH/DELETE)
          refusée en 401 pour un visiteur ouvre l'inscription (api.js).
   3. Écoute : un EXTRAIT DE 30 SECONDES. À 30 s, le lecteur s'arrête et
      l'inscription s'ouvre. S'applique à TOUS les lecteurs audio de la page
      (HTMLMediaElement.play est enveloppé une fois).

   Chargé tôt (juste après api.js) sur toutes les pages.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (typeof window === 'undefined' || window.SmyleGate) return;

  var PREVIEW_SECONDS = 30;
  var WELCOME_SMYLES = 30;

  function hasToken() {
    try { return typeof window.getAuthToken === 'function' && !!window.getAuthToken(); }
    catch (_) { return false; }
  }

  // ── Retour après inscription : chemin interne uniquement ────────────────
  // Refusés : URL absolue (https://…), « //hote », « /\hote », caractères de
  // contrôle, tout ce qui ne reste pas sur ce site une fois résolu.
  function safeReturn(raw) {
    if (typeof raw !== 'string') return null;
    var p = raw.trim();
    if (!p || p.length > 2048) return null;
    if (p.charAt(0) !== '/' || p.charAt(1) === '/' || p.charAt(1) === '\\') return null;
    if (/[\\\u0000-\u001f\u007f]/.test(p)) return null;
    try {
      var u = new URL(p, window.location.origin);
      if (u.origin !== window.location.origin) return null;
      // On retire les paramètres d'ouverture du formulaire (évite une boucle).
      u.searchParams.delete('auth');
      u.searchParams.delete('return');
      var q = u.searchParams.toString();
      var out = u.pathname + (q ? '?' + q : '') + u.hash;
      return (out.charAt(0) === '/' && out.charAt(1) !== '/' && out.charAt(1) !== '\\') ? out : null;
    } catch (_) { return null; }
  }

  function currentPath() {
    return safeReturn(window.location.pathname + window.location.search + window.location.hash) || '/';
  }

  function _hasAuthModal() {
    return !!document.getElementById('authModal') && typeof window.openAuthModal === 'function';
  }

  // Ouvre l'inscription (connexion en lien secondaire). Sur une page sans
  // formulaire d'inscription, on passe par l'accueil avec ?auth=signup et
  // le chemin de retour.
  function openSignup(opts) {
    opts = opts || {};
    var tab = opts.tab === 'login' ? 'login' : 'signup';
    var back = safeReturn(opts.returnTo || '') || currentPath();
    if (_hasAuthModal()) {
      window.__smyleReturnPath = back;
      window.openAuthModal(tab);
      if (opts.reason) {
        var msg = document.getElementById('authReason');
        if (msg) { msg.textContent = opts.reason; msg.hidden = false; }
      }
      return;
    }
    window.location.href = '/?auth=' + tab + '&return=' + encodeURIComponent(back);
  }

  var _lastGate = 0;
  function requireAccount(opts) {
    if (hasToken()) return true;
    var now = Date.now();
    if (now - _lastGate < 800) return false;   // plusieurs déclencheurs simultanés
    _lastGate = now;
    openSignup(opts || {});
    return false;
  }

  // ── Bandeau d'inscription ────────────────────────────────────────────────
  var _cssDone = false;
  function _css() {
    if (_cssDone) return;
    _cssDone = true;
    var st = document.createElement('style');
    st.textContent = [
      '.svb{position:relative;z-index:5;margin:0 auto;max-width:1100px;box-sizing:border-box;padding:0 16px}',
      '.svb-in{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;',
      'margin:14px 0 6px;padding:18px 22px;border-radius:18px;color:#fff;',
      'background:linear-gradient(120deg,#6c4cf0 0%,#3b2bb8 55%,#0055ff 100%);',
      'box-shadow:0 10px 40px rgba(108,76,240,.35);border:1px solid rgba(255,255,255,.18)}',
      '.svb-txt{min-width:0;flex:1 1 320px}',
      '.svb-title{margin:0;font-size:clamp(19px,3.2vw,26px);font-weight:800;line-height:1.2}',
      '.svb-title b{color:#ffd700}',
      '.svb-sub{margin:6px 0 0;font-size:14px;color:rgba(255,255,255,.85);line-height:1.45}',
      '.svb-act{display:flex;align-items:center;gap:14px;flex-wrap:wrap}',
      '.svb-cta{border:none;cursor:pointer;border-radius:12px;padding:14px 22px;font-size:16px;font-weight:800;',
      'background:#ffd700;color:#1a1206;white-space:nowrap}',
      '.svb-cta:hover{filter:brightness(1.06)}',
      '.svb-login{background:none;border:none;color:#fff;text-decoration:underline;cursor:pointer;font-size:14px;padding:4px}',
      '.svb-cta:focus-visible,.svb-login:focus-visible{outline:2px solid #fff;outline-offset:2px}',
      '@media (max-width:560px){.svb-in{padding:16px}.svb-act{width:100%}.svb-cta{flex:1;text-align:center}}',
    ].join('');
    document.head.appendChild(st);
  }

  function renderBanner() {
    var host = document.getElementById('smyle-visitor-banner');
    if (!host) return;
    if (hasToken()) { host.innerHTML = ''; host.hidden = true; return; }
    _css();
    host.hidden = false;
    host.className = 'svb';
    host.innerHTML =
      '<div class="svb-in" role="region" aria-label="Inscription">' +
        '<div class="svb-txt">' +
          '<p class="svb-title">Crée ton compte gratuit — <b>' + WELCOME_SMYLES + ' Smyles offerts</b></p>' +
          '<p class="svb-sub">Écoute un extrait de 30 secondes de chaque son. Avec un compte : écoute en entier, débloque des recettes, publie tes Œuvres.</p>' +
        '</div>' +
        '<div class="svb-act">' +
          '<button type="button" class="svb-cta" data-svb="signup">Créer mon compte</button>' +
          '<button type="button" class="svb-login" data-svb="login">J\'ai déjà un compte</button>' +
        '</div>' +
      '</div>';
  }

  document.addEventListener('click', function (ev) {
    var b = ev.target && ev.target.closest && ev.target.closest('[data-svb]');
    if (!b) return;
    ev.preventDefault();
    openSignup({ tab: b.getAttribute('data-svb') === 'login' ? 'login' : 'signup' });
  });

  // ── Extrait de 30 s pour le visiteur ─────────────────────────────────────
  function _guard(el) {
    if (el.__smylePreviewGuard) return;
    el.__smylePreviewGuard = true;
    function check() {
      if (hasToken()) return;
      if (el.currentTime >= PREVIEW_SECONDS) {
        try { el.pause(); } catch (_) {}
        try { el.currentTime = 0; } catch (_) {}
        requireAccount({ reason: 'Fin de l’extrait de 30 secondes — crée ton compte gratuit pour écouter la suite.' });
      }
    }
    el.addEventListener('timeupdate', check);
    el.addEventListener('seeking', check);
  }
  try {
    var _play = window.HTMLMediaElement && window.HTMLMediaElement.prototype.play;
    if (_play && !window.HTMLMediaElement.prototype.__smyleWrapped) {
      window.HTMLMediaElement.prototype.play = function () {
        if (this && this.tagName === 'AUDIO') {
          _guard(this);
          if (!hasToken() && this.currentTime >= PREVIEW_SECONDS) {
            try { this.currentTime = 0; } catch (_) {}
          }
        }
        return _play.apply(this, arguments);
      };
      window.HTMLMediaElement.prototype.__smyleWrapped = true;
    }
  } catch (_) { /* navigateur ancien : pas d'extrait limité côté client */ }
  // Lecteurs natifs (<audio controls>) lancés par le bouton du navigateur.
  document.addEventListener('play', function (ev) {
    var el = ev.target;
    if (el && el.tagName === 'AUDIO') _guard(el);
  }, true);

  function refresh() { renderBanner(); }

  window.SmyleGate = {
    PREVIEW_SECONDS: PREVIEW_SECONDS,
    isVisitor: function () { return !hasToken(); },
    safeReturn: safeReturn,
    currentPath: currentPath,
    openSignup: openSignup,
    requireAccount: requireAccount,
    refresh: refresh,
    clearPersonalData: function () {
      if (typeof window.smyleClearPersonalData === 'function') window.smyleClearPersonalData();
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderBanner);
  } else { renderBanner(); }
  try {
    if (window.SmyleEvents && window.SmyleEvents.on) {
      window.SmyleEvents.on('smyle:auth-changed', renderBanner);
    }
  } catch (_) {}
})();
