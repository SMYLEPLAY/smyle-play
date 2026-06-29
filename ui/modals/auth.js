/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/modals/auth.js
   Auth modal + auth area. Branché sur FastAPI (JWT smyle_api_token).

   Avant : fake users en localStorage (vestige prototype).
   Maintenant : POST /auth/login + POST /auth/register + GET /users/me.

   API publique préservée pour compat avec les autres modules :
     - getCurrentUser()   → user object (ou null)
     - setCurrentUser(u)  / clearCurrentUser()  (dans storage.js)
     - renderAuthArea()   → rend le header
     - doLogout()         → clear JWT + user + re-render
     - submitLogin()      → handler du formulaire login (async)
     - submitSignup()     → handler du formulaire signup (async)

   Dépendances :
     - ui/core/api.js      (apiFetch, getAuthToken, setAuthToken, clearAuthToken)
     - ui/core/storage.js  (setCurrentUser, getCurrentUser, clearCurrentUser)
   ───────────────────────────────────────────────────────────────────────── */

// ── 5. AUTH (FastAPI) ───────────────────────────────────────────────────────

// Récupère /users/me et synchronise setCurrentUser. Retourne le user ou null.
async function _fetchMeAndSync() {
  try {
    const me = await apiFetch('/users/me');
    if (!me) return null;
    // Format stable pour le reste de l'UI : {id, email, name, credits_balance, ...}
    const user = {
      id: me.id,
      email: me.email,
      name: me.artist_name || me.display_name || (me.email || '').split('@')[0],
      artist_name: me.artist_name || null,
      credits_balance: (typeof me.credits_balance === 'number') ? me.credits_balance : 0,
    };
    setCurrentUser(user);
    return user;
  } catch (e) {
    if (e && e.status === 401) clearAuthToken();
    return null;
  }
}

async function doSignup(email, password, { onAttempt, referralCode } = {}) {
  try {
    // Signup minimal : email + password (+ code de parrainage optionnel).
    // Le profil artiste (artist_name, bio, slug) se crée via le WATT board
    // après connexion (voir /dashboard#profile).
    const payload = { email, password };
    const ref = (referralCode || '').trim();
    if (ref) payload.referral_code = ref;   // mécanique 1 — best-effort côté API
    await apiFetch('/auth/register', {
      method: 'POST',
      json: payload,
      auth: false,
      retries:      1,
      retryDelayMs: 700,
      timeoutMs:    10000,
      onAttempt,
    });
  } catch (e) {
    let msg;
    if (e && e.isNetworkError) {
      msg = e.message || 'Serveur injoignable — réessaie dans un instant.';
    } else if (e && e.status === 409) {
      msg = 'Un compte existe déjà avec cet email.';
    } else if (e && e.status >= 500) {
      msg = 'Erreur serveur — on est sur le coup, réessaie dans un instant.';
    } else {
      msg = (e && e.body && (e.body.detail || e.body.error))
         || (e && e.message)
         || 'Inscription impossible.';
    }
    return { ok: false, msg: String(msg) };
  }
  // Auto-login après register
  return doLogin(email, password);
}

async function doLogin(email, password, { onAttempt } = {}) {
  try {
    const tok = await apiFetch('/auth/login', {
      method: 'POST',
      json: { email, password },
      auth: false,
      // Résilience — le login est critique côté UX : une coupure réseau
      // transitoire ne doit PAS bloquer l'utilisateur. api.js retry
      // UNIQUEMENT sur erreur réseau (pas sur 401/400), donc c'est safe
      // de rejouer (ça ne double pas les identifiants coté serveur).
      retries:      1,
      retryDelayMs: 700,
      timeoutMs:    10000,
      onAttempt,
    });
    if (!tok || !tok.access_token) return { ok: false, msg: 'Réponse serveur invalide.' };
    setAuthToken(tok.access_token);
  } catch (e) {
    // Message diagnostique : on distingue les 3 cas qui fâchent pour
    // donner à l'utilisateur un retour qui lui dit QUOI faire.
    let msg;
    if (e && e.isNetworkError) {
      // API down / offline / CORS / timeout → le message est déjà formaté
      // par api.js (ex: "Serveur injoignable — l'API ne répond pas…").
      msg = e.message || 'Serveur injoignable — réessaie dans un instant.';
    } else if (e && e.status === 401) {
      msg = 'Email ou mot de passe incorrect.';
    } else if (e && e.status === 429) {
      msg = 'Trop de tentatives — attends une minute puis réessaie.';
    } else if (e && e.status >= 500) {
      msg = 'Erreur serveur — on est sur le coup, réessaie dans un instant.';
    } else {
      msg = (e && e.body && (e.body.detail || e.body.error))
         || (e && e.message)
         || 'Connexion impossible.';
    }
    return { ok: false, msg: String(msg) };
  }
  const user = await _fetchMeAndSync();
  if (!user) {
    clearAuthToken();
    return { ok: false, msg: 'Session invalide — réessaie.' };
  }
  // Rafraîchit la bulle crédit immédiatement
  if (window.SmyleBalance && typeof window.SmyleBalance.refresh === 'function') {
    try { window.SmyleBalance.refresh(); } catch (_) { /* noop */ }
  }
  // Ferme le bandeau "session expirée" s'il était encore visible
  if (window.SmyleSessionGuard && typeof window.SmyleSessionGuard.dismiss === 'function') {
    try { window.SmyleSessionGuard.dismiss(); } catch (_) { /* noop */ }
  }
  // Toast de bienvenue
  if (typeof window.smyleToast === 'function') {
    const label = (user.name || user.email || '').split('@')[0];
    const creds = (typeof user.credits_balance === 'number') ? ` · ${user.credits_balance} Smyle${user.credits_balance === 1 ? '' : 's'}` : '';
    window.smyleToast(`Bienvenue ${label}${creds}`, { type: 'success', duration: 3600 });
  }
  return { ok: true };
}

