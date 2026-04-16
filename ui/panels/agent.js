/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/panels/agent.js
   WATT Control Center — panneau de monitoring communautaire.

   Reads shared state from ui/core/state.js: (aucune dépendance directe)
   Calls helpers from:
     ui/core/dom.js — showToast, _esc, _fmtHub
   Cross-module calls (resolved at call time):
     ui/panels/playlist.js — closePanel (via closeAll)
     ui/panels/mix.js      — closeMixPanel (via closeAll)

   Point d'entrée public :
     openAgentPanel()   — ouvre le panneau + charge les données
     closeAgentPanel()  — ferme le panneau
     toggleAgentPanel() — toggle open/close

   Tabs disponibles :
     cockpit     | Classement live + stats globales
     monitoring  | Derniers sons publiés
     inbox       | Demandes de collab reçues
     dna         | Classificateur ADN + générateur prompt Suno

   Doit être chargé AVANT ui/app.js (pour que closeAll() le référence).
   ───────────────────────────────────────────────────────────────────────── */

'use strict';

// ── État interne ──────────────────────────────────────────────────────────────

const _agent = {
  activeTab:  'cockpit',
  loading:    false,
  data: {
    artists: [],
    tracks:  [],
    collabs: [],
    stats:   { artists: 0, tracks: 0, plays: 0 },
    dna:     null,   // dernier résultat DNA analysé
  },
};

// ── Open / Close / Toggle ─────────────────────────────────────────────────────

function openAgentPanel() {
  // Fermer les autres panels d'abord
  closePanel();
  closeMixPanel();

  const panel = document.getElementById('agentPanel');
  if (!panel) return;

  panel.classList.add('open');
  document.getElementById('overlay').classList.add('show');

  // Charger les données dès l'ouverture
  _agentLoadTab(_agent.activeTab);
}

function closeAgentPanel() {
  const panel = document.getElementById('agentPanel');
  if (!panel) return;
  panel.classList.remove('open');

  // Retirer l'overlay seulement si aucun autre panel n'est ouvert
  const trackOpen = document.getElementById('trackPanel')?.classList.contains('open');
  const mixOpen   = document.getElementById('mixPanel')?.classList.contains('open');
  if (!trackOpen && !mixOpen) {
    document.getElementById('overlay').classList.remove('show');
  }
}

function toggleAgentPanel() {
  const panel = document.getElementById('agentPanel');
  if (!panel) return;
  panel.classList.contains('open') ? closeAgentPanel() : openAgentPanel();
}

// ── Navigation entre tabs ─────────────────────────────────────────────────────

function agentTab(tabKey) {
  _agent.activeTab = tabKey;

  // Mettre à jour les boutons de navigation
  document.querySelectorAll('.agent-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabKey);
  });

  _agentLoadTab(tabKey);
}

// ── Chargement des données ────────────────────────────────────────────────────

async function _agentLoadTab(tabKey) {
  const body = document.getElementById('agent-body');
  if (!body) return;

  body.innerHTML = `<div class="agent-loading">
    <span class="agent-loading-dot"></span>
    <span class="agent-loading-dot"></span>
    <span class="agent-loading-dot"></span>
  </div>`;

  try {
    switch (tabKey) {
      case 'cockpit':    await _agentRenderCockpit(body);    break;
      case 'monitoring': await _agentRenderMonitoring(body); break;
      case 'inbox':      await _agentRenderInbox(body);      break;
      case 'dna':        _agentRenderDNA(body);              break;
      default:           body.innerHTML = `<div class="agent-empty">Tab inconnu</div>`;
    }
  } catch (err) {
    body.innerHTML = `<div class="agent-error">
      <div class="agent-error-icon">⚠</div>
      <div>Erreur de chargement</div>
      <div class="agent-error-sub">${err.message || 'Vérifier la connexion au serveur'}</div>
      <button class="agent-retry-btn" onclick="agentTab('${tabKey}')">Réessayer</button>
    </div>`;
  }
}

// ── Tab : Cockpit (stats + classement) ───────────────────────────────────────

