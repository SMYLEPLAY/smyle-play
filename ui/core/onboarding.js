/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/core/onboarding.js  ·  window.SmyleOnboarding
   Parcours V1 (9/10/2026) — guide d'accueil + rappel « vérifie ta boîte mail ».

   GUIDE D'ACCUEIL
   - S'ouvre automatiquement UNE fois, juste après la première connexion
     d'un nouveau compte : le serveur garde la date (`onboarding_done_at`,
     NULL = jamais vu) ; à la fermeture ou à la fin → POST /users/me/onboarding.
   - 5 étapes en français simple (+ une 6e « Pionnier » si le programme est
     ouvert : /pioneer/places répond).
   - Se rouvre depuis le menu du compte (« Guide ») : SmyleOnboarding.open().

   EMAIL NON VÉRIFIÉ
   - Bandeau « Compte créé, vérifie ta boîte mail » + bouton « Renvoyer »
     (POST /auth/resend-verification ; limité côté serveur, et 60 s d'attente
     entre deux clics côté navigateur).

   Dépendances souples : apiFetch, getAuthToken, SmyleTrack.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (typeof window === 'undefined' || window.SmyleOnboarding) return;

  var RESEND_WAIT_S = 60;
  var _me = null;
  var _step = 0;
  var _steps = [];
  var _pionnier = null;   // null = pas encore su ; true/false ensuite

  function _token() {
    try { return typeof window.getAuthToken === 'function' && window.getAuthToken(); } catch (_) { return null; }
  }
  function _track(name) { try { if (window.SmyleTrack) window.SmyleTrack.event(name); } catch (_) {} }
  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c];
    });
  }

  function _baseSteps() {
    return [
      { icon: '⚡', t: 'Les Smyles',
        d: 'Les Smyles sont la monnaie de WATT. <b>Tu en as reçu 30, offerts</b>, pour commencer. Ils servent à débloquer ce qui te plaît.' },
      { icon: '🎧🖼️', t: 'Une Œuvre = un son + une image',
        d: 'Sur WATT, chaque Œuvre réunit un son et son image. Tu peux écouter librement, et débloquer le son, l\'image, ou l\'Œuvre entière.' },
      { icon: '🔓', t: 'Débloquer une recette',
        d: 'La recette, c\'est le texte qui a servi à créer le son avec une IA. En la débloquant avec tes Smyles, tu la gardes dans ta bibliothèque et tu peux créer à ton tour.' },
      { icon: '🚀', t: 'Publier',
        d: 'Dans le WATT BOARD, envoie ton fichier audio, ajoute ton image et ta recette, puis choisis ton prix (entre 10 et 150 Smyles). Tout se retrouve dans « Mes Œuvres ».' },
      { icon: '🔗', t: 'Partager ton lien',
        d: 'Chaque Œuvre a son propre lien. Copie-le et partage-le : tes amis écoutent un extrait et peuvent créer leur compte en un clic.' },
    ];
  }
  var _pionnierStep = { icon: '🏅', t: 'Devenir Pionnier',
    d: 'Les premiers créateurs qui publient une Œuvre deviennent Pionniers : la commission de WATT sur leurs ventes reste plafonnée à 10 %, à vie.' };

  function _checkPionnier() {
    if (_pionnier !== null || typeof window.apiFetch !== 'function') return Promise.resolve(_pionnier);
    return window.apiFetch('/pioneer/places', { auth: false, retries: 0, timeoutMs: 4000 })
      .then(function () { _pionnier = true; }, function () { _pionnier = false; })
      .then(function () { return _pionnier; });
  }

  // ── Fenêtre du guide ─────────────────────────────────────────────────────
  var _cssDone = false;
  function _css() {
    if (_cssDone) return;
    _cssDone = true;
    var st = document.createElement('style');
    st.textContent = [
      '#obWelcome{position:fixed;inset:0;z-index:100000;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.78);padding:16px}',
      '.ob-card{position:relative;max-width:480px;width:100%;max-height:92vh;overflow:auto;box-sizing:border-box;background:#14101f;border:1px solid #2c2440;border-radius:18px;padding:26px;color:#eee;font-family:inherit}',
      '.ob-x{position:absolute;top:12px;right:14px;background:none;border:none;color:#aaa;font-size:26px;cursor:pointer;line-height:1;padding:4px 8px}',
      '.ob-kicker{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#ffb627;margin:0}',
      '.ob-count{font-size:12px;color:#9990ad;margin:4px 0 14px}',
      '.ob-icon{font-size:40px;line-height:1.1;margin:6px 0 10px}',
      '.ob-t{margin:0 0 8px;font-size:22px;color:#fff}',
      '.ob-d{margin:0;font-size:15px;line-height:1.55;color:#cfc6e6;min-height:96px}',
      '.ob-d b{color:#ffd700}',
      '.ob-dots{display:flex;gap:6px;justify-content:center;margin:18px 0 16px}',
      '.ob-dot{width:8px;height:8px;border-radius:50%;background:#3a3150}',
      '.ob-dot.on{background:#ffb627}',
      '.ob-nav{display:flex;gap:10px}',
      '.ob-btn{flex:1;border-radius:12px;padding:13px;cursor:pointer;font-size:15px;font-weight:700;border:1px solid #2c2440;background:#1d1730;color:#cfc6e6}',
      '.ob-btn.main{background:#6c4cf0;border-color:#6c4cf0;color:#fff}',
      '.ob-btn[disabled]{opacity:.35;cursor:default}',
      '.ob-skip{display:block;margin:12px auto 0;background:none;border:none;color:#9990ad;font-size:13px;cursor:pointer;text-decoration:underline}',
    ].join('');
    document.head.appendChild(st);
  }

  function _ensure() {
    var m = document.getElementById('obWelcome');
    if (m) return m;
    _css();
    m = document.createElement('div');
    m.id = 'obWelcome';
    m.setAttribute('role', 'dialog');
    m.setAttribute('aria-modal', 'true');
    m.setAttribute('aria-label', 'Guide de WATT');
    document.body.appendChild(m);
    m.addEventListener('click', function (e) {
      if (e.target === m) { _close(); return; }
      var a = e.target.closest && e.target.closest('[data-ob]');
      if (!a) return;
      var k = a.getAttribute('data-ob');
      if (k === 'prev' && _step > 0) { _step--; _render(); }
      else if (k === 'next') {
        if (_step < _steps.length - 1) { _step++; _render(); }
        else { _close(true); }
      } else if (k === 'close') { _close(); }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && m.style.display === 'flex') _close();
    });
    return m;
  }

  function _render() {
    var m = _ensure();
    var s = _steps[_step];
    var last = _step === _steps.length - 1;
    var dots = _steps.map(function (_, i) {
      return '<span class="ob-dot' + (i === _step ? ' on' : '') + '"></span>';
    }).join('');
    m.innerHTML =
      '<div class="ob-card">' +
        '<button class="ob-x" type="button" data-ob="close" aria-label="Fermer le guide">×</button>' +
        '<p class="ob-kicker">Bienvenue sur WATT</p>' +
        '<p class="ob-count">Étape ' + (_step + 1) + ' sur ' + _steps.length + '</p>' +
        '<div class="ob-icon" aria-hidden="true">' + s.icon + '</div>' +
        '<h2 class="ob-t">' + _esc(s.t) + '</h2>' +
        '<p class="ob-d">' + s.d + '</p>' +
        '<div class="ob-dots" aria-hidden="true">' + dots + '</div>' +
        '<div class="ob-nav">' +
          '<button class="ob-btn" type="button" data-ob="prev"' + (_step === 0 ? ' disabled' : '') + '>Précédent</button>' +
          '<button class="ob-btn main" type="button" data-ob="next">' + (last ? 'C\'est parti !' : 'Suivant') + '</button>' +
        '</div>' +
        (last ? '' : '<button class="ob-skip" type="button" data-ob="close">Passer le guide</button>') +
      '</div>';
    var main = m.querySelector('[data-ob="next"]');
    if (main) { try { main.focus(); } catch (_) {} }
  }

  function open() {
    _steps = _baseSteps();
    _step = 0;
    var go = function () {
      if (_pionnier) _steps.push(_pionnierStep);
      _render();
      _ensure().style.display = 'flex';
      _track('onboarding_start');
    };
    _checkPionnier().then(go, go);
  }

  function _close(complete) {
    var m = document.getElementById('obWelcome');
    if (m) m.style.display = 'none';
    if (complete) _track('onboarding_complete');
    _markDone();
  }

  function _markDone() {
    try { sessionStorage.setItem('smyle_onboarding_vu', '1'); } catch (_) {}
    if (_me && _me.onboarding_done_at) return;
    if (!_token() || typeof window.apiFetch !== 'function') return;
    window.apiFetch('/users/me/onboarding', { method: 'POST' })
      .then(function (r) { if (_me && r) _me.onboarding_done_at = r.onboarding_done_at; })
      .catch(function () {});
  }

  // ── Bandeau « vérifie ta boîte mail » ────────────────────────────────────
  function _emailBanner(me) {
    var id = 'smyle-verify-banner';
    var old = document.getElementById(id);
    if (!me || me.email_verified !== false) { if (old) old.remove(); return; }
    try { if (sessionStorage.getItem('smyle_verify_ferme') === '1') return; } catch (_) {}
    if (old) return;
    var b = document.createElement('div');
    b.id = id;
    b.setAttribute('role', 'status');
    // En haut (sous la barre) : le bas de l'écran est pris par le choix de
    // mesure d'audience et le lecteur.
    b.style.cssText = 'position:fixed;left:50%;top:76px;transform:translateX(-50%);z-index:9998;' +
      'width:min(560px,calc(100% - 32px));box-sizing:border-box;display:flex;gap:10px;align-items:center;flex-wrap:wrap;' +
      'background:#1d1730;border:1px solid #6c4cf0;border-radius:14px;padding:12px 14px;color:#eee;font-size:14px;' +
      'box-shadow:0 8px 30px rgba(0,0,0,.45)';
    b.innerHTML =
      '<span style="flex:1 1 220px;line-height:1.4"><b>Compte créé, vérifie ta boîte mail</b><br>' +
      '<span style="color:#b9b2cc;font-size:13px">Clique sur le lien reçu pour confirmer ton adresse.</span></span>' +
      '<button type="button" data-verify="resend" style="background:#6c4cf0;border:none;color:#fff;border-radius:10px;padding:9px 14px;cursor:pointer;font-weight:700">Renvoyer</button>' +
      '<button type="button" data-verify="close" aria-label="Fermer" style="background:none;border:none;color:#aaa;font-size:20px;cursor:pointer;padding:2px 6px">×</button>' +
      '<span data-verify="msg" style="flex-basis:100%;font-size:12.5px;color:#9ae6b4" hidden></span>';
    document.body.appendChild(b);
    b.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('[data-verify]');
      if (!a) return;
      var k = a.getAttribute('data-verify');
      if (k === 'close') {
        try { sessionStorage.setItem('smyle_verify_ferme', '1'); } catch (_) {}
        b.remove();
      } else if (k === 'resend') {
        _resend(a, b.querySelector('[data-verify="msg"]'), me.email);
      }
    });
  }

  function _resend(btn, msg, email) {
    if (!email || typeof window.apiFetch !== 'function') return;
    btn.disabled = true;
    var show = function (t, ok) {
      if (!msg) return;
      msg.hidden = false;
      msg.style.color = ok ? '#9ae6b4' : '#ff9a9a';
      msg.textContent = t;
    };
    window.apiFetch('/auth/resend-verification', { method: 'POST', json: { email: email }, auth: false })
      .then(function () {
        show('Email renvoyé. Pense à regarder dans les indésirables.', true);
      }, function (e) {
        show(e && e.status === 429
          ? 'Tu as déjà demandé plusieurs fois. Réessaie un peu plus tard.'
          : 'Envoi impossible pour le moment. Réessaie dans un instant.', false);
      })
      .then(function () {
        var left = RESEND_WAIT_S;
        var tick = function () {
          if (left <= 0) { btn.disabled = false; btn.textContent = 'Renvoyer'; return; }
          btn.textContent = 'Renvoyer (' + left + ' s)';
          left--;
          setTimeout(tick, 1000);
        };
        tick();
      });
  }

  // ── Démarrage : après connexion (ou au chargement si déjà connecté) ──────
  function check() {
    if (!_token() || typeof window.apiFetch !== 'function') return;
    window.apiFetch('/users/me').then(function (me) {
      _me = me || null;
      if (!_me) return;
      _emailBanner(_me);
      var vu = false;
      try { vu = sessionStorage.getItem('smyle_onboarding_vu') === '1'; } catch (_) {}
      if (_me.onboarding_done_at == null && !vu) setTimeout(open, 700);
    }).catch(function () {});
  }

  window.SmyleOnboarding = { open: open, check: check, close: function () { _close(); } };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', check);
  } else { check(); }
})();
