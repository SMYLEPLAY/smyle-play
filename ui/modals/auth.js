/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/modals/auth.js
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

async function doSignup(email, password, name, { onAttempt } = {}) {
  try {
    await apiFetch('/auth/register', {
      method: 'POST',
      json: { email, password, display_name: name },
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
    const profileHref = slug ? `/u/${slug}` : '/dashboard';
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
  // On ne devrait donc arriver ici que si l'user est null.
  if (getCurrentUser()) { return; }
  document.getElementById('authModal').classList.add('open');
  switchAuthTab(tab);
  // Focus auto sur le premier champ après l'anim d'ouverture
  setTimeout(() => {
    const firstInput = tab === 'signup'
      ? document.getElementById('signup-name')
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
      ? document.getElementById('signup-name')
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
  if (result.ok) { closeAuthModal(); renderAuthArea(); }
  else msg.textContent = result.msg;
}

async function submitSignup() {
  const name     = document.getElementById('signup-name').value.trim();
  const email    = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  const msg      = document.getElementById('authMsg');
  if (!name || !email || !password) {
    msg.textContent = 'Tous les champs sont requis.';
    return;
  }
  msg.textContent = 'Création du compte…';
  const onAttempt = ({ willRetry }) => {
    if (willRetry) msg.textContent = 'Connexion lente — nouvelle tentative…';
  };
  const result = await doSignup(email, password, name, { onAttempt });
  if (result.ok) { closeAuthModal(); renderAuthArea(); }
  else msg.textContent = result.msg;
}

// ── 7. Bootstrap : si un JWT existe déjà au chargement, resynchroniser ──────
// Appelé une fois au load. Si le token est valide → setCurrentUser →
// renderAuthArea affiche le badge connecté sans que l'utilisateur clique.
async function _bootstrapAuthFromToken() {
  if (typeof getAuthToken !== 'function' || !getAuthToken()) {
    _maybeAutoOpenFromQuery();
    return;
  }
  await _fetchMeAndSync();
  renderAuthArea();
  _maybeAutoOpenFromQuery();
}

// Si on arrive ici via un redirect depuis le bandeau "session expirée" d'une
// page secondaire (/?auth=login&return=/dashboard par exemple), on ouvre
// automatiquement le modal d'auth sur le bon onglet. Le paramètre `return`
// n'est pas consommé ici — c'est à l'utilisateur ou à la logique post-login
// de décider où rediriger ensuite (hors scope de ce sprint).
function _maybeAutoOpenFromQuery() {
  try {
    // Si déjà connecté, on ne ré-ouvre rien.
    if (typeof getAuthToken === 'function' && getAuthToken()) return;
    const params = new URLSearchParams(location.search || '');
    const tab = params.get('auth');
    if (tab !== 'login' && tab !== 'signup') return;
    // Attend un micro-tick pour laisser le DOM du modal être injecté.
    setTimeout(() => {
      if (typeof openAuthModal === 'function') openAuthModal(tab);
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
