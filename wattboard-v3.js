/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — wattboard-v3.js
   Chantier C1 (blueprint VF 2026-06-10) — WattBoard v3.

   Le board devient la HOME du /dashboard :
     1. bandeau identité (avatar · nom · pilules palier/officiel/rang ·
        stats écoutes/abonnés/Smyles · accès édition identité)
     2. bascule 2 mondes 🎧 Audio / 🎨 Visuel + bouton "+ Créer" contextuel
     3. tuiles de contenu à compteurs réels (Sons IA · Beats · ADN · Voix —
        monde Visuel : Images C4 actif · ADN visuel "Bientôt")
     4. rangée transversale (Playlists · Échanges · Trophées · Analytique)

   Les 7 accordéons existants ne sont PAS supprimés : ils deviennent des
   écrans dédiés, ouverts un par un via les tuiles (classe .wb3-open),
   avec une barre "← Retour au WATT BOARD". Tout le JS legacy
   (dashboard.js, ui/playlists.js, messaging…) continue de fonctionner :
   on ne touche qu'à la VISIBILITÉ des sections, jamais à leur contenu.

   Dépendances globales (déjà chargées avant ce script defer) :
     apiFetch (ui/core/api.js) · SpBadges (ui/core/badges.js) ·
     getCurrentUser / getWattProfile / fetchRealRanking / setUploadMode /
     _isOfficialAccount (dashboard.js).
   ───────────────────────────────────────────────────────────────────────── */

