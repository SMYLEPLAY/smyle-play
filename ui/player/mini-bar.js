/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/player/mini-bar.js
   Barre audio fixe en bas de page — visible sur toutes les pages.

   Fix v2 :
   - Lecture meta immédiate sur chaque play event (plus de bug timing)
   - Like/Add câblés directement via SmylePlaylists (pas data-attributes)
   - Layout 3 colonnes : info | controls | actions
   ───────────────────────────────────────────────────────────────────────── */

(function initSmyleMiniBar() {
  'use strict';
  if (typeof window === 'undefined') return;
  if (window.SmyleMiniBar) return;

  // ── State ──────────────────────────────────────────────────────────────────
  let _audio     = null;
  let _trackId   = null;
  let _dismissed = false;
  let _raf       = null;
  let _barEl     = null;
  let _lastMeta  = null;   // dernière meta appliquée (persistance inter-pages)
  let _lastSave  = 0;      // throttle du save

  // ── PLAYER CONTINU V1 (07/07) — persistance inter-pages ────────────────────
  // Le site est multi-pages : chaque navigation tue l'audio. On persiste
  // l'état d'écoute (src + position + meta) dans localStorage et on REPREND
  // sur la page suivante. Si le navigateur bloque l'autoplay (pas de geste
  // utilisateur), la barre s'affiche en pause à la bonne position — un clic
  // sur ▶ relance. Fermer la barre (×) efface l'état : la musique ne te
  // « suit » plus.
  const _PERSIST_KEY = 'smyle_player_state';
  const _PERSIST_TTL = 30 * 60 * 1000; // 30 min

  function _persist(force) {
    try {
      if (!_audio || !_audio.currentSrc) return;
      const now = Date.now();
      if (!force && now - _lastSave < 1000) return;
      _lastSave = now;
      localStorage.setItem(_PERSIST_KEY, JSON.stringify({
        src:     _audio.currentSrc,
        pos:     _audio.currentTime || 0,
        playing: !_audio.paused,
        meta:    _lastMeta || null,
        ts:      now,
      }));
    } catch (_) {}
  }
  function _persistThrottled() { _persist(false); }
  function _clearPersist() {
    try { localStorage.removeItem(_PERSIST_KEY); } catch (_) {}
  }

  // ── Lot M — la playlist continue de page en page ──────────────────────────
  // Quand on lance une playlist (ou My Mix), la file d'attente est gardée :
  // sur une autre page, la barre enchaîne le titre suivant à la fin du
  // morceau, et ⏮ / ⏭ marchent partout, pas seulement sur l'accueil.
  const _QUEUE_KEY = 'smyle_player_queue';
  let _ownAudio = null;   // audio créé par la barre (reprise / file d'attente)

  function _setQueue(items, idx) {
    try {
      const list = (items || []).filter(function (it) { return it && it.src; }).slice(0, 300);
      if (!list.length) { localStorage.removeItem(_QUEUE_KEY); return; }
      localStorage.setItem(_QUEUE_KEY, JSON.stringify({ items: list, idx: Math.max(0, Math.min(idx || 0, list.length - 1)), ts: Date.now() }));
    } catch (_) {}
  }
  function _readQueue() {
    try {
      const q = JSON.parse(localStorage.getItem(_QUEUE_KEY) || 'null');
      if (!q || !Array.isArray(q.items) || !q.items.length) return null;
      if (Date.now() - (q.ts || 0) > 6 * 60 * 60 * 1000) return null;
      return q;
    } catch (_) { return null; }
  }
  function _clearQueue() { try { localStorage.removeItem(_QUEUE_KEY); } catch (_) {} }

  function _bindOwn(a) {
    _unbind();
    _audio = a;
    _ownAudio = a;
    _dismissed = false;
    a.addEventListener('pause', _onPause);
    a.addEventListener('ended', _onEnded);
    a.addEventListener('timeupdate', _persistThrottled);
  }

  function _playQueueItem(q, idx) {
    const it = q.items[idx];
    if (!it) return false;
    q.idx = idx; q.ts = Date.now();
    try { localStorage.setItem(_QUEUE_KEY, JSON.stringify(q)); } catch (_) {}
    if (_audio) { try { _audio.pause(); } catch (_) {} }
    const a = new Audio(it.src);
    a.preload = 'auto';
    a._smbQueue = true;
    _bindOwn(a);
    _applyMeta({ id: it.id || null, name: it.name || '—', artist: it.artist || 'WATT', cover: it.cover || null, color: it.color || null });
    _show();
    a.play().then(function () { _updatePlayBtn(true); _startProgress(); _persist(true); })
      .catch(function () { _updatePlayBtn(false); });
    if (it.id) { try { fetch('/watt/plays/' + encodeURIComponent(it.id), { method: 'POST' }).catch(function () {}); } catch (_) {} }
    return true;
  }

  // La page gère-t-elle elle-même la lecture (player de l'accueil) ?
  function _pageGereLaLecture() {
    return !!(window.smyleAudio && _audio === window.smyleAudio);
  }

  function _queueStep(delta) {
    const q = _readQueue();
    if (!q) return false;
    let i = (q.idx || 0) + delta;
    if (i >= q.items.length) i = 0;          // boucle sur la playlist
    if (i < 0) i = q.items.length - 1;
    return _playQueueItem(q, i);
  }

  function _restore() {
    let st = null;
    try { st = JSON.parse(localStorage.getItem(_PERSIST_KEY) || 'null'); } catch (_) {}
    if (!st || !st.src) return;
    if (Date.now() - (st.ts || 0) > _PERSIST_TTL) { _clearPersist(); return; }
    // Si un player de la page a déjà pris la main, on ne restaure pas.
    if (_audio && !_audio.paused) return;

    const a = new Audio(st.src);
    a.preload = 'auto';
    _bindOwn(a);
    a.addEventListener('loadedmetadata', function () {
      try { a.currentTime = st.pos || 0; } catch (_) {}
    });

    if (st.meta) _applyMeta(st.meta);
    _show();

    if (st.playing) {
      a.play().then(function () {
        _updatePlayBtn(true);
        _startProgress();
      }).catch(function () {
        // Autoplay bloqué → barre visible en pause, prête à reprendre.
        _updatePlayBtn(false);
      });
    } else {
      _updatePlayBtn(false);
    }
  }

  // ── Build DOM ──────────────────────────────────────────────────────────────
  function _build() {
    // Fix 2026-06-11 — la mini-bar embarque SON CSS (ui/player/mini-bar.css,
    // extrait de style.css). Avant : les pages qui ne chargeaient pas
    // style.css (library, artiste…) affichaient la barre NUE en texte brut
    // en bas de page ("—WATT ⏮▶⏭ ↺♡+×"). Une seule source de style,
    // valable sur toutes les pages qui incluent ce script.
    if (!document.getElementById('smb-styles')) {
      const lk = document.createElement('link');
      lk.id   = 'smb-styles';
      lk.rel  = 'stylesheet';
      lk.href = '/ui/player/mini-bar.css?v=20261102lis';
      document.head.appendChild(lk);
    }
    if (document.getElementById('smyle-mini-bar')) {
      _barEl = document.getElementById('smyle-mini-bar');
      return;
    }
    const el = document.createElement('div');
    el.id = 'smyle-mini-bar';
    el.setAttribute('aria-hidden', 'true');
    // Ceinture + bretelles : tant que le CSS n'est pas chargé, la barre
    // reste en display:none inline → impossible de la voir « nue ».
    // _show() retire ce style inline, le CSS prend alors le relais.
    el.style.display = 'none';
    el.innerHTML = [
      '<div class="smb-progress-wrap" id="smb-progress-wrap">',
        '<div class="smb-progress-fill" id="smb-progress-fill"></div>',
      '</div>',

      /* ── COL GAUCHE : cover + info ── */
      '<div class="smb-left">',
        '<div class="smb-cover-wrap">',
          '<span class="smb-cover-ph" id="smb-cover-ph">♪</span>',
          '<img class="smb-cover-img" id="smb-cover-img" src="" alt="" style="display:none">',
        '</div>',
        '<div class="smb-meta">',
          '<span class="smb-title"  id="smb-title">—</span>',
          '<span class="smb-artist" id="smb-artist">WATT</span>',
        '</div>',
      '</div>',

      /* ── COL CENTRE : prev | play | next ── */
      '<div class="smb-center">',
        '<button class="smb-btn smb-prev" id="smb-prev" title="Précédent">⏮</button>',
        '<button class="smb-btn smb-play" id="smb-play" title="Play / Pause">▶</button>',
        '<button class="smb-btn smb-next" id="smb-next" title="Suivant">⏭</button>',
      '</div>',

      /* ── COL DROITE : loop | like | add | close ── */
      '<div class="smb-right">',
        '<button class="smb-btn smb-mix"   id="smb-mix"   title="Ajouter à My Mix" style="display:none">♫</button>',
        '<button class="smb-btn smb-loop"  id="smb-loop"  title="Répéter">↺</button>',
        '<button class="smb-btn smb-like"  id="smb-like"  title="Like">♡</button>',
        '<button class="smb-btn smb-add"   id="smb-add"   title="Ajouter à une playlist">+</button>',
        '<button class="smb-close"         id="smb-close" title="Fermer">×</button>',
      '</div>',
    ].join('');
    document.body.appendChild(el);
    _barEl = el;
    _wireButtons();
  }

  // ── Câblage boutons ────────────────────────────────────────────────────────
  function _wireButtons() {
    // Progress — seek
    _barEl.querySelector('#smb-progress-wrap').addEventListener('click', function(e) {
      if (!_audio || !_audio.duration) return;
      const r = this.getBoundingClientRect();
      _audio.currentTime = ((e.clientX - r.left) / r.width) * _audio.duration;
    });

    // Play / Pause
    _barEl.querySelector('#smb-play').addEventListener('click', function() {
      if (!_audio) return;
      _audio.paused ? _audio.play().catch(() => {}) : _audio.pause();
    });

    // Prev / Next
    _barEl.querySelector('#smb-prev').addEventListener('click', function() {
      if (!_pageGereLaLecture() && _queueStep(-1)) return;
      if (typeof prevTrack === 'function') prevTrack();
      else if (typeof prevMixTrack === 'function') prevMixTrack();
    });
    _barEl.querySelector('#smb-next').addEventListener('click', function() {
      if (!_pageGereLaLecture() && _queueStep(1)) return;
      if (typeof nextTrack === 'function') nextTrack();
      else if (typeof nextMixTrack === 'function') nextMixTrack();
    });

    // Loop
    _barEl.querySelector('#smb-loop').addEventListener('click', function() {
      if (!_audio) return;
      if (typeof toggleLoop === 'function') {
        toggleLoop();
        this.classList.toggle('smb-loop-on', typeof loopMode !== 'undefined' ? loopMode : _audio.loop);
      } else {
        _audio.loop = !_audio.loop;
        this.classList.toggle('smb-loop-on', _audio.loop);
      }
    });

    // Like — câblé direct sur SmylePlaylists
    _barEl.querySelector('#smb-like').addEventListener('click', function() {
      if (!_trackId) return;
      if (window.SmylePlaylists && typeof window.SmylePlaylists.toggleLike === 'function') {
        window.SmylePlaylists.toggleLike(_trackId);
        this.classList.toggle('smb-liked');
      }
    });

    // Add to playlist — câblé direct
    // Lot M — « Ajouter à My Mix » (accueil), repris de l'ancienne barre.
    _barEl.querySelector('#smb-mix').addEventListener('click', function () {
      if (typeof window.addCurrentToMix === 'function') window.addCurrentToMix();
    });

    const _gauche = _barEl.querySelector('.smb-left');
    if (_gauche) {
      _gauche.setAttribute('role', 'button');
      _gauche.setAttribute('tabindex', '0');
      _gauche.setAttribute('title', 'Voir la carte du son');
      _gauche.addEventListener('click', _ouvrirCarte);
      _gauche.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); _ouvrirCarte(); } });
    }

    _barEl.querySelector('#smb-add').addEventListener('click', function() {
      if (!_trackId) return;
      if (window.SmylePlaylists && typeof window.SmylePlaylists.openAddToPlaylistModal === 'function') {
        window.SmylePlaylists.openAddToPlaylistModal(_trackId);
      }
    });

    // Fermer
    _barEl.querySelector('#smb-close').addEventListener('click', function() {
      _dismissed = true;
      _hide();
      if (_audio && !_audio.paused) _audio.pause();
      _clearPersist();  // player continu : × = la musique ne suit plus
      _clearQueue();
    });
  }

  // ── Show / Hide ────────────────────────────────────────────────────────────
  function _show() {
    if (!_barEl) return;
    _barEl.style.display = '';   // retire le display:none inline de _build()
    _barEl.classList.add('smb-visible');
    _barEl.setAttribute('aria-hidden', 'false');
    document.body.classList.add('smyle-mini-bar-open');
  }
  function _hide() {
    if (!_barEl) return;
    _barEl.classList.remove('smb-visible');
    _barEl.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('smyle-mini-bar-open');
  }

  // ── Progress bar ───────────────────────────────────────────────────────────
  function _startProgress() {
    if (_raf) cancelAnimationFrame(_raf);
    function tick() {
      const fill = document.getElementById('smb-progress-fill');
      if (fill && _audio && _audio.duration) {
        fill.style.width = ((_audio.currentTime / _audio.duration) * 100).toFixed(2) + '%';
      }
      _raf = requestAnimationFrame(tick);
    }
    _raf = requestAnimationFrame(tick);
  }
  function _stopProgress() {
    if (_raf) cancelAnimationFrame(_raf);
    _raf = null;
  }

  // ── Bouton play/pause ──────────────────────────────────────────────────────
  function _updatePlayBtn(playing) {
    const btn = document.getElementById('smb-play');
    if (!btn) return;
    btn.innerHTML = playing ? '⏸' : '▶';
    btn.classList.toggle('smb-playing', !!playing);
  }

  // ── Lecture des métadonnées ────────────────────────────────────────────────
  function _readMeta(audioEl) {
    const info = { id: null, name: '—', artist: 'WATT', cover: null, color: null };

    // 1) Singleton principal (window.smyleAudio, index.html)
    if (audioEl === window.smyleAudio && audioEl._trackRef) {
      const t  = audioEl._trackRef;
      const pl = (typeof PLAYLISTS !== 'undefined' && typeof currentPlaylist !== 'undefined')
        ? PLAYLISTS[currentPlaylist] : null;
      info.id     = t.id        || null;
      info.name   = t.name      || '—';
      info.artist = (pl && pl.label) || 'WATT';
      info.cover  = t.cover_url || null;
      info.color  = (pl && pl.theme && /^#[0-9a-fA-F]{6}$/.test(pl.theme)) ? pl.theme : null;
      return info;
    }

    // 2) Audio inline (artiste, marketplace) — remonte l'arbre DOM
    let el = audioEl.parentElement;
    for (let i = 0; i < 8 && el; i++) {
      const tid  = el.dataset.trackId  || el.getAttribute('data-track-id');
      // Fix QA C3 ② — ❤️/➕ de la bar appellent toggleLike /
      // openAddToPlaylistModal qui attendent l'UUID du track (comme les
      // boutons des rows), pas l'id legacy. data-track-uuid est posé par
      // le wrapper audio partagé du profil ; fallback tid sinon.
      const tuid = el.dataset.trackUuid || el.getAttribute('data-track-uuid');
      const name = el.dataset.trackName || el.getAttribute('data-track-name');
      const titleEl = el.querySelector('.mp-son-card-title, .ap-track-card-title, h3.ap-track-card-title');
      if (tid || tuid || name || titleEl) {
        info.id   = tuid || tid || null;
        info.name = name || (titleEl && titleEl.textContent.trim()) || '—';
        // Artist depuis la card
        const artistEl = el.querySelector('.mp-son-card-artist-name, .ap-artist-name');
        if (artistEl) info.artist = artistEl.textContent.trim();
        // Cover
        const img = el.querySelector('img.mp-son-card-cover-img, img.mp-card-linked-thumb, img.ap-track-cover, img.ap-cover, .ap-oe-visual img');
        if (img && img.src) info.cover = img.src;
        // Couleur
        const color = el.style && el.style.getPropertyValue('--son-color');
        if (color) info.color = color.trim();
        break;
      }
      el = el.parentElement;
    }
    return info;
  }

  // ── Mise à jour de l'affichage ─────────────────────────────────────────────
  function _applyMeta(info) {
    _lastMeta = info || null;
    const titleEl  = document.getElementById('smb-title');
    const artistEl = document.getElementById('smb-artist');
    const coverImg = document.getElementById('smb-cover-img');
    const coverPh  = document.getElementById('smb-cover-ph');

    if (titleEl)  titleEl.textContent  = info.name   || '—';
    if (artistEl) artistEl.textContent = info.artist || 'WATT';

    if (info.cover && coverImg && coverPh) {
      coverImg.src          = info.cover;
      coverImg.style.display = '';
      coverPh.style.display  = 'none';
    } else if (coverImg && coverPh) {
      coverImg.style.display = 'none';
      coverPh.style.display  = '';
    }

    // Accent color
    if (info.color && _barEl) {
      _barEl.style.setProperty('--smb-accent', info.color);
    }

    // Sync trackId + like state
    _trackId = info.id ? String(info.id) : null;
    const likeBtn = document.getElementById('smb-like');
    const addBtn  = document.getElementById('smb-add');
    if (likeBtn) {
      likeBtn.style.opacity = _trackId ? '' : '0.3';
      likeBtn.classList.remove('smb-liked');
    }
    if (addBtn) addBtn.style.opacity = _trackId ? '' : '0.3';
    const mixBtn = document.getElementById('smb-mix');
    if (mixBtn) mixBtn.style.display = (typeof window.addCurrentToMix === 'function' && window.smyleAudio && _audio === window.smyleAudio) ? '' : 'none';
    if (_barEl) _barEl.querySelector('.smb-left').classList.toggle('is-link', !!_trackId);
  }

  // ── Capture ANY audio play sur la page ────────────────────────────────────
  // v2 : on lit la meta IMMÉDIATEMENT sur capture play
  function _onAnyPlay(e) {
    const target = e.target;
    if (!(target instanceof HTMLAudioElement)) return;
    if (_dismissed && _audio === target) return;

    // Lot M — un son lancé seul (carte, profil…) remplace la playlist en cours.
    if (target !== window.smyleAudio && !target._smbQueue) _clearQueue();

    // Changer de source audio si nécessaire
    if (_audio !== target) {
      // Stoppe le player global (smyleAudio) si c'est un audio inline qui prend la main
      if (window.smyleAudio && !window.smyleAudio.paused && window.smyleAudio !== target) {
        window.smyleAudio.pause();
        window.smyleAudio.currentTime = 0;
      }
      _unbind();
      _audio    = target;
      _dismissed = false;

      // Pause / ended listeners
      target.addEventListener('pause',  _onPause);
      target.addEventListener('ended',  _onEnded);
      target.addEventListener('timeupdate', _persistThrottled);
    }

    // Lire la meta IMMÉDIATEMENT (le play event est déjà là)
    const info = _readMeta(target);
    _applyMeta(info);
    _updatePlayBtn(true);
    _show();
    _startProgress();
  }

  function _onPause() { _updatePlayBtn(false); _stopProgress(); _persist(true); }
  function _onEnded() {
    _updatePlayBtn(false); _stopProgress();
    // Lot M — playlist reprise sur une autre page : on enchaîne.
    if (_audio && _audio === _ownAudio && !_audio.loop && _readQueue()) _queueStep(1);
  }

  function _unbind() {
    if (!_audio) return;
    _audio.removeEventListener('pause', _onPause);
    _audio.removeEventListener('ended', _onEnded);
    _audio.removeEventListener('timeupdate', _persistThrottled);
    _stopProgress();
    _audio = null;
  }

  // ── SmyleEvents : track changé sur player principal ───────────────────────
  function _onTrackLoaded() {
    if (window.smyleAudio) {
      _unbind();
      _audio    = window.smyleAudio;
      _dismissed = false;
      window.smyleAudio.addEventListener('pause', _onPause);
      window.smyleAudio.addEventListener('ended', _onEnded);
      window.smyleAudio.addEventListener('timeupdate', _persistThrottled);
    }
    // Meta sera lue sur le prochain 'play' event via _onAnyPlay
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  function _init() {
    _build();
    document.addEventListener('play', _onAnyPlay, true);
    // Player continu : sauvegarde ultime au départ de la page + reprise.
    window.addEventListener('pagehide', function () { _persist(true); });
    _restore();
    if (typeof SmyleEvents !== 'undefined') {
      SmyleEvents.on('smyle:track-loaded', _onTrackLoaded);
    }
    // Polling fallback si smyleAudio exposé après init
    let n = 0;
    const p = setInterval(function() {
      if (window.smyleAudio && !window.smyleAudio._smb_bound) {
        window.smyleAudio._smb_bound = true;
        window.smyleAudio.addEventListener('pause', _onPause);
        window.smyleAudio.addEventListener('ended', _onEnded);
        window.smyleAudio.addEventListener('timeupdate', _persistThrottled);
      }
      if (++n > 20) clearInterval(p);
    }, 300);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }

  // ── setTrack : push direct depuis loadTrack() / loadMixTrack() ───────────
  function _setTrack(info) {
    _dismissed = false;
    // Lot M — une lecture lancée depuis l'accueil remplace celle reprise
    // d'une autre page (jamais deux sons en même temps).
    if (_ownAudio && _ownAudio !== window.smyleAudio) { try { _ownAudio.pause(); } catch (_) {} }
    _applyMeta(info);
    // Sync l'audio singleton si pas encore lié
    if (window.smyleAudio && _audio !== window.smyleAudio) {
      _unbind();
      _audio = window.smyleAudio;
      window.smyleAudio.addEventListener('pause', _onPause);
      window.smyleAudio.addEventListener('ended', _onEnded);
      window.smyleAudio.addEventListener('timeupdate', _persistThrottled);
    }
    // Le lecteur de l'accueil n'est pas dans la page : ses « play » ne
    // remontent pas jusqu'au document. On écoute donc l'audio lui-même.
    if (window.smyleAudio && !window.smyleAudio._smbPlayWired) {
      window.smyleAudio._smbPlayWired = true;
      window.smyleAudio.addEventListener('play', function () {
        if (_audio !== window.smyleAudio) return;
        _updatePlayBtn(true); _show(); _startProgress();
      });
    }
    _show();
    _updatePlayBtn(!!(window.smyleAudio && !window.smyleAudio.paused));
    _startProgress();
  }

  // ── Lot M — clic sur la pochette ou le titre : la carte ID du son ─────────
  function _ouvrirCarte() {
    if (!_trackId) return;
    if (window.SmyleTrackCard && typeof window.SmyleTrackCard.open === 'function'
        && window.SmyleTrackCard.open(_trackId)) return;
    window.location.href = '/?son=' + encodeURIComponent(_trackId);
  }

  // ── API publique ──────────────────────────────────────────────────────────
  window.SmyleMiniBar = { show: _show, hide: _hide, setTrack: _setTrack, setQueue: _setQueue, clearQueue: _clearQueue };

})();
