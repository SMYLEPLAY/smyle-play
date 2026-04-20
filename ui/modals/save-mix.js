/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/modals/save-mix.js
   Save Mix modal: persist the current mix as a named playlist.

   Reads shared state from ui/core/state.js:
     myMixTracks
   Calls helpers from:
     ui/core/dom.js     — showToast
     ui/core/storage.js — getCurrentUser, saveUserPlaylist
   Cross-module calls (resolved at call time):
     ui/modals/auth.js  — openAuthModal (prompt login if anonymous)

   Must load after state/dom/storage/auth.
   ───────────────────────────────────────────────────────────────────────── */

// ── 11. SAVE MIX MODAL ──────────────────────────────────────────────────────

function openSaveMix() {
  if (!getCurrentUser()) { openAuthModal('login'); return; }
  if (!myMixTracks.length) { showToast('Aucun morceau dans My Mix.'); return; }
  document.getElementById('saveMixModal').classList.add('open');
  document.getElementById('mix-save-name').value = '';
  document.getElementById('saveMixMsg').textContent = '';
}

function closeSaveMix() {
  document.getElementById('saveMixModal').classList.remove('open');
}

function confirmSaveMix() {
  const name = document.getElementById('mix-save-name').value.trim();
  const msgEl = document.getElementById('saveMixMsg');
  if (!name) { if (msgEl) msgEl.textContent = 'Entre un nom.'; return; }

  // Si une playlist de ce nom existe déjà → on demande confirmation (overwrite)
  const existing = (typeof getUserPlaylists === 'function')
    ? getUserPlaylists().find(p => p.name === name)
    : null;
  if (existing && !window.confirm(`Une playlist « ${name} » existe déjà. La remplacer ?`)) {
    if (msgEl) msgEl.textContent = 'Choisis un autre nom.';
    return;
  }

  const ok = saveUserPlaylist(name, myMixTracks.map(m => ({ ...m })));
  if (ok) {
    // Toast global (si dispo) ou fallback local
    if (typeof window.smyleToast === 'function') {
      window.smyleToast(`« ${name} » sauvegardée`, { type: 'success', duration: 2800 });
    } else {
      showToast(`Playlist « ${name} » sauvegardée !`);
    }
    closeSaveMix();
    // Re-rendre le mix panel pour faire apparaître la nouvelle playlist
    if (typeof renderMixPanel === 'function') renderMixPanel();
  } else {
    if (msgEl) {
      msgEl.textContent = 'Erreur lors de la sauvegarde. Connecte-toi puis réessaie.';
    }
  }
}
