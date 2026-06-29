/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/player/mini-bar.js
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
      lk.href = '/ui/player/mini-bar.css?v=20260611';
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
      if (typeof prevTrack === 'function') prevTrack();
      else if (typeof prevMixTrack === 'function') prevMixTrack();
    });
    _barEl.querySelector('#smb-next').addEventListener('click', function() {
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
        const img = el.querySelector('img.mp-son-card-cover-img, img.ap-track-cover, img.ap-cover');
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
  }

  // ── Capture ANY audio play sur la page ────────────────────────────────────
  // v2 : on lit la meta IMMÉDIATEMENT sur capture play
  function _onAnyPlay(e) {
    const target = e.target;
    if (!(target instanceof HTMLAudioElement)) return;
    if (_dismissed && _audio === target) return;

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
    }

    // Lire la meta IMMÉDIATEMENT (le play event est déjà là)
    const info = _readMeta(target);
    _applyMeta(info);
    _updatePlayBtn(true);
    _show();
    _startProgress();
  }

  function _onPause() { _updatePlayBtn(false); _stopProgress(); }
  function _onEnded() { _updatePlayBtn(false); _stopProgress(); }

  function _unbind() {
    if (!_audio) return;
    _audio.removeEventListener('pause', _onPause);
    _audio.removeEventListener('ended', _onEnded);
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
    }
    // Meta sera lue sur le prochain 'play' event via _onAnyPlay
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  function _init() {
    _build();
    document.addEventListener('play', _onAnyPlay, true);
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
    _applyMeta(info);
    // Sync l'audio singleton si pas encore lié
    if (window.smyleAudio && _audio !== window.smyleAudio) {
      _unbind();
      _audio = window.smyleAudio;
      window.smyleAudio.addEventListener('pause', _onPause);
      window.smyleAudio.addEventListener('ended', _onEnded);
    }
  }

  // ── API publique ──────────────────────────────────────────────────────────
  window.SmyleMiniBar = { show: _show, hide: _hide, setTrack: _setTrack };

})();
