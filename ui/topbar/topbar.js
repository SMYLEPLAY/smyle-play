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

  // ── SVG logo (tête Smyle COMPLÈTE — identique au logo de la home pour un
  // rendu cohérent partout ; l'ancienne version compacte était "décousue"). ──
  const LOGO_SVG = `
    <svg viewBox="0 0 60 80" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <g transform="translate(30,42)">
        <circle cx="24" cy="0" r="2.4" fill="#0c0018"/>
        <circle cx="22.1" cy="8.9" r="2.4" fill="#0e001e"/>
        <circle cx="16.9" cy="16.9" r="2.4" fill="#0c0016"/>
        <circle cx="8.9" cy="22.1" r="2.4" fill="#0e001e"/>
        <circle cx="0" cy="24" r="2.4" fill="#0c0018"/>
        <circle cx="-8.9" cy="22.1" r="2.4" fill="#0e001e"/>
        <circle cx="-16.9" cy="16.9" r="2.4" fill="#0c0016"/>
        <circle cx="-22.1" cy="8.9" r="2.4" fill="#0e001e"/>
        <circle cx="-24" cy="0" r="2.4" fill="#0c0018"/>
        <circle cx="-22.1" cy="-8.9" r="2.4" fill="#0e001e"/>
        <circle cx="-16.9" cy="-16.9" r="2.4" fill="#0c0016"/>
        <circle cx="-8.9" cy="-22.1" r="2.4" fill="#0e001e"/>
        <circle cx="0" cy="-24" r="2.4" fill="#0c0018"/>
        <circle cx="8.9" cy="-22.1" r="2.4" fill="#0e001e"/>
        <circle cx="16.9" cy="-16.9" r="2.4" fill="#0c0016"/>
        <circle cx="22.1" cy="-8.9" r="2.4" fill="#0e001e"/>
        <circle cx="15" cy="0" r="1.9" fill="#130025"/>
        <circle cx="13.5" cy="7.5" r="1.9" fill="#130025"/>
        <circle cx="7.5" cy="13.5" r="1.9" fill="#130025"/>
        <circle cx="0" cy="15" r="1.9" fill="#130025"/>
        <circle cx="-7.5" cy="13.5" r="1.9" fill="#130025"/>
        <circle cx="-13.5" cy="7.5" r="1.9" fill="#130025"/>
        <circle cx="-15" cy="0" r="1.9" fill="#130025"/>
        <circle cx="-13.5" cy="-7.5" r="1.9" fill="#130025"/>
        <circle cx="-7.5" cy="-13.5" r="1.9" fill="#130025"/>
        <circle cx="0" cy="-15" r="1.9" fill="#130025"/>
        <circle cx="7.5" cy="-13.5" r="1.9" fill="#130025"/>
        <circle cx="13.5" cy="-7.5" r="1.9" fill="#130025"/>
        <circle cx="-5.5" cy="-5" r="3.2" fill="#ffffff" opacity="0.96"/>
        <circle cx="5.5" cy="-5" r="3.2" fill="#ffffff" opacity="0.96"/>
        <circle cx="-5.5" cy="-5" r="1.4" fill="#1a0030" opacity="0.55"/>
        <circle cx="5.5" cy="-5" r="1.4" fill="#1a0030" opacity="0.55"/>
        <circle cx="-10" cy="2" r="2" fill="#ffffff" opacity="0.90"/>
        <circle cx="-6.5" cy="7" r="2" fill="#ffffff" opacity="0.90"/>
        <circle cx="-2" cy="9.8" r="2" fill="#ffffff" opacity="0.90"/>
        <circle cx="2.5" cy="10" r="2" fill="#ffffff" opacity="0.90"/>
        <circle cx="7" cy="7.5" r="2" fill="#ffffff" opacity="0.90"/>
        <circle cx="10" cy="3" r="2" fill="#ffffff" opacity="0.90"/>
      </g>
    </svg>`;

  // État local. On ne stocke que ce qui est dynamique (user, mix count).
  const _state = {
    user:     null,      // null = anonyme, sinon objet /users/me
    mixCount: 0,
    dropOpen: false,
  };

  // État notifications (hors messages)
  const _notifState = {
    count:      0,
    open:       false,
    items:      [],
    pollTimer:  null,
  };

  // État messagerie topbar
  const _msgState = {
    count:      0,
    open:       false,
    threads:    [],
    pollTimer:  null,
  };

  const NOTIF_META = {
    purchase: { icon: '💸', color: '#22c55e' },
    like:     { icon: '❤️', color: '#ef4444' },
    follow:   { icon: '👤', color: '#3b82f6' },
    message:  { icon: '✉️', color: '#a855f7' },
    trade:    { icon: '🔄', color: '#f97316' },
    system:   { icon: '⚙️', color: '#6b7280' },
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
    if (p.startsWith('/u/') || p.startsWith('/@') || p.startsWith('/artiste/')) return 'profile';
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


  // ── Helpers notifications ─────────────────────────────────────────────────

  function _timeAgo(iso) {
    if (!iso) return '';
    const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
    if (diff < 60)   return 'à l\'instant';
    if (diff < 3600) return Math.floor(diff / 60) + ' min';
    if (diff < 86400) return Math.floor(diff / 3600) + ' h';
    return Math.floor(diff / 86400) + ' j';
  }

  function _notifText(n) {
    const actor = _esc(n.actor_name || 'Quelqu\'un');
    switch (n.type) {
      case 'purchase': {
        const item = (n.metadata_json && n.metadata_json.item_type) || 'item';
        const amt  = (n.metadata_json && n.metadata_json.amount)    || '';
        return `${actor} a acheté votre ${item === 'prompt' ? 'prompt' : item === 'adn' ? 'ADN' : 'voix'}${amt ? ' · <strong>' + amt + ' Smyles</strong>' : ''}`;
      }
      case 'like':    return `${actor} a liké votre son`;
      case 'follow':  return `${actor} vous suit`;
      case 'message': return `${actor} vous a envoyé un message`;
      case 'trade': {
        // OFFRES-ADN : une notif trade peut être une offre CASH sur un ADN
        // (target_type='adn_offer') — libellés dédiés selon l'action.
        const act = n.metadata_json && n.metadata_json.action;
        const amt = (n.metadata_json && n.metadata_json.amount) || '';
        if (act === 'adn_offer_received')
          return `${actor} te propose <strong>${amt} Smyles</strong> pour ton ADN`;
        if (act === 'adn_offer_accepted')
          return `${actor} a accepté ton offre${amt ? ' · <strong>' + amt + ' Smyles</strong>' : ''} — ADN livré 🧬`;
        if (act === 'adn_offer_rejected')
          return `${actor} a refusé ton offre sur son ADN`;
        return `${actor} vous propose un échange d'ADN`;
      }
      case 'system':  return _esc((n.metadata_json && n.metadata_json.text) || 'Notification système');
      default:        return `Notification de ${actor}`;
    }
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

  // ── Fetchers notifications (cloche — hors messages) ──────────────────────

  async function _fetchUnreadCount() {
    try {
      if (!(window.getAuthToken && window.getAuthToken())) return;
      const data = await apiFetch('/me/notifications?limit=50');
      const items = data.items || [];
      // Cloche = tout sauf messages (messages vont dans l'enveloppe)
      _notifState.items = items.filter(n => n.type !== 'message');
      _notifState.count = _notifState.items.filter(n => !n.read_at).length;
      _updateBellBadge();
    } catch (_) {}
  }

  async function _fetchNotifs() {
    try {
      if (!(window.getAuthToken && window.getAuthToken())) return;
      const data = await apiFetch('/me/notifications?limit=50');
      const items = data.items || [];
      _notifState.items = items.filter(n => n.type !== 'message');
      _notifState.count = _notifState.items.filter(n => !n.read_at).length;
    } catch (_) {}
  }

  function _startNotifPoll() {
    _stopNotifPoll();
    _notifState.pollTimer = setInterval(_fetchUnreadCount, 30000);
  }

  function _stopNotifPoll() {
    if (_notifState.pollTimer) { clearInterval(_notifState.pollTimer); _notifState.pollTimer = null; }
  }

  function _updateBellBadge() {
    const badge = document.getElementById('stb-notif-badge');
    if (!badge) return;
    const n = _notifState.count;
    badge.textContent = n > 99 ? '99+' : String(n);
    badge.style.display = n > 0 ? 'flex' : 'none';
  }

  // ── Fetchers messagerie topbar (enveloppe) ────────────────────────────────

  async function _fetchMsgThreads() {
    try {
      if (!(window.getAuthToken && window.getAuthToken())) return;
      const data = await apiFetch('/messages/threads');
      _msgState.threads = Array.isArray(data) ? data : [];
      _msgState.count   = _msgState.threads.reduce((s, t) => s + (t.unread_count || 0), 0);
      _updateMsgBadge();
    } catch (_) {}
  }

  function _startMsgPoll() {
    _stopMsgPoll();
    _msgState.pollTimer = setInterval(_fetchMsgThreads, 15000);
  }

  function _stopMsgPoll() {
    if (_msgState.pollTimer) { clearInterval(_msgState.pollTimer); _msgState.pollTimer = null; }
  }

  function _updateMsgBadge() {
    const badge = document.getElementById('stb-msg-badge');
    if (!badge) return;
    const n = _msgState.count;
    badge.textContent = n > 99 ? '99+' : String(n);
    badge.style.display = n > 0 ? 'flex' : 'none';
  }

  function _renderMsgDropdown() {
    const panel = document.getElementById('stb-msg-panel');
    if (!panel) return;
    let html;
    if (!_msgState.threads.length) {
      html = `<div class="stb-msg-empty">Aucune conversation</div>`;
    } else {
      html = _msgState.threads.map(t => {
        const init    = (t.other_user_name || '?')[0].toUpperCase();
        const unread  = t.unread_count > 0;
        const preview = t.last_message_preview || '';
        const time    = _timeAgo(t.last_message_at);
        return `
          <button class="stb-msg-thread${unread ? ' stb-msg-unread' : ''}" type="button"
                  onclick="window.SmyleTopbar.openMsgThread('${_esc(t.other_user_id)}','${_esc(t.other_user_name || '')}')">
            <span class="stb-msg-avatar">${_esc(init)}</span>
            <span class="stb-msg-info">
              <span class="stb-msg-name">${_esc(t.other_user_name || 'Utilisateur')}</span>
              <span class="stb-msg-preview">${_esc(preview)}</span>
            </span>
            <span class="stb-msg-meta">
              <span class="stb-msg-time">${_esc(time)}</span>
              ${unread ? `<span class="stb-msg-dot"></span>` : ''}
            </span>
          </button>`;
      }).join('');
    }
    panel.innerHTML = `
      <div class="stb-msg-header">
        <span class="stb-msg-title">Messages</span>
      </div>
      <div class="stb-msg-list">${html}</div>`;
    panel.hidden = false;
    _msgState.open = true;
    // Réinitialise le badge quand on ouvre le dropdown
    _msgState.count = 0;
    _updateMsgBadge();
  }

  function _closeMsgPanel() {
    const panel = document.getElementById('stb-msg-panel');
    if (panel) panel.hidden = true;
    _msgState.open = false;
  }

  async function _toggleMsgPanel(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    if (_msgState.open) {
      _closeMsgPanel();
    } else {
      await _fetchMsgThreads();
      _renderMsgDropdown();
    }
  }

  function _openMsgThread(userId, userName) {
    _closeMsgPanel();
    if (window.SmyleMessaging) {
      window.SmyleMessaging.open(userId);
    }
  }

  function _closeMsgOnOutside(ev) {
    if (!_msgState.open) return;
    const wrap = document.getElementById('stb-msg-wrap');
    if (wrap && wrap.contains(ev.target)) return;
    _closeMsgPanel();
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

    // Enveloppe messagerie (connecté uniquement)
    const msgHtml = user ? `
      <div class="stb-msg-wrap" id="stb-msg-wrap">
        <button class="stb-msg-btn" type="button"
                onclick="window.SmyleTopbar.toggleMsg(event)"
                title="Messages" aria-label="Messages">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
               stroke="currentColor" stroke-width="2.2" aria-hidden="true">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
            <polyline points="22,6 12,13 2,6"/>
          </svg>
          <span class="stb-msg-badge" id="stb-msg-badge" style="display:none">0</span>
        </button>
        <div class="stb-msg-panel" id="stb-msg-panel" hidden></div>
      </div>` : '';

    // Cloche notifications (connecté uniquement — hors messages)
    const bellHtml = user ? `
      <div class="stb-notif-wrap" id="stb-notif-wrap">
        <button class="stb-notif-btn" type="button"
                onclick="window.SmyleTopbar.toggleNotif(event)"
                title="Notifications" aria-label="Notifications">
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none"
               stroke="currentColor" stroke-width="2.2" aria-hidden="true">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
          <span class="stb-notif-badge" id="stb-notif-badge"
                style="display:none">0</span>
        </button>
        <div class="stb-notif-panel" id="stb-notif-panel" hidden></div>
      </div>` : '';

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
        <button class="stb-mymix" type="button" onclick="if(window.openBoutique)window.openBoutique()" title="Boutique" style="gap:6px;">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 9l1-5h16l1 5"/><path d="M4 9v11h16V9"/><path d="M9 13h6"/></svg>
          <span class="stb-mymix-label">Boutique</span>
        </button>
        ${mixHtml}
        ${msgHtml}
        ${bellHtml}
        ${authHtml}
      </div>
    `;
  }

  // ── Notifications panel ───────────────────────────────────────────────────

  function _renderNotifItems() {
    if (!_notifState.items.length) {
      return `<div class="stb-notif-empty">Aucune notification</div>`;
    }
    return _notifState.items.map(n => {
      const meta    = NOTIF_META[n.type] || NOTIF_META.system;
      const unread  = !n.read_at;
      const text    = _notifText(n);
      const time    = _timeAgo(n.created_at);

      // Lien contextuel selon la cible
      let href = '#';
      let extraClick = '';
      if (n.type === 'message' && n.actor_id) {
        // Ouvre le panel messaging si dispo sur la page, sinon ignore
        extraClick = `if(window.SmyleMessaging){event.preventDefault();window.SmyleMessaging.open('${_esc(n.actor_id)}');}`;
      } else if (n.type === 'follow' && n.actor_id) {
        href = `/@${_esc((n.actor_name||'').toLowerCase().replace(/[^a-z0-9]+/g,'-'))}`;
      } else if (n.type === 'trade' && n.target_type === 'adn_offer') {
        // OFFRES-ADN : ouvre l'écran d'offre cash (accepter / refuser /
        // annuler selon le rôle), sans quitter la page.
        href = '/dashboard#sec-trades';
        if (n.target_id) {
          extraClick = `if(window.SmyleTopbar){event.preventDefault();window.SmyleTopbar.openAdnOfferView('${_esc(n.target_id)}');}`;
        }
      } else if (n.type === 'trade') {
        // Ouvre l'écran de proposition directement (offre = n.target_id),
        // sans quitter la page. Fallback : section échanges du dashboard.
        href = '/dashboard#sec-trades';
        if (n.target_id) {
          extraClick = `if(window.SmyleTopbar){event.preventDefault();window.SmyleTopbar.openTradeView('${_esc(n.target_id)}');}`;
        }
      } else if (n.type === 'purchase' && n.target_type === 'prompt') {
        href = '/dashboard';
      }

      const followBtn = (n.type === 'follow' && n.actor_id) ? `
        <button class="stb-notif-followback" type="button"
                data-actor="${_esc(n.actor_id)}"
                onclick="window.SmyleTopbar.followBack(event, '${_esc(n.actor_id)}')">
          + Suivre
        </button>` : '';

      return `
        <a class="stb-notif-item${unread ? ' stb-notif-unread' : ''}"
           href="${href}"
           onclick="window.SmyleTopbar.markRead(event, '${_esc(n.id)}');${extraClick}">
          <span class="stb-notif-icon" style="--ni-color:${meta.color}">${meta.icon}</span>
          <span class="stb-notif-body">
            <span class="stb-notif-text">${text}</span>
            <span class="stb-notif-time">${time}</span>
          </span>
          ${followBtn}
        </a>`;
    }).join('');
  }

  async function _openNotifPanel() {
    await _fetchNotifs();
    const panel = document.getElementById('stb-notif-panel');
    if (!panel) return;
    panel.innerHTML = `
      <div class="stb-notif-header">
        <span class="stb-notif-title">Notifications</span>
        <button type="button" onclick="window.SmyleTopbar.markAllRead(event)"
                style="margin-left:auto;background:none;border:none;color:#cc88ff;font-size:12px;cursor:pointer">Tout effacer</button>
      </div>
      <div class="stb-notif-list" id="stb-notif-list">
        ${_renderNotifItems()}
      </div>`;
    panel.hidden = false;
    _notifState.open = true;
    // Badge disparaît à l'ouverture — les highlights bleus restent sur les items
    _notifState.count = 0;
    _updateBellBadge();
  }

  function _closeNotifPanel() {
    const panel = document.getElementById('stb-notif-panel');
    if (panel) panel.hidden = true;
    _notifState.open = false;
  }

  async function _toggleNotifPanel(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    if (_notifState.open) {
      _closeNotifPanel();
    } else {
      await _openNotifPanel();
    }
  }

  async function _markAllRead(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    try {
      await apiFetch('/me/notifications/read-all', { method: 'POST' });
      _notifState.count = 0;
      _notifState.items = _notifState.items.map(n => ({ ...n, read_at: new Date().toISOString() }));
      _updateBellBadge();
      const list = document.getElementById('stb-notif-list');
      if (list) list.innerHTML = _renderNotifItems();
    } catch (_) {}
  }

  async function _markRead(ev, id) {
    // Retire le highlight bleu sur l'item cliqué sans fermer le panneau
    if (ev && ev.currentTarget) {
      const item = ev.currentTarget;
      item.classList.remove('stb-notif-unread');
    }
    // Marque lu en arrière-plan
    apiFetch(`/me/notifications/${id}/read`, { method: 'PATCH' }).catch(() => {});
    _notifState.items = _notifState.items.map(n =>
      n.id === id ? { ...n, read_at: new Date().toISOString() } : n);
    // Badge déjà à 0 depuis l'ouverture — on ne le touche pas
  }

  async function _followBack(ev, actorId) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    const btn = ev && ev.currentTarget;
    if (btn) { btn.textContent = '...'; btn.disabled = true; }
    try {
      await apiFetch(`/users/${actorId}/follow`, { method: 'POST' });
      if (btn) { btn.textContent = 'Suivi ✓'; btn.classList.add('stb-notif-followback-done'); }
    } catch (_) {
      if (btn) { btn.textContent = 'Déjà suivi'; btn.disabled = true; }
    }
  }

  function _closeNotifOnOutside(ev) {
    if (!_notifState.open) return;
    const wrap = document.getElementById('stb-notif-wrap');
    if (wrap && wrap.contains(ev.target)) return;
    _closeNotifPanel();
  }

  function _renderUserChip(user, mySlug) {
    const name = user.artistName || user.artist_name ||
                 (user.email && user.email.split('@')[0]) || 'Moi';
    const color = user.brandColor || user.brand_color || '#7C3AED';
    const avatarUrl = user.avatarUrl || user.avatar_url || '';
    const avatarInner = avatarUrl
      ? `<img src="${_esc(avatarUrl)}" alt="" />`
      : _esc(_initial(name));

    const profileHref = mySlug ? `/@${mySlug}` : '#';

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
          <a class="stb-drop-item" href="/offres">Offres créateur</a>
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
    // Nettoyage des clés compat legacy si présentes.
    try {
      localStorage.removeItem('smyle_watt_profile');
      localStorage.removeItem('smyle_watt_tracks');
    } catch (_) {}
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

    // Sync badge notif sans refetch (count déjà en mémoire).
    _updateBellBadge();

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
      if (_state.user) {
        await _fetchUnreadCount();
        await _fetchMsgThreads();
        _startNotifPoll();
        _startMsgPoll();
      } else {
        _stopNotifPoll();
        _stopMsgPoll();
        _notifState.count = 0;
        _msgState.count   = 0;
      }
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
    // Clic outside → ferme les dropdowns. On le pose une seule fois.
    document.addEventListener('click', (ev) => {
      _closeDropOnOutside(ev);
      _closeNotifOnOutside(ev);
      _closeMsgOnOutside(ev);
    });
    // Échap → idem.
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') {
        if (_state.dropOpen)  _closeDropOnOutside(ev);
        if (_notifState.open) _closeNotifPanel();
        if (_msgState.open)   _closeMsgPanel();
      }
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
      await _fetchUnreadCount();
      await _fetchMsgThreads();
      _startNotifPoll();
      _startMsgPoll();
    }
    _render();
  }

  // ── Écran "Proposition d'échange" (réutilisable : notif + messages) ──────
  // Affiche l'offre (les 2 prompts + écoute) et permet d'accepter / refuser /
  // annuler selon le rôle. Ouvert via SmyleTopbar.openTradeView(offerId).
  async function _openTradeView(offerId) {
    if (!offerId) return;
    let offers = [];
    try { offers = (await apiFetch('/trades/offers/me')) || []; } catch (_) {}
    const o = offers.find(x => String(x.id) === String(offerId));
    if (!o) { alert("Cette proposition d'échange n'est plus disponible."); return; }

    const myId = (_state.user && _state.user.id) ? String(_state.user.id) : null;
    const isReceiver = myId && String(o.receiver_id) === myId;
    const isSender   = myId && String(o.sender_id) === myId;
    const pending = o.status === 'pending';
    const off = o.offered_prompt || {};
    const req = o.requested_prompt || {};
    const esc = (s) => String(s == null ? '' : s).replace(/</g, '&lt;');
    const audio = (p) => (p && p.audio_url)
      ? `<audio controls preload="none" src="${p.audio_url}" style="width:100%;margin-top:6px;height:30px"></audio>` : '';

    let actions;
    if (pending && isReceiver) {
      actions = `
        <button onclick="SmyleTopbar._tradeAct('${o.id}','accept')" style="flex:1;padding:10px;border:none;border-radius:8px;background:#22c55e;color:#fff;font-weight:600;cursor:pointer">✅ Accepter</button>
        <button onclick="SmyleTopbar._tradeAct('${o.id}','reject')" style="flex:1;padding:10px;border:none;border-radius:8px;background:rgba(255,255,255,.1);color:#eee;cursor:pointer">❌ Refuser</button>`;
    } else if (pending && isSender) {
      actions = `<button onclick="SmyleTopbar._tradeAct('${o.id}','cancel')" style="flex:1;padding:10px;border:none;border-radius:8px;background:rgba(255,255,255,.1);color:#eee;cursor:pointer">Annuler ma proposition</button>`;
    } else {
      const lbl = { accepted: '✅ Échange accepté', rejected: '❌ Refusé', cancelled: 'Annulé', expired: '⏳ Expiré' }[o.status] || o.status;
      actions = `<div style="flex:1;text-align:center;opacity:.7;padding:8px">${lbl}</div>`;
    }

    const card = 'background:#0e0e14;border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:10px;margin-bottom:8px';
    const prev = document.getElementById('smyle-tradeview'); if (prev) prev.remove();
    const el = document.createElement('div');
    el.id = 'smyle-tradeview';
    el.style.cssText = 'position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,.65);display:flex;align-items:center;justify-content:center;padding:16px';
    el.innerHTML = `
      <div style="background:#15151c;border:1px solid rgba(255,255,255,.12);border-radius:14px;max-width:440px;width:100%;padding:18px;color:#eee;font-size:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <strong>🔄 Proposition d'échange</strong>
          <button onclick="document.getElementById('smyle-tradeview').remove()" style="background:none;border:none;color:#aaa;font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="opacity:.85;margin-bottom:10px">${isReceiver ? `${esc(o.sender_name || 'Un artiste')} te propose un échange` : 'Ta proposition'}</div>
        <div style="${card}">
          <div style="opacity:.6;font-size:12px">${isReceiver ? 'Tu recevrais' : 'Tu offres'}</div>
          <strong>${esc(off.title) || '—'}</strong> · ${off.price_credits || 0} crédits
          ${audio(off)}
        </div>
        <div style="text-align:center;opacity:.5;margin:2px 0 8px">⇄</div>
        <div style="${card}">
          <div style="opacity:.6;font-size:12px">${isReceiver ? 'Tu donnerais' : 'Tu demandes'}</div>
          <strong>${esc(req.title) || '—'}</strong> · ${req.price_credits || 0} crédits
          ${audio(req)}
        </div>
        ${o.credit_supplement > 0 ? `<div style="opacity:.8;margin-bottom:8px">+ ${o.credit_supplement} crédits ${isReceiver ? 'pour toi' : 'de ta part'}</div>` : ''}
        ${o.message ? `<div style="opacity:.7;font-style:italic;margin-bottom:10px">« ${esc(o.message)} »</div>` : ''}
        <div style="opacity:.55;font-size:12px;margin-bottom:12px">⚠️ Frais de 20% (brûlé) de chaque côté à l'acceptation.</div>
        <div style="display:flex;gap:8px">${actions}</div>
      </div>`;
    el.addEventListener('click', (ev) => { if (ev.target === el) el.remove(); });
    document.body.appendChild(el);
  }

  // ── OFFRES-ADN — Écran « Offre sur ADN » (calque de _openTradeView) ──────
  // Offre CASH sur un ADN : le vendeur accepte/refuse, l'acheteur annule.
  // Ouvert via SmyleTopbar.openAdnOfferView(offerId) (clic notification).
  const _ADN_TYPE_LABELS = {
    playlist_adn: '🎚 ADN de playlist',
    album_adn:    '🎨 ADN d\'album',
    visual_adn:   '🎨 ADN visuel',
    profile_adn:  '🧬 ADN d\'artiste',
  };

  async function _openAdnOfferView(offerId) {
    if (!offerId) return;
    let offers = [];
    try { offers = (await apiFetch('/adn-offers/me')) || []; } catch (_) {}
    const o = offers.find(x => String(x.id) === String(offerId));
    if (!o) { alert("Cette offre n'est plus disponible."); return; }

    const myId = (_state.user && _state.user.id) ? String(_state.user.id) : null;
    const isSeller = myId && String(o.seller_id) === myId;
    const isBuyer  = myId && String(o.buyer_id) === myId;
    const pending  = o.status === 'pending';
    const esc = (s) => String(s == null ? '' : s).replace(/</g, '&lt;');
    const typeLbl = _ADN_TYPE_LABELS[o.target_type] || 'ADN';

    let actions;
    if (pending && isSeller) {
      actions = `
        <button onclick="SmyleTopbar._adnOfferAct('${o.id}','accept')" style="flex:1;padding:10px;border:none;border-radius:8px;background:#22c55e;color:#fff;font-weight:600;cursor:pointer">✅ Accepter · ${o.amount_credits} Smyles</button>
        <button onclick="SmyleTopbar._adnOfferAct('${o.id}','reject')" style="flex:1;padding:10px;border:none;border-radius:8px;background:rgba(255,255,255,.1);color:#eee;cursor:pointer">❌ Refuser</button>`;
    } else if (pending && isBuyer) {
      actions = `<button onclick="SmyleTopbar._adnOfferAct('${o.id}','cancel')" style="flex:1;padding:10px;border:none;border-radius:8px;background:rgba(255,255,255,.1);color:#eee;cursor:pointer">Annuler mon offre</button>`;
    } else {
      const lbl = { accepted: '✅ Offre acceptée — ADN livré', rejected: '❌ Refusée', cancelled: 'Annulée', expired: '⏳ Expirée' }[o.status] || o.status;
      actions = `<div style="flex:1;text-align:center;opacity:.7;padding:8px">${lbl}</div>`;
    }

    const card = 'background:#0e0e14;border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:12px;margin-bottom:10px';
    const prev = document.getElementById('smyle-adnofferview'); if (prev) prev.remove();
    const el = document.createElement('div');
    el.id = 'smyle-adnofferview';
    el.style.cssText = 'position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,.65);display:flex;align-items:center;justify-content:center;padding:16px';
    el.innerHTML = `
      <div style="background:#15151c;border:1px solid rgba(255,255,255,.12);border-radius:14px;max-width:420px;width:100%;padding:18px;color:#eee;font-size:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <strong>🤝 Offre sur ADN</strong>
          <button onclick="document.getElementById('smyle-adnofferview').remove()" style="background:none;border:none;color:#aaa;font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="opacity:.85;margin-bottom:10px">${isSeller
          ? `${esc(o.buyer_name || 'Un artiste')} te propose un montant pour ton ADN`
          : 'Ton offre'}</div>
        <div style="${card}">
          <div style="opacity:.6;font-size:12px">${typeLbl}</div>
          <strong>${esc(o.target_title) || '—'}</strong>
          <div style="margin-top:8px;font-size:18px;font-weight:700;color:#cc88ff">${o.amount_credits} Smyles</div>
        </div>
        ${o.message ? `<div style="opacity:.7;font-style:italic;margin-bottom:10px">« ${esc(o.message)} »</div>` : ''}
        ${pending && isSeller ? `<div style="opacity:.55;font-size:12px;margin-bottom:12px">À l'acceptation : les Smyles sont transférés (moins la commission plateforme) et l'ADN est livré à l'acheteur.</div>` : ''}
        <div style="display:flex;gap:8px">${actions}</div>
      </div>`;
    el.addEventListener('click', (ev) => { if (ev.target === el) el.remove(); });
    document.body.appendChild(el);
  }

  async function _adnOfferAct(offerId, action) {
    try {
      await apiFetch(`/adn-offers/${offerId}/${action}`, { method: 'PATCH' });
      const el = document.getElementById('smyle-adnofferview'); if (el) el.remove();
      alert({ accept: '✅ Offre acceptée — Smyles reçus, ADN livré !',
              reject: 'Offre refusée.',
              cancel: 'Offre annulée.' }[action] || 'Fait.');
      try { _render(); } catch (_) {}
    } catch (err) {
      const d = (err && err.body && err.body.detail) || err.message || 'Erreur';
      alert('Erreur : ' + (typeof d === 'string' ? d : JSON.stringify(d)));
    }
  }

  async function _tradeAct(offerId, action) {
    try {
      await apiFetch(`/trades/offers/${offerId}/${action}`, { method: 'PATCH' });
      const el = document.getElementById('smyle-tradeview'); if (el) el.remove();
      alert({ accept: '✅ Échange accepté !', reject: 'Proposition refusée.', cancel: 'Proposition annulée.' }[action] || 'Fait.');
      try { _render(); } catch (_) {}
    } catch (err) {
      const d = (err && err.body && err.body.detail) || err.message || 'Erreur';
      alert('Erreur : ' + (typeof d === 'string' ? d : JSON.stringify(d)));
    }
  }

  // API publique minimale (appelée depuis les onclick inlines du template).
  window.SmyleTopbar = {
    openTradeView:    _openTradeView,
    openAdnOfferView: _openAdnOfferView,
    _tradeAct:        _tradeAct,
    _adnOfferAct:     _adnOfferAct,
    refresh:     _render,
    clickMix:    _clickMix,
    clickLogin:  _clickLogin,
    logout:      _logout,
    toggleDrop:  _toggleDrop,
    // Notifications (cloche)
    toggleNotif: _toggleNotifPanel,
    markRead:    _markRead,
    markAllRead: _markAllRead,
    followBack:  _followBack,
    // Messagerie (enveloppe)
    toggleMsg:       _toggleMsgPanel,
    openMsgThread:   _openMsgThread,
    // Pour que l'app puisse forcer un refresh après login manuel sans
    // attendre un event (ex. depuis modals/auth.js).
    reloadUser:  async () => { await _fetchMe(); _render(); },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot, { once: true });
  } else {
    _boot();
  }
})();
