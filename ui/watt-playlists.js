/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/watt-playlists.js  ·  window.WattPlaylists
   Liens directs + « Mes playlists » partout (02/11/2026).

   1. LIENS DIRECTS — chaque lien mène exactement à ce qu'on partage :
        son      → /o/<id>          s'il appartient à une Œuvre (page riche)
                   /sons?son=<id>   sinon (la fiche du son s'ouvre)
        playlist → /u/<slug>?playlist=<id>  (le profil, playlist ouverte)
                   /?playlist=<id>          si le créateur n'est pas connu
      Quand la personne qui partage est connectée, son code est ajouté
      (&ref=CODE) : même mécanique que le lien créateur du Lot K.
        - WattPlaylists.shareSon(track)
        - WattPlaylists.sharePlaylist(playlist, slug)
        - WattPlaylists.share(path, title) — bas niveau

   2. FICHE PLAYLIST — panneau qui liste les sons, « Tout lire », lecture
      son par son (enchaînement automatique), partage de la playlist et de
      chaque son. Lisible sans compte pour une playlist publique.
        - WattPlaylists.open(playlistId, { slug })
      Ouverte automatiquement par ?playlist=<uuid> sur n'importe quelle page.

   3. MES PLAYLISTS — accessibles depuis le menu de toutes les pages
      (bouton « Playlists ») : ♥ Mes likes + toutes mes playlists, lecture
      directe, ouverture de la fiche, création.
        - WattPlaylists.openMine()
      Ouvert aussi par ?mes-playlists=1 (repli des pages sans ce script).

   Lecture : un seul <audio> partagé, posé dans le body pour que la musique
   continue après fermeture du panneau. La mini-barre (ui/player/mini-bar.js)
   le détecte d'elle-même ; la barrière visiteur (extrait 30 s) s'applique.
   Aucun gestionnaire en ligne interpolé (garde-fou test_front_escapers).
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (typeof window === 'undefined' || window.WattPlaylists) return;

  var UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  // ── Utilitaires ─────────────────────────────────────────────────────────
  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c];
    });
  }
  function _toast(msg, type) {
    try {
      if (typeof window.smyleToast === 'function') { window.smyleToast(msg, { type: type || 'info' }); return; }
      if (typeof window.showToast === 'function') { window.showToast(msg); return; }
    } catch (_) {}
  }
  function _hasToken() {
    try { return typeof window.getAuthToken === 'function' && !!window.getAuthToken(); }
    catch (_) { return false; }
  }
  function _api(path, opts) {
    if (typeof window.apiFetch !== 'function') return Promise.reject(new Error('api indisponible'));
    return window.apiFetch(path, opts || {});
  }
  function _color(c) {
    return (typeof c === 'string' && /^#[0-9a-fA-F]{6}$/.test(c)) ? c : '#8800ff';
  }
  function _track(ev, props) {
    try { if (window.SmyleTrack) window.SmyleTrack.event(ev, props || {}); } catch (_) {}
  }

  // Utilisateur connecté + code de parrainage : chargés une fois, à la demande.
  var _meP = null;
  function _me() {
    if (!_hasToken()) return Promise.resolve(null);
    if (!_meP) _meP = _api('/users/me').catch(function () { _meP = null; return null; });
    return _meP;
  }
  var _refP = null;
  function _refCode() {
    if (!_hasToken()) return Promise.resolve(null);
    if (!_refP) {
      _refP = _api('/referrals/me')
        .then(function (d) {
          var c = d && d.referral_code;
          return (c && /^[A-Za-z0-9-]{1,16}$/.test(c)) ? c : null;
        })
        .catch(function () { _refP = null; return null; });
    }
    return _refP;
  }
  function _slugOf(user) {
    if (!user) return null;
    if (user.slug) return user.slug;
    var raw = (user.artistName || user.artist_name || '').trim();
    if (!raw) return null;
    return raw.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || null;
  }
  // Slug du profil affiché (/u/<slug> ou /@<slug>), sinon null.
  function _pageSlug() {
    var m = (location.pathname || '').match(/^\/(?:u\/|@)([^\/?#]+)/);
    if (!m) return null;
    try { return decodeURIComponent(m[1]); } catch (_) { return m[1]; }
  }

  // ── 1. Liens directs + partage ──────────────────────────────────────────
  function _withRef(path, code) {
    if (!code) return path;
    return path + (path.indexOf('?') === -1 ? '?' : '&') + 'ref=' + encodeURIComponent(code);
  }

  function sonPath(t) {
    if (!t) return '/sons';
    var li = t.linkedImage || null;
    var oid = t.oeuvreId || (li && li.id) || null;
    if (oid && UUID_RE.test(String(oid))) return '/o/' + encodeURIComponent(String(oid));
    var id = t.trackUuid || t.id;
    return '/sons?son=' + encodeURIComponent(String(id || ''));
  }

  function playlistPath(id, slug) {
    var q = 'playlist=' + encodeURIComponent(String(id));
    return slug ? '/u/' + encodeURIComponent(slug) + '?' + q : '/?' + q;
  }

  function _copy(url, done) {
    function fallback() {
      try {
        var ta = document.createElement('textarea');
        ta.value = url; ta.setAttribute('readonly', '');
        ta.style.position = 'absolute'; ta.style.left = '-9999px';
        document.body.appendChild(ta); ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        done();
      } catch (_) { window.prompt('Copie ce lien :', url); }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done, fallback);
    } else { fallback(); }
  }

  // Mobile : feuille de partage native (Insta, WhatsApp…). Ordinateur : copie.
  function share(path, title, props) {
    return _refCode().then(function (code) {
      var url = location.origin + _withRef(path, code);
      _track('share_click', props || { path: path });
      var mobile = false;
      try { mobile = window.matchMedia('(pointer: coarse)').matches; } catch (_) {}
      if (mobile && navigator.share) {
        navigator.share({ title: title || document.title, url: url }).catch(function () {});
        return url;
      }
      _copy(url, function () { _toast('Lien copié — colle-le où tu veux.', 'success'); });
      return url;
    });
  }

  function shareSon(t) {
    if (!t) return Promise.resolve(null);
    return share(sonPath(t), (t.name || t.title || 'Son') + ' — WATT', { kind: 'son' });
  }

  function sharePlaylist(pl, slug) {
    if (!pl || !pl.id) return Promise.resolve(null);
    if (pl.visibility && pl.visibility !== 'public') {
      _toast('Cette playlist est privée : rends-la publique pour la partager.', 'error');
      return Promise.resolve(null);
    }
    return share(playlistPath(pl.id, slug), (pl.title || 'Playlist') + ' — WATT', { kind: 'playlist' });
  }

  // ── Lecteur partagé ─────────────────────────────────────────────────────
  var _player = { host: null, audio: null, queue: [], idx: -1, plId: null };

  function _ensurePlayer() {
    if (_player.audio) return _player;
    var host = document.createElement('div');
    host.id = 'wpl-audio-host';
    host.hidden = true;
    host.innerHTML =
      '<span class="ap-artist-name"></span>' +
      '<img class="ap-cover" alt="" />' +
      '<audio preload="none"></audio>';
    document.body.appendChild(host);
    _player.host = host;
    _player.audio = host.querySelector('audio');
    _player.audio.addEventListener('ended', function () { _playIdx(_player.idx + 1); });
    _player.audio.addEventListener('play', _syncRows);
    _player.audio.addEventListener('pause', _syncRows);
    return _player;
  }

  function _srcOf(t) {
    return (t && (t.stream_url || t.streamUrl || t.audio_url)) || '';
  }

  function _playIdx(i) {
    var p = _ensurePlayer();
    if (i < 0 || i >= p.queue.length) { p.idx = -1; _syncRows(); return; }
    var t = p.queue[i];
    p.idx = i;
    // Méta lue par la mini-barre (elle remonte le DOM depuis l'audio).
    p.host.dataset.trackId = String(t.id || '');
    p.host.dataset.trackUuid = String(t.id || '');
    p.host.dataset.trackName = t.title || t.name || '—';
    p.host.querySelector('.ap-artist-name').textContent = p.label || 'WATT';
    var img = p.host.querySelector('img.ap-cover');
    if (t.cover_url) { img.src = t.cover_url; } else { img.removeAttribute('src'); }
    p.audio.src = _srcOf(t);
    var pr = p.audio.play();
    if (pr && pr.catch) pr.catch(function () {});
    _syncRows();
  }

  function playQueue(tracks, startIdx, plId, label) {
    var p = _ensurePlayer();
    p.queue = (tracks || []).filter(function (t) { return !!_srcOf(t); });
    p.plId = plId || null;
    p.label = label || 'WATT';
    if (!p.queue.length) { _toast('Aucun son à lire dans cette playlist.', 'error'); return; }
    _playIdx(Math.max(0, Math.min(startIdx || 0, p.queue.length - 1)));
  }

  function _toggleTrack(tracks, i, plId, label) {
    var p = _ensurePlayer();
    var t = tracks[i];
    var cur = p.idx >= 0 ? p.queue[p.idx] : null;
    if (cur && t && String(cur.id) === String(t.id) && p.plId === plId) {
      if (p.audio.paused) { var pr = p.audio.play(); if (pr && pr.catch) pr.catch(function () {}); }
      else p.audio.pause();
      return;
    }
    var playable = (tracks || []).filter(function (x) { return !!_srcOf(x); });
    var start = playable.indexOf(t);
    if (start === -1) { _toast('Ce son n’est pas disponible à l’écoute.', 'error'); return; }
    playQueue(playable, start, plId, label);
  }

  // Met à jour les ▶/❚❚ de la fiche ouverte.
  function _syncRows() {
    var p = _player;
    var cur = (p.idx >= 0 && p.queue[p.idx]) ? String(p.queue[p.idx].id) : null;
    var playing = !!(p.audio && !p.audio.paused);
    document.querySelectorAll('.wpl-sheet[data-pl-id] .wpl-row').forEach(function (row) {
      var sheet = row.closest('.wpl-sheet');
      var on = cur && sheet && sheet.dataset.plId === String(p.plId) && row.dataset.trackId === cur;
      row.classList.toggle('is-current', !!on);
      var b = row.querySelector('.wpl-row-play');
      if (b) b.textContent = (on && playing) ? '❚❚' : '▶';
    });
  }

  // ── Styles ──────────────────────────────────────────────────────────────
  var _cssDone = false;
  function _css() {
    if (_cssDone) return;
    _cssDone = true;
    var st = document.createElement('style');
    st.id = 'wpl-styles';
    st.textContent = [
      '.wpl-ov{position:fixed;inset:0;z-index:10050;background:rgba(5,5,8,.55);backdrop-filter:blur(3px);',
      'display:flex;justify-content:flex-end;opacity:0;transition:opacity .2s}',
      '.wpl-ov.is-open{opacity:1}',
      '.wpl-sheet{width:min(440px,100%);height:100%;background:var(--sp-surface-raised,#14101f);color:var(--sp-text,#e8e8f0);',
      'border-left:1px solid var(--sp-border,rgba(255,255,255,.1));display:flex;flex-direction:column;',
      'transform:translateX(24px);transition:transform .22s ease;font-family:inherit;box-sizing:border-box}',
      '.wpl-ov.is-open .wpl-sheet{transform:none}',
      '.wpl-hd{position:relative;padding:18px 18px 16px;',
      'background:linear-gradient(160deg,var(--wpl-c,#8800ff) 0%,rgba(20,16,31,0) 85%)}',
      '.wpl-top{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:14px}',
      '.wpl-ico{background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.14);color:#fff;border-radius:999px;',
      'height:32px;min-width:32px;padding:0 12px;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}',
      '.wpl-ico:hover{background:rgba(0,0,0,.45)}',
      '.wpl-kicker{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.75);margin:0 0 4px}',
      '.wpl-title{margin:0;font-size:24px;line-height:1.15;font-weight:800;word-break:break-word}',
      '.wpl-meta{margin:6px 0 0;font-size:13px;color:rgba(255,255,255,.75)}',
      '.wpl-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}',
      '.wpl-btn{border:none;border-radius:999px;padding:10px 16px;font-size:13px;font-weight:700;cursor:pointer;',
      'display:inline-flex;align-items:center;gap:6px;font-family:inherit}',
      '.wpl-btn--main{background:#fff;color:#0b0812}',
      '.wpl-btn--ghost{background:rgba(255,255,255,.1);color:#fff;border:1px solid rgba(255,255,255,.16)}',
      '.wpl-btn:disabled{opacity:.5;cursor:default}',
      '.wpl-note{margin:12px 0 0;font-size:12px;color:rgba(255,255,255,.7)}',
      '.wpl-body{flex:1;overflow-y:auto;padding:6px 10px 90px}',
      '.wpl-row{display:flex;align-items:center;gap:10px;padding:8px;border-radius:10px}',
      '.wpl-row:hover{background:var(--sp-surface,rgba(255,255,255,.04))}',
      '.wpl-row.is-current{background:rgba(136,0,255,.16)}',
      '.wpl-row.is-current .wpl-row-title{color:var(--sp-mauve,#cc88ff)}',
      '.wpl-row-play{flex:none;width:34px;height:34px;border-radius:50%;border:1px solid var(--sp-border,rgba(255,255,255,.12));',
      'background:rgba(255,255,255,.06);color:#fff;font-size:11px;cursor:pointer}',
      '.wpl-row-play:disabled{opacity:.35;cursor:default}',
      '.wpl-row-cover{flex:none;width:40px;height:40px;border-radius:8px;object-fit:cover;background:var(--wpl-rc,#2c2440)}',
      '.wpl-row-txt{flex:1;min-width:0}',
      '.wpl-row-title{display:block;font-size:14px;font-weight:600;color:inherit;text-decoration:none;',
      'white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
      'a.wpl-row-title:hover{text-decoration:underline}',
      '.wpl-row-sub{font-size:12px;color:var(--sp-text-faint,rgba(255,255,255,.55))}',
      '.wpl-row-share{flex:none;background:none;border:none;color:var(--sp-text-faint,rgba(255,255,255,.55));',
      'font-size:12px;cursor:pointer;padding:6px 8px;border-radius:8px}',
      '.wpl-row-share:hover{color:#fff;background:rgba(255,255,255,.08)}',
      '.wpl-empty{padding:28px 12px;text-align:center;color:var(--sp-text-faint,rgba(255,255,255,.55));font-size:14px;line-height:1.5}',
      '.wpl-list-row{cursor:pointer}',
      '.wpl-swatch{flex:none;width:44px;height:44px;border-radius:10px;display:flex;align-items:center;justify-content:center;',
      'font-size:18px;background:linear-gradient(135deg,var(--wpl-rc,#8800ff),rgba(0,0,0,.35))}',
      '.wpl-foot{padding:12px 18px;border-top:1px solid var(--sp-border,rgba(255,255,255,.1))}',
      '@media (max-width:520px){.wpl-sheet{border-left:none}.wpl-title{font-size:21px}}'
    ].join('');
    document.head.appendChild(st);
  }

  // ── Panneau générique (une seule instance à la fois) ────────────────────
  var _current = null;
  function _close() {
    if (!_current) return;
    var ov = _current;
    _current = null;
    ov.classList.remove('is-open');
    setTimeout(function () { if (ov.parentNode) ov.parentNode.removeChild(ov); }, 220);
    document.removeEventListener('keydown', _onEsc);
  }
  function _onEsc(e) { if (e.key === 'Escape') _close(); }
  function _mount(innerHtml, color, plId) {
    _css();
    if (_current && _current.parentNode) _current.parentNode.removeChild(_current);
    var ov = document.createElement('div');
    ov.className = 'wpl-ov';
    ov.innerHTML = '<aside class="wpl-sheet" role="dialog" aria-modal="true"' +
      (plId ? ' data-pl-id="' + _esc(plId) + '"' : '') +
      ' style="--wpl-c:' + _esc(_color(color)) + '">' + innerHtml + '</aside>';
    ov.addEventListener('click', function (e) { if (e.target === ov) _close(); });
    document.body.appendChild(ov);
    document.addEventListener('keydown', _onEsc);
    _current = ov;
    requestAnimationFrame(function () { ov.classList.add('is-open'); });
    return ov;
  }

  // ── 2. Fiche playlist ───────────────────────────────────────────────────
  function _fetchPlaylist(id) {
    var pub = function () { return _api('/watt/playlists/' + encodeURIComponent(id), { auth: false }); };
    if (!_hasToken()) return pub();
    // Connecté : la route propriétaire voit aussi mes playlists privées.
    return _api('/playlists/' + encodeURIComponent(id)).catch(pub);
  }

  function open(id, opts) {
    opts = opts || {};
    if (!id || !UUID_RE.test(String(id))) return Promise.resolve(null);
    var ov = _mount(
      '<div class="wpl-hd"><div class="wpl-top"><span></span>' +
      '<button type="button" class="wpl-ico" data-act="close" aria-label="Fermer">✕</button></div>' +
      '<p class="wpl-kicker">Playlist</p><h2 class="wpl-title">Chargement…</h2></div>',
      null, String(id)
    );
    ov.querySelector('[data-act="close"]').addEventListener('click', _close);

    return Promise.all([_fetchPlaylist(id), _me()]).then(function (res) {
      if (_current !== ov) return null;
      _renderSheet(ov, res[0], res[1], opts);
      return res[0];
    }).catch(function () {
      if (_current !== ov) return null;
      ov.querySelector('.wpl-title').textContent = 'Playlist introuvable';
      var hd = ov.querySelector('.wpl-hd');
      var p = document.createElement('p');
      p.className = 'wpl-meta';
      p.textContent = 'Elle a peut-être été supprimée ou rendue privée.';
      hd.appendChild(p);
      return null;
    });
  }

  // Nouveau nœud à chaque rendu : les écouteurs du rendu précédent partent avec.
  function _freshSheet(ov) {
    var old = ov.querySelector('.wpl-sheet');
    var fresh = old.cloneNode(false);
    old.parentNode.replaceChild(fresh, old);
    return fresh;
  }

  function _renderSheet(ov, pl, me, opts) {
    var sheet = _freshSheet(ov);
    var isOwner = !!(me && pl.owner_id && String(me.id) === String(pl.owner_id));
    var slug = opts.slug || (isOwner ? _slugOf(me) : null) || _pageSlug();
    var tracks = Array.isArray(pl.tracks) ? pl.tracks : [];
    var isPublic = pl.visibility === 'public';
    var color = _color(pl.color);
    sheet.style.setProperty('--wpl-c', color);

    var n = tracks.length;
    var meta = n + ' son' + (n > 1 ? 's' : '') +
      (isOwner ? (isPublic ? ' · Publique' : ' · Privée') : '');

    var back = opts.fromMine
      ? '<button type="button" class="wpl-ico" data-act="back">← Mes playlists</button>'
      : '<span></span>';
    var shareBtn = isPublic
      ? '<button type="button" class="wpl-btn wpl-btn--ghost" data-act="share">🔗 Partager</button>'
      : (isOwner && !opts.isWishlist
        ? '<button type="button" class="wpl-btn wpl-btn--ghost" data-act="publish">🌍 Rendre publique</button>'
        : '');
    var note = (isOwner && !isPublic && !opts.isWishlist)
      ? '<p class="wpl-note">Privée : toi seul la vois. Rends-la publique pour partager son lien.</p>'
      : '';

    var rows = tracks.map(function (t, i) {
      var playable = !!_srcOf(t);
      var cover = t.cover_url
        ? '<img class="wpl-row-cover" src="' + _esc(t.cover_url) + '" alt="" loading="lazy" />'
        : '<span class="wpl-row-cover" style="--wpl-rc:' + _esc(_color(t.color || pl.color)) + '"></span>';
      var title = t.title || 'Sans titre';
      var href = '/sons?son=' + encodeURIComponent(String(t.id || ''));
      return '<div class="wpl-row" data-idx="' + i + '" data-track-id="' + _esc(t.id) + '">' +
        '<button type="button" class="wpl-row-play" data-act="play"' + (playable ? '' : ' disabled') +
        ' aria-label="Lire ' + _esc(title) + '">▶</button>' +
        cover +
        '<div class="wpl-row-txt"><a class="wpl-row-title" href="' + _esc(href) + '">' + _esc(title) + '</a>' +
        '<div class="wpl-row-sub">' + (i + 1) + (t.bpm ? ' · ' + _esc(t.bpm) + ' BPM' : '') + '</div></div>' +
        '<button type="button" class="wpl-row-share" data-act="share-son" title="Partager ce son">🔗</button>' +
      '</div>';
    }).join('');

    sheet.innerHTML =
      '<div class="wpl-hd">' +
        '<div class="wpl-top">' + back +
          '<button type="button" class="wpl-ico" data-act="close" aria-label="Fermer">✕</button></div>' +
        '<p class="wpl-kicker">' + (opts.isWishlist ? 'Tes likes' : 'Playlist') + '</p>' +
        '<h2 class="wpl-title">' + _esc(pl.title || 'Playlist') + '</h2>' +
        '<p class="wpl-meta">' + _esc(meta) + '</p>' +
        '<div class="wpl-actions">' +
          '<button type="button" class="wpl-btn wpl-btn--main" data-act="play-all"' + (n ? '' : ' disabled') + '>▶ Tout lire</button>' +
          shareBtn +
        '</div>' + note +
      '</div>' +
      '<div class="wpl-body">' +
        (n ? rows : '<div class="wpl-empty">Aucun son pour l’instant.' +
          (isOwner ? '<br>Ajoute des sons avec le bouton « + » sur une fiche son.' : '') + '</div>') +
      '</div>';

    var label = pl.title || 'Playlist';
    sheet.addEventListener('click', function (e) {
      var b = e.target.closest('[data-act]');
      if (!b || !sheet.contains(b)) return;
      var act = b.dataset.act;
      if (act === 'close') { _close(); return; }
      if (act === 'back') { openMine(); return; }
      if (act === 'play-all') { playQueue(tracks, 0, String(pl.id), label); return; }
      if (act === 'share') { sharePlaylist(pl, slug); return; }
      if (act === 'publish') { _publish(pl, b, ov, me, opts); return; }
      var row = b.closest('.wpl-row');
      if (!row) return;
      var t = tracks[Number(row.dataset.idx)];
      if (act === 'play') _toggleTrack(tracks, Number(row.dataset.idx), String(pl.id), label);
      if (act === 'share-son') shareSon({ trackUuid: t.id, name: t.title });
    });
    _syncRows();
  }

  function _publish(pl, btn, ov, me, opts) {
    btn.disabled = true;
    _api('/playlists/' + encodeURIComponent(pl.id), { method: 'PATCH', json: { visibility: 'public' } })
      .then(function () {
        pl.visibility = 'public';
        _toast('Playlist publique : tu peux partager son lien.', 'success');
        if (_current === ov) _renderSheet(ov, pl, me, opts);
      })
      .catch(function (err) {
        btn.disabled = false;
        var d = err && err.body && err.body.detail;
        _toast((typeof d === 'string' && d) || 'Impossible de la rendre publique pour le moment.', 'error');
      });
  }

  // ── 3. Mes playlists ────────────────────────────────────────────────────
  function openMine() {
    if (!_hasToken()) {
      if (window.SmyleGate && typeof window.SmyleGate.requireAccount === 'function') {
        window.SmyleGate.requireAccount({ reason: 'Connecte-toi pour retrouver tes playlists.' });
      } else {
        location.href = '/?auth=login';
      }
      return;
    }
    var ov = _mount(
      '<div class="wpl-hd"><div class="wpl-top"><span></span>' +
      '<button type="button" class="wpl-ico" data-act="close" aria-label="Fermer">✕</button></div>' +
      '<p class="wpl-kicker">Ta musique</p><h2 class="wpl-title">Mes playlists</h2>' +
      '<p class="wpl-meta">Chargement…</p></div><div class="wpl-body"></div>',
      '#0055ff', null
    );
    ov.querySelector('[data-act="close"]').addEventListener('click', _close);

    Promise.all([
      _api('/playlists/wishlist').catch(function () { return null; }),
      _api('/playlists/me').catch(function () { return []; }),
      _me(),
    ]).then(function (res) {
      if (_current !== ov) return;
      var wish = res[0];
      var mine = (Array.isArray(res[1]) ? res[1] : [])
        .filter(function (p) { return !wish || String(p.id) !== String(wish.id); })
        .sort(function (a, b) { return String(b.created_at || '').localeCompare(String(a.created_at || '')); });
      var slug = _slugOf(res[2]);
      _renderMine(ov, wish, mine, slug);
    });
  }

  function _renderMine(ov, wish, mine, slug) {
    var sheet = _freshSheet(ov);
    var items = [];
    if (wish) items.push({ p: wish, wish: true });
    mine.forEach(function (p) { items.push({ p: p, wish: false }); });

    var rows = items.map(function (it, i) {
      var p = it.p;
      var n = p.track_count || 0;
      var sub = it.wish
        ? 'Les sons que tu as aimés'
        : n + ' son' + (n > 1 ? 's' : '') + ' · ' + (p.visibility === 'public' ? 'Publique' : 'Privée');
      var canShare = !it.wish && p.visibility === 'public';
      return '<div class="wpl-row wpl-list-row" data-i="' + i + '" data-act="open">' +
        '<button type="button" class="wpl-row-play" data-act="quick" aria-label="Lire">▶</button>' +
        '<span class="wpl-swatch" style="--wpl-rc:' + _esc(_color(p.color)) + '">' + (it.wish ? '♥' : '🎧') + '</span>' +
        '<div class="wpl-row-txt"><span class="wpl-row-title">' + _esc(it.wish ? 'Mes likes' : (p.title || 'Playlist')) + '</span>' +
        '<div class="wpl-row-sub">' + _esc(sub) + '</div></div>' +
        (canShare ? '<button type="button" class="wpl-row-share" data-act="share" title="Partager">🔗</button>' : '') +
      '</div>';
    }).join('');

    var canCreate = !!(window.SmylePlaylists && typeof window.SmylePlaylists.openCreatePlaylistModal === 'function');
    sheet.innerHTML =
      '<div class="wpl-hd"><div class="wpl-top"><span></span>' +
        '<button type="button" class="wpl-ico" data-act="close" aria-label="Fermer">✕</button></div>' +
        '<p class="wpl-kicker">Ta musique</p><h2 class="wpl-title">Mes playlists</h2>' +
        '<p class="wpl-meta">' + items.length + ' playlist' + (items.length > 1 ? 's' : '') + '</p></div>' +
      '<div class="wpl-body">' +
        (items.length > (wish ? 1 : 0) ? rows
          : rows + '<div class="wpl-empty">Tu n’as pas encore de playlist.<br>' +
            'Sur une fiche son, le bouton « + » l’ajoute à une playlist.</div>') +
      '</div>' +
      (canCreate ? '<div class="wpl-foot"><button type="button" class="wpl-btn wpl-btn--main" data-act="create">+ Nouvelle playlist</button></div>' : '');

    sheet.addEventListener('click', function (e) {
      var b = e.target.closest('[data-act]');
      if (!b || !sheet.contains(b)) return;
      var act = b.dataset.act;
      if (act === 'close') { _close(); return; }
      if (act === 'create') {
        window.SmylePlaylists.openCreatePlaylistModal(function () { openMine(); });
        return;
      }
      var row = b.closest('.wpl-list-row');
      if (!row) return;
      var it = items[Number(row.dataset.i)];
      if (!it) return;
      e.stopPropagation();
      if (act === 'quick') {
        _fetchPlaylist(it.p.id).then(function (d) {
          playQueue(d && d.tracks, 0, String(it.p.id), it.wish ? 'Mes likes' : (d && d.title));
        }).catch(function () { _toast('Impossible de lancer la playlist.', 'error'); });
        return;
      }
      if (act === 'share') { sharePlaylist(it.p, slug); return; }
      if (act === 'open') open(it.p.id, { slug: slug, fromMine: true, isWishlist: it.wish });
    });
  }

  // Menu : sur écran moyen la barre est déjà pleine → icône seule.
  (function () {
    try {
      var st = document.createElement('style');
      // Le menu « lissé » (lissage.css) masque les icônes de .hdr-nav : on
      // garde celle de Playlists visible quand le libellé est masqué.
      st.textContent = '@media (max-width:1200px){.wpl-nav-label{display:none}' +
        '.hdr-nav .wpl-nav-btn svg{display:inline-block;width:14px;height:14px}}';
      (document.head || document.documentElement).appendChild(st);
    } catch (_) {}
  })();

  // ── Arrivée par un lien direct ──────────────────────────────────────────
  function _boot() {
    var params;
    try { params = new URLSearchParams(location.search || ''); } catch (_) { return; }
    var pl = (params.get('playlist') || '').trim();
    if (pl && UUID_RE.test(pl)) {
      open(pl, { slug: _pageSlug() });
      return;
    }
    if (params.get('mes-playlists') === '1') {
      params.delete('mes-playlists');
      var q = params.toString();
      try { history.replaceState(null, '', location.pathname + (q ? '?' + q : '') + location.hash); } catch (_) {}
      openMine();
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(_boot, 0); }, { once: true });
  } else {
    setTimeout(_boot, 0);
  }

  window.WattPlaylists = {
    open: open,
    openMine: openMine,
    close: _close,
    share: share,
    shareSon: shareSon,
    sharePlaylist: sharePlaylist,
    sonPath: sonPath,
    playlistPath: playlistPath,
    playQueue: playQueue,
  };
})();
