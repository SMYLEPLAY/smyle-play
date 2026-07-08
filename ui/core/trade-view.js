/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/trade-view.js
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

  // OFFRES-ADN : une offre cash sur un ADN (target_type présent, pas de
  // prompt échangé) doit s'afficher via une carte dédiée, JAMAIS le gabarit
  // give/receive (qui montrerait « Tu recevrais — · 0 crédits »).
  const _ADN_TYPE_LABELS = {
    playlist_adn: 'ADN playlist',
    album_adn:    'ADN album',
    visual_adn:   'ADN visuel',
    profile_adn:  'ADN sonore',
  };
  // Une offre est une offre ADN si elle porte un target_type et n'a pas de
  // prompt offert/demandé (un troc classique en a toujours au moins un).
  const _isAdnOffer = (o) => !!(o && o.target_type &&
    !o.offered_prompt && !o.requested_prompt);

  async function open(offerId) {
    if (!offerId) return;
    // On tente d'abord les trocs classiques ; si l'id n'y est pas, on regarde
    // les offres ADN (mêmes ids TradeOffer, mais deux endpoints distincts).
    // DISSOCIATION ADN : on regarde d'ABORD les offres d'achat ADN. Une offre
    // ADN vit dans la même table que les trocs, donc on la teste en priorité
    // pour ne jamais la rendre via le gabarit « échange » (0 crédits).
    let o = null;
    try {
      const adn = (await apiFetch('/adn-offers/me')) || [];
      o = adn.find((x) => String(x.id) === String(offerId)) || null;
    } catch (_) {}
    const myId = await _getMyId();
    if (o) { _renderAdn(o, myId); return; }
    try {
      const trades = (await apiFetch('/trades/offers/me')) || [];
      o = trades.find((x) => String(x.id) === String(offerId)) || null;
    } catch (_) {}
    if (!o) { alert("Cette proposition n'est plus disponible."); return; }
    if (_isAdnOffer(o)) { _renderAdn(o, myId); return; }
    _render(o, myId);
  }

  // ── Carte offre ADN (offre cash, pas de give/receive) ────────────────────
  function _renderAdn(o, myId) {
    const isSeller = myId && String(o.seller_id) === myId;
    const isBuyer  = myId && String(o.buyer_id) === myId;
    const pending  = o.status === 'pending';
    const typeLbl  = _ADN_TYPE_LABELS[o.target_type] || 'ADN';

    let actions;
    if (pending && isSeller) {
      actions = `
        <button onclick="SmyleTradeView._adnAct('${o.id}','accept')" style="flex:1;padding:10px;border:none;border-radius:8px;background:#22c55e;color:#fff;font-weight:600;cursor:pointer">Accepter · ${o.amount_credits} crédits</button>
        <button onclick="SmyleTradeView._adnAct('${o.id}','reject')" style="flex:1;padding:10px;border:none;border-radius:8px;background:rgba(255,255,255,.1);color:#eee;cursor:pointer">Refuser</button>`;
    } else if (pending && isBuyer) {
      actions = `<button onclick="SmyleTradeView._adnAct('${o.id}','cancel')" style="flex:1;padding:10px;border:none;border-radius:8px;background:rgba(255,255,255,.1);color:#eee;cursor:pointer">Annuler mon offre</button>`;
    } else {
      const lbl = { accepted: '✅ Offre acceptée — ADN livré', rejected: '❌ Refusée', cancelled: 'Annulée', expired: '⏳ Expirée' }[o.status] || o.status;
      actions = `<div style="flex:1;text-align:center;opacity:.7;padding:8px">${lbl}</div>`;
    }

    // Négocier : ouvre un fil de messagerie avec l'autre partie si dispo.
    const otherId   = isSeller ? o.buyer_id : o.seller_id;
    const negotiate = otherId
      ? `<button onclick="if(window.SmyleMessaging){document.getElementById('smyle-tradeview').remove();SmyleMessaging.open('${_esc(otherId)}');}" style="width:100%;margin-top:8px;padding:9px;border:1px solid rgba(204,136,255,.4);border-radius:8px;background:rgba(204,136,255,.1);color:#cdb4ff;cursor:pointer;font-size:13px">💬 Négocier</button>`
      : '';

    const card = 'background:#0e0e14;border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:12px;margin-bottom:10px';
    const prev = document.getElementById('smyle-tradeview'); if (prev) prev.remove();
    const el = document.createElement('div');
    el.id = 'smyle-tradeview';
    el.style.cssText = 'position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,.65);display:flex;align-items:center;justify-content:center;padding:16px';
    el.innerHTML = `
      <div style="background:#15151c;border:1px solid rgba(255,255,255,.12);border-radius:14px;max-width:420px;width:100%;padding:18px;color:#eee;font-size:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <strong>💰 Offre sur ADN</strong>
          <button onclick="document.getElementById('smyle-tradeview').remove()" style="background:none;border:none;color:#aaa;font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="opacity:.85;margin-bottom:10px">${isSeller
          ? `${_esc(o.buyer_name || 'Un artiste')} te propose <strong>${o.amount_credits} crédits</strong> pour ton ${_esc(typeLbl)}`
          : `Ton offre : <strong>${o.amount_credits} crédits</strong>${pending ? ' · en attente' : ''}`}</div>
        <div style="${card}">
          <div style="opacity:.6;font-size:12px">${_esc(typeLbl)}</div>
          <strong>${_esc(o.target_title) || '—'}</strong>
          <div style="margin-top:8px;font-size:18px;font-weight:700;color:#cc88ff">${o.amount_credits} crédits</div>
        </div>
        ${o.message ? `<div style="opacity:.7;font-style:italic;margin-bottom:10px">« ${_esc(o.message)} »</div>` : ''}
        ${pending && isSeller ? `<div style="opacity:.55;font-size:12px;margin-bottom:12px">À l'acceptation : les crédits sont transférés (moins la commission plateforme) et l'ADN est livré à l'acheteur.</div>` : ''}
        <div style="display:flex;gap:8px">${actions}</div>
        ${negotiate}
      </div>`;
    el.addEventListener('click', (ev) => { if (ev.target === el) el.remove(); });
    document.body.appendChild(el);
  }

  async function _adnAct(offerId, action) {
    try {
      await apiFetch(`/adn-offers/${offerId}/${action}`, { method: 'PATCH' });
      const el = document.getElementById('smyle-tradeview'); if (el) el.remove();
      alert({ accept: '✅ Offre acceptée — crédits reçus, ADN livré !', reject: 'Offre refusée.', cancel: 'Offre annulée.' }[action] || 'Fait.');
    } catch (err) {
      const d = (err && err.body && err.body.detail) || err.message || 'Erreur';
      alert('Erreur : ' + (typeof d === 'string' ? d : JSON.stringify(d)));
    }
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

  window.SmyleTradeView = { open, _act, _adnAct };
})();