(function initWattBoardV3() {
  'use strict';
  if (typeof window === 'undefined') return;

  /* ── Écrans dédiés : tuile/bouton → section(s) legacy à afficher ────── */
  var SCREENS = {
    identity:  { ids: ['sec-identity'],              label: 'Identité' },
    sons:      { ids: ['sec-upload'],                label: 'Mes sons' },
    adn:       { ids: ['sec-dna'],                   label: 'ADN musical' },
    voix:      { ids: ['sec-voice-sale'],            label: 'Voix' },
    playlists: { ids: ['sec-playlists'],             label: 'Playlists' },
    trades:    { ids: ['sec-trades'],                label: 'Échanges' },
    stats:     { ids: ['sec-stats', 'sec-ranking'],  label: 'Analytique' },
    trophees:  { ids: ['sec-trophees'],              label: 'Trophées' },
    images:    { ids: ['sec-image-create'],          label: 'Créer une image' },
    // C4 ③ — écran « Mes images » (grille de cards-aperçu owner). Section
    // injectée par images-list.js si absente du HTML.
    'images-list': { ids: ['sec-image-list'],        label: 'Mes images' },
    // C4 ADN Album — écran dédié « Créer un ADN visuel » (génome de style d'UN
    // album, parallèle de l'ADN Playlist). Logique : module window.AdnVisuel.
    'adn-album':   { ids: ['sec-adn-visuel'],        label: 'ADN Album' },
    // C4 ADN Visuel artiste — signature visuelle vendable (1/artiste), mirror
    // EXACT de l'ADN musical #sec-dna. Logique : loadMyVisualAdn (dashboard.js).
    'visual-adn':  { ids: ['sec-visual-adn'],        label: 'ADN Visuel' },
  };

  /* Compteurs (cache local au module, rafraîchi au retour board) */
  var counts = { sons: null, adn: null, voix: null, images: null };
  var hero   = { plays: null, followers: null, rank: null, smyles: null };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function fmt(v) { return (v == null) ? '—' : String(v); }

  /* ── Navigation board ⇆ écrans ──────────────────────────────────────── */

  function openScreen(key) {
    var sc = SCREENS[key];
    if (!sc) return;
    document.querySelectorAll('.dash-section.wb3-open').forEach(function (s) {
      s.classList.remove('wb3-open');
    });
    sc.ids.forEach(function (id) {
      var el = $(id);
      if (!el) return;
      el.classList.add('wb3-open');
      // Les sections legacy démarrent repliées (accordéons) : un écran
      // dédié s'ouvre DÉPLIÉ. L'utilisateur peut toujours replier au clic.
      el.classList.remove('is-collapsed', 'is-collapsed-sub');
      var det = el.querySelector('details');
      if (det) det.open = true;
    });
    document.body.classList.add('wb3-screen-open');
    var lbl = $('wb3-back-label');
    if (lbl) lbl.textContent = sc.label;
    // C4 ADN Album — l'écran « Créer un ADN visuel » (re)peuple son sélecteur
    // d'albums à chaque ouverture (reflète les albums/ADN créés depuis).
    if (key === 'adn-album') {
      try { if (window.AdnVisuel && typeof window.AdnVisuel.init === 'function') window.AdnVisuel.init(); } catch (_) {}
    }
    // C4 ADN Visuel artiste — l'écran « Mon ADN Visuel » (re)charge l'ADN
    // existant pour pré-remplir (empty/summary/editor), mirror de l'ADN musical.
    if (key === 'visual-adn') {
      try { if (typeof window.loadMyVisualAdn === 'function') window.loadMyVisualAdn(); } catch (_) {}
    }
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }

  function backToBoard() {
    document.querySelectorAll('.dash-section.wb3-open').forEach(function (s) {
      s.classList.remove('wb3-open');
    });
    document.body.classList.remove('wb3-screen-open');
    closeCreateMenu();
    window.scrollTo({ top: 0 });
    refreshCounts();   // les compteurs reflètent ce qui vient d'être créé
    refreshHeroStats();
  }

  /* FUSION 2026-06-10 : plus de contexte beats — la cellule Sons IA expose
     les 4 destinations (musique avec recette · partage · beat · beat+pack).
     Le mode est LE choix structurant : il détermine ce qui est vendu et le
     positionnement marketplace (un beat ira sur /beats en C2). */
  // C1.4 — 2 destinations : Musique (with_prompt) · Beat (pack = recette
  // + fichier, un seul prix). Partage simple et beat-fichier-seul supprimés.
  var CREATE_MAP = {
    son:  'with_prompt',
    beat: 'pack',
  };
  function createAction(kind) {
    closeCreateMenu();
    if (kind === 'image') {
      openScreen('images');
      // Le formulaire image gère son propre reset à l'ouverture (idempotent).
      try { if (window.ImageCreate && typeof window.ImageCreate.focus === 'function') window.ImageCreate.focus(); } catch (_) {}
      return;
    }
    if (kind === 'adn')  { openScreen('adn');  return; }
    // C4 — « ADN visuel » du monde Visuel = la SIGNATURE VISUELLE artiste
    // (mirror de l'ADN musical), écran #sec-visual-adn.
    if (kind === 'adn-visuel') { openScreen('visual-adn'); return; }
    // C4 — ADN Album (génome de style d'un album) garde son écran dédié.
    if (kind === 'adn-album')  { openScreen('adn-album'); return; }
    if (kind === 'voix') { openScreen('voix'); return; }
    openScreen('sons');
    try { if (typeof setUploadMode === 'function') setUploadMode(CREATE_MAP[kind] || 'with_prompt'); } catch (_) {}
    // Amène directement la dropzone à l'écran (zone 1b de la section).
    var dz = $('dashDropzone');
    if (dz) { try { dz.scrollIntoView({ block: 'center' }); } catch (_) {} }
  }

  /* "Voir" sur la tuile Sons : déplie le catalogue (wrapper 1a replié). */
  function viewSons() {
    openScreen('sons');
    var hdr1a = document.querySelector('#sec-upload .is-1a-collapsed');
    if (hdr1a) { try { hdr1a.click(); } catch (_) {} }
  }

  /* C1.1 — Analytique : le bloc "2a · Mes Sons Publiés" prenait tout
     l'écran (retour QA Tom). On le rend pliable, PLIÉ par défaut, sur le
     modèle du wrapper 1a de la section Création. */
  function makeStatsTracksCollapsible() {
    var stats = $('sec-stats');
    if (!stats) return;
    var sub = stats.querySelector('.dash-subhdr');   // 1er subhdr = 2a
    if (!sub || sub.dataset.wb3Collapsible) return;
    sub.dataset.wb3Collapsible = '1';

    var toMove = [];
    var n = sub.nextElementSibling;
    while (n && !n.classList.contains('dash-subhdr')) {
      toMove.push(n);
      n = n.nextElementSibling;
    }
    if (!toMove.length) return;
    var wrap = document.createElement('div');
    toMove.forEach(function (el) { wrap.appendChild(el); });
    stats.insertBefore(wrap, n);   // n = subhdr 2b (ou null → fin)

    wrap.style.display = 'none';
    sub.classList.add('is-1a-collapsed');   // réutilise le chevron existant
    sub.style.cursor = 'pointer';
    sub.addEventListener('click', function (e) {
      if (e.target.closest && e.target.closest('button, a, input, select, textarea')) return;
      var hidden = wrap.style.display === 'none';
      wrap.style.display = hidden ? '' : 'none';
      sub.classList.toggle('is-1a-collapsed', !hidden);
    });
  }

  /* ── Bandeau identité ───────────────────────────────────────────────── */

  function heroName() {
    var profile = null, user = null;
    try { profile = (typeof getWattProfile === 'function') ? getWattProfile() : null; } catch (_) {}
    try { user = (typeof getCurrentUser === 'function') ? getCurrentUser() : null; } catch (_) {}
    return (profile && profile.artistName)
        || (user && user.artist_name)
        || (user && user.name)
        || (user && String(user.email || '').split('@')[0])
        || 'Artiste';
  }

  function heroAvatarHtml() {
    var profile = null;
    try { profile = (typeof getWattProfile === 'function') ? getWattProfile() : null; } catch (_) {}
    if (profile && profile.avatarUrl) {
      return '<img src="' + esc(profile.avatarUrl) + '" alt="" loading="lazy" />';
    }
    return esc(heroName().charAt(0).toUpperCase());
  }

  function heroPillsHtml(user) {
    var pills = [];
    var B = window.SpBadges;
    // Palier — la couche entitlements arrive en C6 ; d'ici là tout le monde
    // est affiché Free (source : users.tier quand il existera).
    var tier = (user && user.tier) || 'free';
    if (B && B.palier) pills.push(B.palier(tier));
    var isOfficial = false;
    try { isOfficial = (typeof _isOfficialAccount === 'function') && _isOfficialAccount(); } catch (_) {}
    if (isOfficial) pills.push('<span class="sp-pill sp-pill--palier-mythique" title="Compte officiel Smyle">⚡ Officiel</span>');
    pills.push('<span class="sp-pill" id="wb3-pill-rank" title="Position au classement WATT">Rang —</span>');
    return pills.join(' ');
  }

  /* ── Tuiles par monde ───────────────────────────────────────────────── */

  function tileHtml(key, icon, name, countKey, opts) {
    opts = opts || {};
    if (opts.locked) {
      return '' +
        '<div class="wb3-tile is-locked" data-tile="' + key + '">' +
          '<div class="wb3-tile-head">' +
            '<span class="wb3-tile-ico">' + icon + '</span>' +
            '<span class="wb3-tile-name">' + esc(name) + '</span>' +
          '</div>' +
          '<div class="wb3-tile-count"><span class="wb3-tile-lock">' + esc(opts.lockLabel) + '</span></div>' +
          '<div class="wb3-tile-actions">' +
            '<button type="button" class="wb3-tile-btn" disabled>Bientôt</button>' +
          '</div>' +
        '</div>';
    }
    // Tuile « view-only » (ex. ADN visuel) : pas de bouton « Créer » dédié, un
    // libellé de compteur statique, et un seul bouton d'action « Gérer ».
    if (opts.viewOnly) {
      return '' +
        '<div class="wb3-tile" data-tile="' + key + '">' +
          '<div class="wb3-tile-head">' +
            '<span class="wb3-tile-ico">' + icon + '</span>' +
            '<span class="wb3-tile-name">' + esc(name) + '</span>' +
          '</div>' +
          '<div class="wb3-tile-count"><span class="wb3-count-lbl">' + esc(opts.countLabel || '') + '</span></div>' +
          '<div class="wb3-tile-actions">' +
            '<button type="button" class="wb3-tile-btn wb3-tile-btn--primary" data-wb3-view="' + esc(opts.viewKey) + '">' + esc(opts.countText || 'Voir') + '</button>' +
          '</div>' +
        '</div>';
    }
    return '' +
      '<div class="wb3-tile" data-tile="' + key + '">' +
        '<div class="wb3-tile-head">' +
          '<span class="wb3-tile-ico">' + icon + '</span>' +
          '<span class="wb3-tile-name">' + esc(name) + '</span>' +
        '</div>' +
        '<div class="wb3-tile-count"><span id="wb3-count-' + countKey + '">' + fmt(counts[countKey]) + '</span>' +
          '<span class="wb3-count-lbl">' + esc(opts.countLabel || 'publiés') + '</span></div>' +
        '<div class="wb3-tile-actions">' +
          '<button type="button" class="wb3-tile-btn wb3-tile-btn--primary" data-wb3-create="' + esc(opts.createKind) + '">Créer</button>' +
          '<button type="button" class="wb3-tile-btn" data-wb3-view="' + esc(opts.viewKey) + '">Voir</button>' +
        '</div>' +
      '</div>';
  }

  function tilesHtml(monde) {
    if (monde === 'visuel') {
      // Décisions 2026-06-10 : Images + ADN visuel arrivent en C4 (upload
      // + provenance IA obligatoire).
      // C4 livraison ② : la tuile Images IA est débloquée (création image
      // avec provenance IA obligatoire). ADN visuel = V2 ("Bientôt").
      // C4 taxonomie visuelle (2026-06-16) : « FX » n'est PLUS une catégorie /
      // tuile — c'est devenu un TAG d'usage d'image (cf. images-create). La
      // tuile FX verrouillée est donc supprimée.
      // C4 ADN Visuel artiste (2026-06-17) : la tuile « ADN Visuel » ouvre
      // désormais l'écran SIGNATURE VISUELLE artiste (#sec-visual-adn via
      // openScreen('visual-adn')) — mirror EXACT de l'ADN musical. L'ADN ALBUM
      // (génome de style d'un album) garde sa propre tuile « ADN Album » →
      // écran #sec-adn-visuel. Le bouton « + Créer » expose les deux.
      return tileHtml('images',     '🖼️', 'Images IA',  'images', { createKind: 'image', viewKey: 'images-list', countLabel: 'publiées' })
           + tileHtml('adn-visuel', '🎨', 'ADN Visuel', null, { viewKey: 'visual-adn', viewOnly: true, countLabel: 'ta signature visuelle vendable', countText: 'Gérer' })
           + tileHtml('adn-album',  '🎨', 'ADN Album',  null, { viewKey: 'adn-album', viewOnly: true, countLabel: 'génome de style d\'un album', countText: 'Gérer' });
    }
    // DÉCISION 100 % IA (Tom, 2026-06-10) : aucun produit non-IA vendu sur
    // la plateforme. La tuile « Musique perso » (humaine, gated palier) est
    // SUPPRIMÉE — le Réel reste de la promo externe uniquement (pont C7).
    //
    // FUSION BEATS → SONS IA (Tom, même soir) : un beat IA n'est pas une
    // nature différente d'un son IA, c'est une DESTINATION de vente
    // (un artiste crée dessus vs on écoute le morceau). Le choix se fait
    // dans la création Sons IA (4 types) ; la tuile Beats disparaît.
    // Côté acheteurs, /beats (C2) listera les sons vendus en tant que beats.
    return tileHtml('sons',  '🤖', 'Sons IA',     'sons',  { createKind: 'son',  viewKey: 'sons',  countLabel: 'publiés' })
         + tileHtml('adn',   '🧬', 'ADN musical', 'adn',   { createKind: 'adn',  viewKey: 'adn',   countLabel: 'signature' })
         + tileHtml('voix',  '🎙️', 'Voix',        'voix',  { createKind: 'voix', viewKey: 'voix',  countLabel: 'au catalogue' });
  }

  /* ── Menu "+ Créer" ─────────────────────────────────────────────────── */

  function createMenuHtml(monde) {
    if (monde === 'visuel') {
      // C4 livraison ② : monde Visuel ouvert à la création d'image.
      // C4 ADN Visuel artiste : « ADN visuel » = signature visuelle artiste
      // (écran #sec-visual-adn). « ADN Album » = génome de style d'un album
      // (écran #sec-adn-visuel) — les deux restent accessibles.
      return '' +
        '<button type="button" class="wb3-create-item" data-wb3-create="image">🖼️ <span>Image<em>Visuel IA — l\'achat débloque la recette (prompt + réglages) + le fichier original</em></span></button>' +
        '<button type="button" class="wb3-create-item" data-wb3-create="adn-visuel">🎨 <span>ADN visuel<em>Ta signature visuelle vendable — l\'achat débloque le génome de style</em></span></button>' +
        '<button type="button" class="wb3-create-item" data-wb3-create="adn-album">🎨 <span>ADN Album<em>Le génome de style d\'un album — l\'achat débloque la recette de style</em></span></button>';
    }
    return '' +
      '<button type="button" class="wb3-create-item" data-wb3-create="son">🎵 <span>Musique<em>On écoute le morceau — l\'achat débloque recette + fichier</em></span></button>' +
      '<button type="button" class="wb3-create-item" data-wb3-create="beat">🥁 <span>Beat<em>Un artiste crée dessus — l\'achat débloque fichier + recette</em></span></button>' +
      '<button type="button" class="wb3-create-item" data-wb3-create="adn">🧬 <span>ADN musical<em>Ta signature créative vendable</em></span></button>' +
      '<button type="button" class="wb3-create-item" data-wb3-create="voix">🎙️ <span>Voix<em>Sample 30 s public, fichier complet gaté</em></span></button>';
  }

  function closeCreateMenu() {
    var m = $('wb3-create-menu');
    if (m) m.classList.remove('is-open');
  }

  /* ── Rendu du board ─────────────────────────────────────────────────── */

  function render() {
    var board = $('wb3-board');
    if (!board) return;
    var monde = board.getAttribute('data-monde') || 'audio';
    var user = null;
    try { user = (typeof getCurrentUser === 'function') ? getCurrentUser() : null; } catch (_) {}

    board.innerHTML =
      /* 1. bandeau identité */
      '<div class="wb3-hero">' +
        '<div class="wb3-hero-avatar" id="wb3-avatar">' + heroAvatarHtml() + '</div>' +
        '<div class="wb3-hero-id">' +
          '<h1 class="wb3-hero-name" id="wb3-name">' + esc(heroName()) + '</h1>' +
          '<div class="wb3-hero-pills" id="wb3-pills">' + heroPillsHtml(user) + '</div>' +
        '</div>' +
        '<div class="wb3-hero-stats">' +
          '<div class="wb3-stat"><div class="wb3-stat-val" id="wb3-stat-plays">' + fmt(hero.plays) + '</div><div class="wb3-stat-lbl">Écoutes</div></div>' +
          '<div class="wb3-stat"><div class="wb3-stat-val" id="wb3-stat-followers">' + fmt(hero.followers) + '</div><div class="wb3-stat-lbl">Abonnés</div></div>' +
          '<div class="wb3-stat"><div class="wb3-stat-val" id="wb3-stat-smyles">' + fmt(hero.smyles) + '</div><div class="wb3-stat-lbl">Smyles</div></div>' +
        '</div>' +
        '<button type="button" class="wb3-hero-edit" data-wb3-view="identity">✏️ Mon identité</button>' +
      '</div>' +

      /* 2. bascule mondes + créer */
      '<div class="wb3-mondes-row">' +
        '<div class="wb3-monde-switch" role="tablist" aria-label="Monde">' +
          '<button type="button" class="wb3-monde-btn' + (monde === 'audio'  ? ' is-active' : '') + '" data-monde="audio"  role="tab" aria-selected="' + (monde === 'audio') + '">🎧 Audio</button>' +
          '<button type="button" class="wb3-monde-btn' + (monde === 'visuel' ? ' is-active' : '') + '" data-monde="visuel" role="tab" aria-selected="' + (monde === 'visuel') + '">🎨 Visuel</button>' +
        '</div>' +
        '<div class="wb3-create-wrap">' +
          '<button type="button" class="wb3-create-btn" id="wb3-create-btn">+ Créer</button>' +
          '<div class="wb3-create-menu" id="wb3-create-menu" role="menu">' + createMenuHtml(monde) + '</div>' +
        '</div>' +
      '</div>' +

      /* 3. tuiles de contenu */
      '<div class="wb3-tiles">' + tilesHtml(monde) + '</div>' +

      /* 4. rangée transversale (+ lien Bibliothèque — fix 2026-06-11 :
            la collection n'était pas accessible depuis le board) */
      '<div class="wb3-cross">' +
        (monde === 'visuel'
          ? '<button type="button" class="wb3-cross-btn" data-wb3-view="albums">🖼️ Albums</button>'
          : '<button type="button" class="wb3-cross-btn" data-wb3-view="playlists">📚 Playlists</button>') +
        '<button type="button" class="wb3-cross-btn" data-wb3-view="trades">🔄 Échanges</button>' +
        '<button type="button" class="wb3-cross-btn" data-wb3-view="trophees">🏆 Trophées</button>' +
        '<button type="button" class="wb3-cross-btn" data-wb3-view="stats">📈 Analytique</button>' +
        '<a class="wb3-cross-btn" href="/library" style="text-decoration:none;">📦 Bibliothèque</a>' +
      '</div>';
  }

  /* ── Données : compteurs + stats bandeau ────────────────────────────── */

  function setCount(key, val) {
    counts[key] = val;
    var el = $('wb3-count-' + key);
    if (el) el.textContent = fmt(val);
  }

  function refreshCounts() {
    if (typeof apiFetch !== 'function') return;

    apiFetch('/tracks/me')
      .then(function (tracks) { setCount('sons', Array.isArray(tracks) ? tracks.length : 0); })
      .catch(function () { setCount('sons', counts.sons); });

    apiFetch('/artist/me/adn')
      .then(function () { setCount('adn', 1); })
      .catch(function (e) { setCount('adn', (e && e.status === 404) ? 0 : counts.adn); });

    apiFetch('/api/voices/me')
      .then(function (voices) { setCount('voix', Array.isArray(voices) ? voices.length : 0); })
      .catch(function () { setCount('voix', counts.voix); });

    // C4 ③ — compteur réel des images (remplace bumpImages placeholder).
    // L'endpoint renvoie {count, published} ; la tuile affiche le total
    // (publiées + brouillons) avec le libellé « publiées » défini sur la tuile.
    apiFetch('/artist/me/images/count')
      .then(function (r) { setCount('images', (r && typeof r.count === 'number') ? r.count : 0); })
      .catch(function () { setCount('images', counts.images); });
  }

  function refreshHeroStats() {
    if (typeof apiFetch === 'function') {
      apiFetch('/users/me')
        .then(function (me) {
          hero.smyles = (me && typeof me.credits_balance === 'number') ? me.credits_balance : null;
          var el = $('wb3-stat-smyles');
          if (el) el.textContent = fmt(hero.smyles);
        })
        .catch(function () {});
    }
    if (typeof fetchRealRanking === 'function') {
      fetchRealRanking()
        .then(function (ranking) {
          var idx = -1;
          (ranking || []).forEach(function (a, i) { if (a && a.isMe && idx === -1) idx = i; });
          var mine = idx >= 0 ? ranking[idx] : null;
          hero.plays     = mine ? (mine.plays     || 0) : 0;
          hero.followers = mine ? (mine.followers || 0) : 0;
          hero.rank      = idx >= 0 ? (idx + 1) : null;
          var p = $('wb3-stat-plays');     if (p) p.textContent = fmt(hero.plays);
          var f = $('wb3-stat-followers'); if (f) f.textContent = fmt(hero.followers);
          var r = $('wb3-pill-rank');      if (r) r.textContent = hero.rank ? ('Rang #' + hero.rank) : 'Rang —';
        })
        .catch(function () {});
    }
  }

  /* ── Délégation d'événements ────────────────────────────────────────── */

  function bind() {
    var board = $('wb3-board');
    if (!board) return;

    board.addEventListener('click', function (ev) {
      var t = ev.target.closest ? ev.target.closest('[data-monde], [data-wb3-view], [data-wb3-create], #wb3-create-btn') : null;
      if (!t) return;

      if (t.id === 'wb3-create-btn') {
        var m = $('wb3-create-menu');
        if (m) m.classList.toggle('is-open');
        return;
      }
      if (t.hasAttribute('data-wb3-create')) { createAction(t.getAttribute('data-wb3-create')); return; }
      if (t.hasAttribute('data-wb3-view')) {
        var key = t.getAttribute('data-wb3-view');
        // C4 — monde Visuel : « Albums » ouvre My Mix forcé en mode image
        // (curation des albums). « ADN visuel » a désormais son ÉCRAN DÉDIÉ
        // (#sec-adn-visuel) : il passe par la branche normale openScreen(key).
        if (key === 'albums') {
          try { localStorage.setItem('mymix_mode', 'image'); } catch (_) {}
          // My Mix vit sur la home (index.html). Si la page courante l'expose
          // (toggleMixPanel), on l'ouvre ; sinon (cas dashboard) on redirige
          // vers / qui le porte — le mode image est déjà persisté ci-dessus.
          if (typeof toggleMixPanel === 'function') {
            toggleMixPanel();
            try { if (window.SmyleAlbums && SmyleAlbums.applyMixMode) SmyleAlbums.applyMixMode('image'); } catch (_) {}
          } else {
            try { localStorage.setItem('mymix_open', '1'); } catch (_) {}
            window.location.href = '/';
          }
          return;
        }
        if (key === 'sons') viewSons(); else openScreen(key);
        return;
      }
      if (t.classList.contains('wb3-monde-btn')) {
        board.setAttribute('data-monde', t.getAttribute('data-monde'));
        render();   // re-render tuiles + bouton créer du monde actif
        return;
      }
    });

    // Fermer le menu "+ Créer" au clic extérieur / Échap
    document.addEventListener('click', function (ev) {
      if (!ev.target.closest || !ev.target.closest('.wb3-create-wrap')) closeCreateMenu();
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') closeCreateMenu();
    });

    var back = $('wb3-back-btn');
    if (back) back.addEventListener('click', backToBoard);

    // Compat ancres legacy : tout lien interne #sec-* (CTA "Créer mon
    // profil", liens d'autres pages…) passe par la navigation v3.
    document.addEventListener('click', function (ev) {
      var a = ev.target.closest ? ev.target.closest('a[href^="#sec-"]') : null;
      if (!a) return;
      var id = a.getAttribute('href').slice(1);
      for (var key in SCREENS) {
        if (SCREENS[key].ids.indexOf(id) !== -1) {
          ev.preventDefault();
          openScreen(key);
          return;
        }
      }
    });
  }

  /* ── Init ───────────────────────────────────────────────────────────── */

  function init() {
    var board = $('wb3-board');
    if (!board) return;

    // L'inline script legacy a regroupé sec-dna et sec-voice-sale DANS
    // sec-upload (UX accordéons, obsolète en v3). On les ressort pour que
    // chaque écran dédié soit affichable seul.
    var main  = $('dashMain');
    var dna   = $('sec-dna');
    var voice = $('sec-voice-sale');
    var upload = $('sec-upload');
    if (main && dna   && dna.parentNode   === upload) main.appendChild(dna);
    if (main && voice && voice.parentNode === upload) main.appendChild(voice);

    // C1.1 — Analytique : "Mes Sons Publiés" plié par défaut.
    makeStatsTracksCollapsible();

    render();
    bind();
    document.body.classList.add('wb3-active');

    refreshCounts();
    refreshHeroStats();

    // Deep-link : /dashboard#sec-dna ouvre directement l'écran ADN.
    var hash = (location.hash || '').slice(1);
    if (hash) {
      for (var key in SCREENS) {
        if (SCREENS[key].ids.indexOf(hash) !== -1) { openScreen(key); break; }
      }
    }
  }

  // ⚠️ Timing (bug C1 corrigé en C1.1) : un script `defer` s'exécute quand
  // readyState vaut DÉJÀ 'interactive', AVANT que l'événement
  // DOMContentLoaded ne soit émis. L'ancien test `readyState === 'loading'`
  // faisait donc tourner init() AVANT les handlers DOMContentLoaded legacy
  // (dashboard.js + inline regroup/collapse) → l'inline re-déplaçait ensuite
  // sec-dna / sec-voice-sale DANS sec-upload, et les écrans ADN / Voix
  // s'ouvraient vides. Règle : init() doit courir APRÈS DOMContentLoaded.
  if (document.readyState === 'complete') {
    init();   // bfcache / injection tardive : tout est déjà passé
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }

  // API publique (debug / autres scripts)
  // bumpImages : appelé par images-create.js après une création réussie.
  // C4 ③ — on incrémente d'abord localement pour un retour immédiat, puis
  // on re-synchronise depuis l'endpoint réel /artist/me/images/count (source
  // de vérité, couvre brouillons + publiées). La liste owner est aussi
  // rafraîchie si elle est montée.
  function bumpImages() {
    var cur = (typeof counts.images === 'number') ? counts.images : 0;
    setCount('images', cur + 1);
    if (typeof apiFetch === 'function') {
      apiFetch('/artist/me/images/count')
        .then(function (r) { if (r && typeof r.count === 'number') setCount('images', r.count); })
        .catch(function () {});
    }
    try { if (window.ImagesList && typeof window.ImagesList.refresh === 'function') window.ImagesList.refresh(); } catch (_) {}
  }
  window.WattBoardV3 = { open: openScreen, back: backToBoard, refresh: refreshCounts, bumpImages: bumpImages };
})();