function doLogout() {
  clearAuthToken();
  clearCurrentUser();
  _closeUserMenu();
  // Logout volontaire : on efface aussi le cache "dernier solde connu"
  // pour ne pas afficher les Smyles de l'ancien user au prochain rechargement.
  if (window.SmyleBalance && typeof window.SmyleBalance.clearCache === 'function') {
    try { window.SmyleBalance.clearCache(); } catch (_) { /* noop */ }
  }
  // Ferme aussi le bandeau "session expirée" s'il était visible
  if (window.SmyleSessionGuard && typeof window.SmyleSessionGuard.dismiss === 'function') {
    try { window.SmyleSessionGuard.dismiss(); } catch (_) { /* noop */ }
  }
  renderAuthArea();
  if (window.SmylePageServices) window.SmylePageServices.refresh();
  // Cache la bulle crédit immédiatement
  if (window.SmyleBalance && typeof window.SmyleBalance.refresh === 'function') {
    try { window.SmyleBalance.refresh(); } catch (_) { /* noop */ }
  }
  if (typeof window.smyleToast === 'function') {
    window.smyleToast('Déconnecté — à bientôt', { type: 'info', duration: 2400 });
  }
}

// ── Menu dropdown user ──────────────────────────────────────────────────────
// Ouvert au click sur le badge. Contient : Mon profil · Biblio · Wattboard · Déco.
// Se ferme au click extérieur ou Echap.

