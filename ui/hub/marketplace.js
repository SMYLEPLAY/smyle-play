/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/hub/marketplace.js
   Hydratation de l'accueil transformée en marketplace (Phase 2).

   Responsabilités
   ───────────────
   1. Vitrine Smyle : fetch /watt/artists/smyle + rendu de l'avatar,
      du nom + checkmark, de la bio, des stats, du lien profil.
   2. Classement Top Sons : les N sons les plus joués (tri plays desc,
      source : /watt/tracks-recent jusqu'à l'ajout d'un endpoint top dédié).
   3. Classement Top Artistes : /watt/artists trié plays desc (déjà renvoyé
      trié par le backend, on prend les 10 premiers hors compte officiel).
   4. Grille Tous les sons : toutes les tracks de /watt/tracks-recent.
   5. Grille Tous les artistes : tous les profils publics hors Smyle
      (Smyle est déjà mis en avant dans la vitrine).
   6. Recherche inline (DNA sur les sons, CONNECT sur les profils)
      avec filtre client-side instantané.
   7. Écoute SmyleEvents pour refresh live quand un artiste publie /
      dépublie son profil ou upload / supprime un son.

   Dépendances
   ───────────
     window.apiFetch       — ui/core/api.js
     window.SmyleEvents    — ui/core/events.js
     window.showToast      — ui/core/dom.js (optionnel, best effort)

   Ce fichier doit être chargé APRÈS api.js, events.js, dom.js.
   ───────────────────────────────────────────────────────────────────────── */

(function initMarketplace() {
  'use strict';

  if (typeof window === 'undefined') return;

  // Guard : si la page n'expose pas la vitrine Smyle, on est sur une page
  // qui n'est pas l'accueil (dashboard, artiste, watt). On ne fait rien.
  // Ça rend le script safe à inclure partout via un futur bundler.
  function _isMarketplacePage() {
    return !!document.getElementById('smyle-vitrine');
  }

  // État local — pas de store global, une page = un cycle de rendu.
  const _state = {
    smyleArtist: null,     // payload de /watt/artists/smyle
    artists:     [],       // tous les artistes publics (Smyle compris)
    tracks:      [],       // tous les sons (source tracks-recent)
    // Refs DOM résolues une seule fois pour éviter les lookups répétés.
    dom: null,
  };

  function _resolveDom() {
    _state.dom = {
      vitrineRoot:      document.getElementById('smyle-vitrine'),
      vitrineAvatar:    document.getElementById('smyle-vitrine-avatar'),
      vitrineName:      document.getElementById('smyle-vitrine-name'),
      vitrineBio:       document.getElementById('smyle-vitrine-bio'),
      vitrineFollowers: document.getElementById('smyle-vitrine-followers'),
      vitrineTracks:    document.getElementById('smyle-vitrine-tracks'),
      vitrinePlays:     document.getElementById('smyle-vitrine-plays'),
      vitrineLink:      document.getElementById('smyle-vitrine-link'),
      topSons:          document.getElementById('mp-top-sons'),
      topArtists:       document.getElementById('mp-top-artists'),
      gridSons:         document.getElementById('mp-grid-sons'),
      gridArtists:      document.getElementById('mp-grid-artists'),
      searchDna:        document.getElementById('mp-search-dna'),
      searchConnect:    document.getElementById('mp-search-connect'),
      searchBarDna:     document.querySelector('.mp-search-bar-dna'),
      searchBarConnect: document.querySelector('.mp-search-bar-connect'),
    };
  }

  // Injecte (ou met à jour) le pill de match inline dans une barre de
  // recherche. `match` = { label, color } ou null pour le retirer.
  // Plus discret qu'un panneau : un simple chip coloré à droite du tag.
  function _setMatchPill(barEl, match) {
    if (!barEl) return;
    let pill = barEl.querySelector('.mp-search-match');
    if (!match) {
      if (pill) pill.remove();
      barEl.classList.remove('has-match');
      return;
    }
    if (!pill) {
      pill = document.createElement('span');
      pill.className = 'mp-search-match';
      // On le place juste après le tag (DNA / CONNECT) pour rester aligné
      // sur le design : tag → pill → input.
      const tag = barEl.querySelector('.mp-search-tag');
      if (tag && tag.nextSibling) tag.parentNode.insertBefore(pill, tag.nextSibling);
      else barEl.insertBefore(pill, barEl.querySelector('.mp-search-input'));
    }
    pill.style.setProperty('--match-color', match.color);
    pill.textContent = match.label;
    barEl.classList.add('has-match');
  }


  // ── Helpers ──────────────────────────────────────────────────────────────

  function _esc(s) {
    // Échappement HTML minimal — on construit tout en innerHTML pour garder
    // le code compact, mais toutes les valeurs dynamiques passent par là.
    const div = document.createElement('div');
    div.textContent = s == null ? '' : String(s);
    return div.innerHTML;
  }

  function _fmt(n) {
    // Formate les compteurs : 1234 → 1.2k, 1500000 → 1.5M.
    const v = Number(n) || 0;
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
    if (v >= 1_000)     return (v / 1_000).toFixed(1).replace(/\.0$/, '') + 'k';
    return String(v);
  }

  function _initial(name) {
    const s = (name || '').trim();
    return s ? s[0].toUpperCase() : '?';
  }

  /**
   * SVG du checkmark officiel coloré. Séparé en helper parce qu'on le réutilise
   * dans la vitrine ET dans les listes (top artistes, grid artistes).
   * `size` en px, `color` override optionnelle de la couleur de marque.
   */
  function _checkmarkSvg(size = 12) {
    const s = Number(size);
    return (
      `<span class="mp-checkmark-official" title="Compte officiel" aria-label="Officiel">` +
        `<svg viewBox="0 0 24 26" width="${s}" height="${s}" fill="currentColor">` +
          `<path opacity=".95" d="M12 2l2.5 2.2 3.3-.4 1.3 3 3 1.3-.4 3.3L24 14l-2.3 2.4.4 3.3-3 1.3-1.3 3-3.3-.4L12 26l-2.4-2.3-3.3.4-1.3-3-3-1.3.4-3.3L0 14l2.4-2.6-.4-3.3 3-1.3 1.3-3 3.3.4z"/>` +
          `<polyline points="7 12 10.5 15.5 17 9" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>` +
        `</svg>` +
      `</span>`
    );
  }


  // ── Fetchers ─────────────────────────────────────────────────────────────

  async function _fetchSmyle() {
    // Le slug 'smyle' est garanti par la migration 0022 (artist_name='Smyle',
    // _derive_artist_slug → slugify('Smyle') = 'smyle'). Si le backend n'a
    // pas encore joué la migration, on reçoit 404 → on laisse les
    // placeholders en place et on log (pas de toast bruyant).
    try {
      const artist = await apiFetch('/watt/artists/smyle');
      _state.smyleArtist = artist;
    } catch (err) {
      console.warn('[marketplace] vitrine Smyle indisponible :', err && err.message);
      _state.smyleArtist = null;
    }
  }

  async function _fetchArtists() {
    try {
      const data = await apiFetch('/watt/artists');
      _state.artists = Array.isArray(data && data.artists) ? data.artists : [];
    } catch (err) {
      console.warn('[marketplace] /watt/artists :', err && err.message);
      _state.artists = [];
    }
  }

  async function _fetchTracks() {
    try {
      const data = await apiFetch('/watt/tracks-recent');
      _state.tracks = Array.isArray(data && data.tracks) ? data.tracks : [];
    } catch (err) {
      console.warn('[marketplace] /watt/tracks-recent :', err && err.message);
      _state.tracks = [];
    }
  }


  // ── Rendus ───────────────────────────────────────────────────────────────

  function _renderVitrine() {
    const d = _state.dom;
    const a = _state.smyleArtist;

    if (!d.vitrineRoot) return;

    if (!a) {
      // Pas de compte Smyle → on cache entièrement la vitrine pour éviter
      // l'état "vide" qui donnerait l'impression d'un bug visuel.
      d.vitrineRoot.style.display = 'none';
      return;
    }

    d.vitrineRoot.style.display = '';

    // Couleur de marque — CSS variable consommée par --smyle-brand.
    if (a.brandColor) {
      d.vitrineRoot.style.setProperty('--smyle-brand', a.brandColor);
    }

    // Avatar : image si fournie, sinon initiale sur fond brand.
    if (d.vitrineAvatar) {
      if (a.avatarUrl) {
        d.vitrineAvatar.innerHTML =
          `<img src="${_esc(a.avatarUrl)}" alt="${_esc(a.artistName || 'Smyle')}" />`;
      } else {
        d.vitrineAvatar.textContent = _initial(a.artistName || 'Smyle');
      }
    }

    if (d.vitrineName)      d.vitrineName.textContent      = a.artistName || 'Smyle';
    if (d.vitrineBio && a.bio) d.vitrineBio.textContent    = a.bio;
    if (d.vitrineFollowers) d.vitrineFollowers.textContent = _fmt(a.followersCount || 0);
    if (d.vitrineTracks)    d.vitrineTracks.textContent    = _fmt(a.trackCount || 0);
    if (d.vitrinePlays)     d.vitrinePlays.textContent     = _fmt(a.plays || 0);
    if (d.vitrineLink)      d.vitrineLink.href             = '/u/' + (a.slug || 'smyle');
  }

  function _renderTopSons() {
    const el = _state.dom.topSons;
    if (!el) return;

    // Tri plays desc, top 10. `tracks-recent` renvoie par created_at desc,
    // donc on re-trie côté client.
    const top = _state.tracks
      .slice()
      .sort((a, b) => (b.plays || 0) - (a.plays || 0))
      .slice(0, 10);

    if (top.length === 0) {
      el.innerHTML = '<li class="mp-ranking-empty">Aucun son pour le moment.</li>';
      return;
    }

    el.innerHTML = top.map((t, i) => {
      const artistName = t.artist || '—';
      const plays      = _fmt(t.plays || 0);
      const title      = t.name || 'Sans titre';
      return (
        `<li class="mp-ranking-row" data-track-id="${_esc(t.id || '')}">` +
          `<div class="mp-ranking-rank">${i + 1}</div>` +
          `<div class="mp-ranking-main">` +
            `<div class="mp-ranking-title">${_esc(title)}</div>` +
            `<div class="mp-ranking-sub">` +
              `<span>${_esc(artistName)}</span>` +
            `</div>` +
          `</div>` +
          `<div class="mp-ranking-meta">${plays} écoutes</div>` +
        `</li>`
      );
    }).join('');
  }

  function _renderTopArtists() {
    const el = _state.dom.topArtists;
    if (!el) return;

    // On EXCLUT le compte Smyle du classement — il est déjà en vitrine.
    // Le backend renvoie déjà trié (is_official DESC puis plays DESC), on
    // filtre Smyle puis on garde les 10 premiers.
    const top = _state.artists
      .filter(a => !a.isOfficial)
      .slice(0, 10);

    if (top.length === 0) {
      el.innerHTML = '<li class="mp-ranking-empty">Aucun artiste publié pour le moment.</li>';
      return;
    }

    el.innerHTML = top.map((a, i) => {
      const href  = '/u/' + (a.slug || '');
      const name  = a.artistName || 'Sans nom';
      const city  = a.city || '';
      const genre = a.genre || '';
      const parts = [city, genre].filter(Boolean).map(_esc).join(' · ');
      return (
        `<li class="mp-ranking-row" onclick="window.location.href='${_esc(href)}'">` +
          `<div class="mp-ranking-rank">${i + 1}</div>` +
          `<div class="mp-ranking-main">` +
            `<div class="mp-ranking-title">${_esc(name)}</div>` +
            `<div class="mp-ranking-sub">${parts || '&nbsp;'}</div>` +
          `</div>` +
          `<div class="mp-ranking-meta">${_fmt(a.plays || 0)} écoutes</div>` +
        `</li>`
      );
    }).join('');
  }

  function _renderGridSons(filter = '') {
    const el = _state.dom.gridSons;
    if (!el) return;

    const needle = filter.trim().toLowerCase();

    // ── DNA : analyse l'intention de la query (mood / univers) ─────────
    // Si un univers gagne, on (1) pose un pill coloré dans la barre, et
    // (2) booste dans l'ordre de rendu les tracks dont le genre matche
    // les keywords de l'univers. La recherche textuelle classique reste
    // active en parallèle — c'est un bonus, pas un remplacement.
    const dna = (window.WattDNA && needle) ? window.WattDNA.analyze(needle) : null;
    const dnaHit = dna && dna.winner;
    _setMatchPill(_state.dom.searchBarDna, dnaHit ? { label: dna.label, color: dna.color } : null);

    let items = _state.tracks.filter(t => {
      if (!needle) return true;
      const hay = ((t.name || '') + ' ' + (t.artist || '') + ' ' + (t.genre || '')).toLowerCase();
      // Match texte classique OU match DNA (genre taggé sur l'univers gagnant)
      if (hay.includes(needle)) return true;
      if (dnaHit) {
        for (const kw of dna.keywords) {
          if (hay.includes(kw)) return true;
        }
      }
      return false;
    });

    // Re-ranking DNA : les sons qui matchent l'univers gagnant remontent.
    if (dnaHit && items.length > 1) {
      const kws = dna.keywords;
      items = items.slice().sort((a, b) => {
        const ha = ((a.genre || '') + ' ' + (a.name || '')).toLowerCase();
        const hb = ((b.genre || '') + ' ' + (b.name || '')).toLowerCase();
        const sa = kws.some(k => ha.includes(k)) ? 1 : 0;
        const sb = kws.some(k => hb.includes(k)) ? 1 : 0;
        return sb - sa;
      });
    }

    if (items.length === 0) {
      el.innerHTML = needle
        ? `<div class="mp-grid-empty">Aucun son ne correspond à "${_esc(filter)}".</div>`
        : `<div class="mp-grid-empty">Aucun son dans le catalogue pour le moment.</div>`;
      return;
    }

    el.innerHTML = items.map(t => {
      const color = t.color || '#7C3AED';
      const title = t.name || 'Sans titre';
      const name  = t.artist || '—';
      const plays = _fmt(t.plays || 0);
      return (
        `<div class="mp-son-card" data-track-id="${_esc(t.id || '')}" style="--son-color:${_esc(color)}">` +
          `<div class="mp-son-card-cover">` +
            `<button class="mp-son-card-play" type="button" aria-label="Lire">` +
              `<svg viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>` +
            `</button>` +
          `</div>` +
          `<div class="mp-son-card-title">${_esc(title)}</div>` +
          `<div class="mp-son-card-artist">` +
            `<span class="mp-son-card-artist-name">${_esc(name)}</span>` +
          `</div>` +
          `<div class="mp-son-card-meta">${plays} écoutes</div>` +
        `</div>`
      );
    }).join('');
  }

  function _renderGridArtists(filter = '') {
    const el = _state.dom.gridArtists;
    if (!el) return;

    const needle = filter.trim().toLowerCase();

    // ── CONNECT : détecte la catégorie de collaborateur ciblée ─────────
    // Même logique que DNA côté sons : pill coloré discret + boost dans
    // le rendu des profils dont le genre/role matche la catégorie.
    const cat = (window.WattConnect && needle) ? window.WattConnect.match(needle) : null;
    const connectColor = (window.WattConnect && window.WattConnect.COLOR && window.WattConnect.COLOR.hex) || '#FF1744';
    _setMatchPill(_state.dom.searchBarConnect, cat ? { label: cat.label, color: connectColor } : null);

    // On exclut Smyle de la grille — il est en vitrine au-dessus.
    let items = _state.artists
      .filter(a => !a.isOfficial)
      .filter(a => {
        if (!needle) return true;
        const hay = (
          (a.artistName || '') + ' ' +
          (a.city       || '') + ' ' +
          (a.genre      || '') + ' ' +
          (a.role       || '') + ' ' +
          (a.bio        || '')
        ).toLowerCase();
        if (hay.includes(needle)) return true;
        // Fallback : la query tape sur la catégorie — on garde les profils
        // dont le champ genre/role/bio touche un keyword de la catégorie.
        if (cat) {
          for (const k of cat.keywords) {
            if (hay.includes(k)) return true;
          }
        }
        return false;
      });

    // Re-ranking CONNECT : profils matchant la catégorie remontent.
    if (cat && items.length > 1) {
      const kws = cat.keywords;
      items = items.slice().sort((a, b) => {
        const ha = ((a.genre || '') + ' ' + (a.role || '') + ' ' + (a.bio || '')).toLowerCase();
        const hb = ((b.genre || '') + ' ' + (b.role || '') + ' ' + (b.bio || '')).toLowerCase();
        const sa = kws.some(k => ha.includes(k)) ? 1 : 0;
        const sb = kws.some(k => hb.includes(k)) ? 1 : 0;
        return sb - sa;
      });
    }

    if (items.length === 0) {
      el.innerHTML = needle
        ? `<div class="mp-grid-empty">Aucun profil ne correspond à "${_esc(filter)}".</div>`
        : `<div class="mp-grid-empty">Aucun profil publié pour le moment.</div>`;
      return;
    }

    el.innerHTML = items.map(a => {
      const href  = '/u/' + (a.slug || '');
      const color = a.brandColor || '#7C3AED';
      const name  = a.artistName || 'Sans nom';
      const parts = [a.city, a.genre].filter(Boolean).map(_esc).join(' · ');
      const avatar = a.avatarUrl
        ? `<img src="${_esc(a.avatarUrl)}" alt="${_esc(name)}" />`
        : _esc(_initial(name));
      const tick = a.isOfficial ? _checkmarkSvg(12) : '';
      return (
        `<a class="mp-artist-card" href="${_esc(href)}" style="--artist-color:${_esc(color)}">` +
          `<div class="mp-artist-card-avatar">${avatar}</div>` +
          `<div class="mp-artist-card-main">` +
            `<div class="mp-artist-card-name-row">` +
              `<span class="mp-artist-card-name">${_esc(name)}</span>` +
              tick +
            `</div>` +
            `<div class="mp-artist-card-sub">` +
              (parts ? `<span>${parts}</span>` : '') +
              `<span class="mp-artist-card-sub-sep">·</span>` +
              `<span>${_fmt(a.followersCount || 0)} abonnés</span>` +
            `</div>` +
          `</div>` +
        `</a>`
      );
    }).join('');
  }

  /** Re-render complet de toutes les sections dépendant de l'état. */
  function _renderAll() {
    _renderVitrine();
    _renderTopSons();
    _renderTopArtists();
    _renderGridSons(_state.dom.searchDna ? _state.dom.searchDna.value : '');
    _renderGridArtists(_state.dom.searchConnect ? _state.dom.searchConnect.value : '');
  }


  // ── Bindings ─────────────────────────────────────────────────────────────

  function _bindSearch() {
    const { searchDna, searchConnect } = _state.dom;

    if (searchDna) {
      searchDna.addEventListener('input', (ev) => {
        _renderGridSons(ev.target.value || '');
      });
    }

    if (searchConnect) {
      searchConnect.addEventListener('input', (ev) => {
        _renderGridArtists(ev.target.value || '');
      });
    }
  }

  function _bindBus() {
    const bus = window.SmyleEvents;
    if (!bus || typeof bus.on !== 'function') return;

    const refreshArtists = async () => {
      // Smyle + liste : les deux peuvent bouger si un profil publie/dépublie
      // (le nouveau rang de Smyle peut changer — ex: nouveau top artiste).
      await Promise.all([_fetchSmyle(), _fetchArtists()]);
      _renderAll();
    };

    const refreshTracks = async () => {
      await _fetchTracks();
      _renderAll();
    };

    bus.on(bus.TYPES.PROFILE_PUBLISHED,   refreshArtists);
    bus.on(bus.TYPES.PROFILE_UNPUBLISHED, refreshArtists);
    bus.on(bus.TYPES.TRACK_UPLOADED,      refreshTracks);
    bus.on(bus.TYPES.TRACK_DELETED,       refreshTracks);
  }


  // ── Boot ─────────────────────────────────────────────────────────────────

  async function _boot() {
    if (!_isMarketplacePage()) return;
    _resolveDom();
    _bindSearch();
    _bindBus();

    // Trois fetches en parallèle — indépendants, pas de cascade.
    await Promise.all([_fetchSmyle(), _fetchArtists(), _fetchTracks()]);
    _renderAll();
  }

  // Attend DOMContentLoaded si on est chargé sync avant le body.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot, { once: true });
  } else {
    _boot();
  }

  // Exposition minimale pour debug console uniquement.
  window.SmyleMarketplace = {
    refresh: _boot,
    _debugState: () => JSON.parse(JSON.stringify({
      smyle: _state.smyleArtist,
      artists: _state.artists.length,
      tracks: _state.tracks.length,
    })),
  };
})();
