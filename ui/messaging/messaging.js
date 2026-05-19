/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/messaging/messaging.js
   Composant messagerie 1:1

   Usage :
     <link rel="stylesheet" href="/ui/messaging/messaging.css" />
     <div id="smyle-messaging"></div>
     <script src="/ui/messaging/messaging.js" defer></script>

   API publique :
     window.SmyleMessaging.open(userId?)  — ouvre l'inbox (optionnel: thread direct)
     window.SmyleMessaging.close()        — ferme
     window.SmyleMessaging.toggle()       — bascule
   ───────────────────────────────────────────────────────────────────────── */

(function initSmyleMessaging() {
  'use strict';
  if (typeof window === 'undefined') return;
  if (window.__smyleMessagingInited) return;
  window.__smyleMessagingInited = true;

  // ── State ──────────────────────────────────────────────────────────────────
  const _s = {
    open:           false,
    threads:        [],
    activeThread:   null,   // { id, other_user_id, other_user_name, messages:[] }
    sending:        false,
    loadingThreads: false,
    loadingMsgs:    false,
  };

  // ── Helpers ────────────────────────────────────────────────────────────────
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
    return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
  }

  function _auth() {
    return !!(window.getAuthToken && window.getAuthToken());
  }

  // ── API calls ──────────────────────────────────────────────────────────────
  async function _loadThreads() {
    if (!_auth()) return;
    _s.loadingThreads = true;
    _renderInbox();
    try {
      const data = await apiFetch('/messages/threads');
      _s.threads = data || [];
    } catch (e) {
      _s.threads = [];
    }
    _s.loadingThreads = false;
    _renderInbox();
  }

  async function _openThread(userId, userName) {
    _s.loadingMsgs = true;
    _renderThreadView();
    try {
      // Crée ou récupère le thread
      const thread = await apiFetch(`/messages/threads/${userId}`, { method: 'POST' });
      const msgs   = await apiFetch(`/messages/threads/${thread.id}`);
      _s.activeThread = {
        id:             thread.id,
        other_user_id:  thread.other_user_id  || userId,
        other_user_name: thread.other_user_name || userName || 'Utilisateur',
        messages:       msgs.messages || [],
      };
      // Marquer lu en background
      apiFetch(`/messages/threads/${thread.id}/read`, { method: 'POST' }).catch(() => {});
    } catch (_) {}
    _s.loadingMsgs = false;
    _renderThreadView();
    _scrollBottom();
  }

  async function _sendMessage(content) {
    if (!content.trim() || !_s.activeThread || _s.sending) return;
    _s.sending = true;
    const input = document.getElementById('msg-input');
    if (input) input.disabled = true;
    try {
      const msg = await apiFetch(`/messages/threads/${_s.activeThread.id}/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: content.trim() }),
      });
      _s.activeThread.messages.push(msg);
      _renderMessages();
      _scrollBottom();
      if (input) { input.value = ''; input.style.height = 'auto'; }
    } catch (_) {}
    _s.sending = false;
    if (input) input.disabled = false;
    if (input) input.focus();
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  function _ensureContainer() {
    let el = document.getElementById('smyle-messaging');
    if (!el) {
      el = document.createElement('div');
      el.id = 'smyle-messaging';
      document.body.appendChild(el);
    }
    return el;
  }

  function _buildShell() {
    const el = _ensureContainer();
    el.innerHTML = `
      <div class="msg-overlay" id="msg-overlay" onclick="SmyleMessaging.close()"></div>
      <div class="msg-panel" id="msg-panel" role="dialog" aria-label="Messagerie">
        <div class="msg-pane" id="msg-pane-inbox"></div>
        <div class="msg-pane msg-pane-thread hidden" id="msg-pane-thread"></div>
      </div>`;
    _renderInbox();
  }

  function _renderInbox() {
    const pane = document.getElementById('msg-pane-inbox');
    if (!pane) return;

    if (_s.loadingThreads) {
      pane.innerHTML = `
        <div class="msg-header">
          <span class="msg-title">Messages</span>
          <button class="msg-close-btn" onclick="SmyleMessaging.close()">✕</button>
        </div>
        <div class="msg-loading">Chargement…</div>`;
      return;
    }

    const threadHtml = _s.threads.length === 0
      ? `<div class="msg-empty">Aucune conversation pour l'instant.</div>`
      : _s.threads.map(t => `
          <button class="msg-thread-row" type="button"
                  onclick="SmyleMessaging._selectThread('${_esc(t.other_user_id)}', '${_esc(t.other_user_name)}')">
            <span class="msg-thread-avatar">${_esc((t.other_user_name || '?')[0].toUpperCase())}</span>
            <span class="msg-thread-info">
              <span class="msg-thread-name">${_esc(t.other_user_name || 'Utilisateur')}</span>
              <span class="msg-thread-preview">${_esc(t.last_message_preview || '')}</span>
            </span>
            ${t.unread_count ? `<span class="msg-thread-badge">${t.unread_count}</span>` : ''}
            <span class="msg-thread-time">${_timeAgo(t.last_message_at)}</span>
          </button>`).join('');

    pane.innerHTML = `
      <div class="msg-header">
        <span class="msg-title">Messages</span>
        <button class="msg-close-btn" onclick="SmyleMessaging.close()">✕</button>
      </div>
      <div class="msg-thread-list">${threadHtml}</div>`;
  }

  function _renderThreadView() {
    const pane = document.getElementById('msg-pane-thread');
    if (!pane) return;

    if (_s.loadingMsgs || !_s.activeThread) {
      pane.innerHTML = `
        <div class="msg-header">
          <button class="msg-back-btn" type="button" onclick="SmyleMessaging._backToInbox()">←</button>
          <span class="msg-title">${_s.activeThread ? _esc(_s.activeThread.other_user_name) : '…'}</span>
          <button class="msg-close-btn" onclick="SmyleMessaging.close()">✕</button>
        </div>
        <div class="msg-loading">Chargement…</div>`;
      return;
    }

    pane.innerHTML = `
      <div class="msg-header">
        <button class="msg-back-btn" type="button" onclick="SmyleMessaging._backToInbox()">←</button>
        <span class="msg-title">${_esc(_s.activeThread.other_user_name)}</span>
        <button class="msg-close-btn" onclick="SmyleMessaging.close()">✕</button>
      </div>
      <div class="msg-messages" id="msg-messages"></div>
      <div class="msg-composer">
        <textarea class="msg-input" id="msg-input" rows="1"
          placeholder="Votre message…"
          onkeydown="SmyleMessaging._onKey(event)"
          oninput="SmyleMessaging._autoGrow(this)"></textarea>
        <button class="msg-send-btn" type="button"
                onclick="SmyleMessaging._onSend()">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
               stroke="currentColor" stroke-width="2.5">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>`;

    _renderMessages();
  }

  function _renderMessages() {
    const el = document.getElementById('msg-messages');
    if (!el || !_s.activeThread) return;
    const myId = _currentUserId();
    if (!_s.activeThread.messages.length) {
      el.innerHTML = `<div class="msg-empty">Démarrez la conversation !</div>`;
      return;
    }
    el.innerHTML = _s.activeThread.messages.map(m => {
      const mine = m.sender_id === myId;
      return `
        <div class="msg-bubble ${mine ? 'msg-bubble-me' : 'msg-bubble-other'}">
          <span class="msg-bubble-text">${_esc(m.content)}</span>
          <span class="msg-bubble-time">${_timeAgo(m.created_at)}</span>
        </div>`;
    }).join('');
  }

  function _scrollBottom() {
    setTimeout(() => {
      const el = document.getElementById('msg-messages');
      if (el) el.scrollTop = el.scrollHeight;
    }, 30);
  }

  function _currentUserId() {
    // SmyleTopbar expose _state.user via window.SmyleTopbar
    // On lit depuis le token JWT si disponible, sinon on parse l'objet user
    try {
      const tok = window.getAuthToken && window.getAuthToken();
      if (!tok) return null;
      const payload = JSON.parse(atob(tok.split('.')[1]));
      return payload.sub || payload.user_id || null;
    } catch (_) { return null; }
  }

  // ── Navigation ─────────────────────────────────────────────────────────────
  function _showPane(id) {
    ['msg-pane-inbox', 'msg-pane-thread'].forEach(pid => {
      const p = document.getElementById(pid);
      if (p) p.classList.toggle('hidden', pid !== id);
    });
  }

  function _selectThread(userId, userName) {
    _showPane('msg-pane-thread');
    _s.activeThread = null;
    _s.loadingMsgs = true;
    _renderThreadView();
    _openThread(userId, userName);
  }

  function _backToInbox() {
    _s.activeThread = null;
    _showPane('msg-pane-inbox');
    _loadThreads();
  }

  // ── Input handlers ─────────────────────────────────────────────────────────
  function _onKey(ev) {
    if (ev.key === 'Enter' && !ev.shiftKey) {
      ev.preventDefault();
      _onSend();
    }
  }

  function _autoGrow(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  function _onSend() {
    const input = document.getElementById('msg-input');
    if (!input) return;
    _sendMessage(input.value);
  }

  // ── Open / Close ───────────────────────────────────────────────────────────
  function _open(userId) {
    if (!_auth()) {
      if (window.openAuthModal) window.openAuthModal('login');
      return;
    }
    _s.open = true;
    const el = _ensureContainer();
    el.classList.add('msg-visible');
    if (!document.getElementById('msg-panel')) _buildShell();
    if (userId) {
      _selectThread(userId, '');
    } else {
      _showPane('msg-pane-inbox');
      _loadThreads();
    }
  }

  function _close() {
    _s.open = false;
    const el = document.getElementById('smyle-messaging');
    if (el) el.classList.remove('msg-visible');
  }

  function _toggle(userId) {
    _s.open ? _close() : _open(userId);
  }

  // ── Public API ─────────────────────────────────────────────────────────────
  window.SmyleMessaging = {
    open:          _open,
    close:         _close,
    toggle:        _toggle,
    _selectThread: _selectThread,
    _backToInbox:  _backToInbox,
    _onKey:        _onKey,
    _autoGrow:     _autoGrow,
    _onSend:       _onSend,
  };

})();
