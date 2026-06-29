/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/core/trade-view.js
   Écran réutilisable "Proposition d'échange" : voir les 2 prompts (+ écoute),
   accepter / refuser / annuler selon le rôle. Global, chargé sur toutes les
   pages → utilisable depuis les notifs (topbar + page-services) et les messages.
   Usage : window.SmyleTradeView.open(offerId)
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (typeof window === 'undefined' || window.SmyleTradeView) return;

  let _myId = null;
  async function _getMyId() {
    if (_myId) return _myId;
    try { const me = await apiFetch('/users/me'); _myId = (me && me.id) ? String(me.id) : null; } catch (_) {}
    return _myId;
  }

  const _esc = (s) => String(s == null ? '' : s).replace(/</g, '&lt;');
  const _audio = (p) => (p && p.audio_url)
    ? `<audio controls preload="none" src="${p.audio_url}" style="width:100%;margin-top:6px;height:30px"></audio>` : '';
  // Aperçu image (parité visuel) : si le prompt est une image, on montre la
  // miniature d'aperçu (jamais l'original gaté) pour "voir avant d'accepter".
  const _preview = (p) => (p && p.preview_url)
    ? `<img src="${p.preview_url}" alt="" loading="lazy" style="width:100%;margin-top:6px;border-radius:6px;max-height:160px;object-fit:cover" />` : '';
  const _media = (p) => _preview(p) + _audio(p);

  async function open(offerId) {
    if (!offerId) return;
    let offers = [];
    try { offers = (await apiFetch('/trades/offers/me')) || []; } catch (_) {}
    const o = offers.find((x) => String(x.id) === String(offerId));
    if (!o) { alert("Cette proposition d'échange n'est plus disponible."); return; }
    const myId = await _getMyId();
    _render(o, myId);
  }

  function _render(o, myId) {
    const isReceiver = myId && String(o.receiver_id) === myId;
    const isSender   = myId && String(o.sender_id) === myId;
    const pending = o.status === 'pending';
    const off = o.offered_prompt || {};
    const req = o.requested_prompt || {};

    let actions;
    if (pending && isReceiver) {
      actions = `
        <button onclick="SmyleTradeView._act('${o.id}','accept')" style="flex:1;padding:10px;border:none;border-radius:8px;background:#22c55e;color:#fff;font-weight:600;cursor:pointer">✅ Accepter</button>
        <button onclick="SmyleTradeView._act('${o.id}','reject')" style="flex:1;padding:10px;border:none;border-radius:8px;background:rgba(255,255,255,.1);color:#eee;cursor:pointer">❌ Refuser</button>`;
    } else if (pending && isSender) {
      actions = `<button onclick="SmyleTradeView._act('${o.id}','cancel')" style="flex:1;padding:10px;border:none;border-radius:8px;background:rgba(255,255,255,.1);color:#eee;cursor:pointer">Annuler ma proposition</button>`;
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
        <div style="opacity:.85;margin-bottom:10px">${isReceiver ? `${_esc(o.sender_name || 'Un artiste')} te propose un échange` : 'Ta proposition'}</div>
        <div style="${card}">
          <div style="opacity:.6;font-size:12px">${isReceiver ? 'Tu recevrais' : 'Tu offres'}</div>
          <strong>${_esc(off.title) || '—'}</strong> · ${off.price_credits || 0} crédits
          ${_media(off)}
        </div>
        <div style="text-align:center;opacity:.5;margin:2px 0 8px">⇄</div>
        <div style="${card}">
          <div style="opacity:.6;font-size:12px">${isReceiver ? 'Tu donnerais' : 'Tu demandes'}</div>
          <strong>${_esc(req.title) || '—'}</strong> · ${req.price_credits || 0} crédits
          ${_media(req)}
        </div>
        ${o.credit_supplement > 0 ? `<div style="opacity:.8;margin-bottom:8px">+ ${o.credit_supplement} crédits ${isReceiver ? 'pour toi' : 'de ta part'}</div>` : ''}
        ${o.message ? `<div style="opacity:.7;font-style:italic;margin-bottom:10px">« ${_esc(o.message)} »</div>` : ''}
        <div style="opacity:.55;font-size:12px;margin-bottom:12px">⚠️ Frais de 20% (brûlé) de chaque côté à l'acceptation.</div>
        <div style="display:flex;gap:8px">${actions}</div>
      </div>`;
    el.addEventListener('click', (ev) => { if (ev.target === el) el.remove(); });
    document.body.appendChild(el);
  }

  async function _act(offerId, action) {
    try {
      await apiFetch(`/trades/offers/${offerId}/${action}`, { method: 'PATCH' });
      const el = document.getElementById('smyle-tradeview'); if (el) el.remove();
      alert({ accept: '✅ Échange accepté !', reject: 'Proposition refusée.', cancel: 'Proposition annulée.' }[action] || 'Fait.');
    } catch (err) {
      const d = (err && err.body && err.body.detail) || err.message || 'Erreur';
      alert('Erreur : ' + (typeof d === 'string' ? d : JSON.stringify(d)));
    }
  }

  window.SmyleTradeView = { open, _act };
})();