async function _agentRenderCockpit(body) {
  const res     = await fetch('/api/artists');
  if (!res.ok) throw new Error(`API /api/artists : ${res.status}`);
  const { artists } = await res.json();

  _agent.data.artists = artists || [];

  const totalTracks = artists.reduce((s, a) => s + (a.trackCount || 0), 0);
  const totalPlays  = artists.reduce((s, a) => s + (a.plays     || 0), 0);

  const rankRows = artists.length
    ? artists.map((a, i) => {
        const medals = ['🥇', '🥈', '🥉'];
        const medal  = i < 3 ? `<span class="agent-medal">${medals[i]}</span>` : `<span class="agent-rank-num">${String(i + 1).padStart(2, '0')}</span>`;
        return `
          <div class="agent-rank-row" onclick="window.location.href='/artiste/${_esc(a.slug)}'">
            ${medal}
            <div class="agent-rank-info">
              <span class="agent-rank-name">${_esc(a.artistName)}</span>
              ${a.genre ? `<span class="agent-rank-genre">${_esc(a.genre)}</span>` : ''}
            </div>
            <span class="agent-rank-plays">${_fmtHub(a.plays || 0)} ▶</span>
            <span class="agent-rank-tracks">${a.trackCount || 0} son${(a.trackCount || 0) > 1 ? 's' : ''}</span>
          </div>`;
      }).join('')
    : `<div class="agent-empty">
         <div class="agent-empty-icon">🎵</div>
         <div>Aucun artiste dans le réseau pour l'instant.</div>
         <a href="/watt" class="agent-cta-link">Rejoindre WATT →</a>
       </div>`;

  body.innerHTML = `
    <!-- Stats globales -->
    <div class="agent-stats-row">
      <div class="agent-stat-card">
        <div class="agent-stat-val">${artists.length}</div>
        <div class="agent-stat-lbl">artistes</div>
      </div>
      <div class="agent-stat-card">
        <div class="agent-stat-val">${totalTracks}</div>
        <div class="agent-stat-lbl">sons publiés</div>
      </div>
      <div class="agent-stat-card">
        <div class="agent-stat-val">${_fmtHub(totalPlays)}</div>
        <div class="agent-stat-lbl">écoutes totales</div>
      </div>
    </div>

    <!-- Classement -->
    <div class="agent-section-title">
      <svg viewBox="0 0 24 24" fill="currentColor" width="10" height="10"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
      Classement WATT
    </div>
    <div class="agent-rank-list">${rankRows}</div>

    <!-- Lien vers la page WATT complète -->
    <a href="/watt" class="agent-full-link">Voir la page WATT complète →</a>
  `;
}

// ── Tab : Monitoring (derniers sons) ─────────────────────────────────────────

async function _agentRenderMonitoring(body) {
  const res = await fetch('/api/tracks/recent');
  if (!res.ok) throw new Error(`API /api/tracks/recent : ${res.status}`);
  const { tracks } = await res.json();

  _agent.data.tracks = tracks || [];

  const trackRows = tracks.length
    ? tracks.map(t => {
        const d       = new Date(t.uploadedAt || Date.now());
        const dateStr = d.toLocaleDateString('fr', { day: 'numeric', month: 'short', year: 'numeric' });
        const timeStr = d.toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' });
        return `
          <div class="agent-track-row" onclick="window.location.href='/artiste/${_esc(t.artistSlug || '')}'">
            <div class="agent-track-avatar">${(t.artistName || '?')[0].toUpperCase()}</div>
            <div class="agent-track-info">
              <div class="agent-track-name">${_esc(t.name || 'Sans titre')}</div>
              <div class="agent-track-meta">
                <span class="agent-track-artist">${_esc(t.artistName || '—')}</span>
                ${t.genre ? `· <span class="agent-track-genre">${_esc(t.genre)}</span>` : ''}
              </div>
            </div>
            <div class="agent-track-date">
              <div>${dateStr}</div>
              <div class="agent-track-time">${timeStr}</div>
            </div>
            ${(t.plays > 0) ? `<span class="agent-track-plays">${_fmtHub(t.plays)} ▶</span>` : ''}
          </div>`;
      }).join('')
    : `<div class="agent-empty">
         <div class="agent-empty-icon">🎧</div>
         <div>Aucun son publié pour l'instant.</div>
         <a href="/dashboard" class="agent-cta-link">Publier un son →</a>
       </div>`;

  body.innerHTML = `
    <div class="agent-section-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="10" height="10" stroke-linecap="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
      Derniers sons publiés
    </div>
    <div class="agent-track-list">${trackRows}</div>
  `;
}

// ── Tab : Inbox (demandes de collab) ─────────────────────────────────────────

