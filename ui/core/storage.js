/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/storage.js
   localStorage wrappers: users, current user, play counters, user playlists.
   Pure functions — no shared state. Doit être chargé après state.js/dom.js
   et avant les consommateurs (modals, player, hub, app).
   ───────────────────────────────────────────────────────────────────────── */

// ── 4. PLAY COUNTER — cache local + sync DB via POST /api/watt/plays/<id> ───
// Stratégie :
//   1. Incrément immédiat du cache localStorage (UX instantanée, +1 visible
//      avant tout aller-retour réseau).
//   2. POST en background à l'endpoint backend.
//   3. Quand la réponse DB arrive, sa valeur écrase le cache (source de
//      vérité) et met à jour tous les compteurs visibles dans le DOM pour
//      ce track.
// Throttle 5 s par track côté client pour absorber les double-clics rapides
// et les changements de piste en chaîne — n'évite pas la fraude, c'est juste
// du smoothing UX. Le backend reste l'unique compteur autoritatif.
// Tracks legacy hardcodés (pas en DB) : l'endpoint renvoie {ok:false}, on
// garde alors le compteur local optimiste sans le réécrire à zéro.

const _playPostThrottle = Object.create(null);

function getPlayCount(id) {
  return parseInt(localStorage.getItem(`smyle_plays_${id}`) || '0', 10);
}

function _writePlayCount(id, n) {
  try { localStorage.setItem(`smyle_plays_${id}`, n); } catch (_) {}
  const el = document.getElementById(`plays-${id}`);
  if (el && typeof fmtPlays === 'function') {
    el.textContent = `${fmtPlays(n)} ▶`;
  }
}

function incrementPlay(id) {
  if (id == null || id === '') return 0;
  const local = getPlayCount(id) + 1;
  _writePlayCount(id, local);

  // Throttle 5 s par track côté client
  const now = Date.now();
  if (_playPostThrottle[id] && now - _playPostThrottle[id] < 5000) {
    return local;
  }
  _playPostThrottle[id] = now;

  // POST backend en background — on n'attend pas, on n'interrompt jamais
  // la lecture audio si l'API tombe. Si le backend renvoie un compteur DB
  // valide, on l'utilise comme source de vérité.
  if (typeof fetch !== 'function') return local;

  fetch(`/api/watt/plays/${encodeURIComponent(id)}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Accept': 'application/json' },
  })
    .then(r => (r && r.ok) ? r.json() : null)
    .then(data => {
      if (!data || data.ok !== true) return;
      const dbPlays = parseInt(data.plays, 10);
      if (Number.isFinite(dbPlays) && dbPlays >= local) {
        _writePlayCount(id, dbPlays);
      }
    })
    .catch(() => { /* offline / réseau : on garde le cache local */ });

  return local;
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