function _userMenuSlug() {
  const u = getCurrentUser();
  if (!u) return '';
  // Aligné sur `_derive_artist_slug` côté backend (watt_compat.py) :
  // priorité à `artist_name` (slugifié), fallback sur le local-part de l'email.
  // Sans cet alignement, dès que l'user remplit son artist_name, le lien
  // topbar renvoie vers une URL obsolète et le backend 404.
  const source = u.artist_name || (String(u.email || '').split('@')[0] || '');
  return source
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')   // retirer accents
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function toggleUserMenu(ev) {
  if (ev) ev.stopPropagation();
  const menu = document.getElementById('smyle-user-menu');
  if (!menu) return;
  if (menu.classList.contains('open')) _closeUserMenu();
  else _openUserMenu();
}

function _openUserMenu() {
  const menu = document.getElementById('smyle-user-menu');
  if (!menu) return;
  menu.classList.add('open');
  setTimeout(() => {
    document.addEventListener('click', _onDocClickCloseMenu, { once: true });
    document.addEventListener('keydown', _onEscCloseMenu);
  }, 0);
}

function _closeUserMenu() {
  const menu = document.getElementById('smyle-user-menu');
  if (!menu) return;
  menu.classList.remove('open');
  document.removeEventListener('keydown', _onEscCloseMenu);
}

function _onDocClickCloseMenu(e) {
  const menu = document.getElementById('smyle-user-menu');
  if (!menu) return;
  if (!menu.contains(e.target) && !e.target.closest('.user-badge')) _closeUserMenu();
  else {
    // Si click interne, re-registrer pour le prochain
    document.addEventListener('click', _onDocClickCloseMenu, { once: true });
  }
}

function _onEscCloseMenu(e) {
  if (e.key === 'Escape') _closeUserMenu();
}

// ── 6. AUTH UI ──────────────────────────────────────────────────────────────

function renderAuthArea() {
  const user = getCurrentUser();
  const area = document.getElementById('authArea');
  if (!area) return;

  if (user) {
    // Initiales compactes : on se base sur l'email (plus stable que le nom).
    const src = String(user.email || user.name || '??');
    const base = src.split('@')[0].replace(/[^a-z0-9]/gi, ' ').trim();
    const parts = base.split(/\s+/);
    let initials;
    if (parts.length >= 2) {
      initials = (parts[0][0] + parts[1][0]).toUpperCase();
    } else {
      initials = base.slice(0, 2).toUpperCase();
    }
    const fullName = user.name || user.email;
    const slug = _userMenuSlug();
    const profileHref = slug ? `/@${slug}` : '/dashboard';
    // Effigie "petit bonhomme" : raccourci direct vers /u/<slug>.
    // URL neutre : un compte peut exister comme fan (sans son publié) et
    // l'URL ne présume pas du statut artiste. Le statut « artiste » est
    // acquis par l'action (1er son posté). La page /u/<slug> est L'UNIQUE
    // endroit où vit le profil — création, édition in-place et vue
    // publique cohabitent (mode owner / mode fan selon isSelf). Le WATT
    // BOARD (/dashboard) est réservé au back : analytique + upload sons +
    // recettes Suno.
    area.innerHTML = `
      <a class="profile-quick-btn" href="${profileHref}" title="Mon profil" aria-label="Mon profil">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 016-6h4a6 6 0 016 6v1"/></svg>
      </a>
      <div class="user-badge" title="${fullName}" onclick="toggleUserMenu(event)">
        <div class="user-avatar">${initials}</div>
        <span class="user-badge-caret" aria-hidden="true">▾</span>
      </div>
      <div class="user-menu" id="smyle-user-menu" role="menu">
        <div class="user-menu-head">
          <div class="user-menu-avatar">${initials}</div>
          <div class="user-menu-info">
            <div class="user-menu-name">${fullName}</div>
            <div class="user-menu-mail">${user.email || ''}</div>
          </div>
        </div>
        <a class="user-menu-item" href="${profileHref}" role="menuitem">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 016-6h4a6 6 0 016 6v1"/></svg>
          Mon profil
        </a>
        <a class="user-menu-item" href="/library" role="menuitem">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
          Ma bibliothèque
        </a>
        <a class="user-menu-item" href="/dashboard" role="menuitem">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
          WATT BOARD
        </a>
        <button class="user-menu-item" onclick="openStreakModal()" role="menuitem">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8.5 14.5A2.5 2.5 0 0011 17c2 0 3.5-1.5 3.5-4 0-3-2-4.5-2-7 0 0-3 1.5-3 5 0-1.5-.5-2.5-1.5-3.5-.5 1.5-1 2.5-1 4.5a4 4 0 002 3z"/></svg>
          Récompense du jour
        </button>
        <button class="user-menu-item" onclick="openReferralModal()" role="menuitem">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><path d="M20 8v6M23 11h-6"/></svg>
          Parrainage
        </button>
        <button class="user-menu-item" onclick="openPackModal()" role="menuitem">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="20 12 20 22 4 22 4 12"/><rect x="2" y="7" width="20" height="5"/><line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 010-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 000-5C13 2 12 7 12 7z"/></svg>
          Ouvrir un pack
        </button>
        <div class="user-menu-sep"></div>
        <button class="user-menu-item user-menu-item-danger" onclick="doLogout()" role="menuitem">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          Déconnexion
        </button>
      </div>
    `;
  } else {
    area.innerHTML = `
      <button class="auth-btn" onclick="openAuthModal('login')">Connexion</button>
      <button class="auth-btn" onclick="openAuthModal('signup')" style="margin-left:6px">S'inscrire</button>
    `;
  }
}

function openAuthModal(tab) {
  // Si déjà connecté, le badge ouvre le user menu (via toggleUserMenu).
  // "Connecté" = un JWT existe. Avant, on testait getCurrentUser() (cache
  // localStorage) : un cache périmé sans token bloquait l'ouverture du
  // modal — bouton "Se connecter" et ?auth=login devenaient inopérants
  // (constat audit 2026-06-10). Le token est LA source de vérité ; si un
  // cache user traîne sans token, on le purge pour réaligner l'UI.
  const _hasToken = (typeof getAuthToken === 'function') && !!getAuthToken();
  if (_hasToken) { return; }
  if (getCurrentUser()) {
    try { localStorage.removeItem('smyle_current_user'); } catch (_) { /* */ }
    if (typeof renderAuthArea === 'function') renderAuthArea();
  }
  document.getElementById('authModal').classList.add('open');
  switchAuthTab(tab);
  // Focus auto sur le premier champ après l'anim d'ouverture
  setTimeout(() => {
    const firstInput = tab === 'signup'
      ? document.getElementById('signup-email')
      : document.getElementById('login-email');
    if (firstInput) firstInput.focus();
  }, 120);
}

function closeAuthModal() {
  document.getElementById('authModal').classList.remove('open');
  document.getElementById('authMsg').textContent = '';
}

function switchAuthTab(tab) {
  document.getElementById('tab-login').classList.toggle('active',  tab === 'login');
  document.getElementById('tab-signup').classList.toggle('active', tab === 'signup');
  document.getElementById('form-login').style.display  = tab === 'login'  ? '' : 'none';
  document.getElementById('form-signup').style.display = tab === 'signup' ? '' : 'none';
  document.getElementById('authMsg').textContent = '';
  // Focus auto sur le bon champ quand on change d'onglet
  setTimeout(() => {
    const firstInput = tab === 'signup'
      ? document.getElementById('signup-email')
      : document.getElementById('login-email');
    if (firstInput && document.getElementById('authModal').classList.contains('open')) {
      firstInput.focus();
    }
  }, 40);
}

// Toggle visibility d'un champ password (œil)
function togglePasswordVisibility(inputId, btn) {
  const el = document.getElementById(inputId);
  if (!el) return;
  const showing = el.type === 'text';
  el.type = showing ? 'password' : 'text';
  if (btn) btn.textContent = showing ? '👁' : '🙈';
}

async function submitLogin() {
  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const msg      = document.getElementById('authMsg');
  if (!email || !password) { msg.textContent = 'Email et mot de passe requis.'; return; }

  msg.textContent = 'Connexion…';
  // Callback retry : si le premier essai réseau échoue (API down transient),
  // on bascule le message pour que l'utilisateur voie qu'on insiste.
  const onAttempt = ({ willRetry }) => {
    if (willRetry) msg.textContent = 'Connexion lente — nouvelle tentative…';
  };
  const result = await doLogin(email, password, { onAttempt });
  if (result.ok) {
    closeAuthModal();
    renderAuthArea();
    if (window.SmylePageServices) window.SmylePageServices.refresh();
    _consumeReturnParam();
  } else msg.textContent = result.msg;
}

// Consomme ?return=/chemin après un login/signup réussi : l'utilisateur
// arrivé via "/?auth=login&return=/dashboard" (garde d'accès d'une page
// protégée) repart là où il voulait aller au lieu de rester sur l'accueil
// (perte de contexte constatée à l'audit 2026-06-10). Sécurité : on
// n'accepte que les chemins relatifs internes ("/...") — jamais une URL
// absolue ou protocol-relative ("//evil.com") pour interdire toute
// redirection ouverte vers un site externe.
function _consumeReturnParam() {
  try {
    const params = new URLSearchParams(location.search || '');
    const target = params.get('return') || '';
    if (target && target.startsWith('/') && !target.startsWith('//')) {
      window.location.href = target;
    }
  } catch (_) { /* noop */ }
}

async function submitSignup() {
  const email    = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  const refEl    = document.getElementById('signup-referral');
  const referralCode = refEl ? refEl.value.trim() : '';
  const msg      = document.getElementById('authMsg');
  if (!email || !password) {
    msg.textContent = 'Email et mot de passe requis.';
    return;
  }
  msg.textContent = 'Création du compte…';
  const onAttempt = ({ willRetry }) => {
    if (willRetry) msg.textContent = 'Connexion lente — nouvelle tentative…';
  };
  const result = await doSignup(email, password, { onAttempt, referralCode });
  if (result.ok) {
    closeAuthModal();
    renderAuthArea();
    if (window.SmylePageServices) window.SmylePageServices.refresh();
    _consumeReturnParam();
  } else msg.textContent = result.msg;
}

// ── Parrainage (mécanique 1) — modal "Mon parrainage" ───────────────────────
// Affiche le code de l'utilisateur + lien partageable + stats (GET /referrals/me).
// Modal injecté à la demande pour ne pas alourdir le DOM initial.

function _ensureReferralModal() {
  let modal = document.getElementById('referralModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'referralModal';
  modal.className = 'modal-overlay';
  modal.style.cssText = 'position:fixed;inset:0;z-index:1000;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.6);';
  modal.innerHTML = `
    <div class="modal-card" style="max-width:420px;width:92%;background:#14101f;border:1px solid #2c2440;border-radius:16px;padding:22px;color:#eee;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h3 style="margin:0;font-size:18px;">Parraine tes amis</h3>
        <button onclick="closeReferralModal()" aria-label="Fermer" style="background:none;border:none;color:#aaa;font-size:22px;cursor:pointer;line-height:1;">×</button>
      </div>
      <p style="margin:0 0 14px;font-size:13px;color:#b9b2cc;">Partage ton code. Quand ton filleul poste son 1er son ou fait son 1er achat, vous gagnez <strong>10 Smyles chacun</strong>.</p>
      <div id="referralBody" style="font-size:14px;">Chargement…</div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeReferralModal(); });
  return modal;
}

async function openReferralModal() {
  _closeUserMenu();
  const modal = _ensureReferralModal();
  modal.style.display = 'flex';
  const body = document.getElementById('referralBody');
  body.textContent = 'Chargement…';
  try {
    const data = await apiFetch('/referrals/me');
    const code = (data && data.referral_code) || '—';
    const link = `${location.origin}/?ref=${encodeURIComponent(code)}`;
    const total   = (data && data.total_referred) || 0;
    const rewarded = (data && data.rewarded) || 0;
    const pending  = (data && data.pending) || 0;
    const earned   = (data && data.credits_earned) || 0;
    body.innerHTML = `
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;">
        <code style="flex:1;background:#0d0a16;border:1px solid #2c2440;border-radius:10px;padding:10px 12px;font-size:18px;letter-spacing:2px;text-align:center;">${code}</code>
        <button onclick="copyReferral('${code}')" style="background:#6c4cf0;border:none;color:#fff;border-radius:10px;padding:10px 12px;cursor:pointer;font-size:13px;">Copier le code</button>
      </div>
      <button onclick="copyReferral('${link.replace(/'/g, "\\'")}')" style="width:100%;background:#1d1730;border:1px solid #2c2440;color:#cfc6e6;border-radius:10px;padding:9px;cursor:pointer;font-size:12px;margin-bottom:16px;">Copier le lien d'invitation</button>
      <div style="display:flex;text-align:center;gap:8px;">
        <div style="flex:1;background:#0d0a16;border-radius:10px;padding:10px;"><div style="font-size:20px;font-weight:700;">${total}</div><div style="font-size:11px;color:#9990ad;">filleuls</div></div>
        <div style="flex:1;background:#0d0a16;border-radius:10px;padding:10px;"><div style="font-size:20px;font-weight:700;">${rewarded}</div><div style="font-size:11px;color:#9990ad;">validés</div></div>
        <div style="flex:1;background:#0d0a16;border-radius:10px;padding:10px;"><div style="font-size:20px;font-weight:700;">${earned}</div><div style="font-size:11px;color:#9990ad;">Smyles gagnés</div></div>
      </div>
      ${pending ? `<p style="margin:12px 0 0;font-size:12px;color:#9990ad;text-align:center;">${pending} filleul${pending > 1 ? 's' : ''} en attente de leur 1ère action.</p>` : ''}`;
  } catch (e) {
    body.innerHTML = `<p style="color:#e58;">Impossible de charger ton parrainage. ${(e && e.status === 401) ? 'Reconnecte-toi.' : 'Réessaie dans un instant.'}</p>`;
  }
}

function closeReferralModal() {
  const modal = document.getElementById('referralModal');
  if (modal) modal.style.display = 'none';
}

function copyReferral(text) {
  const done = () => { if (typeof window.smyleToast === 'function') window.smyleToast('Copié ✓', { type: 'success', duration: 1800 }); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => done());
  } else {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (_) {}
    document.body.removeChild(ta); done();
  }
}

if (typeof window !== 'undefined') {
  window.openReferralModal = openReferralModal;
  window.closeReferralModal = closeReferralModal;
  window.copyReferral = copyReferral;
}

// ── Streak (mécanique 2) — récompense de connexion quotidienne ───────────────
// +1 Smyle/jour, +3 au 7e jour consécutif. Modal de réclamation + rappel toast.

function _ensureStreakModal() {
  let modal = document.getElementById('streakModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'streakModal';
  modal.style.cssText = 'position:fixed;inset:0;z-index:1000;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.6);';
  modal.innerHTML = `
    <div class="modal-card" style="max-width:380px;width:90%;background:#14101f;border:1px solid #2c2440;border-radius:16px;padding:24px;color:#eee;text-align:center;">
      <button onclick="closeStreakModal()" aria-label="Fermer" style="position:absolute;top:14px;right:18px;background:none;border:none;color:#aaa;font-size:22px;cursor:pointer;">×</button>
      <div id="streakBody" style="font-size:14px;">Chargement…</div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeStreakModal(); });
  return modal;
}

