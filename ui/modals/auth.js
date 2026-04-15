/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/modals/auth.js
   Auth modal + auth area: signup/login/logout flows.

   Calls helpers from:
     ui/core/storage.js — getUsers, saveUsers, getCurrentUser,
                          setCurrentUser, clearCurrentUser

   Must load after storage.js and before script.js.
   ───────────────────────────────────────────────────────────────────────── */

// ── 5. AUTH ─────────────────────────────────────────────────────────────────

function doSignup(email, password, name) {
  const users = getUsers();
  if (users.find(u => u.email === email)) return { ok: false, msg: 'Email déjà utilisé.' };
  const user = { id: Date.now(), email, password, name, playlists: [] };
  users.push(user);
  saveUsers(users);
  setCurrentUser(user);
  return { ok: true };
}

function doLogin(email, password) {
  const users = getUsers();
  const user  = users.find(u => u.email === email && u.password === password);
  if (!user) return { ok: false, msg: 'Email ou mot de passe incorrect.' };
  setCurrentUser(user);
  return { ok: true };
}

function doLogout() {
  clearCurrentUser();
  renderAuthArea();
}

// ── 6. AUTH UI ──────────────────────────────────────────────────────────────

function renderAuthArea() {
  const user = getCurrentUser();
  const area = document.getElementById('authArea');
  if (!area) return;

  if (user) {
    const initials = user.name.slice(0, 2).toUpperCase();
    area.innerHTML = `
      <div class="user-badge" onclick="openAuthModal('login')">
        <div class="user-avatar">${initials}</div>
        <span class="user-name">${user.name}</span>
      </div>
      <button class="auth-btn" onclick="doLogout()" style="margin-left:10px">Déco</button>
    `;
  } else {
    area.innerHTML = `
      <button class="auth-btn" onclick="openAuthModal('login')">Connexion</button>
      <button class="auth-btn" onclick="openAuthModal('signup')" style="margin-left:6px">S'inscrire</button>
    `;
  }
}

function openAuthModal(tab) {
  document.getElementById('authModal').classList.add('open');
  switchAuthTab(tab);
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
}

function submitLogin() {
  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const result   = doLogin(email, password);
  if (result.ok) { closeAuthModal(); renderAuthArea(); }
  else document.getElementById('authMsg').textContent = result.msg;
}

function submitSignup() {
  const name     = document.getElementById('signup-name').value.trim();
  const email    = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  if (!name || !email || !password) {
    document.getElementById('authMsg').textContent = 'Tous les champs sont requis.';
    return;
  }
  const result = doSignup(email, password, name);
  if (result.ok) { closeAuthModal(); renderAuthArea(); }
  else document.getElementById('authMsg').textContent = result.msg;
}
