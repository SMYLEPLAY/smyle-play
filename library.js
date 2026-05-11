/* ═══════════════════════════════════════════════════════════════════════════
   SMYLE PLAY — library.js
   Page /library · contenu possédé (prompts IA + ADN Playlists débloqués)
   Backend : GET /me/library/prompts · GET /me/library/adns (auth requis)
   ═══════════════════════════════════════════════════════════════════════════ */
'use strict';

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s || '');
  return d.innerHTML;
}

function getEl(id) { return document.getElementById(id); }

function setEl(id, v) {
  const el = getEl(id);
  if (el) el.textContent = String(v ?? '');
}

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch (_) { return '—'; }
}

let _libData = { prompts: [], adns: [], voices: [] };


/* ── Init + auth gate ────────────────────────────────────────────────────── */

async function init() {
  // Pas connecté → page verrouillée
  if (typeof getAuthToken !== 'function' || !getAuthToken()) {
    _showLocked();
    return;
  }

  // Connecté mais token invalide → on teste /users/me, sinon lock
  try {
    await apiFetch('/users/me');
  } catch (err) {
    if (err && err.status === 401) {
      if (typeof clearAuthToken === 'function') clearAuthToken();
      _showLocked();
      return;
    }
    // Autres erreurs : on laisse passer et on tente quand même le chargement
  }

  _showMain();
  loadAll();
}

function _showLocked() {
  const locked = getEl('lib-locked');
  const main   = getEl('lib-main');
  if (locked) locked.style.display = '';
  if (main)   main.style.display   = 'none';
}
function _showMain() {
  const locked = getEl('lib-locked');
  const main   = getEl('lib-main');
  if (locked) locked.style.display = 'none';
  if (main)   main.style.display   = '';
}


/* ── Chargement (en parallèle) ───────────────────────────────────────────── */

async function loadAll() {
  // P1-F9 — voix (3e onglet) chargées en parallèle des 2 autres.
  // Note importante sur le shape : /api/voices/me/unlocked renvoie
  // directement une liste (pas un { items: [...] }) — le backend voices
  // n'est pas paginé contrairement à /me/library/prompts. On accède donc
  // à voicesRes.value directement, pas .items.
  const [promptsRes, adnsRes, voicesRes] = await Promise.allSettled([
    apiFetch('/me/library/prompts?per_page=100'),
    apiFetch('/me/library/adns?per_page=100'),
    apiFetch('/api/voices/me/unlocked'),
  ]);

  if (promptsRes.status === 'fulfilled') {
    _libData.prompts = promptsRes.value.items || [];
    renderPrompts(_libData.prompts);
  } else {
    _renderError('lib-prompts-list', promptsRes.reason);
  }

  if (adnsRes.status === 'fulfilled') {
    _libData.adns = adnsRes.value.items || [];
    renderAdns(_libData.adns);
  } else {
    _renderError('lib-adns-list', adnsRes.reason);
  }

  if (voicesRes.status === 'fulfilled') {
    _libData.voices = Array.isArray(voicesRes.value) ? voicesRes.value : [];
    renderVoices(_libData.voices);
  } else {
    _renderError('lib-voices-list', voicesRes.reason);
  }

  setEl('lib-count-prompts', _libData.prompts.length);
  setEl('lib-count-adns',    _libData.adns.length);
  setEl('lib-count-voices',  _libData.voices.length);
}

function _renderError(containerId, err) {
  const el = getEl(containerId);
  if (!el) return;
  if (err && err.status === 401) {
    _showLocked();
    return;
  }
  console.warn('[library] erreur chargement :', err);
  el.innerHTML = `<div class="lib-empty">Impossible de charger ce contenu — réessaie plus tard.</div>`;
}


/* ── Tabs ────────────────────────────────────────────────────────────────── */

function switchTab(tab) {
  document.querySelectorAll('.lib-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  document.querySelectorAll('.lib-tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === `lib-panel-${tab}`);
  });
}


/* ── Render prompts ──────────────────────────────────────────────────────── */

