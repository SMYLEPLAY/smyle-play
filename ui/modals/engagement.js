/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/modals/engagement.js
   Streak + Parrainage rendus accessibles sur TOUTES les pages.

   AUTONOME (IIFE) : embarque sa propre logique, ne dépend pas de auth.js →
   fonctionne sur profil / bibliothèque / WATT BOARD (où auth.js n'est pas
   chargé). Identifiants DOM préfixés "eg" pour ne jamais entrer en collision
   avec les modals de auth.js sur l'accueil. Seuls window.openStreakPanel et
   window.openReferralPanel sont exposés.

   Dépendances tolérées : api.js (apiFetch), smyle-balance, toast.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  function _api(p, o) {
    if (typeof apiFetch !== 'function') return Promise.reject(new Error('api indisponible'));
    return apiFetch(p, o);
  }
  function _toast(m, o) { if (typeof window.smyleToast === 'function') window.smyleToast(m, o || {}); }
  function _refreshBalance() {
    if (window.SmyleBalance && typeof window.SmyleBalance.refresh === 'function') {
      try { window.SmyleBalance.refresh(); } catch (_) {}
    }
  }

  function _ensure(id, z) {
    let m = document.getElementById(id);
    if (m) return m;
    m = document.createElement('div');
    m.id = id;
    m.style.cssText = `position:fixed;inset:0;z-index:${z};display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.7);padding:16px;`;
    document.body.appendChild(m);
    m.addEventListener('click', (e) => { if (e.target === m) m.style.display = 'none'; });
    return m;
  }

  // ── Streak ────────────────────────────────────────────────────────────────
  function _ensureStreak() {
    let m = document.getElementById('egStreakModal');
    if (m) return m;
    m = _ensure('egStreakModal', 1250);
    m.innerHTML = `
      <div style="position:relative;max-width:380px;width:90%;background:#14101f;border:1px solid #2c2440;border-radius:16px;padding:24px;color:#eee;text-align:center;font-family:inherit;">
        <button id="egStreakClose" aria-label="Fermer" style="position:absolute;top:14px;right:18px;background:none;border:none;color:#aaa;font-size:22px;cursor:pointer;">×</button>
        <div id="egStreakBody" style="font-size:14px;">Chargement…</div>
      </div>`;
    m.querySelector('#egStreakClose').addEventListener('click', () => { m.style.display = 'none'; });
    return m;
  }
  async function _renderStreak() {
    const body = document.getElementById('egStreakBody');
    if (!body) return;
    body.textContent = 'Chargement…';
    try {
      const s = await _api('/streak/me');
      const count = (s && s.streak_count) || 0;
      const can = !!(s && s.can_checkin_today);
      const next = (s && s.next_reward) || 1;
      body.innerHTML = `
        <div style="font-size:44px;line-height:1;margin:6px 0 4px;">🔥</div>
        <div style="font-size:28px;font-weight:800;">${count} jour${count > 1 ? 's' : ''}</div>
        <div style="font-size:12px;color:#9990ad;margin-bottom:18px;">de connexion consécutive</div>
        ${can
          ? `<button id="egStreakClaim" style="width:100%;background:#6c4cf0;border:none;color:#fff;border-radius:12px;padding:13px;cursor:pointer;font-size:15px;font-weight:700;">Réclamer +${next} Smyle${next > 1 ? 's' : ''}</button>
             <p style="margin:12px 0 0;font-size:11px;color:#9990ad;">+1 chaque jour · +3 tous les 7 jours</p>`
          : `<div style="background:#0d0a16;border-radius:12px;padding:13px;color:#9ae6b4;font-size:14px;">✓ Récompense du jour réclamée</div>
             <p style="margin:12px 0 0;font-size:11px;color:#9990ad;">Reviens demain pour continuer ta série.</p>`}`;
      const btn = document.getElementById('egStreakClaim');
      if (btn) btn.addEventListener('click', _claimStreak);
    } catch (e) {
      body.innerHTML = `<p style="color:#e58;">Impossible de charger ta récompense. ${(e && e.status === 401) ? 'Reconnecte-toi.' : 'Réessaie.'}</p>`;
    }
  }
  async function _claimStreak() {
    try {
      const r = await _api('/streak/checkin', { method: 'POST' });
      if (r && r.claimed) {
        const bonus = r.is_milestone ? ' 🎉 palier 7 jours !' : '';
        _toast(`+${r.reward_granted} Smyle${r.reward_granted > 1 ? 's' : ''}${bonus}`, { type: 'success', duration: 3200 });
      }
      _refreshBalance();
      await _renderStreak();
    } catch (_) {
      const body = document.getElementById('egStreakBody');
      if (body) body.innerHTML = `<p style="color:#e58;">Réclamation impossible. Réessaie.</p>`;
    }
  }
  function _openStreak() {
    _ensureStreak().style.display = 'flex';
    _renderStreak();
  }

  // ── Parrainage ─────────────────────────────────────────────────────────────
  function _ensureRef() {
    let m = document.getElementById('egRefModal');
    if (m) return m;
    m = _ensure('egRefModal', 1250);
    m.innerHTML = `
      <div style="position:relative;max-width:420px;width:92%;background:#14101f;border:1px solid #2c2440;border-radius:16px;padding:22px;color:#eee;font-family:inherit;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
          <h3 style="margin:0;font-size:18px;">Parraine tes amis</h3>
          <button id="egRefClose" aria-label="Fermer" style="background:none;border:none;color:#aaa;font-size:22px;cursor:pointer;line-height:1;">×</button>
        </div>
        <p style="margin:0 0 14px;font-size:13px;color:#b9b2cc;">Partage ton code. Quand ton filleul poste son 1er son ou fait son 1er achat, vous gagnez <strong>10 Smyles chacun</strong>.</p>
        <div id="egRefBody" style="font-size:14px;">Chargement…</div>
      </div>`;
    m.querySelector('#egRefClose').addEventListener('click', () => { m.style.display = 'none'; });
    return m;
  }
  function _copy(text) {
    const done = () => _toast('Copié ✓', { type: 'success', duration: 1800 });
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(done);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (_) {}
      document.body.removeChild(ta); done();
    }
  }
  async function _renderRef() {
    const body = document.getElementById('egRefBody');
    if (!body) return;
    body.textContent = 'Chargement…';
    try {
      const d = await _api('/referrals/me');
      const code = (d && d.referral_code) || '—';
      const link = `${location.origin}/?ref=${encodeURIComponent(code)}`;
      const total = (d && d.total_referred) || 0;
      const rewarded = (d && d.rewarded) || 0;
      const earned = (d && d.credits_earned) || 0;
      const pending = (d && d.pending) || 0;
      body.innerHTML = `
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;">
          <code style="flex:1;background:#0d0a16;border:1px solid #2c2440;border-radius:10px;padding:10px 12px;font-size:18px;letter-spacing:2px;text-align:center;">${code}</code>
          <button id="egRefCopyCode" style="background:#6c4cf0;border:none;color:#fff;border-radius:10px;padding:10px 12px;cursor:pointer;font-size:13px;">Copier</button>
        </div>
        <button id="egRefCopyLink" style="width:100%;background:#1d1730;border:1px solid #2c2440;color:#cfc6e6;border-radius:10px;padding:9px;cursor:pointer;font-size:12px;margin-bottom:16px;">Copier le lien d'invitation</button>
        <div style="display:flex;text-align:center;gap:8px;">
          <div style="flex:1;background:#0d0a16;border-radius:10px;padding:10px;"><div style="font-size:20px;font-weight:700;">${total}</div><div style="font-size:11px;color:#9990ad;">filleuls</div></div>
          <div style="flex:1;background:#0d0a16;border-radius:10px;padding:10px;"><div style="font-size:20px;font-weight:700;">${rewarded}</div><div style="font-size:11px;color:#9990ad;">validés</div></div>
          <div style="flex:1;background:#0d0a16;border-radius:10px;padding:10px;"><div style="font-size:20px;font-weight:700;">${earned}</div><div style="font-size:11px;color:#9990ad;">Smyles gagnés</div></div>
        </div>
        ${pending ? `<p style="margin:12px 0 0;font-size:12px;color:#9990ad;text-align:center;">${pending} filleul${pending > 1 ? 's' : ''} en attente de leur 1ère action.</p>` : ''}`;
      const c1 = document.getElementById('egRefCopyCode');
      const c2 = document.getElementById('egRefCopyLink');
      if (c1) c1.addEventListener('click', () => _copy(code));
      if (c2) c2.addEventListener('click', () => _copy(link));
    } catch (e) {
      body.innerHTML = `<p style="color:#e58;">Impossible de charger ton parrainage. ${(e && e.status === 401) ? 'Reconnecte-toi.' : 'Réessaie.'}</p>`;
    }
  }
  function _openRef() {
    _ensureRef().style.display = 'flex';
    _renderRef();
  }

  if (typeof window !== 'undefined') {
    window.openStreakPanel = _openStreak;
    window.openReferralPanel = _openRef;
  }
})();
