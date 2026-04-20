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
// Stockées en localStorage sous la clé "smyle_user_playlists_<userId>".
// Cette nouvelle implémentation ne dépend plus du tableau legacy smyle_users
// (qui n'est plus rempli depuis la migration vers l'auth JWT/FastAPI).
// Elle fonctionne donc pour tout utilisateur connecté via JWT.

function _userPlaylistsKey(userId) {
  return `smyle_user_playlists_${userId}`;
}

function getUserPlaylists() {
  const user = getCurrentUser();
  if (!user || !user.id) return [];
  try {
    return JSON.parse(localStorage.getItem(_userPlaylistsKey(user.id)) || '[]');
  } catch (_) {
    return [];
  }
}

function saveUserPlaylist(name, tracks) {
  const user = getCurrentUser();
  if (!user || !user.id) return false;
  const list = getUserPlaylists();

  // Si une playlist du même nom existe, on la remplace (pas de doublons).
  const existingIdx = list.findIndex(p => p.name === name);
  const entry = {
    id: existingIdx >= 0 ? list[existingIdx].id : ('pl_' + Date.now().toString(36)),
    name,
    tracks: tracks.map(t => ({ ...t })),
    createdAt: existingIdx >= 0 ? list[existingIdx].createdAt : Date.now(),
    updatedAt: Date.now(),
  };
  if (existingIdx >= 0) list[existingIdx] = entry;
  else list.push(entry);

  try {
    localStorage.setItem(_userPlaylistsKey(user.id), JSON.stringify(list));
    return true;
  } catch (_) {
    return false;
  }
}

function deleteUserPlaylist(playlistId) {
  const user = getCurrentUser();
  if (!user || !user.id) return false;
  const list = getUserPlaylists().filter(p => p.id !== playlistId);
  try {
    localStorage.setItem(_userPlaylistsKey(user.id), JSON.stringify(list));
    return true;
  } catch (_) {
    return false;
  }
}
