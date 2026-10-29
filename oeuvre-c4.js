/* ═════════════════════════════════════════════════════════════════════════
   oeuvre-c4.js — Page ŒUVRE (1 son + 1 image) · /o/<id>   (Lot 2, 23/09)
   ─────────────────────────────────────────────────────────────────────────
   L'Œuvre est LA fonctionnalité centrale : un son et une image réunis.
   Cette page est le lien que le créateur partage (aperçu social injecté par
   le serveur). Elle monte :
     • l'image (aperçu, jamais l'original) ;
     • le lecteur audio du son ;
     • les deux moitiés, chacune achetable SÉPARÉMENT (drawer unifié) — la
       moitié son n'est achetable que si le morceau a une recette ;
     • un lien vers le profil du créateur ;
     • « Acheter l'Œuvre » (#o-bundle, Lot 3) : son + image, remise choisie par le créateur (0/10/20 %), en un
       seul achat (POST /watt/oeuvres/<id>/acheter). Si une moitié est déjà
       possédée, le bouton complète l'Œuvre au prix plein de l'autre.

   API : GET /watt/oeuvres/<id> (public, aperçu anti-fuite).
   ═════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  // Échappeur complet (& < > " ' `) — copie de ui/albums.js.
  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c];
    });
  }

  // Lot J — provenance lisible : « Fait avec Suno · v6 ».
  var _OUTILS = {
    suno: 'Suno', udio: 'Udio', riffusion: 'Riffusion', stable_audio: 'Stable Audio',
    elevenlabs: 'ElevenLabs Music', midjourney: 'Midjourney', dalle: 'DALL·E',
    chatgpt: 'ChatGPT', flux: 'Flux', stable_diffusion: 'Stable Diffusion',
    ideogram: 'Ideogram', leonardo: 'Leonardo', firefly: 'Adobe Firefly',
    google: 'Google (Imagen / Nano Banana)', recraft: 'Recraft', seedream: 'Seedream',
    grok: 'Grok', autre: 'un autre outil',
  };
  function _provenance(platform, version) {
    var outil = platform ? (_OUTILS[platform] || platform) : '';
    if (!outil) return '';
    // Lot M — pas de « Suno · Suno » quand la version répète le nom.
    var v = String(version || '').trim();
    if (v && v.toLowerCase().replace(/[^a-z0-9]/g, '') === outil.toLowerCase().replace(/[^a-z0-9]/g, '')) v = '';
    return 'Fait avec ' + outil + (v ? ' · ' + v : '');
  }

  function _toast(msg, type) {
    try { if (window.smyleToast) return window.smyleToast(msg, { type: type || 'info' }); } catch (_) {}
  }

  function _id() {
    var m = window.location.pathname.match(/^\/o\/([0-9a-fA-F-]{36})\/?$/);
    return m ? m[1] : null;
  }
  var OID = _id();

  function _previewUrl(key) {
    if (!key) return '';
    return '/watt/images/' + String(key).split('/').map(encodeURIComponent).join('/');
  }

  function _show(id) {
    ['o-loading', 'o-empty', 'o-content'].forEach(function (x) {
      var n = document.getElementById(x);
      if (n) n.style.display = (x === id) ? '' : 'none';
    });
  }

  var _data = null;

  // Parcours V1 : un visiteur qui tente une action ouvre l'inscription
  // (retour ensuite sur cette Œuvre).
  function _gate() {
    return !window.SmyleGate || window.SmyleGate.requireAccount();
  }

  function _buy(kind) {
    if (!_data) return;
    if (!_gate()) return;
    if (!window.PurchaseDrawer || typeof window.PurchaseDrawer.open !== 'function') {
      _toast('Module d\'achat indisponible — recharge la page.', 'error');
      return;
    }
    var half = kind === 'image'
      ? { type: 'image', id: _data.image.id, price: _data.image.priceCredits, title: _data.image.title }
      : { type: 'son', id: _data.sound.recipe.id, price: _data.sound.recipe.priceCredits, title: _data.sound.title };
    window.PurchaseDrawer.open({
      type: half.type, id: half.id, price: half.price, title: half.title,
      platform: kind === 'image' ? (_data.image.platform || '') : (_data.sound.platform || ''),
      onSuccess: function () { _toast('Débloqué — retrouve-le dans ta bibliothèque.', 'success'); },
    });
  }

  // Fix 29/10 — confirmation DANS la page (plus de window.confirm, que le
  // navigateur peut bloquer en silence : le clic ne faisait alors rien).
  // 1er clic : le bouton devient « Confirmer l'achat · N Smyles » (6 s) ;
  // 2e clic : achat. Les erreurs sont affichées SOUS le bouton.
  var _confirmTimer = null;

  function _noteBundle(msg, type) {
    var box = document.getElementById('o-bundle');
    if (!box) return;
    var n = box.querySelector('.o-bundle-msg');
    if (!n) {
      n = document.createElement('p');
      n.className = 'o-bundle-note o-bundle-msg';
      n.setAttribute('role', 'status');
      box.appendChild(n);
    }
    n.textContent = msg || '';
    n.style.color = type === 'error' ? '#ff8a9a' : '';
  }

  function _buyBundle(btn) {
    if (!_gate()) return;
    if (!_data || !_data.bundle) return;
    var prix = _data.bundle.priceCredits;
    // Lot K — équivalent en euros dès que l'achat de Smyles est ouvert.
    var _eur = (window.WATT_LAUNCH && window.WATT_LAUNCH.achatSmyles)
      ? ' (≈ ' + (Math.round(prix * 0.07 * 100) / 100).toFixed(2).replace('.', ',') + ' €)' : '';
    if (btn.getAttribute('data-confirm') !== '1') {
      btn.setAttribute('data-confirm', '1');
      btn.setAttribute('data-label', btn.textContent);
      btn.textContent = 'Confirmer l\'achat · ' + prix + ' Smyles' + _eur;
      _noteBundle('Clique encore une fois pour confirmer.', 'info');
      clearTimeout(_confirmTimer);
      _confirmTimer = setTimeout(function () {
        btn.removeAttribute('data-confirm');
        btn.textContent = btn.getAttribute('data-label') || btn.textContent;
        _noteBundle('');
      }, 6000);
      return;
    }
    clearTimeout(_confirmTimer);
    btn.removeAttribute('data-confirm');
    btn.disabled = true;
    btn.textContent = 'Achat en cours…';
    _noteBundle('');
    // Lot G — prix attendu envoyé : si le créateur l'a changé entre-temps,
    // smyleAcheter demande de confirmer le nouveau prix avant de rejouer.
    var _chemin = '/watt/oeuvres/' + encodeURIComponent(OID) + '/acheter';
    (window.smyleAcheter
      ? window.smyleAcheter(_chemin, prix)
      : window.apiFetch(_chemin, { method: 'POST' }))
      .then(function () {
        _toast('Œuvre débloquée — le son et l\'image sont dans ta bibliothèque.', 'success');
        try { if (window.SmyleBalance && window.SmyleBalance.refresh) window.SmyleBalance.refresh(); } catch (_) {}
        load();
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.textContent = btn.getAttribute('data-label') || ('Acheter l\'œuvre · ' + prix + ' Smyles');
        var s = err && err.status;
        var d = err && err.body && err.body.detail;
        var msg;
        if (err && err.annule) { msg = 'Achat annulé : le prix a changé.'; load(); }
        else if (s === 402) {
          msg = (d && typeof d === 'object' && d.required != null)
            ? 'Solde insuffisant : il te faut ' + d.required + ' Smyles, tu en as ' + d.available + '.'
            : 'Pas assez de Smyles pour cette œuvre.';
          // Lot L : achat de Smyles proposé directement quand il est ouvert.
          if (window.WATT_LAUNCH && window.WATT_LAUNCH.achatSmyles && typeof window.openCreditsBuyModal === 'function') {
            try { window.openCreditsBuyModal(); } catch (_) {}
          } else {
            msg += ' Invite un ami : +20 Smyles pour toi et pour lui.';
          }
        }
        else if (s === 401) msg = 'Reconnecte-toi pour acheter cette œuvre.';
        else if (s === 409) msg = (typeof d === 'string') ? d : 'Tu possèdes déjà cette œuvre.';
        else if (typeof d === 'string') msg = d;
        else msg = 'Achat impossible pour le moment. Réessaie.';
        _noteBundle(msg, 'error');
        _toast(msg, 'error');
      });
  }

  // Texte de l'offre groupée : avec remise (prix barré) ou sans (0 %).
  function _detailOffre(plein, prix, pct) {
    if (!pct) return 'Le son et l\'image en un seul achat : ' + _esc(prix) + ' Smyles.';
    return 'Le son et l\'image ensemble : <s>' + _esc(plein) + '</s> ' + _esc(prix) +
      ' Smyles (−' + _esc(pct) + ' %).';
  }

  var _ICON_PLAY = '<svg width="16" height="16" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 1.5v11l9-5.5z" fill="#050508"/></svg>';
  var _ICON_PAUSE = '<svg width="16" height="16" viewBox="0 0 14 14" aria-hidden="true"><rect x="2.5" y="1.5" width="3.2" height="11" rx="1" fill="#050508"/><rect x="8.3" y="1.5" width="3.2" height="11" rx="1" fill="#050508"/></svg>';

  function _mmss(t) {
    t = Math.max(0, Math.floor(t || 0));
    return Math.floor(t / 60) + ':' + ('0' + (t % 60)).slice(-2);
  }

  function _wirePlayer() {
    var a = document.getElementById('o-audio');
    var btn = document.getElementById('o-wplay');
    var bar = document.getElementById('o-wbar');
    var fill = document.getElementById('o-wfill');
    var time = document.getElementById('o-wtime');
    if (!a || !btn) return;
    function maj() {
      var dur = a.duration || 0;
      var pct = dur ? (a.currentTime / dur) * 100 : 0;
      fill.style.width = pct + '%';
      bar.setAttribute('aria-valuenow', String(Math.round(pct)));
      time.textContent = dur ? _mmss(a.currentTime) + ' / ' + _mmss(dur) : (a.paused ? 'Écouter' : '…');
    }
    btn.addEventListener('click', function () {
      if (a.paused) {
        var p = a.play();
        if (p && p.catch) p.catch(function () { _toast('Lecture impossible pour le moment.', 'error'); });
      } else { a.pause(); }
    });
    a.addEventListener('play', function () { btn.innerHTML = _ICON_PAUSE; btn.setAttribute('aria-label', 'Mettre en pause'); maj(); });
    a.addEventListener('pause', function () { btn.innerHTML = _ICON_PLAY; btn.setAttribute('aria-label', 'Écouter le son'); maj(); });
    a.addEventListener('timeupdate', maj);
    a.addEventListener('loadedmetadata', maj);
    a.addEventListener('ended', function () { a.currentTime = 0; maj(); });
    function chercher(pct) { if (a.duration) { a.currentTime = Math.min(1, Math.max(0, pct)) * a.duration; maj(); } }
    bar.addEventListener('click', function (ev) {
      var r = bar.getBoundingClientRect();
      chercher((ev.clientX - r.left) / r.width);
    });
    bar.addEventListener('keydown', function (ev) {
      if (!a.duration) return;
      if (ev.key === 'ArrowRight') { a.currentTime = Math.min(a.duration, a.currentTime + 5); ev.preventDefault(); }
      if (ev.key === 'ArrowLeft') { a.currentTime = Math.max(0, a.currentTime - 5); ev.preventDefault(); }
    });
  }

  // Lot M — aperçu de la recette : outils et longueur, jamais le texte.
  function _renderRecette(d) {
    var box = document.getElementById('o-recette');
    if (!box) return;
    var snd = d.sound || {}, img = d.image || {};
    var chips = [];
    var outilSon = snd.platform ? (_OUTILS[snd.platform] || snd.platform) : '';
    var outilImg = img.platform ? (_OUTILS[img.platform] || img.platform) : '';
    if (outilSon) chips.push('<span class="o-chip o-chip--son">Son · ' + _esc(_provenance(snd.platform, snd.modelVersion).replace(/^Fait avec /, '')) + '</span>');
    if (outilImg) chips.push('<span class="o-chip o-chip--image">Image · ' + _esc(_provenance(img.platform, img.modelVersion).replace(/^Fait avec /, '')) + '</span>');
    var longueurs = [];
    var ls = snd.recipe && snd.recipe.promptLength;
    if (ls) longueurs.push('prompt du son : ' + ls + ' caractères');
    if (img.promptLength) longueurs.push('prompt de l\'image : ' + img.promptLength + ' caractères');
    if (!chips.length && !longueurs.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML =
      '<div class="o-recette-head"><p class="o-recette-kicker">APERÇU DE LA RECETTE</p>' +
      '<p class="o-recette-sub">En entier après déblocage</p></div>' +
      (chips.length ? '<div class="o-chips">' + chips.join('') + '</div>' : '') +
      '<p class="o-lock"><svg width="14" height="16" viewBox="0 0 14 16" aria-hidden="true"><rect x="1.5" y="7" width="11" height="8" rx="2" fill="none" stroke="#ffd700" stroke-width="1.6"/><path d="M4 7V5a3 3 0 0 1 6 0v2" fill="none" stroke="#ffd700" stroke-width="1.6"/></svg>' +
      _esc(longueurs.length ? longueurs.join(' · ') : 'Prompt complet et réglages') + '</p>';
  }

  // Lot M — téléphone : barre d'achat collée en bas tant que l'offre
  // principale n'est pas à l'écran.
  var _stickyObs = null;
  function _renderSticky(d) {
    var bar = document.getElementById('o-stickybar');
    var box = document.getElementById('o-bundle');
    if (!bar || !box) return;
    if (_stickyObs) { _stickyObs.disconnect(); _stickyObs = null; }
    var b = d.bundle;
    var vendable = !d.masquee && b && b.priceCredits != null && (b.mode === 'oeuvre' || b.mode === 'moitie_manquante');
    if (!vendable) { bar.hidden = true; bar.innerHTML = ''; document.body.classList.remove('o-has-sticky'); return; }
    var alt = [];
    if (b.mode === 'oeuvre') {
      if (d.sound && d.sound.recipe) alt.push('<button type="button" data-o-buy="son">Le son seul · ' + _esc(d.sound.recipe.priceCredits) + '</button>');
      if (d.image && d.image.priceCredits != null) alt.push('<button type="button" data-o-buy="image">L\'image seule · ' + _esc(d.image.priceCredits) + '</button>');
    }
    bar.innerHTML = '<button type="button" class="o-btn o-btn--bundle" data-o-buy="bundle">' +
      (b.mode === 'moitie_manquante' ? 'Compléter l\'œuvre · ' : 'Acheter l\'œuvre · ') + _esc(b.priceCredits) + ' Smyles</button>' +
      (alt.length ? '<div class="o-stickybar-alt">' + alt.join('') + '</div>' : '');
    bar.hidden = false;
    document.body.classList.add('o-has-sticky');
    if ('IntersectionObserver' in window) {
      _stickyObs = new IntersectionObserver(function (e) {
        bar.classList.toggle('is-on', !e[0].isIntersecting);
      });
      _stickyObs.observe(box);
    } else {
      bar.classList.add('is-on');
    }
  }

  function _render(d) {
    _data = d;
    var creator = d.creator || {};
    var title = d.title || 'Œuvre';
    document.title = title + ' · WATT';
    document.getElementById('o-title').textContent = title;

    var by = document.getElementById('o-by');
    if (creator.slug) {
      by.innerHTML = 'par <a href="/u/' + encodeURIComponent(creator.slug) + '">' +
        _esc(creator.name || creator.slug) + '</a>';
    } else {
      by.textContent = creator.name ? ('par ' + creator.name) : '';
    }
    // Lot M — preuve sociale discrète : le nombre d'écoutes.
    var _plays = (d.sound && d.sound.plays) || 0;
    if (_plays > 0) {
      by.insertAdjacentHTML('beforeend', '<span class="o-by-stat"> · ' + _esc(_plays) +
        (_plays > 1 ? ' écoutes' : ' écoute') + '</span>');
    }

    var img = d.image || {};
    var url = _previewUrl(img.previewKey);
    document.getElementById('o-visual').innerHTML = url
      ? '<img src="' + _esc(url) + '" alt="' + _esc(img.title || title) + '" />'
      : '<span class="o-visual-ph" aria-hidden="true">🖼</span>';

    var snd = d.sound || {};
    var player = document.getElementById('o-player');
    // Lot M — lecteur aux couleurs WATT (le lecteur gris du navigateur
    // reste dans la page, caché, et fait le travail).
    player.innerHTML = snd.streamUrl
      ? '<div class="o-wplayer">' +
          '<button type="button" class="o-wplay" id="o-wplay" aria-label="Écouter le son">' + _ICON_PLAY + '</button>' +
          '<div class="o-wbar" id="o-wbar" role="slider" aria-label="Position dans le son" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" tabindex="0"><span id="o-wfill"></span></div>' +
          '<span class="o-wtime" id="o-wtime">Écouter</span>' +
        '</div>' +
        '<audio id="o-audio" preload="none" src="' + _esc(snd.streamUrl) + '" hidden></audio>'
      : '<p class="o-player-empty">L\'écoute de ce son n\'est pas disponible pour le moment.</p>';
    _wirePlayer();
    _renderRecette(d);

    // Moitié SON
    var sonThumb = snd.coverUrl
      ? '<img src="' + _esc(snd.coverUrl) + '" alt="" />'
      : '<span aria-hidden="true">🎵</span>';
    var sonAction = snd.recipe
      ? '<button type="button" class="o-btn" data-o-buy="son">Débloquer · ' +
        _esc(snd.recipe.priceCredits) + ' Smyles</button>'
      : '';
    document.getElementById('o-half-son').innerHTML =
      '<div class="o-half-thumb">' + sonThumb + '</div>' +
      '<div class="o-half-body"><p class="o-half-kind o-half-kind--son">Le son</p>' +
      '<p class="o-half-title">' + _esc(snd.title || title) + '</p>' +
      '<p class="o-half-note">' + (snd.recipe ? 'Recette + fichier' : 'En écoute libre') + '</p>' +
      (_provenance(snd.platform, snd.modelVersion)
        ? '<p class="o-half-note o-half-prov">' + _esc(_provenance(snd.platform, snd.modelVersion)) + '</p>' : '') +
      '</div>' +
      sonAction;

    // Moitié IMAGE
    document.getElementById('o-half-image').innerHTML =
      '<div class="o-half-thumb">' + (url ? '<img src="' + _esc(url) + '" alt="" />' : '<span aria-hidden="true">🖼</span>') + '</div>' +
      '<div class="o-half-body"><p class="o-half-kind o-half-kind--image">L\'image</p>' +
      '<p class="o-half-title">' + _esc(img.title || title) + '</p>' +
      '<p class="o-half-note">Recette + image originale</p>' +
      (_provenance(img.platform, img.modelVersion)
        ? '<p class="o-half-note o-half-prov">' + _esc(_provenance(img.platform, img.modelVersion)) + '</p>' : '') +
      '</div>' +
      (img.priceCredits != null
        ? '<button type="button" class="o-btn" data-o-buy="image">Débloquer · ' + _esc(img.priceCredits) + ' Smyles</button>'
        : '');

    // Achat de l'Œuvre entière (Lot 3) : son + image, remise 0/10/20 % (créateur).
    var bundle = document.getElementById('o-bundle');
    var b = d.bundle;
    var repSon = document.getElementById('o-report-son');
    if (repSon) repSon.hidden = !(snd && snd.trackId);
    if (d.masquee) {
      // Parcours V1 : Œuvre masquée par son créateur — visible ici seulement
      // par lui et ceux qui l'ont achetée.
      bundle.hidden = false;
      bundle.innerHTML = '<p class="o-bundle-note">Cette œuvre est masquée : seuls son créateur et ceux qui l\'ont achetée la voient.</p>';
      document.querySelectorAll('[data-o-buy]').forEach(function (n) { n.remove(); });
    } else if (b && b.mode === 'createur') {
      // C'est l'Œuvre de la personne connectée : rien à acheter. On lui montre
      // l'offre exactement comme ses visiteurs la voient.
      document.querySelectorAll('[data-o-buy]').forEach(function (n) { n.remove(); });
      bundle.hidden = false;
      bundle.innerHTML =
        (b.discountPct > 0 ? '<p class="o-bundle-tag">★ Meilleure offre</p>' : '') +
        '<button type="button" class="o-btn o-btn--bundle" disabled>Acheter l\'œuvre · ' + _esc(b.publicPriceCredits) + ' Smyles</button>' +
        '<p class="o-bundle-note">C\'est ton œuvre : voici l\'offre que voient tes visiteurs. ' + _detailOffre(b.fullPriceCredits, b.publicPriceCredits, b.discountPct) +
        ' Change la remise (0, 10 ou 20 %) depuis <a href="/mes-oeuvres">Mes Œuvres</a>.</p>';
    } else if (b && b.mode === 'possedee') {
      bundle.hidden = false;
      bundle.innerHTML = '<p class="o-bundle-note">Tu possèdes cette œuvre — retrouve-la dans ta bibliothèque.</p>';
    } else if (b && b.priceCredits != null) {
      var label = b.mode === 'moitie_manquante'
        ? 'Compléter l\'œuvre · ' + _esc(b.priceCredits) + ' Smyles'
        : 'Acheter l\'œuvre · ' + _esc(b.priceCredits) + ' Smyles';
      var detail = (b.mode === 'oeuvre' && b.fullPriceCredits != null)
        ? '<p class="o-bundle-note">' + _detailOffre(b.fullPriceCredits, b.priceCredits, b.discountPct) + '</p>'
        : '<p class="o-bundle-note">Tu as déjà une moitié : l\'autre est au prix normal.</p>';
      bundle.hidden = false;
      // Lot M — « Ce que tu reçois », en trois lignes, sous l'offre.
      var recois = b.mode === 'oeuvre'
        ? '<ul class="o-recois" aria-label="Ce que tu reçois">' +
            '<li>Le son en entier, à télécharger</li>' +
            '<li>L\'image originale en haute qualité</li>' +
            '<li>Les deux recettes, pour toujours dans ta bibliothèque</li>' +
          '</ul>'
        : '';
      bundle.innerHTML = (b.mode === 'oeuvre' && b.discountPct > 0 ? '<p class="o-bundle-tag">★ Meilleure offre</p>' : '') +
        '<button type="button" class="o-btn o-btn--bundle" data-o-buy="bundle">' + label + '</button>' + detail + recois;
    } else {
      bundle.hidden = true;
      bundle.innerHTML = '';
    }
    _show('o-content');
    _renderSticky(d);
    // Arrivée depuis « Acheter l'œuvre » d'une fiche : on amène l'offre à l'écran.
    if (window.location.hash === '#offre' && !bundle.hidden) {
      try { bundle.scrollIntoView({ block: 'center' }); } catch (_) {}
    }
  }

  function _wire() {
    document.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-o-buy]');
      if (b) {
        var k = b.getAttribute('data-o-buy');
        if (k === 'son' || k === 'image') _buy(k);
        if (k === 'bundle') _buyBundle(b);
        return;
      }
      if (ev.target.closest('#o-report')) {
        if (window.ReportModal && _data) window.ReportModal.open({ targetType: 'image', targetId: _data.image.id, title: _data.image.title });
        return;
      }
      // Parcours V1 : le son de l'Œuvre est signalable lui aussi.
      if (ev.target.closest('#o-report-son')) {
        if (window.ReportModal && _data && _data.sound && _data.sound.trackId) {
          window.ReportModal.open({ targetType: 'track', targetId: _data.sound.trackId, title: _data.sound.title });
        }
        return;
      }
      if (ev.target.closest('#o-share')) {
        // Lot K — le créateur partage SON lien (avec son code) : les personnes
        // qu'il amène lui sont attribuées et sa commission tombe à 10 %.
        var _lp = _data && _data.bundle && _data.bundle.mode === 'createur' && _data.bundle.lienPartage;
        var link = window.location.origin + (_lp || ('/o/' + (OID || '')));
        var done = function () { _toast('Lien copié — colle-le où tu veux.', 'success'); };
        try {
          if (navigator.share) {
            navigator.share({ title: document.title, url: link }).catch(function () {});
            return;
          }
          navigator.clipboard.writeText(link).then(done, function () { window.prompt('Copie ce lien :', link); });
        } catch (_) { window.prompt('Copie ce lien :', link); }
        try { if (window.SmyleTrack) window.SmyleTrack.event('share_click', { oeuvre: OID }); } catch (_) {}
      }
    });
  }

  function load() {
    if (!OID || !window.apiFetch) { _show('o-empty'); return; }
    // Jeton joint s'il existe : le prix de l'Œuvre est calculé pour l'acheteur.
    window.apiFetch('/watt/oeuvres/' + encodeURIComponent(OID))
      .then(function (d) {
        if (!d || !d.image) { _show('o-empty'); return; }
        _render(d);
      })
      .catch(function (err) {
        _show('o-empty');
        var s = err && err.status;
        if (s && s !== 404) _toast('Chargement impossible pour le moment — réessaie.', 'error');
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    _wire();
    load();
  });
})();
