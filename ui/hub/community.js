/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/hub/community.js
   Community hub: fetch playlists + WATT community injection +
   top-3 artists rendering from /api/artists.

   Reads/writes shared state from ui/core/state.js:
     writes PLAYLISTS (in fetchPlaylists, injectCommunityPlaylist, playWattTrack)

   Calls helpers from:
     ui/core/dom.js     — showToast, _esc, _slugify, _fmtHub
   Cross-module calls (resolved at call time):
     ui/player/audio.js — loadTrack (from playWattTrack)

   ── BRIDGE PROTECTED BLOCK ─────────────────────────────────────────────────
   `_renderHubFromAPI()` was flagged by Graphify as a cross-community bridge
   (C0 → C1 via `setVal()`). Static analysis misresolved the call: `setVal`
   is a LOCAL closure const declared INSIDE the function body (line marked
   below), not the unrelated `dashboard.js` global. The closure + the
   function are kept as a single indivisible block — they move together as
   one unit. Do NOT split them across files or refactor the closure out.
   ── ─────────────────────────────────────────────────────────────────────

   Must load after state/dom/storage/audio.
   ───────────────────────────────────────────────────────────────────────── */

// ── 2. CHARGEMENT DYNAMIQUE DES PLAYLISTS ───────────────────────────────────

async function fetchPlaylists() {
  // Charge depuis FastAPI /watt/tracks-catalog (shape identique au tracks.json legacy).
  try {
    PLAYLISTS = await apiFetch('/watt/tracks-catalog');
  } catch (err) {
    // Fallback : tracks.json statique (dev hors API ou API down)
    console.warn('[SMYLE] /watt/tracks-catalog erreur, fallback /tracks.json :', err.message);
    try {
      const res = await fetch('/tracks.json');
      if (res.ok) PLAYLISTS = await res.json();
    } catch (e2) {
      console.error('[SMYLE] Impossible de charger les playlists :', e2);
    }
  }

  // Mettre à jour les compteurs sur les cartes officielles
  Object.keys(PLAYLISTS).forEach(key => {
    const el = document.getElementById(`count-${key}`);
    if (el) {
      const n = (PLAYLISTS[key]?.tracks || []).length;
      el.textContent = `${n} titre${n > 1 ? 's' : ''}`;
    }
  });

  // Sprint D — Injecter les sons communautaires WATT dans le player
  injectCommunityPlaylist();
}

// ── 2b. INJECTION PLAYLIST COMMUNAUTAIRE (Sprint D) ─────────────────────────

function injectCommunityPlaylist() {
  const wattTracks = JSON.parse(localStorage.getItem('smyle_watt_tracks') || '[]');
  const profile    = JSON.parse(localStorage.getItem('smyle_watt_profile') || 'null');
  if (!wattTracks.length) return;

  const artistName = profile?.artistName || 'Artiste WATT';

  // Convertir les tracks WATT au format PLAYLISTS compatible avec le player
  const converted = wattTracks.map(t => ({
    id:       t.id,
    file:     t.file || '',
    name:     t.name || 'Sans titre',
    duration: 0,
    url:      t.streamUrl || null,   // URL R2 pour streaming (null = pas streamable depuis l'accueil)
    genre:    t.genre || '',
    artist:   artistName,
    coverDataUrl: t.coverDataUrl || null,
    watt:     true,                  // flag pour distinguer les tracks communautaires
  }));

  // N'ajouter que les tracks avec une URL streamable
  const streamable = converted.filter(t => t.url);

  if (streamable.length) {
    PLAYLISTS['watt-community'] = {
      label:          'WATT Community',
      folder:         'WATT',
      theme:          'watt-community',
      tracks:         streamable,
      total_duration: 0,
    };
  }
}

// Jouer un son communautaire depuis le hub (identifié par son id)
function playWattTrack(trackId) {
  // Chercher d'abord dans la playlist watt-community injectée
  const wattPl = PLAYLISTS['watt-community'];
  if (wattPl) {
    const idx = wattPl.tracks.findIndex(t => t.id === trackId);
    if (idx >= 0) { loadTrack('watt-community', idx); return; }
  }

  // Fallback : chercher dans localStorage et lire directement si URL disponible
  const wattTracks = JSON.parse(localStorage.getItem('smyle_watt_tracks') || '[]');
  const t = wattTracks.find(t => t.id === trackId);
  if (t && t.streamUrl) {
    // Injection à la volée pour ce track
    if (!PLAYLISTS['watt-community']) {
      PLAYLISTS['watt-community'] = { label: 'WATT Community', folder: 'WATT', theme: 'watt-community', tracks: [], total_duration: 0 };
    }
    const profile    = JSON.parse(localStorage.getItem('smyle_watt_profile') || 'null');
    const artistName = profile?.artistName || 'Artiste WATT';
    const converted  = { id: t.id, file: t.file || '', name: t.name, duration: 0, url: t.streamUrl, genre: t.genre || '', artist: artistName, coverDataUrl: t.coverDataUrl || null, watt: true };
    PLAYLISTS['watt-community'].tracks.push(converted);
    loadTrack('watt-community', PLAYLISTS['watt-community'].tracks.length - 1);
  } else {
    showToast('Ce son n\'est pas encore disponible en streaming.');
  }
}

