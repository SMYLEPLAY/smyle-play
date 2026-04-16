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

// ── Refresh (bouton reload dans le header du panel) ───────────────────────────

function agentRefresh() {
  _agentLoadTab(_agent.activeTab);
}