async function openStreakModal() {
  _closeUserMenu();
  const modal = _ensureStreakModal();
  modal.style.display = 'flex';
  await _renderStreakBody();
}

async function _renderStreakBody() {
  const body = document.getElementById('streakBody');
  if (!body) return;
  body.textContent = 'Chargement…';
  try {
    const s = await apiFetch('/streak/me');
    const count = (s && s.streak_count) || 0;
    const can = !!(s && s.can_checkin_today);
    const nextReward = (s && s.next_reward) || 1;
    body.innerHTML = `
      <div style="font-size:44px;line-height:1;margin:6px 0 4px;">🔥</div>
      <div style="font-size:28px;font-weight:800;">${count} jour${count > 1 ? 's' : ''}</div>
      <div style="font-size:12px;color:#9990ad;margin-bottom:18px;">de connexion consécutive</div>
      ${can
        ? `<button onclick="claimStreak()" style="width:100%;background:#6c4cf0;border:none;color:#fff;border-radius:12px;padding:13px;cursor:pointer;font-size:15px;font-weight:700;">Réclamer +${nextReward} Smyle${nextReward > 1 ? 's' : ''}</button>
           <p style="margin:12px 0 0;font-size:11px;color:#9990ad;">+1 chaque jour · +3 tous les 7 jours</p>`
        : `<div style="background:#0d0a16;border-radius:12px;padding:13px;color:#9ae6b4;font-size:14px;">✓ Récompense du jour réclamée</div>
           <p style="margin:12px 0 0;font-size:11px;color:#9990ad;">Reviens demain pour continuer ta série.</p>`}`;
  } catch (e) {
    body.innerHTML = `<p style="color:#e58;">Impossible de charger ta récompense. ${(e && e.status === 401) ? 'Reconnecte-toi.' : 'Réessaie dans un instant.'}</p>`;
  }
}

