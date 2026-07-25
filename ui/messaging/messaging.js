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
    activeThread:   null,   // { id, other_user_id, other_user_name, myId, myColor, otherColor, messages:[] }
    sending:        false,
    loadingThreads: false,
    loadingMsgs:    false,
    // Cache utilisateur courant (évite un fetch par thread)
    _myId:    null,
    _myColor: null,
  };

  // ── Helpers ────────────────────────────────────────────────────────────────
  function _esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  // Couleur déterministe à partir d'un ID (fallback si pas de brand_color)
  function _colorFromId(id) {
    let h = 0;
    for (let i = 0; i < (id || '').length; i++) {
      h = ((h << 5) - h) + (id || '').charCodeAt(i);
      h |= 0;
    }
    return `hsl(${Math.abs(h) % 360}, 60%, 55%)`;
  }

  // Fetch + cache ID réel et couleur de l'utilisateur courant
  // IMPORTANT : le JWT sub = email (pas UUID), on lit donc /users/me
  async function _getMyInfo() {
    if (_s._myId && _s._myColor) return { id: _s._myId, color: _s._myColor };
    try {
      const me = await apiFetch('/users/me');
      _s._myId    = me.id    ? String(me.id)    : null;
      _s._myColor = me.brand_color || me.brandColor || '#7C3AED';
    } catch (_) {
      _s._myColor = '#7C3AED';
    }
    return { id: _s._myId, color: _s._myColor };
  }

  // Fetch couleur de marque d'un autre utilisateur
  async function _getUserColor(userId) {
    try {
      const u = await apiFetch(`/users/${userId}`);
      return u.brand_color || u.brandColor || _colorFromId(userId);
    } catch (_) {
      return _colorFromId(userId);
    }
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
      // 1. Crée ou récupère le thread
      const thread = await apiFetch(`/messages/threads/${userId}`, { method: 'POST' });
      const otherUid = thread.other_user_id || userId;

      // 2. Messages (critique) + infos utilisateurs (couleurs) en parallèle
      const [msgs, myInfo, otherColor] = await Promise.all([
        apiFetch(`/messages/threads/${thread.id}`),
        _getMyInfo().catch(() => ({ id: null, color: '#7C3AED' })),
        _getUserColor(otherUid).catch(() => _colorFromId(otherUid)),
      ]);

      _s.activeThread = {
        id:              thread.id,
        other_user_id:   otherUid,
        other_user_name: thread.other_user_name || userName || 'Utilisateur',
        messages:        msgs.messages || [],
        myId:            myInfo.id,       // UUID réel pour comparer sender_id
        myColor:         myInfo.color,
        otherColor,
      };
      // Marquer lu en background
      apiFetch(`/messages/threads/${thread.id}/read`, { method: 'POST' }).catch(() => {});
    } catch (e) {
      console.error('[SmyleMessaging] _openThread error', e);
    }
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
              <span class="msg-thread-preview">${(t.last_message_preview || '').indexOf('__TRADE_OFFER__') === 0 ? '🔄 Proposition d\'échange' : _esc(t.last_message_preview || '')}</span>
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

    // MODE LANCEMENT — TROC masqué : l'option « Proposer un échange » n'est pas
    // rendue tant que l'item n'est pas VISIBLE. Défensif : window.WATT_LAUNCH
    // absent → masqué. Le menu ⋮ ne contenant que cette action, on masque le
    // bouton ⋮ et son conteneur ensemble pour ne pas laisser un menu vide.
    const _trocMenu = (window.WATT_LAUNCH && window.WATT_LAUNCH.troc) ? `
        <button class="msg-menu-btn" type="button" title="Actions sur cette conversation" onclick="SmyleMessaging._toggleConvMenu(event)"
                style="background:none;border:none;color:rgba(255,255,255,.8);font-size:22px;font-weight:700;cursor:pointer;padding:2px 8px;line-height:1">⋮</button>
        <div id="msg-conv-menu" style="display:none;position:absolute;top:100%;right:8px;z-index:100;min-width:190px;background:#1c1c24;border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:6px;box-shadow:0 6px 20px rgba(0,0,0,.45)">
          <button type="button" onclick="SmyleMessaging._openTradeFromConv()"
                  style="display:block;width:100%;text-align:left;background:none;border:none;color:#eee;padding:8px 10px;border-radius:6px;cursor:pointer;font-size:13px">🔄 Proposer un échange</button>
        </div>` : '';

    pane.innerHTML = `
      <div class="msg-header" style="position:relative">
        <button class="msg-back-btn" type="button" onclick="SmyleMessaging._backToInbox()">←</button>
        <span class="msg-title">${_esc(_s.activeThread.other_user_name)}</span>
        ${_trocMenu}
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

    // Utilise myId stocké dans activeThread (UUID réel depuis /users/me)
    // NE PAS lire le JWT sub qui contient l'email, pas l'UUID
    const myId       = _s.activeThread.myId;
    const myColor    = _s.activeThread.myColor    || '#7C3AED';
    const otherColor = _s.activeThread.otherColor || '#4B5563';

    if (!_s.activeThread.messages.length) {
      el.innerHTML = `<div class="msg-empty">Démarrez la conversation !</div>`;
      return;
    }

    el.innerHTML = _s.activeThread.messages.map(m => {
      // Comparaison en String() pour éviter les bugs de type UUID vs string
      const mine = myId && String(m.sender_id) === String(myId);

      // Carte d'échange : message marqueur "__TRADE_OFFER__<id>" → carte cliquable
      // qui ouvre l'écran de proposition (au lieu d'un texte brut).
      const content0 = m.content || '';
      if (content0.indexOf('__TRADE_OFFER__') === 0) {
        const offerId = content0.slice('__TRADE_OFFER__'.length);
        return `
          <div class="msg-bubble ${mine ? 'msg-bubble-me' : 'msg-bubble-other'}">
            <button type="button" onclick="if(window.SmyleTradeView){SmyleTradeView.open('${offerId}');}"
                    style="display:block;text-align:left;background:rgba(124,58,237,.16);border:1px solid rgba(124,58,237,.55);color:#cdb4ff;border-radius:12px;padding:10px 14px;cursor:pointer;font-size:13px;line-height:1.4">
              🔄 <strong>Offre / proposition</strong><br>
              <span style="opacity:.75;font-size:12px">Cliquer pour voir et répondre</span>
            </button>
            <span class="msg-bubble-time">${_timeAgo(m.created_at)}</span>
          </div>`;
      }

      const color = mine ? myColor : otherColor;

      // Moi : bulle solide ma couleur (droite) — Autre : bulle tintée sa couleur (gauche)
      const bubbleStyle = mine
        ? `background:${color}; color:#fff; border-bottom-right-radius:4px;`
        : `background:${color}22; border:1px solid ${color}55; color:rgba(255,255,255,.9); border-bottom-left-radius:4px;`;

      return `
        <div class="msg-bubble ${mine ? 'msg-bubble-me' : 'msg-bubble-other'}">
          <span class="msg-bubble-text" style="${bubbleStyle}">${_esc(m.content)}</span>
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
  // ── Menu ⋮ de conversation + commande "Proposer un échange" ──────────────
  // Extensible : d'autres commandes pourront s'ajouter dans le même menu.
  function _toggleConvMenu(ev) {
    if (ev) ev.stopPropagation();
    const menu = document.getElementById('msg-conv-menu');
    if (!menu) return;
    const show = menu.style.display === 'none';
    menu.style.display = show ? 'block' : 'none';
    if (show) {
      const close = () => { menu.style.display = 'none'; document.removeEventListener('click', close); };
      setTimeout(() => document.addEventListener('click', close), 0);
    }
  }

  async function _openTradeFromConv() {
    const menu = document.getElementById('msg-conv-menu');
    if (menu) menu.style.display = 'none';
    const th = _s.activeThread;
    if (!th || !th.other_user_id) return;
    const receiverId = th.other_user_id;
    const receiverName = th.other_user_name || 'cet artiste';

    // Parité visuel (C4) : un produit échangeable = une ligne `prompts` (son
    // OU image). On agrège donc les recettes audio ET les images des deux
    // côtés. Les images viennent de /images?artist_id=... (leur catalogue) et
    // /artist/me/images ; chaque option est préfixée d'une icône de nature.
    let theirs = [], mine = [];
    try {
      const d = await apiFetch(`/catalog/prompts?artist_id=${encodeURIComponent(receiverId)}&per_page=50`);
      theirs = ((d && d.items) || d || []).map(p => ({ id: p.id, title: p.title, price_credits: p.price_credits, kind: 'son' }));
    } catch (_) {}
    try {
      const d = await apiFetch(`/images?artist_id=${encodeURIComponent(receiverId)}&limit=50`);
      const imgs = (d && d.images) || [];
      theirs = theirs.concat(imgs.map(p => ({ id: p.id, title: p.title, price_credits: p.priceCredits, kind: 'image' })));
    } catch (_) {}
    try {
      const d = await apiFetch('/artist/me/prompts?limit=50');
      mine = ((d && d.items) || d || []).map(p => ({ id: p.id, title: p.title, price_credits: p.price_credits, kind: 'son' }));
    } catch (_) {}
    try {
      // /artist/me/images renvoie ImageOwnerRead (clés snake_case : price_credits,
      // is_published). Seules les images PUBLIÉES sont échangeables (le backend
      // exige offered.is_published à la création de l'offre).
      const d = await apiFetch('/artist/me/images');
      const imgs = Array.isArray(d) ? d : ((d && d.items) || []);
      mine = mine.concat(imgs.filter(p => p.is_published).map(p => ({ id: p.id, title: p.title, price_credits: p.price_credits, kind: 'image' })));
    } catch (_) {}

    if (!theirs.length) { alert(`${receiverName} n'a pas encore de produit échangeable.`); return; }

    const esc = (s) => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
    const _ic = (k) => k === 'image' ? '🖼 ' : '🎵 ';
    const theirOpts = theirs.map(p => `<option value="${p.id}">${_ic(p.kind)}${esc(p.title) || 'Sans titre'} · ${p.price_credits || 0} crédits</option>`).join('');
    const myOpts = mine.length
      ? mine.map(p => `<option value="${p.id}">${_ic(p.kind)}${esc(p.title) || 'Sans titre'} · ${p.price_credits || 0} crédits</option>`).join('')
      : '<option value="" disabled>Aucun produit à proposer</option>';

    const prev = document.getElementById('msg-trade-modal');
    if (prev) prev.remove();
    const sel = 'width:100%;padding:8px;border-radius:8px;background:#0e0e14;color:#eee;border:1px solid rgba(255,255,255,.15)';
    const el = document.createElement('div');
    el.id = 'msg-trade-modal';
    el.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:16px';
    el.innerHTML = `
      <div style="background:#15151c;border:1px solid rgba(255,255,255,.12);border-radius:14px;max-width:420px;width:100%;padding:18px;color:#eee;font-size:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <strong>🔄 Échange avec ${esc(receiverName)}</strong>
          <button onclick="document.getElementById('msg-trade-modal').remove()" style="background:none;border:none;color:#aaa;font-size:18px;cursor:pointer">✕</button>
        </div>
        <label style="display:block;margin:8px 0 4px;opacity:.8">Tu demandes (son son ou son image)</label>
        <select id="msg-trade-req" style="${sel}"><option value="">-- Choisir --</option>${theirOpts}</select>
        <label style="display:block;margin:12px 0 4px;opacity:.8">Tu proposes (ton son ou ton image)</label>
        <select id="msg-trade-off" style="${sel}"><option value="">-- Choisir --</option>${myOpts}</select>
        <label style="display:block;margin:12px 0 4px;opacity:.8">Complément en crédits (optionnel)</label>
        <input id="msg-trade-supp" type="number" min="0" value="0" style="${sel}" />
        <p style="opacity:.6;font-size:12px;margin:12px 0">⚠️ Frais de 20% (brûlé) par côté. Offre valable 7 jours.</p>
        <button id="msg-trade-send" onclick="SmyleMessaging._submitTradeFromConv('${receiverId}')"
                style="width:100%;padding:10px;border:none;border-radius:8px;background:#7C3AED;color:#fff;font-weight:600;cursor:pointer">Envoyer la proposition</button>
      </div>`;
    el.addEventListener('click', ev => { if (ev.target === el) el.remove(); });
    document.body.appendChild(el);
  }

  async function _submitTradeFromConv(receiverId) {
    const req  = (document.getElementById('msg-trade-req')  || {}).value || '';
    const off  = (document.getElementById('msg-trade-off')  || {}).value || '';
    const supp = parseInt((document.getElementById('msg-trade-supp') || {}).value || '0', 10);
    const btn  = document.getElementById('msg-trade-send');
    if (!req) { alert('Choisis le produit que tu veux récupérer.'); return; }
    if (!off) { alert('Choisis un de tes produits à proposer.'); return; }
    if (btn) { btn.textContent = 'Envoi…'; btn.disabled = true; }
    try {
      // notify:false → pas de notification, la proposition apparaît comme
      // une carte directement dans le fil de la conversation.
      const offer = await apiFetch('/trades/offers', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receiver_id:         receiverId,
          offered_prompt_id:   off,
          requested_prompt_id: req,
          credit_supplement:   Math.max(0, supp || 0),
          message:             null,
          notify:              false,
        }),
      });
      const m = document.getElementById('msg-trade-modal'); if (m) m.remove();
      // Poste une carte d'échange dans la conversation (marqueur détecté au rendu).
      const offerId = offer && offer.id;
      if (offerId && _s.activeThread) {
        try {
          const msg = await apiFetch(`/messages/threads/${_s.activeThread.id}/send`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: '__TRADE_OFFER__' + offerId }),
          });
          _s.activeThread.messages.push(msg);
          _renderMessages();
          _scrollBottom();
        } catch (_) {}
      }
    } catch (err) {
      if (btn) { btn.textContent = 'Envoyer la proposition'; btn.disabled = false; }
      const detail = (err && err.body && err.body.detail) || err.message || 'Erreur';
      alert('Erreur : ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)));
    }
  }

  window.SmyleMessaging = {
    open:          _open,
    close:         _close,
    toggle:        _toggle,
    _selectThread: _selectThread,
    _backToInbox:  _backToInbox,
    _onKey:        _onKey,
    _autoGrow:     _autoGrow,
    _onSend:       _onSend,
    _toggleConvMenu:      _toggleConvMenu,
    _openTradeFromConv:   _openTradeFromConv,
    _submitTradeFromConv: _submitTradeFromConv,
  };

})();
