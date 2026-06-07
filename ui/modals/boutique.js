/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/modals/boutique.js
   La BOUTIQUE : vitrine universelle où dépenser / rechargera ses Smyles.

   AUTONOME : module IIFE qui embarque SA PROPRE logique d'ouverture de pack
   (modal + animation). Ne dépend PAS de auth.js → fonctionne sur TOUTES les
   pages (accueil, profil, bibliothèque, WATT BOARD) du moment que api.js est
   chargé. Tout est privé (scope IIFE) ; seul window.openBoutique est exposé.
   Identifiants DOM préfixés "bq" pour ne jamais entrer en collision avec les
   modals de auth.js sur l'accueil.

   Sections : Dépenser (Pack Mystère, actif) · Recharger (bientôt) · Abonnement.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  // ── Données ───────────────────────────────────────────────────────────────
  const RARITY = {
    commun:     { label: 'Commun',     color: '#9aa0aa' },
    rare:       { label: 'Rare',       color: '#4ea1ff' },
    epique:     { label: 'Épique',     color: '#b06cff' },
    legendaire: { label: 'Légendaire', color: '#ffb627' },
  };
  // Paliers de recharge — alignés sur CREDIT_PACKS (backend).
  const SMYLE_PACKS = [
    { credits: 10,  eur: 8,   best: false },
    { credits: 50,  eur: 35,  best: true  },
    { credits: 200, eur: 120, best: false },
  ];
  // Abonnement — 3 paliers décidés. Avantages à définir plus tard.
  const SUB_TIERS = [
    { name: 'Standard', icon: '🎫', accent: '#9aa0aa' },
    { name: 'Premium',  icon: '⭐', accent: '#6c4cf0' },
    { name: 'Mythique', icon: '👑', accent: '#ffb627' },
  ];

  // ── Helpers externes (tolérants : la page peut ne pas tout exposer) ───────
  function _api(path, opts) {
    if (typeof apiFetch !== 'function') return Promise.reject(new Error('api indisponible'));
    return apiFetch(path, opts);
  }
  function _toast(msg, opts) {
    if (typeof window.smyleToast === 'function') window.smyleToast(msg, opts || {});
  }
  function _refreshBalance() {
    if (window.SmyleBalance && typeof window.SmyleBalance.refresh === 'function') {
      try { window.SmyleBalance.refresh(); } catch (_) {}
    }
  }
  function _currentUser() {
    return (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
  }
  function _isLoggedIn() {
    if (_currentUser()) return true;
    // Fallback : présence d'un token JWT.
    if (typeof getAuthToken === 'function') return !!getAuthToken();
    return true; // on laisse l'API trancher (401) si on ne sait pas
  }

  // ── Modal Boutique ────────────────────────────────────────────────────────
  function _ensureBoutique() {
    let m = document.getElementById('bqBoutiqueModal');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'bqBoutiqueModal';
    m.style.cssText = 'position:fixed;inset:0;z-index:1200;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.72);padding:16px;';
    m.innerHTML = `
      <div style="position:relative;max-width:600px;width:100%;max-height:90vh;overflow:auto;background:#14101f;border:1px solid #2c2440;border-radius:18px;padding:26px;color:#eee;font-family:inherit;">
        <button id="bqBoutiqueClose" aria-label="Fermer" style="position:absolute;top:16px;right:20px;background:none;border:none;color:#aaa;font-size:24px;cursor:pointer;line-height:1;">×</button>
        <h2 style="margin:0 0 4px;font-size:22px;">Boutique</h2>
        <p style="margin:0 0 22px;font-size:13px;color:#9990ad;">Dépense tes Smyles. D'autres produits arrivent bientôt.</p>
        <div id="bqBody"></div>
      </div>`;
    document.body.appendChild(m);
    m.addEventListener('click', (e) => { if (e.target === m) _closeBoutique(); });
    m.querySelector('#bqBoutiqueClose').addEventListener('click', _closeBoutique);
    return m;
  }

  function _soonBadge(label) {
    return `<span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;background:#3a3350;color:#cfc6e6;padding:3px 8px;border-radius:999px;">${label}</span>`;
  }
  function _sectionTitle(t) {
    return `<div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9990ad;margin:22px 0 10px;">${t}</div>`;
  }

  function _renderBoutiqueBody() {
    const body = document.getElementById('bqBody');
    if (!body) return;

    // ── 0. GAGNER des Smyles — Récompense du jour + Parrainage ──────────
    let html = _sectionTitle('Gagner des Smyles');
    html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
      <div id="bqEarnStreak" style="cursor:pointer;background:#0d0a16;border:1px solid #2c2440;border-radius:14px;padding:16px;text-align:center;transition:border-color .15s;"
           onmouseover="this.style.borderColor='#6c4cf0'" onmouseout="this.style.borderColor='#2c2440'">
        <div style="font-size:30px;line-height:1;margin-bottom:6px;">🔥</div>
        <div style="font-size:14px;font-weight:800;">Récompense du jour</div>
        <div style="font-size:11px;color:#9990ad;margin-top:3px;">Reviens chaque jour</div>
      </div>
      <div id="bqEarnRef" style="cursor:pointer;background:#0d0a16;border:1px solid #2c2440;border-radius:14px;padding:16px;text-align:center;transition:border-color .15s;"
           onmouseover="this.style.borderColor='#6c4cf0'" onmouseout="this.style.borderColor='#2c2440'">
        <div style="font-size:30px;line-height:1;margin-bottom:6px;">🤝</div>
        <div style="font-size:14px;font-weight:800;">Parrainage</div>
        <div style="font-size:11px;color:#9990ad;margin-top:3px;">Invite, gagnez à deux</div>
      </div>
    </div>`;

    html += _sectionTitle('Dépenser tes Smyles');
    html += `
      <div id="bqPackCard" style="cursor:pointer;background:#0d0a16;border:1px solid #2c2440;border-radius:14px;padding:18px;display:flex;gap:14px;align-items:center;transition:border-color .15s;"
           onmouseover="this.style.borderColor='#6c4cf0'" onmouseout="this.style.borderColor='#2c2440'">
        <div style="font-size:38px;line-height:1;">🎁</div>
        <div style="flex:1;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:17px;font-weight:800;">Pack Mystère</span>
            <span style="font-size:10px;font-weight:700;text-transform:uppercase;background:#6c4cf0;color:#fff;padding:3px 8px;border-radius:999px;">Raretés</span>
          </div>
          <div style="font-size:12px;color:#9990ad;margin-top:3px;">Tire un son au hasard — tu peux décrocher une pépite bien plus chère que le prix du pack.</div>
        </div>
        <div style="color:#6c4cf0;font-size:20px;">›</div>
      </div>`;
    // Marché secondaire — acheter des prompts revendus par d'autres.
    html += `
      <div id="bqMarketCard" style="cursor:pointer;background:#0d0a16;border:1px solid #2c2440;border-radius:14px;padding:18px;display:flex;gap:14px;align-items:center;margin-top:10px;transition:border-color .15s;"
           onmouseover="this.style.borderColor='#6c4cf0'" onmouseout="this.style.borderColor='#2c2440'">
        <div style="font-size:38px;line-height:1;">💱</div>
        <div style="flex:1;">
          <div style="font-size:17px;font-weight:800;">Marché secondaire</div>
          <div style="font-size:12px;color:#9990ad;margin-top:3px;">Achète des sons revendus par d'autres. L'artiste d'origine touche une royaltie.</div>
        </div>
        <div style="color:#6c4cf0;font-size:20px;">›</div>
      </div>`;

    html += _sectionTitle('Recharger tes Smyles');
    html += `<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">`;
    html += SMYLE_PACKS.map(p => `
      <div class="bqSoon" style="cursor:default;position:relative;background:#0d0a16;border:1px solid ${p.best ? '#6c4cf0' : '#2c2440'};border-radius:14px;padding:16px 12px;text-align:center;opacity:.85;">
        ${p.best ? '<div style="position:absolute;top:-9px;left:50%;transform:translateX(-50%);font-size:9px;font-weight:700;text-transform:uppercase;background:#6c4cf0;color:#fff;padding:2px 8px;border-radius:999px;white-space:nowrap;">Meilleur rapport</div>' : ''}
        <div style="font-size:24px;font-weight:800;">${p.credits}</div>
        <div style="font-size:11px;color:#9990ad;margin-bottom:8px;">Smyles</div>
        <div style="font-size:15px;font-weight:700;color:#cfc6e6;">${p.eur} €</div>
      </div>`).join('');
    html += `</div>`;
    html += `<div style="display:flex;align-items:center;gap:8px;margin-top:10px;">${_soonBadge('Bientôt')}<span style="font-size:12px;color:#9990ad;">Le paiement arrive prochainement.</span></div>`;

    html += _sectionTitle('Abonnement');
    html += `<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">`;
    html += SUB_TIERS.map(t => `
      <div class="bqSoon" style="cursor:default;background:#0d0a16;border:1px solid ${t.accent};border-radius:14px;padding:16px 12px;text-align:center;opacity:.85;">
        <div style="font-size:28px;line-height:1;margin-bottom:6px;">${t.icon}</div>
        <div style="font-size:15px;font-weight:800;color:${t.accent};">${t.name}</div>
        <div style="font-size:11px;color:#9990ad;margin-top:4px;">Avantages à venir</div>
      </div>`).join('');
    html += `</div>`;
    html += `<div style="display:flex;align-items:center;gap:8px;margin-top:10px;">${_soonBadge('Bientôt')}<span style="font-size:12px;color:#9990ad;">Trois formules — détails en préparation.</span></div>`;

    body.innerHTML = html;
    const earnStreak = body.querySelector('#bqEarnStreak');
    const earnRef = body.querySelector('#bqEarnRef');
    if (earnStreak) earnStreak.addEventListener('click', () => {
      _closeBoutique();
      if (typeof window.openStreakPanel === 'function') window.openStreakPanel();
    });
    if (earnRef) earnRef.addEventListener('click', () => {
      _closeBoutique();
      if (typeof window.openReferralPanel === 'function') window.openReferralPanel();
    });
    body.querySelector('#bqPackCard').addEventListener('click', _onPackCardClick);
    const marketCard = body.querySelector('#bqMarketCard');
    if (marketCard) marketCard.addEventListener('click', _openMarket);
    body.querySelectorAll('.bqSoon').forEach(el => el.addEventListener('click', () => {
      _toast('Bientôt disponible — on y travaille 🛠️', { type: 'info', duration: 2600 });
    }));
  }

  function _onPackCardClick() {
    if (!_isLoggedIn()) {
      _closeBoutique();
      if (typeof window.openAuthModal === 'function') window.openAuthModal('login');
      else _toast('Connecte-toi pour accéder à la boutique', { type: 'info', duration: 3000 });
      return;
    }
    _openPack();
  }

  function _openBoutique() {
    _ensureBoutique();
    _renderBoutiqueBody();
    document.getElementById('bqBoutiqueModal').style.display = 'flex';
  }
  function _closeBoutique() {
    const m = document.getElementById('bqBoutiqueModal');
    if (m) m.style.display = 'none';
  }

  // ── Modal Pack (autonome) ─────────────────────────────────────────────────
  function _ensurePack() {
    let m = document.getElementById('bqPackModal');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'bqPackModal';
    m.style.cssText = 'position:fixed;inset:0;z-index:1300;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.78);padding:16px;';
    m.innerHTML = `
      <div style="position:relative;max-width:400px;width:92%;background:#14101f;border:1px solid #2c2440;border-radius:16px;padding:24px;color:#eee;text-align:center;font-family:inherit;">
        <button id="bqPackClose" aria-label="Fermer" style="position:absolute;top:14px;right:18px;background:none;border:none;color:#aaa;font-size:22px;cursor:pointer;">×</button>
        <div id="bqPackBody" style="font-size:14px;">Chargement…</div>
      </div>`;
    document.body.appendChild(m);
    m.addEventListener('click', (e) => { if (e.target === m) _closePack(); });
    m.querySelector('#bqPackClose').addEventListener('click', _closePack);
    return m;
  }
  function _closePack() {
    const m = document.getElementById('bqPackModal');
    if (m) m.style.display = 'none';
  }

  async function _openPack() {
    _closeBoutique();
    _ensurePack();
    document.getElementById('bqPackModal').style.display = 'flex';
    await _renderPackIntro();
  }

  async function _renderPackIntro() {
    const body = document.getElementById('bqPackBody');
    if (!body) return;
    body.textContent = 'Chargement…';
    try {
      const info = await _api('/packs/mystery');
      const price = (info && info.price) || 8;
      const pool = (info && info.pool_count) || 0;
      if (pool <= 0) {
        body.innerHTML = `
          <div style="font-size:44px;margin:6px 0 8px;">🎁</div>
          <div style="font-size:18px;font-weight:700;margin-bottom:6px;">Pool vide</div>
          <p style="font-size:13px;color:#9990ad;">Tu possèdes déjà tous les sons disponibles au tirage. Reviens quand de nouveaux sons seront publiés.</p>`;
        return;
      }
      const odds = (info && info.odds) || [];
      const legend = odds.map(o => {
        const r = RARITY[o.name] || { label: o.name, color: '#9aa0aa' };
        return `<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:#b9b2cc;margin:0 6px;"><span style="width:8px;height:8px;border-radius:50%;background:${r.color};display:inline-block;"></span>${r.label} ${o.pct}%</span>`;
      }).join('');
      body.innerHTML = `
        <div style="font-size:48px;margin:4px 0 8px;">🎁</div>
        <div style="font-size:20px;font-weight:800;margin-bottom:4px;">Pack mystère</div>
        <p style="font-size:13px;color:#b9b2cc;margin-bottom:4px;">Tire un son au hasard parmi <strong>${pool}</strong> disponibles.</p>
        <p style="font-size:11px;color:#9990ad;margin-bottom:12px;">Tu pourrais décrocher un son bien plus cher que le prix du tirage.</p>
        <div style="margin-bottom:18px;line-height:1.8;">${legend}</div>
        <button id="bqOpenBtn" style="width:100%;background:#6c4cf0;border:none;color:#fff;border-radius:12px;padding:14px;cursor:pointer;font-size:16px;font-weight:700;">Ouvrir — ${price} Smyle${price > 1 ? 's' : ''}</button>`;
      body.querySelector('#bqOpenBtn').addEventListener('click', _drawPack);
    } catch (e) {
      body.innerHTML = `<p style="color:#e58;">Impossible de charger le pack. ${(e && e.status === 401) ? 'Reconnecte-toi.' : 'Réessaie dans un instant.'}</p>`;
    }
  }

  async function _drawPack() {
    const body = document.getElementById('bqPackBody');
    // Phase 1 — suspense.
    if (body) body.innerHTML = `
      <style>
        @keyframes bqShake{0%,100%{transform:rotate(-7deg) translateY(0)}25%{transform:rotate(7deg) translateY(-5px)}50%{transform:rotate(-5deg) translateY(0)}75%{transform:rotate(6deg) translateY(-4px)}}
        @keyframes bqGlow{0%,100%{filter:drop-shadow(0 0 6px rgba(108,76,240,.5))}50%{filter:drop-shadow(0 0 28px rgba(108,76,240,.95))}}
        @keyframes bqBurst{0%{transform:scale(1);opacity:1}55%{transform:scale(1.55);opacity:1}100%{transform:scale(2.3);opacity:0}}
        @keyframes bqReveal{0%{transform:scale(.3) translateY(24px);opacity:0}60%{transform:scale(1.1)}100%{transform:scale(1) translateY(0);opacity:1}}
        @keyframes bqRing{0%{transform:scale(.7);opacity:.9}100%{transform:scale(2.6);opacity:0}}
        @keyframes bqShine{0%{left:-60%}100%{left:150%}}
        @keyframes bqSpark{0%{transform:translateY(0) scale(1);opacity:1}100%{transform:translateY(-46px) scale(.3);opacity:0}}
      </style>
      <div style="height:150px;display:flex;align-items:center;justify-content:center;">
        <div id="bqBox" style="font-size:74px;animation:bqShake .42s ease-in-out infinite, bqGlow 1s ease-in-out infinite;">🎁</div>
      </div>
      <p style="font-size:13px;color:#9990ad;">Ouverture du pack…</p>`;
    try {
      const r = await _api('/packs/mystery/open', { method: 'POST' });
      _refreshBalance();
      const title = (r && r.title) || 'Un son';
      const rar = RARITY[r && r.rarity] || { label: 'Commun', color: '#9aa0aa' };
      const isTop = r && (r.rarity === 'epique' || r.rarity === 'legendaire');

      await new Promise(res => setTimeout(res, 700));
      const box = document.getElementById('bqBox');
      if (box) box.style.animation = 'bqBurst .45s ease-out forwards';
      await new Promise(res => setTimeout(res, 430));

      const sparks = isTop
        ? ['✨','🌟','✨','💫','✨'].map((s, i) => `<span style="position:absolute;left:${8 + i * 21}%;top:${15 + (i % 2) * 32}%;font-size:22px;animation:bqSpark ${0.8 + i * 0.12}s ease-out forwards;animation-delay:${i * 0.06}s;">${s}</span>`).join('')
        : '';
      if (body) body.innerHTML = `
        <div style="position:relative;">
          ${sparks}
          <div style="position:relative;display:inline-block;margin:4px auto 12px;">
            <div style="position:absolute;inset:-14px;border-radius:50%;border:2px solid ${rar.color};animation:bqRing .7s ease-out forwards;"></div>
            <div style="font-size:52px;animation:bqReveal .5s cubic-bezier(.2,1.3,.4,1) both;filter:drop-shadow(0 0 18px ${rar.color});">${isTop ? '🌟' : '🎉'}</div>
          </div>
          <div style="animation:bqReveal .5s cubic-bezier(.2,1.3,.4,1) both;animation-delay:.08s;">
            <div style="position:relative;overflow:hidden;display:inline-block;background:${rar.color}22;border:1px solid ${rar.color};color:${rar.color};font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:5px 14px;border-radius:999px;margin-bottom:10px;">
              ${rar.label}
              <span style="position:absolute;top:0;left:-60%;width:45%;height:100%;background:linear-gradient(100deg,transparent,rgba(255,255,255,.55),transparent);animation:bqShine 1s ease-in-out .3s both;"></span>
            </div>
            <div style="font-size:22px;font-weight:800;margin:4px 0 16px;color:${isTop ? rar.color : '#fff'};">${title}</div>
            <a href="/library" style="display:block;background:#6c4cf0;color:#fff;border-radius:12px;padding:12px;text-decoration:none;font-weight:700;margin-bottom:8px;">Voir dans ma bibliothèque</a>
            <button id="bqAgainBtn" style="width:100%;background:#1d1730;border:1px solid #2c2440;color:#cfc6e6;border-radius:10px;padding:10px;cursor:pointer;font-size:13px;">Ouvrir un autre pack</button>
          </div>
        </div>`;
      const again = document.getElementById('bqAgainBtn');
      if (again) again.addEventListener('click', _renderPackIntro);
      _toast(`${isTop ? '🌟' : '🎁'} ${rar.label} — « ${title} » !`, { type: 'success', duration: 3400 });
    } catch (e) {
      let msg = 'Tirage impossible. Réessaie dans un instant.';
      if (e && e.status === 402) {
        const d = e.body && e.body.detail;
        msg = (d && d.message) || 'Solde insuffisant pour ouvrir un pack.';
      } else if (e && e.status === 409) {
        msg = 'Tu possèdes déjà tous les sons disponibles au tirage.';
      }
      if (body) {
        body.innerHTML = `<div style="font-size:40px;margin:12px 0;">😕</div><p style="color:#e9a;font-size:14px;">${msg}</p><button id="bqBackBtn" style="margin-top:14px;background:#1d1730;border:1px solid #2c2440;color:#cfc6e6;border-radius:10px;padding:10px 16px;cursor:pointer;font-size:13px;">Retour</button>`;
        const back = document.getElementById('bqBackBtn');
        if (back) back.addEventListener('click', _renderPackIntro);
      }
    }
  }

  // ── Marché secondaire : parcourir + acheter ────────────────────────────────
  async function _openMarket() {
    const body = document.getElementById('bqBody');
    if (!body) return;
    body.innerHTML = `<div style="font-size:13px;color:#9990ad;">Chargement du marché…</div>`;
    try {
      const items = await _api('/resale/market');
      if (!items || !items.length) {
        body.innerHTML = `
          <div style="text-align:center;padding:10px 0;">
            <div style="font-size:40px;margin-bottom:8px;">💱</div>
            <div style="font-size:16px;font-weight:700;margin-bottom:4px;">Marché vide</div>
            <p style="font-size:13px;color:#9990ad;">Aucun son en revente pour l'instant. Reviens plus tard.</p>
            <button id="bqMarketBack" style="margin-top:14px;background:#1d1730;border:1px solid #2c2440;color:#cfc6e6;border-radius:10px;padding:9px 16px;cursor:pointer;font-size:13px;">← Retour</button>
          </div>`;
        const b = document.getElementById('bqMarketBack');
        if (b) b.addEventListener('click', _renderBoutiqueBody);
        return;
      }
      const rows = items.map(it => {
        const ltd = (it.max_supply != null)
          ? `<span style="font-size:10px;color:#FBBF24;margin-left:6px;">édition limitée</span>` : '';
        return `
          <div style="display:flex;align-items:center;gap:10px;background:#0d0a16;border:1px solid #2c2440;border-radius:12px;padding:12px;margin-bottom:8px;">
            <div style="flex:1;min-width:0;">
              <div style="font-size:14px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${it.title || 'Un son'}${ltd}</div>
              <div style="font-size:11px;color:#9990ad;">revente · royaltie artiste incluse</div>
            </div>
            <button class="bqBuyResale" data-id="${it.unlocked_prompt_id}" style="background:#6c4cf0;border:none;color:#fff;border-radius:10px;padding:9px 14px;cursor:pointer;font-size:13px;font-weight:700;white-space:nowrap;">Acheter · ${it.resale_price}</button>
          </div>`;
      }).join('');
      body.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
          <div style="font-size:16px;font-weight:800;">💱 Marché secondaire</div>
          <button id="bqMarketBack" style="background:none;border:none;color:#9990ad;cursor:pointer;font-size:13px;">← Retour</button>
        </div>
        ${rows}`;
      const b = document.getElementById('bqMarketBack');
      if (b) b.addEventListener('click', _renderBoutiqueBody);
      body.querySelectorAll('.bqBuyResale').forEach(btn => {
        btn.addEventListener('click', () => _buyResale(btn.getAttribute('data-id')));
      });
    } catch (e) {
      body.innerHTML = `<p style="color:#e58;">Impossible de charger le marché. ${(e && e.status === 401) ? 'Reconnecte-toi.' : 'Réessaie.'}</p>`;
    }
  }

  async function _buyResale(unlockedId) {
    if (!_isLoggedIn()) {
      _closeBoutique();
      if (typeof window.openAuthModal === 'function') window.openAuthModal('login');
      return;
    }
    try {
      const r = await _api(`/resale/${unlockedId}/buy`, { method: 'POST' });
      _refreshBalance();
      _toast(`Acheté ✓ (−${r.price_paid} Smyles)`, { type: 'success', duration: 3000 });
      await _openMarket();   // rafraîchit la liste (le son acheté disparaît)
    } catch (e) {
      let msg = 'Achat impossible. Réessaie.';
      if (e && e.status === 402) msg = 'Solde insuffisant pour cet achat.';
      else if (e && e.status === 409) msg = 'Tu possèdes déjà ce son.';
      else if (e && e.status === 404) msg = 'Ce son n\'est plus en vente.';
      _toast(msg, { type: 'error', duration: 3000 });
      await _openMarket();
    }
  }

  // ── API publique ──────────────────────────────────────────────────────────
  window.openBoutique = _openBoutique;
  window.closeBoutique = _closeBoutique;
})();