// ── 14c. COMMUNITY HUB — chargé depuis l'API ────────────────────────────────

function renderCommunityHub() {
  _renderHubFromAPI();   // async — gère ses propres états
}

async function _renderHubFromAPI() {
  let artists = [];

  try {
    const json = await apiFetch('/watt/artists');
    artists = json.artists || [];
  } catch (_) {
    // Fallback localStorage si l'API est indisponible
    const profile = JSON.parse(localStorage.getItem('smyle_watt_profile') || 'null');
    const tracks  = JSON.parse(localStorage.getItem('smyle_watt_tracks')  || '[]');
    if (profile && profile.artistName) {
      artists = [{
        artistName: profile.artistName,
        slug:       profile.slug || '',
        plays:      tracks.reduce((s, t) => s + (t.plays || 0), 0),
        trackCount: tracks.length,
      }];
    }
  }

  // Stats
  // ── BRIDGE PROTECTED: `setVal` is a LOCAL closure const, NOT the global
  //    `setVal` from dashboard.js that Graphify mis-resolved. Keep inline. ──
  const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const totalTracks = artists.reduce((s, a) => s + (a.trackCount || 0), 0);
  const totalPlays  = artists.reduce((s, a) => s + (a.plays || 0), 0);
  setVal('hub-nb-artists', artists.length);
  setVal('hub-nb-tracks',  totalTracks);
  setVal('hub-nb-plays',   _fmtHub(totalPlays));

  // Bandes d'artistes — classement public (type "réseau + classement" du dashboard)
  const el = document.getElementById('hub-top3');
  if (!el) return;

  if (!artists.length) {
    // Philosophie unifiée : pas de signup séparé "WATT", on invite à créer
    // un compte SMYLE PLAY qui inclut automatiquement l'espace artiste.
    el.innerHTML = `<div class="hub-t3-empty">Aucun artiste pour l'instant · <a href="/?auth=signup" class="hub-t3-empty-link">Créer mon compte →</a></div>`;
    return;
  }

  // On affiche jusqu'à 10 artistes, triés par plays décroissants
  const src = [...artists].sort((a, b) => (b.plays || 0) - (a.plays || 0)).slice(0, 10);

  el.innerHTML = src.map((a, i) => {
    const slug   = a.slug || _slugify(a.artistName);
    const url    = slug ? `/u/${slug}` : '/watt';
    // Chantier 1.2 — on privilégie `brandColor` (canonique) défini par
    // l'artiste dans son wattboard. `avatarColor` reste le fallback legacy
    // pour les comptes qui n'ont pas encore choisi de couleur explicite.
    const brand  = a.brandColor || a.avatarColor || '#FFD700';
    const name   = a.artistName || 'Artiste';
    const genre  = (a.genre || '').trim();
    const plays  = _fmtHub(a.plays || 0);
    const tracks = a.trackCount || 0;
    // Initiales pour l'avatar (2 premières lettres du nom d'artiste)
    const initialsBase = String(name).replace(/[^a-z0-9]/gi, ' ').trim();
    const parts = initialsBase.split(/\s+/);
    const initials = (parts.length >= 2
      ? (parts[0][0] + parts[1][0])
      : initialsBase.slice(0, 2)).toUpperCase();
    const rankCls = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : 'plain';

    return `
      <a class="hub-band hub-band-${rankCls}" href="${url}"
         style="--band-brand:${brand}"
         aria-label="Voir le profil de ${_esc(name)}">
        <span class="hub-band-rank">${String(i + 1).padStart(2, '0')}</span>
        <span class="hub-band-avatar" style="background:linear-gradient(135deg, ${brand}, rgba(10,4,26,.9))">
          ${_esc(initials)}
        </span>
        <span class="hub-band-info">
          <span class="hub-band-name">${_esc(name)}</span>
          <span class="hub-band-meta">
            ${genre ? `<span class="hub-band-genre">${_esc(genre)}</span>` : ''}
            ${genre ? `<span class="hub-band-dot">·</span>` : ''}
            <span class="hub-band-tracks">${tracks} son${tracks > 1 ? 's' : ''}</span>
          </span>
        </span>
        <span class="hub-band-plays">
          <span class="hub-band-plays-val">${plays}</span>
          <span class="hub-band-plays-lbl">écoutes</span>
        </span>
        <span class="hub-band-arrow" aria-hidden="true">→</span>
      </a>`;
  }).join('');
}
