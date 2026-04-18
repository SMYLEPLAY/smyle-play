/**
 * SMYLE BALANCE — Widget compteur de Smyles (crédits)
 *
 * Affiche le solde de Smyles de l'utilisateur connecté dans un petit
 * widget avec la tête Smyle en icône de monnaie.
 *
 * Usage :
 *   1. Inclure ce script dans n'importe quelle page :
 *        <script src="/ui/smyle-balance.js" defer></script>
 *   2. Le widget s'auto-injecte dans #smyle-balance-container s'il existe,
 *      sinon il se place en haut à droite du body en position fixed.
 *   3. Pour rafraîchir après un unlock / grant :
 *        window.SmyleBalance.refresh();
 *
 * Comportement :
 *   - Si /api/auth/me renvoie user=null → widget masqué.
 *   - Si user connecté → fetch /api/credits puis affichage.
 *   - Actualise automatiquement toutes les 60s.
 */
(function () {
  'use strict';

  // ── SVG tête Smyle (version compacte, 24x24 viewBox optimisé) ──────────
  const LOGO_SVG = `
    <svg viewBox="0 0 60 80" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <g transform="translate(30,42)">
        <circle cx="24"   cy="0"     r="2.4" fill="#0c0018"/>
        <circle cx="22.1" cy="8.9"   r="2.4" fill="#0e001e"/>
        <circle cx="16.9" cy="16.9"  r="2.4" fill="#0c0016"/>
        <circle cx="8.9"  cy="22.1"  r="2.4" fill="#0e001e"/>
        <circle cx="0"    cy="24"    r="2.4" fill="#0c0018"/>
        <circle cx="-8.9" cy="22.1"  r="2.4" fill="#0e001e"/>
        <circle cx="-16.9" cy="16.9" r="2.4" fill="#0c0016"/>
        <circle cx="-22.1" cy="8.9"  r="2.4" fill="#0e001e"/>
        <circle cx="-24"  cy="0"     r="2.4" fill="#0c0018"/>
        <circle cx="-22.1" cy="-8.9" r="2.4" fill="#0e001e"/>
        <circle cx="-16.9" cy="-16.9" r="2.4" fill="#0c0016"/>
        <circle cx="-8.9" cy="-22.1" r="2.4" fill="#0e001e"/>
        <circle cx="0"    cy="-24"   r="2.4" fill="#0c0018"/>
        <circle cx="8.9"  cy="-22.1" r="2.4" fill="#0e001e"/>
        <circle cx="16.9" cy="-16.9" r="2.4" fill="#0c0016"/>
        <circle cx="22.1" cy="-8.9"  r="2.4" fill="#0e001e"/>
        <circle cx="15"   cy="0"     r="1.9" fill="#130025"/>
        <circle cx="13.5" cy="7.5"   r="1.9" fill="#130025"/>
        <circle cx="7.5"  cy="13.5"  r="1.9" fill="#130025"/>
        <circle cx="0"    cy="15"    r="1.9" fill="#130025"/>
        <circle cx="-7.5" cy="13.5"  r="1.9" fill="#130025"/>
        <circle cx="-13.5" cy="7.5"  r="1.9" fill="#130025"/>
        <circle cx="-15"  cy="0"     r="1.9" fill="#130025"/>
        <circle cx="-13.5" cy="-7.5" r="1.9" fill="#130025"/>
        <circle cx="-7.5" cy="-13.5" r="1.9" fill="#130025"/>
        <circle cx="0"    cy="-15"   r="1.9" fill="#130025"/>
        <circle cx="7.5"  cy="-13.5" r="1.9" fill="#130025"/>
        <circle cx="13.5" cy="-7.5"  r="1.9" fill="#130025"/>
        <circle cx="-5.5" cy="-5"    r="3.2" fill="#ffffff" opacity="0.96"/>
        <circle cx="5.5"  cy="-5"    r="3.2" fill="#ffffff" opacity="0.96"/>
        <circle cx="-10"  cy="2"     r="2"   fill="#ffffff" opacity="0.90"/>
        <circle cx="-6.5" cy="7"     r="2"   fill="#ffffff" opacity="0.90"/>
        <circle cx="-2"   cy="9.8"   r="2"   fill="#ffffff" opacity="0.90"/>
        <circle cx="2.5"  cy="10"    r="2"   fill="#ffffff" opacity="0.90"/>
        <circle cx="7"    cy="7.5"   r="2"   fill="#ffffff" opacity="0.90"/>
        <circle cx="10"   cy="3"     r="2"   fill="#ffffff" opacity="0.90"/>
      </g>
    </svg>
  `;

  // ── Styles injectés en une fois ────────────────────────────────────────
  const CSS = `
    .smyle-balance {
      display: none;
      align-items: center;
      gap: 8px;
      padding: 6px 14px 6px 8px;
      border-radius: 999px;
      background: linear-gradient(135deg, rgba(255,215,0,0.12), rgba(255,231,55,0.06));
      border: 1px solid rgba(255,215,0,0.35);
      color: #FFD700;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-weight: 600;
      font-size: 14px;
      letter-spacing: 0.02em;
      cursor: default;
      user-select: none;
      transition: all 0.2s ease;
      box-shadow: 0 2px 8px rgba(255,215,0,0.15);
    }
    .smyle-balance.is-visible { display: inline-flex; }
    .smyle-balance:hover {
      background: linear-gradient(135deg, rgba(255,215,0,0.2), rgba(255,231,55,0.1));
      box-shadow: 0 2px 12px rgba(255,215,0,0.25);
    }
    .smyle-balance__icon {
      width: 26px;
      height: 26px;
      flex-shrink: 0;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, #2a0048, #0a0014);
      padding: 1px;
      box-shadow: 0 0 6px rgba(170,0,255,0.4);
    }
    .smyle-balance__icon svg { width: 100%; height: 100%; display: block; }
    .smyle-balance__amount {
      font-variant-numeric: tabular-nums;
      min-width: 1ch;
    }
    .smyle-balance__label {
      font-size: 11px;
      font-weight: 500;
      opacity: 0.75;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .smyle-balance.is-floating {
      position: fixed;
      top: 14px;
      right: 14px;
      z-index: 9999;
    }
    @media (max-width: 600px) {
      .smyle-balance { font-size: 13px; padding: 5px 10px 5px 6px; gap: 6px; }
      .smyle-balance__icon { width: 22px; height: 22px; }
      .smyle-balance__label { display: none; }
    }
  `;

  // ── État ───────────────────────────────────────────────────────────────
  const state = { balance: null, user: null, intervalId: null };

  function injectStyle() {
    if (document.getElementById('smyle-balance-style')) return;
    const style = document.createElement('style');
    style.id = 'smyle-balance-style';
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function getOrCreateContainer() {
    // Priorité 1 : container explicite posé dans la page
    let container = document.getElementById('smyle-balance');
    if (container) return container;

    // Priorité 2 : création automatique en flottant (position fixed)
    container = document.createElement('div');
    container.id = 'smyle-balance';
    container.className = 'smyle-balance is-floating';
    document.body.appendChild(container);
    return container;
  }

  function renderBalance(container) {
    container.className = container.className.replace(/\bis-visible\b/g, '').trim();
    container.innerHTML = '';

    if (state.user === null || state.balance === null) {
      // Non connecté ou pas encore récupéré → masqué
      return;
    }

    container.classList.add('smyle-balance', 'is-visible');
    if (!document.getElementById('smyle-balance') || container.classList.contains('is-floating')) {
      container.classList.add('is-floating');
    }

    container.innerHTML = `
      <span class="smyle-balance__icon">${LOGO_SVG}</span>
      <span class="smyle-balance__amount">${state.balance}</span>
      <span class="smyle-balance__label">Smyle${state.balance === 1 ? '' : 's'}</span>
    `;
    container.title = `Tu as ${state.balance} Smyle${state.balance === 1 ? '' : 's'}`;
  }

  async function fetchMe() {
    try {
      const r = await fetch('/api/auth/me', { credentials: 'same-origin' });
      if (!r.ok) return null;
      const data = await r.json();
      return data.user || null;
    } catch (e) {
      return null;
    }
  }

  async function fetchCredits() {
    try {
      const r = await fetch('/api/credits', { credentials: 'same-origin' });
      if (!r.ok) return null;
      const data = await r.json();
      return typeof data.credits === 'number' ? data.credits : null;
    } catch (e) {
      return null;
    }
  }

  async function refresh() {
    const container = getOrCreateContainer();
    const me = await fetchMe();
    state.user = me;
    if (!me) {
      state.balance = null;
      renderBalance(container);
      return;
    }
    state.balance = await fetchCredits();
    renderBalance(container);
  }

  function init() {
    injectStyle();
    refresh();
    // Re-fetch toutes les 60s pour attraper les changements (grant, unlock)
    if (state.intervalId) clearInterval(state.intervalId);
    state.intervalId = setInterval(refresh, 60000);
  }

  // Exposition publique : permet de forcer un refresh après unlock / login
  window.SmyleBalance = { refresh };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
