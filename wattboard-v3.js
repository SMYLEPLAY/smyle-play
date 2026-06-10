/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — wattboard-v3.js
   Chantier C1 (blueprint VF 2026-06-10) — WattBoard v3.

   Le board devient la HOME du /dashboard :
     1. bandeau identité (avatar · nom · pilules palier/officiel/rang ·
        stats écoutes/abonnés/Smyles · accès édition identité)
     2. bascule 2 mondes 🎧 Audio / 🎨 Visuel + bouton "+ Créer" contextuel
     3. tuiles de contenu à compteurs réels (Sons IA · Beats · ADN · Voix —
        monde Visuel verrouillé : Images C4 · ADN visuel C4 · FX phase 2)
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
  };

  /* Compteurs (cache local au module, rafraîchi au retour board) */
  var counts = { sons: null, beats: null, adn: null, voix: null };
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

  /* C1.1 — contexte de création par CELLULE (décision Tom 2026-06-10) :
     chaque cellule n'expose que SES types de publication, parce que la
     cellule d'origine déterminera le positionnement marketplace du contenu.
       sons  → Avec recette · Simple (sans prompt)
       beats → Beat seul · Recette + beat (pack)
     Le contexte est posé sur dashUploadForm.dataset.context ; les pills
     hors contexte sont masquées en CSS (wattboard-v3.css). */
  function setUploadContext(ctx) {
    var form = $('dashUploadForm');
    if (form) form.dataset.context = ctx;
  }

  /* "Créer" contextuel : positionne contexte + mode du formulaire AVANT
     d'ouvrir l'écran, pour que le choix structurant soit déjà fait. */
  var CREATE_MAP = {
    son:     { ctx: 'sons',  mode: 'with_prompt' },
    partage: { ctx: 'sons',  mode: 'simple' },
    beat:    { ctx: 'beats', mode: 'beat' },
    pack:    { ctx: 'beats', mode: 'pack' },
  };
  function createAction(kind) {
    closeCreateMenu();
    if (kind === 'adn')  { openScreen('adn');  return; }
    if (kind === 'voix') { openScreen('voix'); return; }
    var c = CREATE_MAP[kind] || CREATE_MAP.son;
    setUploadContext(c.ctx);
    openScreen('sons');
    try { if (typeof setUploadMode === 'function') setUploadMode(c.mode); } catch (_) {}
    // Amène directement la dropzone à l'écran (zone 1b de la section).
    var dz = $('dashDropzone');
    if (dz) { try { dz.scrollIntoView({ block: 'center' }); } catch (_) {} }
  }

  /* "Voir" sur les tuiles Sons / Beats : même écran catalogue, mais le
     contexte de création suit la cellule d'où on vient. Déplie le
     catalogue (wrapper 1a replié). */
  function viewSons(ctx) {
    setUploadContext(ctx || 'sons');
    try {
      if (typeof setUploadMode === 'function') {
        setUploadMode(ctx === 'beats' ? 'beat' : 'with_prompt');
      }
    } catch (_) {}
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
      // + provenance IA obligatoire) ; FX = phase 2 du monde Visuel
      // (doublon avec le prompt vendu avec l'image, miroir des Voix).
      return tileHtml('images',     '🖼️', 'Images IA',  null, { locked: true, lockLabel: 'Chantier C4' })
           + tileHtml('adn-visuel', '🎨', 'ADN visuel', null, { locked: true, lockLabel: 'Chantier C4' })
           + tileHtml('fx',         '✨', 'FX',         null, { locked: true, lockLabel: 'Phase 2' });
    }
    // DÉCISION 100 % IA (Tom, 2026-06-10) : aucun produit non-IA vendu sur
    // la plateforme. La tuile « Musique perso » (humaine, gated palier) est
    // SUPPRIMÉE — le Réel reste de la promo externe uniquement (pont C7).
    return tileHtml('sons',  '🤖', 'Sons IA',     'sons',  { createKind: 'son',  viewKey: 'sons',  countLabel: 'publiés' })
         + tileHtml('beats', '🥁', 'Beats IA',    'beats', { createKind: 'beat', viewKey: 'beats', countLabel: 'en vente' })
         + tileHtml('adn',   '🧬', 'ADN musical', 'adn',   { createKind: 'adn',  viewKey: 'adn',   countLabel: 'signature' })
         + tileHtml('voix',  '🎙️', 'Voix',        'voix',  { createKind: 'voix', viewKey: 'voix',  countLabel: 'au catalogue' });
  }

  /* ── Menu "+ Créer" ─────────────────────────────────────────────────── */

  function createMenuHtml(monde) {
    if (monde === 'visuel') return '';
    return '' +
      '<button type="button" class="wb3-create-item" data-wb3-create="son">🤖 <span>Son IA avec recette<em>Le son + son prompt vendable</em></span></button>' +
      '<button type="button" class="wb3-create-item" data-wb3-create="beat">🥁 <span>Beat IA seul<em>Fichier audio + licence lease / vente unique</em></span></button>' +
      '<button type="button" class="wb3-create-item" data-wb3-create="pack">📦 <span>Recette + beat (pack)<em>Les deux, avec un prix pack</em></span></button>' +
      '<button type="button" class="wb3-create-item" data-wb3-create="partage">🎵 <span>Partage simple<em>Juste un son, rien à vendre</em></span></button>' +
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
          '<button type="button" class="wb3-create-btn" id="wb3-create-btn"' + (monde === 'visuel' ? ' disabled title="Le monde Visuel ouvre au chantier C4"' : '') + '>+ Créer</button>' +
          '<div class="wb3-create-menu" id="wb3-create-menu" role="menu">' + createMenuHtml(monde) + '</div>' +
        '</div>' +
      '</div>' +

      /* 3. tuiles de contenu */
      '<div class="wb3-tiles">' + tilesHtml(monde) + '</div>' +

      /* 4. rangée transversale */
      '<div class="wb3-cross">' +
        '<button type="button" class="wb3-cross-btn" data-wb3-view="playlists">📚 Playlists</button>' +
        '<button type="button" class="wb3-cross-btn" data-wb3-view="trades">🔄 Échanges</button>' +
        '<button type="button" class="wb3-cross-btn" data-wb3-view="trophees">🏆 Trophées</button>' +
        '<button type="button" class="wb3-cross-btn" data-wb3-view="stats">📈 Analytique</button>' +
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

    apiFetch('/artist/me/prompts?per_page=100')
      .then(function (resp) {
        var items = (resp && resp.items) || [];
        setCount('beats', items.filter(function (p) { return p.product_type === 'beat'; }).length);
      })
      .catch(function () { setCount('beats', counts.beats); });

    apiFetch('/artist/me/adn')
      .then(function () { setCount('adn', 1); })
      .catch(function (e) { setCount('adn', (e && e.status === 404) ? 0 : counts.adn); });

    apiFetch('/api/voices/me')
      .then(function (voices) { setCount('voix', Array.isArray(voices) ? voices.length : 0); })
      .catch(function () { setCount('voix', counts.voix); });
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
        if (key === 'sons' || key === 'beats') viewSons(key); else openScreen(key);
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

    // C1.1 — contexte de création par défaut : Sons IA.
    setUploadContext('sons');

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
  window.WattBoardV3 = { open: openScreen, back: backToBoard, refresh: refreshCounts };
})();