function renderPrompts(items) {
  const el = getEl('lib-prompts-list');
  if (!el) return;

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Tu ne possèdes pas encore de recette.<br>
        <a href="/" class="lib-empty-cta">Explorer la marketplace →</a>
      </div>`;
    return;
  }

  // P1-F4 enrichi (Sprint 1 PR3 2026-05-04) — affichage des réglages
  // génération révélés après achat. Plateforme + Modèle + Vocal sont
  // visibles partout. Weirdness + Style Influence sont GATED (cachés
  // sur la card publique, révélés ici dans /library après unlock).
  const PROMPT_PLATFORM_LBL = {
    suno: 'Suno', udio: 'Udio', riffusion: 'Riffusion',
    stable_audio: 'Stable Audio', autre: 'Autre',
  };
  const PROMPT_VOCAL_LBL = {
    masculin: '🎙 Voix masculine',
    feminin: '🎙 Voix féminine',
    instrumental: '🎵 Instrumental',
  };

  el.innerHTML = items.map((p, i) => {
    const artist   = p.artist || {};
    const hasLyrics= !!(p.lyrics && p.lyrics.trim());
    const slug     = artist.slug || '';
    const artistLink = slug
      ? `<a href="/u/${esc(slug)}">${esc(artist.artist_name || artist.artistName || 'Artiste')}</a>`
      : esc(artist.artist_name || artist.artistName || 'Artiste');

    const lyricsBlock = hasLyrics ? `
      <div class="lib-content-block lyrics">
        <div class="lib-content-header">
          <span class="lib-content-label">🎤 Paroles</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-lyrics-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-lyrics-${i}">${esc(p.lyrics)}</div>
      </div>
    ` : '';

    // Réglages génération (P1-F4). Weirdness + style_influence sont
    // RÉVÉLÉS ici (l'utilisateur a payé), invisibles sur la card publique.
    const platformLbl = PROMPT_PLATFORM_LBL[p.prompt_platform] || p.prompt_platform || '';
    const vocalLbl = PROMPT_VOCAL_LBL[p.prompt_vocal_gender] || '';
    const settingsBadges = [
      platformLbl,
      p.prompt_model_version,
      vocalLbl,
    ].filter(Boolean).map(s => `<span class="lib-prompt-badge">${esc(s)}</span>`).join('');
    const settingsBadgesBlock = settingsBadges
      ? `<div class="lib-prompt-badges">${settingsBadges}</div>` : '';

    const weirdnessBlock = p.prompt_weirdness ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">🎛 Weirdness</span>
        </div>
        <div class="lib-content-body lib-content-body-short">${esc(p.prompt_weirdness)}</div>
      </div>
    ` : '';

    const styleInfluenceBlock = p.prompt_style_influence ? `
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">✨ Style influence</span>
        </div>
        <div class="lib-content-body lib-content-body-short">${esc(p.prompt_style_influence)}</div>
      </div>
    ` : '';

    return `
      <div class="lib-item">
        <div class="lib-item-head">
          <div class="lib-item-title">${esc(p.title || 'Recette IA')}</div>
          <div class="lib-item-meta">Débloqué le ${fmtDate(p.unlocked_at)}</div>
        </div>
        <div class="lib-item-artist">par ${artistLink}</div>
        ${p.description ? `<div class="lib-item-desc">${esc(p.description)}</div>` : ''}
        ${settingsBadgesBlock}

        <div class="lib-content-block">
          <div class="lib-content-header">
            <span class="lib-content-label">🎛 Prompt IA</span>
            <button class="lib-copy-btn" onclick="copyContent('lib-prompt-${i}', this)">Copier</button>
          </div>
          <div class="lib-content-body" id="lib-prompt-${i}">${esc(p.prompt_text || '')}</div>
        </div>

        ${weirdnessBlock}
        ${styleInfluenceBlock}
        ${lyricsBlock}
      </div>`;
  }).join('');
}


/* ── Render ADN ──────────────────────────────────────────────────────────── */

