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
      cursor: pointer;
      user-select: none;
      text-decoration: none;
      transition: all 0.2s ease;
      box-shadow: 0 2px 8px rgba(255,215,0,0.15);
    }
    .smyle-balance.is-visible { display: inline-flex; }
    .smyle-balance:hover {
      background: linear-gradient(135deg, rgba(255,215,0,0.22), rgba(255,231,55,0.12));
      box-shadow: 0 2px 14px rgba(255,215,0,0.32);
      transform: translateY(-1px);
    }
    .smyle-balance:active { transform: translateY(0) scale(0.98); }
    /* Animation flash : déclenchée quand le solde change */
    @keyframes smyleFlash {
      0%   { box-shadow: 0 2px 8px rgba(255,215,0,0.15); transform: scale(1); }
      30%  { box-shadow: 0 0 28px rgba(255,215,0,0.85), 0 0 0 6px rgba(255,215,0,0.18); transform: scale(1.08); }
      100% { box-shadow: 0 2px 8px rgba(255,215,0,0.15); transform: scale(1); }
    }
    .smyle-balance.is-flashing { animation: smyleFlash 0.9s ease-out; }
    @keyframes smyleCountBump {
      0%   { color: #FFD700; }
      40%  { color: #ffffff; text-shadow: 0 0 12px rgba(255,215,0,0.9); }
      100% { color: #FFD700; }
    }
    .smyle-balance.is-flashing .smyle-balance__amount { animation: smyleCountBump 0.9s ease-out; }
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
    /* Variante "session expirée" : on affiche le dernier solde connu en
       version grisée avec un petit cadenas, pour que l'utilisateur voie
       que ses Smyles sont toujours là, même s'il est déconnecté. */
    .smyle-balance.is-stale {
      background: linear-gradient(135deg, rgba(200,200,210,0.10), rgba(120,120,130,0.05));
      border-color: rgba(200,200,210,0.32);
      color: #d6d3e0;
      box-shadow: none;
      opacity: 0.78;
    }
    .smyle-balance.is-stale:hover {
      background: linear-gradient(135deg, rgba(200,200,210,0.16), rgba(120,120,130,0.08));
      box-shadow: 0 2px 10px rgba(180,180,200,0.12);
      opacity: 0.95;
    }
    .smyle-balance.is-stale .smyle-balance__icon {
      filter: grayscale(0.6) brightness(0.85);
    }
    .smyle-balance__lock {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 14px;
      height: 14px;
      margin-left: 2px;
      color: rgba(214,211,224,0.75);
    }
    .smyle-balance__lock svg { width: 100%; height: 100%; display: block; }
    @media (max-width: 600px) {
      .smyle-balance { font-size: 13px; padding: 5px 10px 5px 6px; gap: 6px; }
      .smyle-balance__icon { width: 22px; height: 22px; }
      .smyle-balance__label { display: none; }
    }
  `;

  // ── État ───────────────────────────────────────────────────────────────
  const state = { balance: null, user: null, intervalId: null, stale: false };

  // ── Cache localStorage (résilience session expirée) ─────────────────────
  // Si l'utilisateur perd son JWT (hard reload, expiration, nettoyage
  // cache…), on veut quand même lui montrer son dernier solde connu —
  // en grisé, avec un petit cadenas — plutôt que de faire disparaître
  // totalement le widget. Ses Smyles ne sont PAS perdus (ils sont en DB),
  // on lui rappelle juste qu'il doit se reconnecter pour les utiliser.
  const CACHE_KEY = 'smyle_last_known_balance';

  function saveBalanceCache(balance, user) {
    try {
      if (typeof balance !== 'number') return;
      const payload = {
        balance,
        userId:   user && user.id     ? String(user.id)    : null,
        email:    user && user.email  ? String(user.email) : null,
        ts:       Date.now(),
      };
      localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
    } catch (_) { /* quota / mode privé → silent */ }
  }

  function readBalanceCache() {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed.balance !== 'number') return null;
      return parsed;
    } catch (_) { return null; }
  }

  function clearBalanceCache() {
    try { localStorage.removeItem(CACHE_KEY); } catch (_) { /* silent */ }
  }

  function injectStyle() {
    if (document.getElementById('smyle-balance-style')) return;
    const style = document.createElement('style');
    style.id = 'smyle-balance-style';
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function getOrCreateContainer() {
    // Nettoyage défensif : si un rendu précédent a laissé un badge flottant
    // en dehors de la topbar (race init ou hot reload), on le supprime pour
    // éviter le doublon "S10 smyleES" qui chevauche l'avatar.
    _removeFloatingOrphans();

    // Priorité 1 : container explicite posé dans la page
    let container = document.getElementById('smyle-balance');
    if (container) return container;

    // Priorité 2 : si la page a une topbar partagée (placeholder
    // #smyle-topbar), on attend qu'elle crée son propre slot — ne PAS
    // créer de flottant prématuré qui resterait collé au coin haut-droit
    // en doublon de celui de la topbar.
    if (document.getElementById('smyle-topbar')) return null;

    // Priorité 3 : pas de topbar → création automatique en flottant
    container = document.createElement('div');
    container.id = 'smyle-balance';
    container.className = 'smyle-balance is-floating';
    document.body.appendChild(container);
    return container;
  }

  function _removeFloatingOrphans() {
    // Si un #smyle-balance existe dans la topbar ET qu'il y a aussi un
    // élément flottant en dehors, le flottant est un résidu → remove.
    // querySelectorAll voit bien les id dupliqués (browser toléré).
    const topbar = document.getElementById('smyle-topbar');
    if (!topbar) return;
    const all = document.querySelectorAll('#smyle-balance, .smyle-balance.is-floating');
    all.forEach((el) => {
      if (!topbar.contains(el) && el.classList.contains('is-floating')) {
        el.remove();
      }
    });
  }

  function renderBalance(container) {
    // Sauvegarde l'ancien solde pour détecter un changement → animation flash
    const prevBalance = state._lastRendered;

    container.className = container.className
      .replace(/\bis-visible\b/g, '')
      .replace(/\bis-stale\b/g, '')
      .trim();
    container.innerHTML = '';

    if (state.balance === null) {
      // Aucun solde à afficher (ni live, ni cache) → masqué
      state._lastRendered = null;
      return;
    }

    container.classList.add('smyle-balance', 'is-visible');
    if (state.stale) container.classList.add('is-stale');
    if (!document.getElementById('smyle-balance') || container.classList.contains('is-floating')) {
      container.classList.add('is-floating');
    }

    const label = `Smyle${state.balance === 1 ? '' : 's'}`;
    // En mode "stale" on ajoute un petit cadenas pour signaler que
    // l'affichage provient du cache local et que l'utilisateur doit
    // se reconnecter pour interagir.
    const lockIcon = state.stale
      ? `<span class="smyle-balance__lock" aria-hidden="true">
           <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
             <rect x="4" y="11" width="16" height="10" rx="2"/>
             <path d="M8 11V7a4 4 0 0 1 8 0v4"/>
           </svg>
         </span>`
      : '';
    container.innerHTML = `
      <span class="smyle-balance__icon">${LOGO_SVG}</span>
      <span class="smyle-balance__amount">${state.balance}</span>
      <span class="smyle-balance__label">${label}</span>
      ${lockIcon}
    `;
    container.title = state.stale
      ? `${state.balance} ${label} — dernier solde connu. Reconnecte-toi pour utiliser tes Smyles.`
      : `${state.balance} ${label} — clique pour recharger ou voir l'historique`;
    // Rend le container cliquable. La page /smyles arrive au Chantier 2 — en
    // attendant, on affiche un toast "bientôt disponible" pour éviter un 404.
    container.onclick = (ev) => {
      ev.preventDefault();
      // Mode stale : on bascule le clic vers la reconnexion plutôt que
      // d'ouvrir une page d'achat qui échouerait de toute façon.
      if (state.stale) {
        if (window.SmyleSessionGuard && typeof window.SmyleSessionGuard.show === 'function') {
          window.SmyleSessionGuard.show({ source: 'balance-widget' });
        } else if (typeof window.openAuthModal === 'function') {
          window.openAuthModal('login');
        } else {
          const current = (location && location.pathname + location.search + location.hash) || '/';
          window.location.href = '/?auth=login&return=' + encodeURIComponent(current);
        }
        return;
      }
      // P1-C2a (2026-04-28) — Click sur badge balance → ouvre la modale
      // d'achat de SMYLES (ui/modals/credits-buy.js, V1 stub gratuit, V2
      // bascule sur Stripe Checkout). Si la modale n'est pas chargée sur
      // cette page (ex: page legacy non migrée), on retombe sur le toast
      // "bientôt disponible" historique pour ne pas casser l'UX.
      if (typeof window.openCreditsBuyModal === 'function') {
        window.openCreditsBuyModal();
      } else if (typeof window.smyleToast === 'function') {
        window.smyleToast('Page d\'achat de Smyles — bientôt disponible', { type: 'info', duration: 2800 });
      } else {
        alert('Page d\'achat de Smyles — bientôt disponible');
      }
    };

    // Flash si le solde a changé (hors initial render / hors stale)
    if (!state.stale && prevBalance !== null && prevBalance !== undefined && prevBalance !== state.balance) {
      container.classList.remove('is-flashing');
      void container.offsetWidth; // reflow
      container.classList.add('is-flashing');
      setTimeout(() => container.classList.remove('is-flashing'), 1000);
    }
    state._lastRendered = state.balance;
  }

  // Nouvelle stack : FastAPI + JWT. On appelle /users/me qui renvoie déjà
  // user + credits_balance en un seul round-trip. Si apiFetch (ui/core/api.js)
  // est chargé, on l'utilise (il lit le JWT depuis localStorage et gère les
  // erreurs). Sinon fallback manuel.
  async function fetchMeAndCredits() {
    // Pas de token → pas connecté. Court-circuit.
    const token = (typeof getAuthToken === 'function') ? getAuthToken() : null;
    if (!token) return null;

    try {
      if (typeof apiFetch === 'function') {
        const data = await apiFetch('/users/me');
        return data || null;
      }
      // Fallback si api.js pas chargé
      const base = (typeof window !== 'undefined' && window.API_BASE) || 'http://localhost:8000';
      const r = await fetch(base + '/users/me', {
        headers: { 'Accept': 'application/json', 'Authorization': `Bearer ${token}` },
      });
      if (!r.ok) {
        if (r.status === 401 && typeof clearAuthToken === 'function') clearAuthToken();
        return null;
      }
      return await r.json();
    } catch (e) {
      // 401 → token expiré ou invalide ; on nettoie silencieusement
      if (e && e.status === 401 && typeof clearAuthToken === 'function') clearAuthToken();
      return null;
    }
  }

  async function refresh() {
    const container = getOrCreateContainer();
    // Pas de container dispo (topbar pas encore montée) : on skip. La topbar
    // rappellera SmyleBalance.refresh() après son _render() (cf. topbar.js).
    if (!container) return;
    const me = await fetchMeAndCredits();
    state.user = me;
    if (!me) {
      // Pas connecté (aucun JWT / token expiré). On essaie de réafficher
      // le dernier solde connu en mode "stale" plutôt que de faire
      // disparaître le widget. Ça évite la panique "mes Smyles ont
      // disparu" à chaque hard reload.
      const cached = readBalanceCache();
      if (cached && typeof cached.balance === 'number') {
        state.balance = cached.balance;
        state.stale   = true;
      } else {
        state.balance = null;
        state.stale   = false;
      }
      renderBalance(container);
      return;
    }
    state.stale   = false;
    state.balance = (typeof me.credits_balance === 'number') ? me.credits_balance : null;
    // Sauvegarde cache : solde + identifiant pour invalider si un autre
    // user se connecte sur le même navigateur plus tard.
    if (state.balance !== null) saveBalanceCache(state.balance, me);
    renderBalance(container);
  }

  // ── Réaction à l'event "smyle:session-expired" (émis par api.js) ────────
  // Dès qu'un 401 arrive, api.js purge le JWT périmé et émet l'event.
  // On rebascule immédiatement le widget en mode "stale" (cache visible,
  // cadenas, clic = reconnecter) sans attendre le prochain tick de 60s.
  function _handleSessionExpired() {
    const container = getOrCreateContainer();
    if (!container) return;
    const cached = readBalanceCache();
    if (cached && typeof cached.balance === 'number') {
      state.user    = null;
      state.balance = cached.balance;
      state.stale   = true;
      renderBalance(container);
    } else {
      state.user    = null;
      state.balance = null;
      state.stale   = false;
      renderBalance(container);
    }
  }

  function init() {
    injectStyle();
    refresh();
    // Re-fetch toutes les 60s pour attraper les changements (grant, unlock)
    if (state.intervalId) clearInterval(state.intervalId);
    state.intervalId = setInterval(refresh, 60000);
    // Écoute l'event de session expirée émis par ui/core/api.js
    window.addEventListener('smyle:session-expired', _handleSessionExpired);
  }

  // Exposition publique : permet de forcer un refresh après unlock / login
  window.SmyleBalance = {
    refresh,
    clearCache: clearBalanceCache,   // à appeler lors d'un logout explicite
  };
  // Alias court utilisé par artiste.js / library.js après un unlock
  window.refreshSmyleBalance = refresh;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