function closeStreakModal() {
  const modal = document.getElementById('streakModal');
  if (modal) modal.style.display = 'none';
}

async function claimStreak() {
  const body = document.getElementById('streakBody');
  try {
    const r = await apiFetch('/streak/checkin', { method: 'POST' });
    if (r && r.claimed && typeof window.smyleToast === 'function') {
      const bonus = r.is_milestone ? ' 🎉 palier 7 jours !' : '';
      window.smyleToast(`+${r.reward_granted} Smyle${r.reward_granted > 1 ? 's' : ''}${bonus}`, { type: 'success', duration: 3200 });
    }
    // Rafraîchit la bulle de solde Smyle.
    if (window.SmyleBalance && typeof window.SmyleBalance.refresh === 'function') {
      try { window.SmyleBalance.refresh(); } catch (_) {}
    }
    await _renderStreakBody();
  } catch (e) {
    if (body) body.innerHTML = `<p style="color:#e58;">Réclamation impossible. Réessaie dans un instant.</p>`;
  }
}

// Au login : si une récompense est réclamable aujourd'hui, on ouvre
// directement la fenêtre de réclamation (1 clic, impossible à rater).
// Garde-fou : une seule ouverture auto par session de navigateur — ensuite
// l'utilisateur garde l'accès via le menu « Récompense du jour ». Le flag se
// réinitialise à la fermeture du navigateur (nouvelle journée → nouveau push).
async function _maybeNudgeStreak() {
  try {
    let alreadyOpened = false;
    try { alreadyOpened = sessionStorage.getItem('smyle_streak_autoopened') === '1'; } catch (_) {}
    if (alreadyOpened) return;
    const s = await apiFetch('/streak/me');
    if (s && s.can_checkin_today) {
      try { sessionStorage.setItem('smyle_streak_autoopened', '1'); } catch (_) {}
      openStreakModal();
    }
  } catch (_) { /* silencieux : ne jamais bloquer le chargement */ }
}

