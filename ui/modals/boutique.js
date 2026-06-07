/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/modals/boutique.js
   La BOUTIQUE : vitrine où l'utilisateur dépense / rechargera ses Smyles.

   v1.1 — 3 sections :
     1. Dépenser  → Pack Mystère (ACTIF, réutilise openPackModal d'auth.js)
     2. Recharger → paliers de Smyles (BIENTÔT — issus de CREDIT_PACKS backend)
     3. Abonnement → aperçu provisoire (BIENTÔT — à affiner)

   Les sections "Bientôt" sont des vitrines de projection : présentées
   proprement mais NON achetables (clic → message "bientôt"). Aucune promesse
   commerciale ferme tant que le paiement (Stripe) n'est pas branché.

   Dépendances : storage.js (getCurrentUser), auth.js (openPackModal, openAuthModal).
   ───────────────────────────────────────────────────────────────────────── */

// Paliers de recharge — alignés sur CREDIT_PACKS (services/credits.py).
// Prix en euros. "best" = meilleur rapport (mis en avant).
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

function _ensureBoutiqueModal() {
  let modal = document.getElementById('boutiqueModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'boutiqueModal';
  modal.style.cssText = 'position:fixed;inset:0;z-index:1000;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.72);padding:16px;';
  modal.innerHTML = `
    <div class="modal-card" style="position:relative;max-width:600px;width:100%;max-height:90vh;overflow:auto;background:#14101f;border:1px solid #2c2440;border-radius:18px;padding:26px;color:#eee;">
      <button onclick="closeBoutique()" aria-label="Fermer" style="position:absolute;top:16px;right:20px;background:none;border:none;color:#aaa;font-size:24px;cursor:pointer;line-height:1;">×</button>
      <h2 style="margin:0 0 4px;font-size:22px;">Boutique</h2>
      <p style="margin:0 0 22px;font-size:13px;color:#9990ad;">Dépense tes Smyles. D'autres produits arrivent bientôt.</p>
      <div id="boutiqueBody"></div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeBoutique(); });
  return modal;
}

function _soonBadge(label) {
  return `<span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;background:#3a3350;color:#cfc6e6;padding:3px 8px;border-radius:999px;">${label}</span>`;
}

function _sectionTitle(txt) {
  return `<div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#9990ad;margin:22px 0 10px;">${txt}</div>`;
}

function _renderBoutiqueBody() {
  const body = document.getElementById('boutiqueBody');
  if (!body) return;

  // ── 1. DÉPENSER — Pack Mystère (actif) ──────────────────────────────
  let html = _sectionTitle('Dépenser tes Smyles');
  html += `
    <div onclick="_boutiqueOpenPack()" style="cursor:pointer;background:#0d0a16;border:1px solid #2c2440;border-radius:14px;padding:18px;display:flex;gap:14px;align-items:center;transition:border-color .15s;"
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

  // ── 2. RECHARGER — paliers de Smyles (bientôt) ──────────────────────
  html += _sectionTitle('Recharger tes Smyles');
  html += `<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">`;
  html += SMYLE_PACKS.map(p => `
    <div onclick="_boutiqueSoon()" style="cursor:default;position:relative;background:#0d0a16;border:1px solid ${p.best ? '#6c4cf0' : '#2c2440'};border-radius:14px;padding:16px 12px;text-align:center;opacity:.85;">
      ${p.best ? '<div style="position:absolute;top:-9px;left:50%;transform:translateX(-50%);font-size:9px;font-weight:700;text-transform:uppercase;background:#6c4cf0;color:#fff;padding:2px 8px;border-radius:999px;white-space:nowrap;">Meilleur rapport</div>' : ''}
      <div style="font-size:24px;font-weight:800;">${p.credits}</div>
      <div style="font-size:11px;color:#9990ad;margin-bottom:8px;">Smyles</div>
      <div style="font-size:15px;font-weight:700;color:#cfc6e6;">${p.eur} €</div>
    </div>`).join('');
  html += `</div>`;
  html += `<div style="display:flex;align-items:center;gap:8px;margin-top:10px;">${_soonBadge('Bientôt')}<span style="font-size:12px;color:#9990ad;">Le paiement arrive prochainement.</span></div>`;

  // ── 3. ABONNEMENT — 3 paliers (bientôt, avantages à venir) ──────────
  html += _sectionTitle('Abonnement');
  html += `<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">`;
  html += SUB_TIERS.map(t => `
    <div onclick="_boutiqueSoon()" style="cursor:default;background:#0d0a16;border:1px solid ${t.accent};border-radius:14px;padding:16px 12px;text-align:center;opacity:.85;">
      <div style="font-size:28px;line-height:1;margin-bottom:6px;">${t.icon}</div>
      <div style="font-size:15px;font-weight:800;color:${t.accent};">${t.name}</div>
      <div style="font-size:11px;color:#9990ad;margin-top:4px;">Avantages à venir</div>
    </div>`).join('');
  html += `</div>`;
  html += `<div style="display:flex;align-items:center;gap:8px;margin-top:10px;">${_soonBadge('Bientôt')}<span style="font-size:12px;color:#9990ad;">Trois formules — détails en préparation.</span></div>`;

  body.innerHTML = html;
}

function _boutiqueOpenPack() {
  // Gating auth.
  const u = (typeof getCurrentUser === 'function') ? getCurrentUser() : null;
  if (!u) {
    closeBoutique();
    if (typeof window.openAuthModal === 'function') window.openAuthModal('login');
    if (typeof window.smyleToast === 'function') window.smyleToast('Connecte-toi pour accéder à la boutique', { type: 'info', duration: 3000 });
    return;
  }
  closeBoutique();
  if (typeof window.openPackModal === 'function') window.openPackModal();
}

function _boutiqueSoon() {
  if (typeof window.smyleToast === 'function') {
    window.smyleToast('Bientôt disponible — on y travaille 🛠️', { type: 'info', duration: 2600 });
  }
}

function openBoutique() {
  const modal = _ensureBoutiqueModal();
  _renderBoutiqueBody();
  modal.style.display = 'flex';
}

function closeBoutique() {
  const modal = document.getElementById('boutiqueModal');
  if (modal) modal.style.display = 'none';
}

if (typeof window !== 'undefined') {
  window.openBoutique = openBoutique;
  window.closeBoutique = closeBoutique;
  window._boutiqueOpenPack = _boutiqueOpenPack;
  window._boutiqueSoon = _boutiqueSoon;
}