async function _agentRenderInbox(body) {
  const res = await fetch('/api/collabs/inbox');

  if (res.status === 401) {
    body.innerHTML = `
      <div class="agent-empty">
        <div class="agent-empty-icon">🔒</div>
        <div>Connecte-toi pour voir tes demandes de collab.</div>
        <a href="/dashboard" class="agent-cta-link">Se connecter →</a>
      </div>`;
    return;
  }

  if (!res.ok) throw new Error(`API /api/collabs/inbox : ${res.status}`);
  const { collabs } = await res.json();

  _agent.data.collabs = collabs || [];

  const collabRows = collabs.length
    ? collabs.map(c => {
        const d       = new Date(c.created_at);
        const dateStr = d.toLocaleDateString('fr', { day: 'numeric', month: 'short' });
        const statusClass = { pending: 'pending', seen: 'seen', accepted: 'accepted', declined: 'declined' }[c.status] || 'pending';
        const statusLabel = { pending: 'Nouveau', seen: 'Lu', accepted: 'Accepté', declined: 'Décliné' }[c.status] || c.status;
        return `
          <div class="agent-collab-row">
            <div class="agent-collab-header">
              <div class="agent-collab-from">
                <a href="/artiste/${_esc(c.from.slug)}" class="agent-collab-name">${_esc(c.from.name)}</a>
                <span class="agent-collab-arrow">→</span>
                <span class="agent-collab-to">${_esc(c.to.name)}</span>
              </div>
              <div class="agent-collab-meta">
                <span class="agent-collab-date">${dateStr}</span>
                <span class="agent-collab-status ${statusClass}">${statusLabel}</span>
              </div>
            </div>
            <div class="agent-collab-msg">${_esc(c.message)}</div>
          </div>`;
      }).join('')
    : `<div class="agent-empty">
         <div class="agent-empty-icon">📭</div>
         <div>Aucune demande de collaboration pour l'instant.</div>
         <div class="agent-empty-sub">Elles apparaîtront ici quand un artiste voudra collaborer avec toi.</div>
       </div>`;

  body.innerHTML = `
    <div class="agent-section-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="10" height="10" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
      Demandes de collaboration
      ${collabs.length > 0 ? `<span class="agent-inbox-count">${collabs.length}</span>` : ''}
    </div>
    <div class="agent-collab-list">${collabRows}</div>
  `;
}

// ── Tab : DNA Classifier + Suno Prompt Architect ─────────────────────────────

function _agentRenderDNA(body) {
  const prev = _agent.data.dna;

  body.innerHTML = `
    <div class="agent-section-title">
      <svg viewBox="0 0 24 24" fill="currentColor" width="10" height="10"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
      Classificateur ADN WATT
    </div>

    <div class="agent-dna-form">
      <input
        class  = "agent-dna-input"
        id     = "agent-dna-name"
        type   = "text"
        placeholder = "Nom du morceau (ex: Golden Hour Drift)"
        value  = "${_esc(prev ? prev.track_name : '')}"
        maxlength = "200"
      />
      <input
        class  = "agent-dna-input"
        id     = "agent-dna-genre"
        type   = "text"
        placeholder = "Genre (ex: tropical house, neo soul...)"
        value  = ""
        maxlength = "80"
      />
      <button class="agent-dna-btn" id="agent-dna-run" onclick="agentRunDNA()">
        ⚡ Analyser l'ADN
      </button>
    </div>

    <div id="agent-dna-result">
      ${prev ? _agentDNAResultHTML(prev) : '<div class="agent-empty"><span class="agent-empty-icon">🧬</span><div>Lance une analyse pour voir l\'ADN du morceau, la playlist cible et le prompt Suno.</div></div>'}
    </div>
  `;
}

async function agentRunDNA() {
  const nameEl  = document.getElementById('agent-dna-name');
  const genreEl = document.getElementById('agent-dna-genre');
  const btn     = document.getElementById('agent-dna-run');
  const result  = document.getElementById('agent-dna-result');

  const name  = (nameEl  ? nameEl.value  : '').trim();
  const genre = (genreEl ? genreEl.value : '').trim();

  if (!name) {
    nameEl && nameEl.focus();
    return;
  }

  // État loading
  btn.disabled   = true;
  btn.textContent = '⏳ Analyse en cours…';
  result.innerHTML = `<div class="agent-loading">
    <span class="agent-loading-dot"></span>
    <span class="agent-loading-dot"></span>
    <span class="agent-loading-dot"></span>
  </div>`;

  try {
    const res = await fetch('/api/agents/process-track', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ name, genre }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const json = await res.json();
    if (!json.ok) throw new Error(json.error || 'Erreur serveur');

    _agent.data.dna = json.result;
    result.innerHTML = _agentDNAResultHTML(json.result);

  } catch (err) {
    result.innerHTML = `<div class="agent-error">
      <div class="agent-error-icon">⚠</div>
      <div>Erreur d'analyse</div>
      <div class="agent-error-sub">${_esc(err.message)}</div>
      <button class="agent-retry-btn" onclick="agentRunDNA()">Réessayer</button>
    </div>`;
  } finally {
    btn.disabled    = false;
    btn.textContent = '⚡ Analyser l\'ADN';
  }
}