if (typeof window !== 'undefined') {
  window.openStreakModal = openStreakModal;
  window.closeStreakModal = closeStreakModal;
  window.claimStreak = claimStreak;
}

// ── Packs aléatoires (mécanique 3) — "mystery pack" ─────────────────────────
// Dépense un prix fixe de Smyles → tire 1 son au hasard du pool éligible.
// Le sink de la boucle : rend les Smyles gagnés (parrainage/streak) désirables.

function _ensurePackModal() {
  let modal = document.getElementById('packModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'packModal';
  modal.style.cssText = 'position:fixed;inset:0;z-index:1000;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.7);';
  modal.innerHTML = `
    <div class="modal-card" style="position:relative;max-width:400px;width:92%;background:#14101f;border:1px solid #2c2440;border-radius:16px;padding:24px;color:#eee;text-align:center;">
      <button onclick="closePackModal()" aria-label="Fermer" style="position:absolute;top:14px;right:18px;background:none;border:none;color:#aaa;font-size:22px;cursor:pointer;">×</button>
      <div id="packBody" style="font-size:14px;">Chargement…</div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closePackModal(); });
  return modal;
}

async function openPackModal() {
  _closeUserMenu();
  const modal = _ensurePackModal();
  modal.style.display = 'flex';
  await _renderPackIntro();
}

// Couleurs + libellés des raretés (alignés sur RARITY_TIERS backend).
const PACK_RARITY = {
  commun:     { label: 'Commun',     color: '#9aa0aa' },
  rare:       { label: 'Rare',       color: '#4ea1ff' },
  epique:     { label: 'Épique',     color: '#b06cff' },
  legendaire: { label: 'Légendaire', color: '#ffb627' },
};

async function _renderPackIntro() {
  const body = document.getElementById('packBody');
  if (!body) return;
  body.textContent = 'Chargement…';
  try {
    const info = await apiFetch('/packs/mystery');
    const price = (info && info.price) || 8;
    const pool = (info && info.pool_count) || 0;
    if (pool <= 0) {
      body.innerHTML = `
        <div style="font-size:44px;margin:6px 0 8px;">🎁</div>
        <div style="font-size:18px;font-weight:700;margin-bottom:6px;">Pool vide</div>
        <p style="font-size:13px;color:#9990ad;">Tu possèdes déjà tous les sons disponibles au tirage. Reviens quand de nouveaux sons seront publiés.</p>`;
      return;
    }
    // Légende des chances par rareté (transparence).
    const odds = (info && info.odds) || [];
    const legend = odds.map(o => {
      const r = PACK_RARITY[o.name] || { label: o.name, color: '#9aa0aa' };
      return `<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:#b9b2cc;margin:0 6px;">
        <span style="width:8px;height:8px;border-radius:50%;background:${r.color};display:inline-block;"></span>${r.label} ${o.pct}%</span>`;
    }).join('');
    body.innerHTML = `
      <div style="font-size:48px;margin:4px 0 8px;">🎁</div>
      <div style="font-size:20px;font-weight:800;margin-bottom:4px;">Pack mystère</div>
      <p style="font-size:13px;color:#b9b2cc;margin-bottom:4px;">Tire un son au hasard parmi <strong>${pool}</strong> disponibles.</p>
      <p style="font-size:11px;color:#9990ad;margin-bottom:12px;">Tu pourrais décrocher un son bien plus cher que le prix du tirage.</p>
      <div style="margin-bottom:18px;line-height:1.8;">${legend}</div>
      <button id="packOpenBtn" onclick="openPack()" style="width:100%;background:#6c4cf0;border:none;color:#fff;border-radius:12px;padding:14px;cursor:pointer;font-size:16px;font-weight:700;">Ouvrir — ${price} Smyle${price > 1 ? 's' : ''}</button>`;
  } catch (e) {
    body.innerHTML = `<p style="color:#e58;">Impossible de charger le pack. ${(e && e.status === 401) ? 'Reconnecte-toi.' : 'Réessaie dans un instant.'}</p>`;
  }
}

async function openPack() {
  const body = document.getElementById('packBody');
  const btn = document.getElementById('packOpenBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Ouverture…'; }
  // ── Phase 1 : suspense — la boîte tremble et pulse pendant l'appel API.
  if (body) body.innerHTML = `
    <style>
      @keyframes packShake{0%,100%{transform:rotate(-7deg) translateY(0)}25%{transform:rotate(7deg) translateY(-5px)}50%{transform:rotate(-5deg) translateY(0)}75%{transform:rotate(6deg) translateY(-4px)}}
      @keyframes packGlow{0%,100%{filter:drop-shadow(0 0 6px rgba(108,76,240,.5))}50%{filter:drop-shadow(0 0 28px rgba(108,76,240,.95))}}
      @keyframes packBurst{0%{transform:scale(1);opacity:1}55%{transform:scale(1.55);opacity:1}100%{transform:scale(2.3);opacity:0}}
      @keyframes cardReveal{0%{transform:scale(.3) translateY(24px);opacity:0}60%{transform:scale(1.1)}100%{transform:scale(1) translateY(0);opacity:1}}
      @keyframes ringPulse{0%{transform:scale(.7);opacity:.9}100%{transform:scale(2.6);opacity:0}}
      @keyframes shineSweep{0%{left:-60%}100%{left:150%}}
      @keyframes sparkFloat{0%{transform:translateY(0) scale(1);opacity:1}100%{transform:translateY(-46px) scale(.3);opacity:0}}
    </style>
    <div style="height:150px;display:flex;align-items:center;justify-content:center;">
      <div id="packBox" style="font-size:74px;animation:packShake .42s ease-in-out infinite, packGlow 1s ease-in-out infinite;">🎁</div>
    </div>
    <p style="font-size:13px;color:#9990ad;">Ouverture du pack…</p>`;
  try {
    const r = await apiFetch('/packs/mystery/open', { method: 'POST' });
    // Rafraîchit la bulle de solde.
    if (window.SmyleBalance && typeof window.SmyleBalance.refresh === 'function') {
      try { window.SmyleBalance.refresh(); } catch (_) {}
    }
    const title = (r && r.title) || 'Un son';
    const rar = PACK_RARITY[r && r.rarity] || { label: 'Commun', color: '#9aa0aa' };
    const isTop = r && (r.rarity === 'epique' || r.rarity === 'legendaire');

    // ── Phase 2 : la boîte explose après un court suspense.
    await new Promise((res) => setTimeout(res, 700));
    const boxEl = document.getElementById('packBox');
    if (boxEl) boxEl.style.animation = 'packBurst .45s ease-out forwards';
    await new Promise((res) => setTimeout(res, 430));

    // ── Phase 3 : révélation de la carte, colorée selon la rareté.
    const sparks = isTop
      ? ['✨', '🌟', '✨', '💫', '✨']
          .map((s, i) => `<span style="position:absolute;left:${8 + i * 21}%;top:${15 + (i % 2) * 32}%;font-size:22px;animation:sparkFloat ${0.8 + i * 0.12}s ease-out forwards;animation-delay:${i * 0.06}s;">${s}</span>`)
          .join('')
      : '';
    if (body) body.innerHTML = `
      <div style="position:relative;">
        ${sparks}
        <div style="position:relative;display:inline-block;margin:4px auto 12px;">
          <div style="position:absolute;inset:-14px;border-radius:50%;border:2px solid ${rar.color};animation:ringPulse .7s ease-out forwards;"></div>
          <div style="font-size:52px;animation:cardReveal .5s cubic-bezier(.2,1.3,.4,1) both;filter:drop-shadow(0 0 18px ${rar.color});">${isTop ? '🌟' : '🎉'}</div>
        </div>
        <div style="animation:cardReveal .5s cubic-bezier(.2,1.3,.4,1) both;animation-delay:.08s;">
          <div style="position:relative;overflow:hidden;display:inline-block;background:${rar.color}22;border:1px solid ${rar.color};color:${rar.color};font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:5px 14px;border-radius:999px;margin-bottom:10px;">
            ${rar.label}
            <span style="position:absolute;top:0;left:-60%;width:45%;height:100%;background:linear-gradient(100deg,transparent,rgba(255,255,255,.55),transparent);animation:shineSweep 1s ease-in-out .3s both;"></span>
          </div>
          <div style="font-size:22px;font-weight:800;margin:4px 0 16px;color:${isTop ? rar.color : '#fff'};">${title}</div>
          <a href="/library" style="display:block;background:#6c4cf0;color:#fff;border-radius:12px;padding:12px;text-decoration:none;font-weight:700;margin-bottom:8px;">Voir dans ma bibliothèque</a>
          <button onclick="_renderPackIntro()" style="width:100%;background:#1d1730;border:1px solid #2c2440;color:#cfc6e6;border-radius:10px;padding:10px;cursor:pointer;font-size:13px;">Ouvrir un autre pack</button>
        </div>
      </div>`;
    if (typeof window.smyleToast === 'function') {
      window.smyleToast(`${isTop ? '🌟' : '🎁'} ${rar.label} — « ${title} » !`, { type: 'success', duration: 3400 });
    }
  } catch (e) {
    let msg = 'Tirage impossible. Réessaie dans un instant.';
    if (e && e.status === 402) {
      const d = e.body && e.body.detail;
      msg = (d && d.message) || 'Solde insuffisant pour ouvrir un pack.';
    } else if (e && e.status === 409) {
      msg = 'Tu possèdes déjà tous les sons disponibles au tirage.';
    }
    if (body) body.innerHTML = `<div style="font-size:40px;margin:12px 0;">😕</div><p style="color:#e9a;font-size:14px;">${msg}</p>
      <button onclick="_renderPackIntro()" style="margin-top:14px;background:#1d1730;border:1px solid #2c2440;color:#cfc6e6;border-radius:10px;padding:10px 16px;cursor:pointer;font-size:13px;">Retour</button>`;
  }
}

function closePackModal() {
  const modal = document.getElementById('packModal');
  if (modal) modal.style.display = 'none';
}

if (typeof window !== 'undefined') {
  window.openPackModal = openPackModal;
  window.closePackModal = closePackModal;
  window.openPack = openPack;
  window._renderPackIntro = _renderPackIntro;
}

// ── 7. Bootstrap : si un JWT existe déjà au chargement, resynchroniser ──────
// Appelé une fois au load. Si le token est valide → setCurrentUser →
// renderAuthArea affiche le badge connecté sans que l'utilisateur clique.
async function _bootstrapAuthFromToken() {
  if (typeof getAuthToken !== 'function' || !getAuthToken()) {
    // Pas de token → on purge un éventuel cache user périmé pour que la
    // topbar n'affiche pas un faux état "connecté" (avatar/menu) alors que
    // toutes les requêtes API échoueraient (constat audit 2026-06-10).
    try {
      if (getCurrentUser()) {
        localStorage.removeItem('smyle_current_user');
        renderAuthArea();
      }
    } catch (_) { /* noop */ }
    _maybeAutoOpenFromQuery();
    return;
  }
  await _fetchMeAndSync();
  renderAuthArea();
  _maybeAutoOpenFromQuery();
  // Rappel streak (mécanique 2) — léger délai pour ne pas chevaucher le rendu.
  setTimeout(() => { _maybeNudgeStreak(); }, 1200);
}

// Si on arrive ici via un redirect depuis le bandeau "session expirée" d'une
// page secondaire (/?auth=login&return=/dashboard par exemple), on ouvre
// automatiquement le modal d'auth sur le bon onglet. Le paramètre `return`
// est consommé après le login/signup réussi par _consumeReturnParam()
// (défini plus haut) : retour direct vers la page protégée d'origine.
function _maybeAutoOpenFromQuery() {
  try {
    // Si déjà connecté, on ne ré-ouvre rien.
    if (typeof getAuthToken === 'function' && getAuthToken()) return;
    const params = new URLSearchParams(location.search || '');
    // Lien de parrainage : ?ref=CODE → on ouvre directement le signup et on
    // pré-remplit le champ code (mécanique 1). Le ref prime sur ?auth=.
    const ref = (params.get('ref') || '').trim();
    let tab = params.get('auth');
    if (ref) tab = 'signup';
    if (tab !== 'login' && tab !== 'signup') return;
    // Attend un micro-tick pour laisser le DOM du modal être injecté.
    setTimeout(() => {
      if (typeof openAuthModal === 'function') openAuthModal(tab);
      if (ref) {
        const refEl = document.getElementById('signup-referral');
        if (refEl) refEl.value = ref.toUpperCase();
      }
    }, 50);
  } catch (_) { /* noop */ }
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _bootstrapAuthFromToken);
  } else {
    _bootstrapAuthFromToken();
  }
}
