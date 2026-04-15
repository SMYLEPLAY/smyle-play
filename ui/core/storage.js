/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/storage.js
   localStorage wrappers: users, current user, play counters, user playlists.
   Pure functions — no shared state. Doit être chargé après state.js/dom.js
   et avant les consommateurs (modals, player, hub, app).
   ───────────────────────────────────────────────────────────────────────── */

// ── 4. PLAY COUNTER (localStorage) ──────────────────────────────────────────

function getPlayCount(id) {
  return parseInt(localStorage.getItem(`smyle_plays_${id}`) || '0', 10);
}

function incrementPlay(id) {
  const n = getPlayCount(id) + 1;
  localStorage.setItem(`smyle_plays_${id}`, n);
  return n;
}

// ── 5. AUTH ─────────────────────────────────────────────────────────────────

function getUsers()        { return JSON.parse(localStorage.getItem('smyle_users') || '[]'); }
function saveUsers(u)      { localStorage.setItem('smyle_users', JSON.stringify(u)); }
function getCurrentUser()  { return JSON.parse(localStorage.getItem('smyle_current_user') || 'null'); }
function setCurrentUser(u) { localStorage.setItem('smyle_current_user', JSON.stringify(u)); }
function clearCurrentUser(){ localStorage.removeItem('smyle_current_user'); }

// ── USER PLAYLISTS ──────────────────────────────────────────────────────────

function saveUserPlaylist(name, tracks) {
  const user = getCurrentUser();
  if (!user) return false;
  const users = getUsers();
  const idx   = users.findIndex(u => u.id === user.id);
  if (idx === -1) return false;
  users[idx].playlists = users[idx].playlists || [];
  users[idx].playlists.push({ name, tracks, createdAt: Date.now() });
  saveUsers(users);
  setCurrentUser(users[idx]);
  return true;
}