function _agentDNAResultHTML(r) {
  // Barre de confiance
  const pct   = Math.round((r.confidence || 0) * 100);
  const color = r.playlist_color || '#ffd700';

  // Scores des 3 ADN
  const scoreRows = Object.entries(r.scores || {})
    .sort((a, b) => b[1] - a[1])
    .map(([dna, score]) => {
      const w = Math.round(score * 100);
      const isWinner = dna === r.dna;
      return `
        <div class="agent-dna-score-row ${isWinner ? 'winner' : ''}">
          <span class="agent-dna-score-label">${_esc(dna.replace('_', ' '))}</span>
          <div class="agent-dna-score-bar-wrap">
            <div class="agent-dna-score-bar" style="width:${w}%;background:${isWinner ? color : 'rgba(255,255,255,.1)'}"></div>
          </div>
          <span class="agent-dna-score-pct">${w}%</span>
        </div>`;
    }).join('');

  // Tags Suno cliquables (copie au clic)
  const tags = (r.style_tags || [])
    .map(t => `<span class="agent-suno-tag" onclick="agentCopyTag(this,'${_esc(t)}')">${_esc(t)}</span>`)
    .join('');

  return `
    <!-- ADN résultat -->
    <div class="agent-dna-card" style="border-color:${color}22;background:${color}08">
      <div class="agent-dna-badge" style="color:${color};border-color:${color}44">
        ${_esc(r.playlist_emoji)} ${_esc(r.dna.replace(/_/g, ' '))}
      </div>
      <div class="agent-dna-playlist">
        Playlist cible : <strong style="color:${color}">${_esc(r.playlist_label)}</strong>
      </div>
      <div class="agent-dna-mood">${_esc(r.mood)}</div>

      <!-- Jauge de confiance -->
      <div class="agent-dna-confidence">
        <div class="agent-dna-conf-label">Confiance <span>${pct}%</span></div>
        <div class="agent-dna-conf-bar">
          <div class="agent-dna-conf-fill" style="width:${pct}%;background:${color}"></div>
        </div>
      </div>

      <!-- Scores par ADN -->
      <div class="agent-dna-scores">${scoreRows}</div>
    </div>

    <!-- Prompt Suno -->
    <div class="agent-section-title" style="margin-top:18px">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="10" height="10" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
      Prompt Suno généré
    </div>
    <div class="agent-suno-box">
      <div class="agent-suno-prompt" id="agent-suno-text">${_esc(r.suno_prompt)}</div>
      <button class="agent-suno-copy" onclick="agentCopyPrompt()">📋 Copier</button>
    </div>

    <!-- Tags de style -->
    <div class="agent-section-title" style="margin-top:14px">Tags de style</div>
    <div class="agent-suno-tags">${tags}</div>

    <!-- BPM + négatif -->
    <div class="agent-dna-meta">
      <span>⏱ ${_esc(r.bpm_hint)}</span>
      ${r.negative ? `<span title="À éviter dans Suno">✗ ${_esc(r.negative.split(',').slice(0,3).join(', '))}…</span>` : ''}
    </div>

    <div class="agent-dna-method">méthode : ${_esc(r.method)} · analysé le ${new Date(r.processed_at).toLocaleString('fr')}</div>
  `;
}

function agentCopyPrompt() {
  const el = document.getElementById('agent-suno-text');
  if (!el) return;
  navigator.clipboard.writeText(el.textContent).then(() => {
    const btn = el.parentElement.querySelector('.agent-suno-copy');
    if (btn) { btn.textContent = '✓ Copié !'; setTimeout(() => { btn.textContent = '📋 Copier'; }, 2000); }
  });
}

function agentCopyTag(el, tag) {
  navigator.clipboard.writeText(tag).then(() => {
    el.classList.add('copied');
    setTimeout(() => el.classList.remove('copied'), 1500);
  });
}

// ── Refresh (bouton reload dans le header du panel) ───────────────────────────

function agentRefresh() {
  _agentLoadTab(_agent.activeTab);
}
