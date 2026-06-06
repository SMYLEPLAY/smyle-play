/* ─────────────────────────────────────────────────────────────────────────
   ui/core/page-services.js
   Messagerie + Notifications pour les pages sans topbar.js partagée
   (index.html, dashboard.html).

   Usage : inclure après messaging.js et api.js
   ───────────────────────────────────────────────────────────────────────── */
(function initPageServices() {
  'use strict';
  if (window.__pageServicesInited) return;
  window.__pageServicesInited = true;

  const _s = {
    notifItems:  [],
    notifCount:  0,
    notifOpen:   false,
    msgThreads:  [],
    msgCount:    0,
    msgOpen:     false,
    pollTimer:   null,
  };

  function _auth() {
    return !!(window.getAuthToken && window.getAuthToken());
  }

  function _hdr() {
    const h = { 'Accept': 'application/json' };
    const t = window.getAuthToken && window.getAuthToken();
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
  }

  function _esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function _timeAgo(iso) {
    if (!iso) return '';
    const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
    if (diff < 60)    return 'à l\'instant';
    if (diff < 3600)  return Math.floor(diff / 60) + ' min';
    if (diff < 86400) return Math.floor(diff / 3600) + ' h';
    return Math.floor(diff / 86400) + ' j';
  }

  const NOTIF_META = {
    purchase: { icon: '💸', color: '#22c55e' },
    like:     { icon: '❤️', color: '#ef4444' },
    follow:   { icon: '👤', color: '#3b82f6' },
    trade:    { icon: '🔄', color: '#f97316' },
    system:   { icon: '⚙️', color: '#6b7280' },
  };

  function _notifText(n) {
    const actor = _esc(n.actor_name || 'Quelqu\'un');
    switch (n.type) {
      case 'purchase': return `${actor} a acheté votre item`;
      case 'like':     return `${actor} a liké votre son`;
      case 'follow':   return `${actor} vous suit`;
      case 'trade':    return `${actor} vous propose un échange d'ADN`;
      case 'system':   return _esc((n.metadata_json && n.metadata_json.text) || 'Notification système');
      default:         return `Notification de ${actor}`;
    }
  }

  // ── Fetchers ──────────────────────────────────────────────────────────────

  async function _poll() {
    if (!_auth()) return;
    try {
      const r = await fetch('/me/notifications?limit=50', { headers: _hdr(), credentials: 'same-origin' });
      if (r.ok) {
        const data = await r.json();
        const items = (data.items || []).filter(n => n.type !== 'message');
        _s.notifItems = items;
        _s.notifCount = items.filter(n => !n.read_at).length;
        _updateNotifBadge();
      }
    } catch (_) {}
    try {
      const r = await fetch('/messages/threads', { headers: _hdr(), credentials: 'same-origin' });
      if (r.ok) {
        const data = await r.json();
        _s.msgThreads = Array.isArray(data) ? data : [];
        _s.msgCount   = _s.msgThreads.reduce((s, t) => s + (t.unread_count || 0), 0);
        _updateMsgBadge();
      }
    } catch (_) {}
  }

  // ── Badges ────────────────────────────────────────────────────────────────

  function _updateNotifBadge() {
    const b = document.getElementById('page-notif-badge');
    if (!b) return;
    const n = _s.notifCount;
    b.textContent = n > 99 ? '99+' : String(n);
    b.style.display = n > 0 ? 'flex' : 'none';
  }

  function _updateMsgBadge() {
    const b = document.getElementById('page-msg-badge');
    if (!b) return;
    const n = _s.msgCount;
    b.textContent = n > 99 ? '99+' : String(n);
    b.style.display = n > 0 ? 'flex' : 'none';
  }

  // ── Panels notifs ─────────────────────────────────────────────────────────

  function _renderNotifPanel() {
    const panel = document.getElementById('page-notif-panel');
    if (!panel) return;
    let html;
    if (!_s.notifItems.length) {
      html = '<div class="stb-notif-empty">Aucune notification</div>';
    } else {
      html = _s.notifItems.map(n => {
        const meta   = NOTIF_META[n.type] || NOTIF_META.system;
        const unread = !n.read_at;
        const text   = _notifText(n);
        const time   = _timeAgo(n.created_at);
        // Notif d'échange → ouvre l'écran de proposition (voir + écouter + accepter).
        const tradeClick = (n.type === 'trade' && n.target_id)
          ? `;if(window.SmyleTradeView){SmyleTradeView.open('${_esc(n.target_id)}');}`
          : '';
        return `
          <div class="stb-notif-item${unread ? ' stb-notif-unread' : ''}"
               onclick="window.__pageMarkRead('${_esc(n.id)}', this)${tradeClick}">
            <span class="stb-notif-icon" style="--ni-color:${meta.color}">${meta.icon}</span>
            <span class="stb-notif-body">
              <span class="stb-notif-text">${text}</span>
              <span class="stb-notif-time">${time}</span>
            </span>
          </div>`;
      }).join('');
    }
    panel.innerHTML = `
      <div class="stb-notif-header">
        <span class="stb-notif-title">Notifications</span>
      </div>
      <div class="stb-notif-list">${html}</div>`;
    panel.hidden = false;
    _s.notifOpen  = true;
    // Badge disparaît à l'ouverture
    _s.notifCount = 0;
    _updateNotifBadge();
  }

  function _closeNotifPanel() {
    const p = document.getElementById('page-notif-panel');
    if (p) p.hidden = true;
    _s.notifOpen = false;
  }

  window.__pageToggleNotif = function(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    _closeMsgPanel();
    _s.notifOpen ? _closeNotifPanel() : _renderNotifPanel();
  };

  window.__pageMarkRead = function(id, el) {
    if (el) el.classList.remove('stb-notif-unread');
    fetch(`/me/notifications/${id}/read`, { method: 'PATCH', headers: _hdr(), credentials: 'same-origin' }).catch(() => {});
    _s.notifItems = _s.notifItems.map(n => n.id === id ? { ...n, read_at: new Date().toISOString() } : n);
  };

  // ── Panel messages ────────────────────────────────────────────────────────

  function _renderMsgPanel() {
    const panel = document.getElementById('page-msg-panel');
    if (!panel) return;
    let html;
    if (!_s.msgThreads.length) {
      html = '<div class="stb-msg-empty">Aucune conversation</div>';
    } else {
      html = _s.msgThreads.map(t => {
        const init   = (t.other_user_name || '?')[0].toUpperCase();
        const unread = t.unread_count > 0;
        const time   = _timeAgo(t.last_message_at);
        return `
          <button class="stb-msg-thread${unread ? ' stb-msg-unread' : ''}" type="button"
                  onclick="window.__pageOpenThread('${_esc(t.other_user_id)}')">
            <span class="stb-msg-avatar">${_esc(init)}</span>
            <span class="stb-msg-info">
              <span class="stb-msg-name">${_esc(t.other_user_name || 'Utilisateur')}</span>
              <span class="stb-msg-preview">${_esc(t.last_message_preview || '')}</span>
            </span>
            <span class="stb-msg-meta">
              <span class="stb-msg-time">${_esc(time)}</span>
              ${unread ? '<span class="stb-msg-dot"></span>' : ''}
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
    _s.msgOpen   = true;
    _s.msgCount  = 0;
    _updateMsgBadge();
  }

  function _closeMsgPanel() {
    const p = document.getElementById('page-msg-panel');
    if (p) p.hidden = true;
    _s.msgOpen = false;
  }

  window.__pageToggleMsg = function(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    _closeNotifPanel();
    _s.msgOpen ? _closeMsgPanel() : _renderMsgPanel();
  };

  window.__pageOpenThread = function(userId) {
    _closeMsgPanel();
    if (window.SmyleMessaging) window.SmyleMessaging.open(userId);
  };

  // ── Fermeture sur clic extérieur ─────────────────────────────────────────

  document.addEventListener('click', (ev) => {
    if (_s.notifOpen) {
      const w = document.getElementById('page-notif-btn');
      const p = document.getElementById('page-notif-panel');
      if (w && !w.contains(ev.target) && p && !p.contains(ev.target)) _closeNotifPanel();
    }
    if (_s.msgOpen) {
      const w = document.getElementById('page-msg-btn');
      const p = document.getElementById('page-msg-panel');
      if (w && !w.contains(ev.target) && p && !p.contains(ev.target)) _closeMsgPanel();
    }
  });

  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') { _closeNotifPanel(); _closeMsgPanel(); }
  });

  // ── Boot ──────────────────────────────────────────────────────────────────

  async function _boot() {
    if (!_auth()) return;
    const services  = document.getElementById('page-icon-services');
    const logoutBtn = document.getElementById('header-logout-btn');
    if (services)  services.style.display  = 'flex';
    if (logoutBtn) logoutBtn.style.display = 'inline-flex';
    await _poll();
    _s.pollTimer = setInterval(_poll, 30000);
  }

  // Expose pour les onclick inline
  window.pageToggleMsg   = window.__pageToggleMsg;
  window.pageToggleNotif = window.__pageToggleNotif;

  // ── Refresh public — appelé par auth.js après login / logout ─────────────
  // Permet d'afficher (ou masquer) les icônes sans recharger la page, même
  // si _boot() avait déjà tourné à froid sans token.
  function _refreshAuth() {
    const services  = document.getElementById('page-icon-services');
    const logoutBtn = document.getElementById('header-logout-btn');
    if (_auth()) {
      if (services)  services.style.display  = 'flex';
      if (logoutBtn) logoutBtn.style.display = 'inline-flex';
      // Lance le polling si pas encore démarré
      if (!_s.pollTimer) {
        _poll();
        _s.pollTimer = setInterval(_poll, 30000);
      }
    } else {
      if (services)  services.style.display  = 'none';
      if (logoutBtn) logoutBtn.style.display = 'none';
      if (_s.pollTimer) { clearInterval(_s.pollTimer); _s.pollTimer = null; }
    }
  }

  window.SmylePageServices = { refresh: _refreshAuth };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot, { once: true });
  } else {
    _boot();
  }
})();
