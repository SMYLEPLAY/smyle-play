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

function _saveMixAuthHeaders() {
  const h = { 'Accept': 'application/json' };
  if (typeof getAuthToken === 'function') {
    const t = getAuthToken();
    if (t) h['Authorization'] = 'Bearer ' + t;
  }
  return h;
}

async function confirmSaveMix() {
  const name = document.getElementById('mix-save-name').value.trim();
  const msgEl = document.getElementById('saveMixMsg');
  if (!name) { if (msgEl) msgEl.textContent = 'Entre un nom.'; return; }

  // Visibilité — lu depuis le radio toggle injecté dans la modale
  let visibility = 'private';
  const visRadio = document.querySelector('input[name="mix-save-vis"]:checked');
  if (visRadio) visibility = visRadio.value;

  if (!getCurrentUser()) {
    if (msgEl) msgEl.textContent = 'Connecte-toi pour sauvegarder.';
    return;
  }

  // POST /playlists (DB) puis POST tracks un par un
  try {
    const createResp = await fetch('/playlists', {
      method: 'POST',
      credentials: 'same-origin',
      headers: Object.assign(_saveMixAuthHeaders(), { 'Content-Type': 'application/json' }),
      body: JSON.stringify({ title: name, visibility: visibility })
    });
    if (!createResp.ok) {
      const status = createResp.status;
      if (msgEl) msgEl.textContent = 'Création impossible (HTTP ' + status + ').';
      return;
    }
    const playlist = await createResp.json();

    // POST chaque track. Un track sans ID DB (ex: legacy hardcoded) est skip.
    let added = 0;
    let skipped = 0;
    for (const m of myMixTracks) {
      if (!m.id) { skipped++; continue; }
      try {
        const r = await fetch('/playlists/' + encodeURIComponent(playlist.id) + '/tracks', {
          method: 'POST',
          credentials: 'same-origin',
          headers: Object.assign(_saveMixAuthHeaders(), { 'Content-Type': 'application/json' }),
          body: JSON.stringify({ track_id: m.id })
        });
        if (r.ok || r.status === 409) added++;
        else skipped++;
      } catch (_) { skipped++; }
    }

    // Toast feedback
    const msg = skipped > 0
      ? `« ${name} » sauvegardée (${added} sons ajoutés, ${skipped} ignorés).`
      : `« ${name} » sauvegardée (${added} sons).`;
    if (typeof window.smyleToast === 'function') {
      window.smyleToast(msg, { type: 'success', duration: 3200 });
    } else {
      showToast(msg);
    }
    closeSaveMix();
    if (typeof renderMixPanel === 'function') await renderMixPanel();
  } catch (e) {
    if (msgEl) msgEl.textContent = 'Erreur réseau : ' + (e && e.message || 'inconnue');
  }
}
