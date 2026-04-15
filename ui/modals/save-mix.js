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
  if (!name) { document.getElementById('saveMixMsg').textContent = 'Entre un nom.'; return; }
  const ok = saveUserPlaylist(name, myMixTracks.map(m => ({ ...m })));
  if (ok) {
    showToast(`Playlist « ${name} » sauvegardée !`);
    closeSaveMix();
  } else {
    document.getElementById('saveMixMsg').textContent = 'Erreur lors de la sauvegarde.';
  }
}