function renderAdns(items) {
  const el = getEl('lib-adns-list');
  if (!el) return;

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Tu ne possèdes pas encore d'ADN.<br>
        <span class="lib-empty-note">L'ADN se décline en deux types&nbsp;: <b>ADN Playlist</b> (univers sonore) ou <b>ADN Artiste</b> (signature complète d'un profil).</span><br>
        <a href="/" class="lib-empty-cta">Explorer les univers →</a>
      </div>`;
    return;
  }

  el.innerHTML = items.map((a, i) => {
    const artist   = a.artist || {};
    const slug     = artist.slug || '';
    const brand    = artist.brand_color || artist.brandColor || '#FFD700';
    const artistLink = slug
      ? `<a href="/u/${esc(slug)}">${esc(artist.artist_name || artist.artistName || 'Artiste')}</a>`
      : esc(artist.artist_name || artist.artistName || 'Artiste');

    const usageBlock = a.usage_guide ? `
      <span class="lib-adn-section-title">Guide d'utilisation</span>
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">📘 Usage</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-usage-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-usage-${i}">${esc(a.usage_guide)}</div>
      </div>
    ` : '';

    const exampleBlock = a.example_outputs ? `
      <span class="lib-adn-section-title">Exemples de sorties</span>
      <div class="lib-content-block">
        <div class="lib-content-header">
          <span class="lib-content-label">✨ Exemples</span>
          <button class="lib-copy-btn" onclick="copyContent('lib-ex-${i}', this)">Copier</button>
        </div>
        <div class="lib-content-body" id="lib-ex-${i}">${esc(a.example_outputs)}</div>
      </div>
    ` : '';

    // Détection du sous-type d'ADN :
    //   - "artist" → ADN Artiste (signature complète de profil)
    //   - "playlist" (ou défaut) → ADN Playlist (univers sonore)
    const rawKind = String(a.kind || a.adn_type || a.type || 'playlist').toLowerCase();
    const isArtist = rawKind === 'artist' || rawKind === 'artiste' || rawKind === 'profile';
    const kindLabel = isArtist ? 'ADN Artiste' : 'ADN Playlist';
    const kindSub   = isArtist
      ? `signature complète de ${artistLink}`
      : `univers signature de ${artistLink}`;
    const kindBadgeCls = isArtist ? 'lib-adn-kind-artist' : 'lib-adn-kind-playlist';

    return `
      <div class="lib-item" style="border-left: 3px solid ${esc(brand)}">
        <div class="lib-item-head">
          <div class="lib-item-title">
            <svg class="lib-adn-dna-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="14" height="14" aria-hidden="true">
              <path d="M7 3c0 4 10 6 10 10M7 11c0 4 10 6 10 10M7 21c0-4 10-6 10-10"/>
              <path d="M8 5h8M8 8h8M8 13h8M8 16h8M8 19h8" stroke-width="1.1" opacity="0.55"/>
            </svg>
            ADN — ${esc(artist.artist_name || artist.artistName || 'Artiste')}
            <span class="lib-adn-kind ${kindBadgeCls}">${kindLabel}</span>
          </div>
          <div class="lib-item-meta">Acquis le ${fmtDate(a.owned_at)}</div>
        </div>
        <div class="lib-item-artist">${kindSub}</div>
        ${a.description ? `<div class="lib-item-desc">${esc(a.description)}</div>` : ''}
        ${usageBlock}
        ${exampleBlock}
      </div>`;
  }).join('');
}


/* ── Render Voices (P1-F9) ───────────────────────────────────────────────
   Affiche les voix unlock par l'user (GET /api/voices/me/unlocked).
   Chaque card expose :
   - nom + style + licence
   - genres compatibles
   - lecteur audio inline (sample_url R2)
   - bouton "Télécharger" (a download de sample_url)

   Note sur l'absence de nom d'artiste : le backend /api/voices renvoie
   uniquement artist_id (pas le payload artist enrichi). Pour la 1re
   version, on laisse l'utilisateur cliquer "Voir l'artiste" → /u/<id>
   (résolu côté serveur). On enrichira plus tard si besoin (effort
   minimal côté backend pour ajouter artist_name + slug).                  */

const VOICE_LICENSE_LBL_LIB = {
  personnel:  'Personnel',
  commercial: 'Commercial',
  exclusif:   'Exclusif',
};

const VOICE_GENRES_LBL_LIB = {
  rnb: 'RnB', pop: 'Pop', trap: 'Trap', rap: 'Rap', electro: 'Electro',
  house: 'House', afro: 'Afro', jazz: 'Jazz', soul: 'Soul', rock: 'Rock',
  autre: 'Autre',
};

function _libVoiceGenresStr(keys) {
  if (!Array.isArray(keys) || !keys.length) return '';
  return keys.map(k => VOICE_GENRES_LBL_LIB[k] || k).join(' · ');
}

function renderVoices(items) {
  const el = getEl('lib-voices-list');
  if (!el) return;

  if (!items.length) {
    el.innerHTML = `
      <div class="lib-empty">
        Tu n'as pas encore débloqué de voix.<br>
        <span class="lib-empty-note">Une voix débloquée te donne accès au sample audio + à la licence d'usage. Choisis-la sur le profil de l'artiste.</span><br>
        <a href="/" class="lib-empty-cta">Explorer la marketplace →</a>
      </div>`;
    return;
  }

  el.innerHTML = items.map((v, i) => {
    const license = VOICE_LICENSE_LBL_LIB[v.license] || v.license || '';
    const genres  = _libVoiceGenresStr(v.genres);
    // Backend enrichi (feat/voices-enriched-payload) — v.artist contient
    // { id, artist_name, slug, brand_color }. On affiche "par <Artiste>"
    // avec lien /u/<slug> + bordure brand_color sur la card.
    const artist = v.artist || null;
    const artistName = (artist && artist.artist_name) || '';
    const artistSlug = (artist && artist.slug) || '';
    const brandColor = (artist && artist.brand_color) || '';
    const artistBlock = artistName
      ? (artistSlug
          ? `<div class="lib-item-artist">par <a href="/u/${esc(artistSlug)}">${esc(artistName)}</a></div>`
          : `<div class="lib-item-artist">par ${esc(artistName)}</div>`)
      : '';
    // Téléchargement du sample : on pose un <a download> direct sur l'URL R2.
    // Pas d'auth header → l'URL R2 doit être publique (signed-URL ou public-read).
    const dlBtn = v.sample_url
      ? `<a href="${esc(v.sample_url)}" download class="lib-copy-btn">Télécharger le sample</a>`
      : `<span class="lib-copy-btn" style="opacity:.5">Sample indisponible</span>`;
    const audioBlock = v.sample_url
      ? `<div class="lib-content-block">
           <div class="lib-content-header">
             <span class="lib-content-label">🎙 Sample audio</span>
             ${dlBtn}
           </div>
           <div class="lib-content-body lib-voice-audio-wrap">
             <audio controls preload="none" src="${esc(v.sample_url)}" class="lib-voice-audio"></audio>
           </div>
         </div>`
      : '';
    // Bordure brand_color sur la card si dispo (cohérent avec ADN cards).
    const cardStyle = brandColor ? ` style="border-left: 3px solid ${esc(brandColor)}"` : '';
    return `
      <div class="lib-item"${cardStyle}>
        <div class="lib-item-head">
          <div class="lib-item-title">
            🎙 ${esc(v.name || 'Voix')}
            <span class="lib-adn-kind lib-adn-kind-playlist">${esc(license)}</span>
          </div>
          <div class="lib-item-meta">Acquise le ${fmtDate(v.owned_at || v.updated_at || v.created_at)}</div>
        </div>
        ${artistBlock}
        ${v.style ? `<div class="lib-item-desc">${esc(v.style)}</div>` : ''}
        ${genres ? `<div class="lib-item-artist">Genres : ${esc(genres)}</div>` : ''}
        ${audioBlock}
      </div>`;
  }).join('');
}


/* ── Copy ────────────────────────────────────────────────────────────────── */

function copyContent(sourceId, btn) {
  const src = getEl(sourceId);
  if (!src) return;
  const text = src.textContent;

  const done = () => {
    if (!btn) return;
    const prev = btn.textContent;
    btn.textContent = '✓ Copié';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = prev;
      btn.classList.remove('copied');
    }, 1600);
    showToast('Contenu copié dans le presse-papiers');
  };

  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(done).catch(() => _fallbackCopy(text, done));
  } else {
    _fallbackCopy(text, done);
  }
}

function _fallbackCopy(text, cb) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); cb && cb(); }
  catch (_) { showToast('Copie impossible.'); }
  document.body.removeChild(ta);
}


/* ── Toast ───────────────────────────────────────────────────────────────── */

let _toastTimer = null;
function showToast(msg) {
  const el = getEl('lib-toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 2400);
}


/* ── Init ────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', init);
