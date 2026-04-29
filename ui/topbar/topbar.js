/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/topbar/topbar.js
   Composant topbar partagé (Phase 4 refonte architecture).

   Objectif
   ────────
   Unifier la navigation entre les pages : logo, nav contextuelle
   (Marketplace / WATT BOARD / Bibliothèque), widget balance, bouton
   MY MIX (reliée au mix-panel si la page l'expose), et un chip user
   (avatar + nom ▾) avec dropdown (Mon profil / Dashboard / Déconnexion)
   — ou un CTA "Se connecter" si déconnecté.

   Usage
   ─────
     <link rel="stylesheet" href="topbar.css" />
     <div id="smyle-topbar"></div>
     <script src="ui/core/api.js"></script>
     <script src="ui/core/events.js"></script>
     <script src="ui/topbar/topbar.js" defer></script>

   Le composant :
     - s'auto-render au DOMContentLoaded dans #smyle-topbar (ou en tête
       de <body> si le placeholder n'existe pas — fallback non-invasif)
     - fetch /users/me pour hydrater le chip user
     - écoute SmyleEvents pour réagir aux login/logout (refresh)
     - marque le lien de nav actif via data-current

   Context detection
   ─────────────────
   Par défaut, le contexte est dérivé de location.pathname :
     /              → context="marketplace"
     /u/<slug>      → context="profile"
     /dashboard     → context="dashboard"
     /library       → context="library"
   Override possible : <div id="smyle-topbar" data-context="profile"></div>

   Dépendances
   ───────────
     window.apiFetch, window.ApiError  — ui/core/api.js
     window.SmyleEvents (optionnel)    — ui/core/events.js
     window.toggleMixPanel (optionnel) — présent sur index.html
     window.openAuthModal (optionnel)  — présent sur index.html
   ───────────────────────────────────────────────────────────────────────── */

(function initSmyleTopbar() {
  'use strict';

  if (typeof window === 'undefined') return;
  // Guard anti-double-init (si le script est inclus deux fois).
  if (window.__smyleTopbarInited) return;
  window.__smyleTopbarInited = true;

  // ── SVG logo (tête Smyle compacte — reprise du style du logo principal) ──
  const LOGO_SVG = `
    <svg viewBox="0 0 60 80" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <g transform="translate(30,42)">
        <circle cx="24" cy="0" r="2.4" fill="#0c0018"/>
        <circle cx="0"  cy="24" r="2.4" fill="#0c0018"/>
        <circle cx="-24" cy="0" r="2.4" fill="#0c0018"/>
        <circle cx="0"  cy="-24" r="2.4" fill="#0c0018"/>
        <circle cx="-5.5" cy="-5" r="3.2" fill="#fff" opacity=".96"/>
        <circle cx="5.5"  cy="-5" r="3.2" fill="#fff" opacity=".96"/>
        <circle cx="-10"  cy="2"  r="2"   fill="#fff" opacity=".9"/>
        <circle cx="2.5"  cy="10" r="2"   fill="#fff" opacity=".9"/>
        <circle cx="10"   cy="3"  r="2"   fill="#fff" opacity=".9"/>
      </g>
    </svg>`;

  // État local. On ne stocke que ce qui est dynamique (user, mix count).
  const _state = {
    user:     null,      // null = anonyme, sinon objet /users/me
    mixCount: 0,
    dropOpen: false,
  };


  // ── Helpers ──────────────────────────────────────────────────────────────

  function _esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function _initial(name) {
    const s = (name || '').trim();
    return s ? s[0].toUpperCase() : '?';
  }

  function _deriveContext() {
    const root = document.getElementById('smyle-topbar');
    if (root && root.dataset.context) return root.dataset.context;
    const p = (location.pathname || '/').toLowerCase();
    if (p === '/' || p === '/index.html')         return 'marketplace';
    if (p.startsWith('/u/') || p.startsWith('/artiste/')) return 'profile';
    if (p.startsWith('/dashboard'))               return 'dashboard';
    if (p.startsWith('/library'))                 return 'library';
    return 'marketplace';
  }

  /**
   * Slug "me" dérivé de l'user courant. Mêmes règles que le backend
   * _derive_artist_slug : artist_name > email local-part. On met tout en
   * lower-case + on retire les caractères non-alphanumériques (basique).
   */
  function _meSlug(user) {
    if (!user) return null;
    const raw = (user.artistName || user.artist_name ||
                 (user.email && user.email.split('@')[0]) || '').trim();
    if (!raw) return null;
    return raw
      .toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      || null;
  }

  function _readMixCount() {
    // Le mix est persisté en localStorage par ui/panels/mix.js ; on lit la
    // clé historique. Si le format change un jour, un event "mix:updated"
    // nous remettra à jour via _bindBus plutôt que de coupler au format.
    try {
      const raw = localStorage.getItem('smyle_mix');
      if (!raw) return 0;
      const arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr.length : 0;
    } catch (_) { return 0; }
  }


  // ── Fetchers ─────────────────────────────────────────────────────────────

  async function _fetchMe() {
    try {
      const token = (window.getAuthToken && window.getAuthToken()) || null;
      if (!token) { _state.user = null; return; }
      _state.user = await apiFetch('/users/me');
    } catch (err) {
      // 401 / token invalide → on traite comme anonyme, silencieusement.
      _state.user = null;
    }
  }


  // ── Template ─────────────────────────────────────────────────────────────

  function _renderTemplate(context) {
    const user = _state.user;
    const mySlug = _meSlug(user);

    // Nav : on construit les 3 liens principaux, et on masque celui qui
    // correspond au contexte actuel (on n'invite pas à aller où on est).
    const navItems = [
      { key: 'marketplace', href: '/',                 label: 'Marketplace' },
      { key: 'dashboard',   href: '/dashboard',        label: 'WATT BOARD' },
      { key: 'library',     href: '/library',          label: 'Bibliothèque' },
    ];

    const navHtml = navItems
      .filter(it => it.key !== context)
      .map(it => `<a class="stb-nav-link" href="${it.href}">${_esc(it.label)}</a>`)
      .join('');

    // MY MIX : on affiche le compteur. Le clic ouvre la mix-panel si la
    // page l'expose (window.toggleMixPanel), sinon on renvoie sur /.
    const mixHtml = `
      <button class="stb-mymix" type="button"
              onclick="window.SmyleTopbar.clickMix(event)"
              title="My Mix">
        <span class="stb-mymix-label">MY MIX</span>
        <span class="stb-mymix-count" id="stb-mix-count">${_esc(_state.mixCount)}</span>
      </button>`;

    // Auth chip : connecté ou anonyme.
    const authHtml = user ? _renderUserChip(user, mySlug) : _renderAnonChip();

    return `
      <a href="/" class="stb-logo" aria-label="Accueil WATT">
        ${LOGO_SVG}
        <span class="stb-logo-text">WATT</span>
      </a>

      <nav class="stb-nav" aria-label="Navigation principale">
        ${navHtml}
      </nav>

      <div class="stb-right">
        <div id="smyle-balance" class="stb-balance-slot"></div>
        ${mixHtml}
        ${authHtml}
      </div>
    `;
  }

  function _renderUserChip(user, mySlug) {
    const name = user.artistName || user.artist_name ||
                 (user.email && user.email.split('@')[0]) || 'Moi';
    const color = user.brandColor || user.brand_color || '#7C3AED';
    const avatarUrl = user.avatarUrl || user.avatar_url || '';
    const avatarInner = avatarUrl
      ? `<img src="${_esc(avatarUrl)}" alt="" />`
      : _esc(_initial(name));

    const profileHref = mySlug ? `/u/${mySlug}` : '#';

    return `
      <div class="stb-user-wrap">
        <button class="stb-user-chip" type="button"
                onclick="window.SmyleTopbar.toggleDrop(event)"
                aria-haspopup="true" aria-expanded="false">
          <span class="stb-user-avatar" style="--stb-user-color:${_esc(color)}">${avatarInner}</span>
          <span class="stb-user-name">${_esc(name)}</span>
          <svg class="stb-user-caret" viewBox="0 0 24 24" width="10" height="10" fill="none"
               stroke="currentColor" stroke-width="2.2" aria-hidden="true">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>
        <div class="stb-user-drop" role="menu" hidden>
          <a class="stb-drop-item" href="${_esc(profileHref)}">Mon profil</a>
          <a class="stb-drop-item" href="/dashboard">WATT BOARD</a>
          <a class="stb-drop-item" href="/library">Bibliothèque</a>
          <div class="stb-drop-sep" role="separator"></div>
          <button class="stb-drop-item stb-drop-logout" type="button"
                  onclick="window.SmyleTopbar.logout(event)">Déconnexion</button>
        </div>
      </div>`;
  }

  function _renderAnonChip() {
    return `
      <button class="stb-auth-cta" type="button"
              onclick="window.SmyleTopbar.clickLogin(event)">
        Se connecter
      </button>`;
  }


  // ── Handlers ─────────────────────────────────────────────────────────────

  function _clickMix(ev) {
    if (ev) ev.preventDefault();
    // Ouvre la mix-panel si la page l'expose (cas index.html). Sinon on
    // redirige vers / qui expose le panel.
    if (typeof window.toggleMixPanel === 'function') {
      window.toggleMixPanel();
    } else {
      window.location.href = '/';
    }
  }

  function _clickLogin(ev) {
    if (ev) ev.preventDefault();
    // Ouvre la modale d'auth si la page l'expose (cas index.html). Sinon
    // on renvoie sur / où elle existe.
    if (typeof window.openAuthModal === 'function') {
      window.openAuthModal('login');
    } else {
      window.location.href = '/';
    }
  }

  function _logout(ev) {
    if (ev) ev.preventDefault();
    // Pas de fetch logout côté API (JWT sans serveur-state) — on nettoie
    // juste le token + on recharge la page pour repartir propre.
    try { if (window.clearAuthToken) window.clearAuthToken(); } catch (_) {}
    // P1-B8 (2026-04-29) — purge complète des caches smyle_* / watt* pour
    // éviter toute fuite de données vers le compte suivant qui se
    // connecterait sur le même navigateur. Itération sur toutes les clés
    // localStorage : robuste si on ajoute de nouveaux caches plus tard.
    try {
      const keysToRemove = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (!k) continue;
        if (k.startsWith('smyle_') || k.startsWith('watt_') || k === 'smyleWattVoiceDraft') {
          keysToRemove.push(k);
        }
      }
      keysToRemove.forEach((k) => {
        try { localStorage.removeItem(k); } catch (_) {}
      });
    } catch (_) {}
    // Reset le cache balance widget côté composant lui-même
    try { if (window.SmyleBalance && typeof window.SmyleBalance.clearCache === 'function') window.SmyleBalance.clearCache(); } catch (_) {}
    if (window.SmyleEvents) {
      window.SmyleEvents.emit('smyle:auth-changed', { user: null });
    }
    // Redirection explicite vers / (simple et sûr).
    window.location.href = '/';
  }

  function _toggleDrop(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    const wrap = document.querySelector('#smyle-topbar .stb-user-wrap');
    if (!wrap) return;
    const drop = wrap.querySelector('.stb-user-drop');
    const btn  = wrap.querySelector('.stb-user-chip');
    if (!drop || !btn) return;
    _state.dropOpen = !_state.dropOpen;
    drop.hidden = !_state.dropOpen;
    btn.setAttribute('aria-expanded', _state.dropOpen ? 'true' : 'false');
    wrap.classList.toggle('stb-user-wrap-open', _state.dropOpen);
  }

  function _closeDropOnOutside(ev) {
    if (!_state.dropOpen) return;
    const wrap = document.querySelector('#smyle-topbar .stb-user-wrap');
    if (wrap && wrap.contains(ev.target)) return;
    _state.dropOpen = false;
    const drop = wrap && wrap.querySelector('.stb-user-drop');
    const btn  = wrap && wrap.querySelector('.stb-user-chip');
    if (drop) drop.hidden = true;
    if (btn)  btn.setAttribute('aria-expanded', 'false');
    if (wrap) wrap.classList.remove('stb-user-wrap-open');
  }


  // ── Mount ────────────────────────────────────────────────────────────────

  function _ensureRoot() {
    let root = document.getElementById('smyle-topbar');
    if (!root) {
      // Pas de placeholder : on n'insère rien (c'est une page qui ne veut
      // pas de topbar partagée, ex. index.html / dashboard.html en Phase 4.1).
      return null;
    }
    root.classList.add('stb-root');
    // Astuce layout : en hydratant après que la CSS topbar.css ait chargé,
    // on évite un flash non-stylé (FOUC).
    return root;
  }

  function _marqueNavActive(root, context) {
    // data-current sur <body> = hook CSS propre (évite les classes en dur).
    if (document.body) document.body.dataset.smyleContext = context;
    if (root) root.dataset.context = context;
  }

  function _render() {
    const root = _ensureRoot();
    if (!root) return;
    const context = _deriveContext();
    root.innerHTML = _renderTemplate(context);
    _marqueNavActive(root, context);

    // Sync le compteur MY MIX depuis localStorage.
    _state.mixCount = _readMixCount();
    const c = document.getElementById('stb-mix-count');
    if (c) c.textContent = String(_state.mixCount);

    // Post-rendu : smyle-balance.js s'auto-injecte dans #smyle-balance s'il
    // est déjà chargé. Si le widget est déjà en place on le laisse, sinon
    // on lui demande un refresh pour qu'il (re)prenne sa place dans le slot.
    if (window.SmyleBalance && typeof window.SmyleBalance.refresh === 'function') {
      window.SmyleBalance.refresh();
    }
  }


  // ── Bus & listeners ──────────────────────────────────────────────────────

  function _bindBus() {
    const bus = window.SmyleEvents;
    if (!bus || typeof bus.on !== 'function') return;

    // Login / logout → re-fetch + re-render (le chip user change d'état).
    bus.on('smyle:auth-changed', async () => {
      await _fetchMe();
      _render();
    });
    // Mix modifié → on met à jour juste le compteur, pas tout le DOM.
    bus.on('smyle:mix-updated', () => {
      _state.mixCount = _readMixCount();
      const c = document.getElementById('stb-mix-count');
      if (c) c.textContent = String(_state.mixCount);
    });
  }

  function _bindGlobal() {
    // Clic outside → ferme le dropdown. On le pose une seule fois.
    document.addEventListener('click', _closeDropOnOutside);
    // Échap → idem.
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && _state.dropOpen) _closeDropOnOutside(ev);
    });
    // Synchronisation cross-tabs du mix via storage event : si une autre
    // fenêtre modifie smyle_mix, on met à jour le compteur.
    window.addEventListener('storage', (ev) => {
      if (ev.key !== 'smyle_mix') return;
      _state.mixCount = _readMixCount();
      const c = document.getElementById('stb-mix-count');
      if (c) c.textContent = String(_state.mixCount);
    });
  }


  // ── Boot ─────────────────────────────────────────────────────────────────

  async function _boot() {
    if (!document.getElementById('smyle-topbar')) return;
    _bindGlobal();
    _bindBus();
    // 1er rendu avec user=null pour éviter le flash "Se connecter"
    // seulement si on sait déjà qu'il n'y a pas de token.
    const hasToken = !!((window.getAuthToken && window.getAuthToken()));
    if (hasToken) {
      await _fetchMe();
    }
    _render();
  }

  // API publique minimale (appelée depuis les onclick inlines du template).
  window.SmyleTopbar = {
    refresh:    _render,
    clickMix:   _clickMix,
    clickLogin: _clickLogin,
    logout:     _logout,
    toggleDrop: _toggleDrop,
    // Pour que l'app puisse forcer un refresh après login manuel sans
    // attendre un event (ex. depuis modals/auth.js).
    reloadUser: async () => { await _fetchMe(); _render(); },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot, { once: true });
  } else {
    _boot();
  }
})();
