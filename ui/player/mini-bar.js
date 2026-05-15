/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/player/mini-bar.js
   Barre audio fixe en bas de page — visible sur toutes les pages.

   Fonctionnement :
   - S'attache à window.smyleAudio (singleton, exposé par state.js)
   - Détecte aussi les <audio> inline (page artiste) via capture 'play'
   - Mise à jour automatique : cover, titre, artiste, barre de progression
   - Contrôles : prev | play/pause | next | loop | like | add to playlist | close

   Chargement : après ui/core/state.js et ui/player/audio.js.
   Doit être inclus dans index.html, artiste.html, library.html.
   ───────────────────────────────────────────────────────────────────────── */

(function initSmyleMiniBar() {
  'use strict';
  if (typeof window === 'undefined') return;
  if (window.SmyleMiniBar) return;  // guard double init

  // ── State interne ──────────────────────────────────────────────────────────
  let _audio      = null;   // Audio element actif
  let _trackId    = null;   // ID du track courant
  let _dismissed  = false;  // l'utilisateur a fermé la barre → ne pas rouvrir pour CE track
  let _raf        = null;   // requestAnimationFrame pour la progress bar
  let _barEl      = null;

  // ── Création DOM ──────────────────────────────────────────────────────────
  function _build() {
    if (document.getElementById('smyle-mini-bar')) return;
    const el = document.createElement('div');
    el.id = 'smyle-mini-bar';
    el.setAttribute('aria-hidden', 'true');
    el.innerHTML = [
      /* barre de progression en haut */
      '<div class="smb-progress-wrap" id="smb-progress-wrap">',
        '<div class="smb-progress-fill" id="smb-progress-fill"></div>',
      '</div>',
      /* cover */
      '<div class="smb-cover-wrap" id="smb-cover-wrap">',
        '<span class="smb-cover-placeholder" id="smb-cover-placeholder">♪</span>',
        '<img class="smb-cover" id="smb-cover" src="" alt="" style="display:none">',
      '</div>',
      /* infos */
      '<div class="smb-meta">',
        '<span class="smb-title" id="smb-title">&mdash;</span>',
        '<span class="smb-artist" id="smb-artist">WATT</span>',
      '</div>',
      /* contrôles centraux */
      '<div class="smb-controls">',
        '<button class="smb-btn smb-prev"     id="smb-prev"      title="Précédent">⏮</button>',
        '<button class="smb-btn smb-playpause" id="smb-playpause" title="Play / Pause">▶</button>',
        '<button class="smb-btn smb-next"     id="smb-next"      title="Suivant">⏭</button>',
      '</div>',
      /* actions droite */
      '<div class="smb-actions">',
        '<button class="smb-btn smb-loop"  id="smb-loop"  title="Répéter">↺</button>',
        '<button class="smb-btn smb-like  like-btn"  id="smb-like-btn"  title="Like" data-like-btn=""></button>',
        '<button class="smb-btn smb-addpl add-to-pl-btn" id="smb-addpl-btn" title="Ajouter à une playlist" data-add-to-playlist="">+</button>',
      '</div>',
      /* fermer */
      '<button class="smb-close" id="smb-close" title="Fermer">×</button>',
    ].join('');
    document.body.appendChild(el);
    _barEl = el;
    _wireEvents(el);
  }

  // ── Câblage boutons ────────────────────────────────────────────────────────
  function _wireEvents(bar) {
    // Progress bar — clic pour seek
    const prog = bar.querySelector('#smb-progress-wrap');
    prog.addEventListener('click', function(e) {
      if (!_audio || !_audio.duration) return;
      const rect = prog.getBoundingClientRect();
      const pct  = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      _audio.currentTime = pct * _audio.duration;
    });

    // Play/Pause
    bar.querySelector('#smb-playpause').addEventListener('click', function() {
      if (!_audio) return;
      if (_audio.paused) {
        _audio.play().catch(() => {});
      } else {
        _audio.pause();
      }
    });

    // Prev / Next — appelle les globales de audio.js si dispo
    bar.querySelector('#smb-prev').addEventListener('click', function() {
      if (typeof prevTrack === 'function') prevTrack();
    });
    bar.querySelector('#smb-next').addEventListener('click', function() {
      if (typeof nextTrack === 'function') nextTrack();
    });

    // Loop
    bar.querySelector('#smb-loop').addEventListener('click', function() {
      if (!_audio) return;
      if (typeof toggleLoop === 'function') {
        toggleLoop();
      } else {
        _audio.loop = !_audio.loop;
      }
      this.classList.toggle('smb-loop-active', _audio.loop || (typeof loopMode !== 'undefined' && loopMode));
    });

    // Fermer
    bar.querySelector('#smb-close').addEventListener('click', function() {
      _dismissed = true;
      _hide();
      if (_audio && !_audio.paused) _audio.pause();
    });

    // NB : like-btn et add-to-pl-btn sont gérés par la délégation globale
    // de ui/playlists.js via data-like-btn / data-add-to-playlist
  }

  // ── Affichage / masquage ───────────────────────────────────────────────────
  function _show() {
    if (!_barEl) return;
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

  // ── Mise à jour de la barre de progression ────────────────────────────────
  function _startProgress() {
    if (_raf) cancelAnimationFrame(_raf);
    function _tick() {
      const fill = document.getElementById('smb-progress-fill');
      if (fill && _audio && _audio.duration) {
        fill.style.width = ((_audio.currentTime / _audio.duration) * 100).toFixed(2) + '%';
      }
      _raf = requestAnimationFrame(_tick);
    }
    _raf = requestAnimationFrame(_tick);
  }

  function _stopProgress() {
    if (_raf) cancelAnimationFrame(_raf);
    _raf = null;
  }

  // ── Mise à jour des métadonnées affichées ─────────────────────────────────
  function _updateMeta(info) {
    // info : { name, artist, cover, id, color }
    const titleEl  = document.getElementById('smb-title');
    const artistEl = document.getElementById('smb-artist');
    const coverEl  = document.getElementById('smb-cover');
    const phEl     = document.getElementById('smb-cover-placeholder');
    const likeBtn  = document.getElementById('smb-like-btn');
    const addBtn   = document.getElementById('smb-addpl-btn');
    const barEl    = document.getElementById('smyle-mini-bar');

    if (titleEl)  titleEl.textContent  = info.name   || '—';
    if (artistEl) artistEl.textContent = info.artist || 'WATT';

    // Cover
    if (info.cover && coverEl && phEl) {
      coverEl.src          = info.cover;
      coverEl.style.display = '';
      phEl.style.display   = 'none';
    } else if (coverEl && phEl) {
      coverEl.style.display = 'none';
      phEl.style.display   = '';
    }

    // Couleur accent si dispo
    if (info.color && barEl) {
      const m = String(info.color).match(/^#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/i);
      if (m) {
        barEl.style.setProperty('--smb-accent', info.color);
      }
    }

    // Buttons data-attributes pour like/add delegation
    _trackId = info.id ? String(info.id) : null;
    if (likeBtn) {
      likeBtn.setAttribute('data-like-btn', _trackId || '');
      if (!_trackId) likeBtn.style.opacity = '0.35';
      else likeBtn.style.opacity = '';
    }
    if (addBtn) {
      addBtn.setAttribute('data-add-to-playlist', _trackId || '');
      if (!_trackId) addBtn.style.opacity = '0.35';
      else addBtn.style.opacity = '';
    }

    // Sync état liked
    if (_trackId && typeof window.SmylePlaylists !== 'undefined' && typeof window.SmylePlaylists.syncLikeBtns === 'function') {
      window.SmylePlaylists.syncLikeBtns();
    }
  }

  // ── Lecture des métadonnées depuis l'audio actif ──────────────────────────
  function _readMeta(audioEl) {
    let info = { name: '—', artist: 'WATT', cover: null, id: null, color: null };

    // 1) window.smyleAudio singleton (player principal index.html)
    if (audioEl === window.smyleAudio && audioEl._trackRef) {
      const t  = audioEl._trackRef;
      // Récupérer la playlist courante
      const pl = (typeof PLAYLISTS !== 'undefined' && typeof currentPlaylist !== 'undefined')
        ? PLAYLISTS[currentPlaylist] : null;
      info.name   = t.name       || info.name;
      info.artist = (pl && pl.label) || info.artist;
      info.cover  = t.cover_url  || null;
      info.id     = t.id         || null;
      info.color  = (pl && pl.theme && /^#[0-9a-fA-F]{6}$/.test(pl.theme)) ? pl.theme : null;
      return info;
    }

    // 2) Audio inline artiste — chercher les data-attrs dans le parent
    // L'audio est dans .ap-track-inner ; le parent .ap-track-card a data-track-id / data-track-name
    let el = audioEl.parentElement;
    for (let i = 0; i < 6 && el; i++) {
      const tid  = el.dataset.trackId  || el.getAttribute('data-track-id');
      const name = el.dataset.trackName || el.getAttribute('data-track-name');
      if (tid || name) {
        info.id   = tid   || null;
        info.name = name  || info.name;
        // Cover : chercher img.ap-track-cover dans le même card
        const img = el.querySelector('img.ap-track-cover, img.ap-cover, .ap-track-cover img');
        if (img) info.cover = img.src || null;
        break;
      }
      el = el.parentElement;
    }
    return info;
  }

  // ── Bind sur un Audio element ─────────────────────────────────────────────
  function _bindAudio(audioEl) {
    if (_audio === audioEl) return;   // déjà attaché
    _unbindAudio();
    _audio    = audioEl;
    _dismissed = false;

    const onPlay = function() {
      _updateMeta(_readMeta(audioEl));
      _updatePlayBtn(true);
      _show();
      _startProgress();
    };
    const onPause = function() {
      _updatePlayBtn(false);
      _stopProgress();
    };
    const onEnded = function() {
      _updatePlayBtn(false);
      _stopProgress();
    };

    audioEl._smb_play   = onPlay;
    audioEl._smb_pause  = onPause;
    audioEl._smb_ended  = onEnded;

    audioEl.addEventListener('play',   onPlay);
    audioEl.addEventListener('pause',  onPause);
    audioEl.addEventListener('ended',  onEnded);

    // Si déjà en cours de lecture (ex: on charge la page mid-song)
    if (!audioEl.paused) {
      _updateMeta(_readMeta(audioEl));
      _updatePlayBtn(true);
      _show();
      _startProgress();
    }
  }

  function _unbindAudio() {
    if (!_audio) return;
    if (_audio._smb_play)  _audio.removeEventListener('play',   _audio._smb_play);
    if (_audio._smb_pause) _audio.removeEventListener('pause',  _audio._smb_pause);
    if (_audio._smb_ended) _audio.removeEventListener('ended',  _audio._smb_ended);
    delete _audio._smb_play;
    delete _audio._smb_pause;
    delete _audio._smb_ended;
    _stopProgress();
    _audio = null;
  }

  // ── Bouton play/pause de la barre ─────────────────────────────────────────
  function _updatePlayBtn(playing) {
    const btn = document.getElementById('smb-playpause');
    if (!btn) return;
    btn.innerHTML = playing
      ? '⏸' /* ⏸ */
      : '▶' /* ▶ */;
    btn.classList.toggle('smb-playing', playing);
  }

  // ── Détection capture : tout audio qui démarre sur la page ────────────────
  function _onCapturePlay(e) {
    const target = e.target;
    if (!(target instanceof HTMLAudioElement)) return;
    if (_dismissed && _audio === target) return;
    _bindAudio(target);
  }

  // ── SmyleEvents : le player principal notifie quand un track change ────────
  function _onTrackChange() {
    // Rebind sur smyleAudio si ce n'est pas déjà le cas
    if (window.smyleAudio && _audio !== window.smyleAudio) {
      _bindAudio(window.smyleAudio);
    } else if (window.smyleAudio) {
      // Même audio mais track différent — rafraîchir les métas
      _updateMeta(_readMeta(window.smyleAudio));
    }
    _dismissed = false;
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  function _init() {
    _build();

    // Bind immédiat sur le singleton principal s'il existe déjà
    if (window.smyleAudio) {
      _bindAudio(window.smyleAudio);
    }

    // Capture tous les <audio> de la page (artiste inline, etc.)
    document.addEventListener('play', _onCapturePlay, true);

    // Écouter SmyleEvents si dispo
    if (typeof SmyleEvents !== 'undefined') {
      SmyleEvents.on('smyle:track-loaded', _onTrackChange);
    }
    // Polling léger au cas où smyleAudio est exposé après notre init
    // (race condition si state.js charge après mini-bar dans certaines pages)
    let _pollCount = 0;
    const _poll = setInterval(function() {
      if (window.smyleAudio && _audio !== window.smyleAudio) {
        _bindAudio(window.smyleAudio);
      }
      if (++_pollCount > 20) clearInterval(_poll);
    }, 300);
  }

  // Lancement dès que le DOM est prêt
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }

  // ── API publique ──────────────────────────────────────────────────────────
  window.SmyleMiniBar = {
    // Permet aux pages de forcer la mise à jour des métadonnées
    setTrack: function(info) {
      // info : { name, artist, cover, id, color }
      _dismissed = false;
      _updateMeta(info);
      if (window.smyleAudio && !window.smyleAudio.paused) {
        _updatePlayBtn(true);
        _show();
      }
    },
    show: _show,
    hide: _hide,
    bindAudio: _bindAudio,
  };

})();
