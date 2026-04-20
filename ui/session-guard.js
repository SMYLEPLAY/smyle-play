/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/session-guard.js

   Petit module UX qui écoute l'event `smyle:session-expired` émis par
   ui/core/api.js dès qu'une requête retourne 401 alors qu'un JWT était
   envoyé. Il affiche un bandeau persistant en haut de page avec un
   bouton "Reconnecter" qui ouvre le modal d'auth (sur index.html)
   ou renvoie vers la page d'accueil avec un paramètre `return`
   (sur les autres pages, où le modal n'est pas chargé).

   Objectif : que l'utilisateur ne se retrouve jamais "déconnecté en
   silence" (ses Smyles qui disparaissent, ses sons qui ne se chargent
   plus, etc.) sans comprendre ce qui s'est passé. Cf. Chantier #33.

   À charger APRÈS ui/core/api.js, sur toutes les pages qui importent
   déjà smyle-balance.js (index, dashboard, artiste, watt, library).
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  const CSS = `
    .smyle-session-banner {
      position: fixed;
      top: 22px;
      left: 50%;
      transform: translateX(-50%) translateY(-14px);
      z-index: 10001;
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 12px 16px 12px 18px;
      border-radius: 999px;
      background: rgba(30, 0, 50, 0.96);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border: 1px solid rgba(255, 90, 120, 0.55);
      color: #ffe9ec;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 13px;
      font-weight: 500;
      letter-spacing: 0.01em;
      box-shadow: 0 12px 40px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,90,120,0.18);
      opacity: 0;
      transition: opacity .3s ease, transform .3s ease;
      max-width: calc(100vw - 40px);
      pointer-events: auto;
    }
    .smyle-session-banner.show {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
    .smyle-session-banner__icon {
      width: 18px;
      height: 18px;
      flex-shrink: 0;
      color: #ff6b7a;
    }
    .smyle-session-banner__text {
      color: #ffe9ec;
      font-weight: 500;
    }
    .smyle-session-banner__cta {
      border: 0;
      background: linear-gradient(135deg, #ff6b7a, #d94759);
      color: #fff;
      font: inherit;
      font-weight: 600;
      padding: 6px 14px;
      border-radius: 999px;
      cursor: pointer;
      letter-spacing: 0.02em;
      box-shadow: 0 2px 10px rgba(255, 90, 120, 0.35);
      transition: transform .15s ease, box-shadow .15s ease;
    }
    .smyle-session-banner__cta:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 16px rgba(255, 90, 120, 0.5);
    }
    .smyle-session-banner__cta:active {
      transform: translateY(0) scale(0.97);
    }
    .smyle-session-banner__close {
      background: transparent;
      border: 0;
      color: rgba(255,233,236,0.6);
      font-size: 20px;
      line-height: 1;
      cursor: pointer;
      padding: 0 4px;
      transition: color .15s ease;
    }
    .smyle-session-banner__close:hover { color: #fff; }

    @media (max-width: 600px) {
      .smyle-session-banner {
        top: 12px;
        font-size: 12px;
        padding: 10px 12px;
        gap: 10px;
      }
      .smyle-session-banner__cta { padding: 5px 11px; }
    }
  `;

  const ICON_SVG = `
    <svg class="smyle-session-banner__icon" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" stroke-width="2.2" stroke-linecap="round"
         stroke-linejoin="round" aria-hidden="true">
      <path d="M12 2a10 10 0 1 0 10 10"/>
      <path d="M12 6v6l4 2"/>
    </svg>
  `;

  let _styleInjected = false;
  let _currentBanner = null;

  function _injectStyle() {
    if (_styleInjected) return;
    if (document.getElementById('smyle-session-banner-style')) {
      _styleInjected = true;
      return;
    }
    const s = document.createElement('style');
    s.id = 'smyle-session-banner-style';
    s.textContent = CSS;
    document.head.appendChild(s);
    _styleInjected = true;
  }

  function _dismiss() {
    if (!_currentBanner) return;
    const b = _currentBanner;
    _currentBanner = null;
    b.classList.remove('show');
    setTimeout(() => { if (b.parentNode) b.parentNode.removeChild(b); }, 320);
  }

  function _onReconnect(ev) {
    if (ev) ev.preventDefault();

    // Défense en profondeur : si l'user est encore en cache localStorage
    // au moment où on clique, `openAuthModal` va faire un `return` silencieux
    // (guard "déjà connecté"). On le purge ici avant d'ouvrir le modal.
    // En théorie api.js l'a déjà fait sur le 401 — ceci couvre le cas où
    // on appelle showSessionExpiredBanner manuellement (tests, etc.).
    if (typeof window.clearCurrentUser === 'function') {
      try { window.clearCurrentUser(); } catch (_) { /* noop */ }
    }
    // Rafraîchit la barre d'auth en haut (badge → boutons Connexion/S'inscrire).
    if (typeof window.renderAuthArea === 'function') {
      try { window.renderAuthArea(); } catch (_) { /* noop */ }
    }

    // Cas 1 : on est sur index.html → le modal auth est disponible
    if (typeof window.openAuthModal === 'function') {
      _dismiss();
      try { window.openAuthModal('login'); } catch (_) { /* no-op */ }
      return;
    }

    // Cas 2 : pages secondaires (dashboard/artiste/watt/library) → on
    // renvoie vers / avec un return param. index.html peut lire ce
    // paramètre et ouvrir automatiquement le modal (optionnel).
    const current = (typeof location !== 'undefined')
      ? (location.pathname + location.search + location.hash)
      : '/';
    const target = '/?auth=login&return=' + encodeURIComponent(current);
    window.location.href = target;
  }

  function showSessionExpiredBanner(detail) {
    _injectStyle();
    // Si déjà affiché, on ne spam pas : on garde le banner existant
    if (_currentBanner && _currentBanner.parentNode) return;

    const banner = document.createElement('div');
    banner.className = 'smyle-session-banner';
    banner.setAttribute('role', 'alert');
    banner.setAttribute('aria-live', 'polite');
    banner.innerHTML = `
      ${ICON_SVG}
      <span class="smyle-session-banner__text">
        Session expirée — reconnecte-toi pour retrouver tes Smyles.
      </span>
      <button type="button" class="smyle-session-banner__cta" data-action="reconnect">
        Reconnecter
      </button>
      <button type="button" class="smyle-session-banner__close"
              aria-label="Fermer" data-action="dismiss">×</button>
    `;

    document.body.appendChild(banner);
    _currentBanner = banner;

    // Wire actions
    banner.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-action]');
      if (!btn) return;
      const action = btn.getAttribute('data-action');
      if (action === 'reconnect') _onReconnect(ev);
      else if (action === 'dismiss') _dismiss();
    });

    // Animate in
    requestAnimationFrame(() => banner.classList.add('show'));
  }

  // ── Listener principal ──────────────────────────────────────────────────
  // L'event est émis par ui/core/api.js dès qu'un 401 arrive avec un JWT
  // présent. On laisse api.js faire le nettoyage du token ; ici on gère
  // uniquement l'UX (bandeau + reconnect).
  if (typeof window !== 'undefined') {
    window.addEventListener('smyle:session-expired', (ev) => {
      showSessionExpiredBanner(ev && ev.detail ? ev.detail : {});
    });

    // Expo pour les consommateurs (tests manuels, dashboard "déconnexion manuelle", etc.)
    window.SmyleSessionGuard = {
      show:    showSessionExpiredBanner,
      dismiss: _dismiss,
    };
  }
})();
