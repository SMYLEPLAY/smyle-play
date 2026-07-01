/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/hub/marketplace.js
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

  // Vue selon l'URL : 'home' (accueil), 'sons' (/sons), 'artists' (/artistes).
  // /sons et /artistes réutilisent le shell index.html → vraies URL
  // partageables + SEO. On masque les autres cellules en CSS et on affiche la
  // cellule concernée en PLEIN (catalogue complet). La home, elle, ne montre
  // que les meilleurs (3 par cellule) pour ne pas qu'un artiste prenne tout.
  const _VIEW = (function () {
    const p = (typeof location !== 'undefined' ? location.pathname : '') || '';
    if (p === '/sons' || p === '/sons/') return 'sons';
    if (p === '/beats' || p === '/beats/') return 'beats';  // C2 — étagère beats
    if (p === '/voix' || p === '/voix/') return 'voix';     // chantier Voix
    if (p === '/images' || p === '/images/') return 'images'; // C4 ③ — vitrine images
    if (p === '/artistes' || p === '/artistes/') return 'artists';
    return 'home';
  })();
  const HOME_CAP = 3;

  // ── Mode Musique ⇄ Image (C4 étape 2) ─────────────────────────────────────
  // Deux « mondes » à parité sur la home. Le mode choisi est persisté dans
  // localStorage (mp_mode) et restauré au chargement. Défaut = musique.
  const _MP_MODE_KEY = 'mp_mode';
  function _readMode() {
    try {
      const v = localStorage.getItem(_MP_MODE_KEY);
      return v === 'image' ? 'image' : 'musique';
    } catch (_) { return 'musique'; }
  }
  function _writeMode(mode) {
    try { localStorage.setItem(_MP_MODE_KEY, mode); } catch (_) { /* best effort */ }
  }
  // Flag : les sections Image de la home ont-elles déjà été hydratées ? On
  // diffère le fetch du Monde Image au premier passage en mode image (lazy)
  // pour ne pas charger inutilement si l'user reste en musique.
  let _imageWorldLoaded = false;

  // Moods sélectionnés sur la page /sons (chips DNA inline). Filtre les sons
  // uniquement — la colonne artistes n'est pas touchée.
  const _pageMoodSet = new Set();
  // Liste des moods proposés sur /sons (alignée sur les tags des sons + loupe).
  const _PAGE_MOODS = [
    'chill', 'énergique', 'dark', 'festif', 'romantique', 'mélancolique',
    'instrumental', 'vocal', 'groovy', 'hypnotique', 'agressif',
    'nostalgique', 'euphorique', 'cinématique', 'loop', 'acapella',
  ];

  // Rôles CONNECT sélectionnés sur la page /artistes (chips inline —
  // miroir exact des moods DNA de /sons, demande Tom 2026-06-11).
  // Valeurs = ROLE_CODES backend (schemas/user.py, casquettes migration
  // 0018), alignées sur les chips CONNECT de la loupe (ui/modals/search.js).
  const _pageRoleSet = new Set();
  const _PAGE_ROLES = [
    { label: 'Artiste',     val: 'artiste'       },
    { label: 'Producteur',  val: 'producteur'    },
    { label: 'Beatmaker',   val: 'beatmaker'     },
    { label: 'Compositeur', val: 'compositeur'   },
    { label: 'Topliner',    val: 'topliner'      },
    { label: 'Parolier',    val: 'parolier'      },
    { label: 'Ghostwriter', val: 'ghostwriter'   },
    { label: 'Arrangeur',   val: 'arrangeur'     },
    { label: 'DJ',          val: 'dj'            },
    { label: 'Ingé son',    val: 'ingenieur_son' },
    { label: 'Éditeur',     val: 'editeur'       },
    { label: 'Auditeur',    val: 'auditeur'      },
  ];

  // Rôles CONNECT pour le MODE IMAGE — créateurs visuels (miroir exact des
  // chips CONNECT image de la loupe, ui/modals/search.js · ROLE_CODES visuels
  // schemas/user.py). Affichés à la place de _PAGE_ROLES quand mp_mode=image.
  const _PAGE_ROLES_IMG = [
    { label: 'Illustrateur',         val: 'illustrateur'         },
    { label: 'Graphiste',            val: 'graphiste'            },
    { label: 'Directeur artistique', val: 'directeur_artistique' },
    { label: 'Photographe',          val: 'photographe'          },
    { label: 'Concept artist',       val: 'concept_artist'       },
    { label: 'Character designer',   val: 'character_designer'   },
    { label: 'Retoucheur',           val: 'retoucheur'           },
    { label: 'Coloriste',            val: 'coloriste'            },
    { label: 'Artiste 3D',           val: 'artiste_3d'           },
    { label: 'Prompteur',            val: 'prompteur'            },
    { label: 'Designer',             val: 'designer'             },
    { label: 'Collectionneur',       val: 'collectionneur'       },
  ];

  function _injectViewStyles() {
    if (document.getElementById('mp-view-styles')) return;
    const s = document.createElement('style');
    s.id = 'mp-view-styles';
    s.textContent =
      '.mp-only-sons .smyle-vitrine,.mp-only-sons .mp-section-top-sons,.mp-only-sons .mp-section-top-artists,.mp-only-sons .mp-section-artists{display:none!important}' +
      '.mp-only-artists .smyle-vitrine,.mp-only-artists .mp-section-top-sons,.mp-only-artists .mp-section-top-artists,.mp-only-artists .mp-section-sons{display:none!important}' +
      // Chantier Voix — la page /voix masque tout et injecte sa section.
      '.mp-only-voix .smyle-vitrine,.mp-only-voix .mp-section-top-sons,.mp-only-voix .mp-section-top-artists,.mp-only-voix .mp-section-sons,.mp-only-voix .mp-section-artists{display:none!important}' +
      // C4 ③ — la page /images masque tout et injecte sa section vitrine images.
      '.mp-only-images .smyle-vitrine,.mp-only-images .mp-section-top-sons,.mp-only-images .mp-section-top-artists,.mp-only-images .mp-section-sons,.mp-only-images .mp-section-artists{display:none!important}' +
      // C4 étape 2 — commutateur Musique ⇄ Image sur la HOME. Deux mondes à
      // parité : les classes body mp-mode-musique / mp-mode-image montrent/
      // masquent les bonnes sections (même esprit que mp-only-*). Les sections
      // image existent dans le DOM mais sont masquées en mode musique, et
      // inversement. La vitrine Smyle est partagée (jamais masquée par le mode).
      // Sections Monde Image masquées par défaut (avant que le mode soit posé).
      '.mp-section-top-images,.mp-section-top-artists-image,.mp-section-images-home,.mp-section-albums-adn{display:none}' +
      // Mode Musique : on masque les sections Image (top-images, top-artistes-image, catalogue images, catalogue ADN Album).
      '.mp-mode-musique .mp-section-top-images,.mp-mode-musique .mp-section-top-artists-image,.mp-mode-musique .mp-section-images-home,.mp-mode-musique .mp-section-albums-adn{display:none!important}' +
      // Mode Image : on masque les sections Musique (top-sons, top-artistes, catalogue sons, grille artistes) ; on RÉVÈLE les sections Image.
      '.mp-mode-image .mp-section-top-sons,.mp-mode-image .mp-section-top-artists,.mp-mode-image .mp-section-sons,.mp-mode-image .mp-section-artists{display:none!important}' +
      '.mp-mode-image .mp-section-top-images,.mp-mode-image .mp-section-top-artists-image,.mp-mode-image .mp-section-images-home,.mp-mode-image .mp-section-albums-adn{display:block!important}' +
      // Commutateur : pilule à deux onglets, centrée au-dessus de la vitrine.
      '.mp-mode-switch{display:flex;gap:6px;justify-content:center;margin:0 auto 18px;padding:5px;width:max-content;border-radius:999px;border:1px solid rgba(124,58,237,.35);background:rgba(255,255,255,.03)}' +
      '.mp-mode-btn{cursor:pointer;border:0;background:transparent;color:rgba(255,255,255,.6);font-family:inherit;font-size:.92rem;font-weight:700;padding:9px 22px;border-radius:999px;transition:all .15s}' +
      '.mp-mode-btn:hover{color:#fff}' +
      '.mp-mode-btn.is-active{background:linear-gradient(90deg,#7C3AED,#a855f7);color:#fff;box-shadow:0 4px 16px rgba(124,58,237,.35)}' +
      // Le commutateur n'a de sens que sur la home : on le masque ailleurs.
      'body:not(.mp-view-home) .mp-mode-switch{display:none}' +
      // Section Œuvre complète (les deux modes) — grille de cartes œuvre.
      '.mp-oeuvres-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}' +
      '.mp-oeuvre-card{cursor:pointer;border:1px solid rgba(255,255,255,.09);border-radius:16px;overflow:hidden;background:rgba(255,255,255,.025);transition:border-color .15s,transform .15s}' +
      '.mp-oeuvre-card:hover{border-color:rgba(124,58,237,.6);transform:translateY(-2px)}' +
      '.mp-oeuvre-card-covers{position:relative;display:flex;aspect-ratio:2/1}' +
      '.mp-oeuvre-card-cover{flex:1;position:relative;overflow:hidden;background:rgba(124,58,237,.10);display:flex;align-items:center;justify-content:center}' +
      '.mp-oeuvre-card-cover img{width:100%;height:100%;object-fit:cover;display:block}' +
      '.mp-oeuvre-card-cover-fallback{font-size:2rem;opacity:.5}' +
      '.mp-oeuvre-card-body{padding:11px 13px 13px;display:flex;flex-direction:column;gap:6px}' +
      '.mp-oeuvre-card-title{font-weight:700;color:#f3f0ff;font-size:.95rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.mp-oeuvre-card-prices{display:flex;gap:10px;font-size:.78rem;color:#cbb3ff;font-weight:600}' +
      // Top Images / Top Artistes Image — réutilisent .mp-ranking ; on ajoute
      // juste une vignette d'aperçu sur les rangs.
      '.mp-ranking-thumb{width:42px;height:42px;border-radius:9px;object-fit:cover;flex:none;background:rgba(124,58,237,.12)}' +
      // MODE RÉSULTATS (2026-06-11) — dès qu'une recherche ou un filtre est
      // actif sur la home, la vitrine et les podiums s'effacent : les
      // grilles résultats prennent toute la place (sans plafond de 3).
      '.mp-searching .smyle-vitrine,.mp-searching .mp-section-top-sons,.mp-searching .mp-section-top-artists{display:none!important}' +
      // Ciblage par groupe : rôles seuls → la section sons disparaît ·
      // moods seuls → la section artistes disparaît (chaque filtre ne
      // montre que SA grille ; le texte libre montre les deux).
      '.mp-hide-sons .mp-section-sons{display:none!important}' +
      '.mp-hide-artists .mp-section-artists{display:none!important}' +
      '.mp-voir-tout{display:block;text-align:center;margin:12px auto 0;padding:9px 18px;border-radius:999px;border:1px solid rgba(124,58,237,.4);color:#c4b5fd;font-size:.82rem;font-weight:600;text-decoration:none;width:max-content;cursor:pointer}' +
      '.mp-voir-tout:hover{background:rgba(124,58,237,.12)}' +
      // C4 — barre de catégories (étagères) en HAUT, sous le commutateur de mode.
      // Réutilise le look pilule des .mp-voir-tout. Contextuelle au mode via les
      // classes body mp-mode-musique / mp-mode-image, et home-only.
      '.mp-cat-nav{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;align-items:center;margin:0 auto 20px;width:max-content;max-width:96%}' +
      // NE PAS forcer display ici (sinon ça écrase le display:none par
      // spécificité → les 2 jeux s'affichaient en même temps). Marge seule.
      '.mp-cat-nav .mp-cat-link{margin:0}' +
      // Cachés par défaut ; seuls les liens du mode actif sont affichés (règles
      // .mp-mode-* ci-dessous, spécificité supérieure au display:none).
      '.mp-cat-link{display:none}' +
      'body:not(.mp-view-home) .mp-cat-nav{display:none}' +
      // Mode Musique : Sons/Beats/Voix · Mode Image : Images/Avatars.
      '.mp-mode-musique .mp-cat-musique{display:inline-block}' +
      '.mp-mode-image .mp-cat-image{display:inline-block}';
    document.head.appendChild(s);
  }

  // État local — pas de store global, une page = un cycle de rendu.
  const _state = {
    smyleArtist: null,     // payload de /watt/artists/smyle
    artists:     [],       // tous les artistes publics (Smyle compris)
    tracks:      [],       // tous les sons (source tracks-recent)
    // adnBySlug supprimé (2026-05-14) : badge recette utilise promptId/promptPriceCredits par track.
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
      // Barres DNA + CONNECT supprimées — recherche migrée dans la loupe topbar (search.js)
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
    // P1-B9 front (2026-04-29) — l'endpoint renvoie { artist: {...} }
    // (cf. watt_compat.py:535), pas l'objet artist directement. Avant ce
    // fix, _state.smyleArtist contenait le wrapper → tous les a.artistName,
    // a.bio, a.brandColor étaient undefined → vitrine vide silencieusement.
    // On extrait .artist défensivement (compat si l'API change un jour).
    try {
      const data = await apiFetch('/watt/artists/smyle');
      _state.smyleArtist = (data && data.artist) ? data.artist : data;
    } catch (err) {
      console.warn('[marketplace] vitrine Smyle indisponible :', err && err.message);
      _state.smyleArtist = null;
    }
  }

  async function _fetchArtists() {
    try {
      const data = await apiFetch('/watt/artists');
      _state.artists = Array.isArray(data && data.artists) ? data.artists : [];
      // Badge recette : données par track (promptId/promptPriceCredits depuis /watt/tracks-recent).
    } catch (err) {
      console.warn('[marketplace] /watt/artists :', err && err.message);
      _state.artists = [];
      _state.adnBySlug = {};
    }
  }

  async function _fetchTracks() {
    try {
      // On charge large (jusqu'à 100) pour que le top-3 et les compteurs
      // "voir tout (N)" soient justes. L'affichage home reste cappé à 3.
      const data = await apiFetch('/watt/tracks-recent?limit=100');
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
    if (d.vitrineLink)      d.vitrineLink.href             = '/@' + (a.slug || 'smyle');
  }

  function _renderTopSons() {
    const el = _state.dom.topSons;
    if (!el) return;

    // Tri plays desc. Home = seulement les 3 meilleurs (le catalogue complet
    // est sur la page /sons). `tracks-recent` renvoie par created_at desc.
    const _allTop = _state.tracks
      .slice()
      .sort((a, b) => (b.plays || 0) - (a.plays || 0));
    const top = _allTop.slice(0, HOME_CAP);

    if (top.length === 0) {
      el.innerHTML = '<li class="mp-ranking-empty">Aucun son pour le moment.</li>';
      return;
    }

    el.innerHTML = top.map((t, i) => {
      const artistName = t.artist || '—';
      const artistSlug = t.artistSlug || '';
      const plays      = _fmt(t.plays || 0);
      const title      = t.name || 'Sans titre';
      const streamUrl  = t.streamUrl || '';
      // Pivot écoute v2 (2026-05-05) — chaque row du Top Sons embarque
      // un mini bouton play + audio cache. Click sur ▶ = toggle play
      // de la track. Click ailleurs (titre/rang/écoutes) = redirect
      // vers le profil ancré sur le track. Memes data-attributes que
      // les cards de la grille pour reuse du _bindTrackClicks.
      const playBtn = streamUrl
        ? `<button class="mp-ranking-play" type="button" aria-label="Lire / Pause">` +
            `<svg viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>` +
          `</button>`
        : '';
      const audioEl = streamUrl
        ? `<audio preload="none" class="mp-ranking-audio" src="${_esc(streamUrl)}"></audio>`
        : '';
      return (
        `<li class="mp-ranking-row mp-ranking-row-clickable" data-track-id="${_esc(t.id || '')}" data-stream-url="${_esc(streamUrl)}" data-artist-slug="${_esc(artistSlug)}">` +
          `<div class="mp-ranking-rank">${i + 1}</div>` +
          `<div class="mp-ranking-main">` +
            `<div class="mp-ranking-title" style="cursor:pointer" title="Voir les détails">${_esc(title)}</div>` +
            `<div class="mp-ranking-sub">` +
              `<a href="/@${_esc(artistSlug)}" onclick="event.stopPropagation();" style="color:inherit;text-decoration:none">${_esc(artistName)}</a>` +
            `</div>` +
          `</div>` +
          playBtn +
          `<div class="mp-ranking-meta">${plays} écoutes</div>` +
          `<button class="add-to-pl-btn mp-ranking-add" type="button" data-add-to-playlist="${_esc(t.trackUuid || t.id || '')}" title="Ajouter à une playlist" aria-label="Ajouter à une playlist">+</button>` +
          `<button class="like-btn mp-ranking-like" type="button" data-like-btn="${_esc(t.trackUuid || t.id || '')}" title="J\u0027aime / retirer" aria-label="Liker"></button>` +
          audioEl +
        `</li>`
      );
    }).join('') + (_allTop.length > HOME_CAP
      ? '<li style="list-style:none"><a class="mp-voir-tout" href="/sons">Voir tous les sons (' + _allTop.length + ') →</a></li>'
      : '');

    // Register virtual PLAYLIST pour le player principal (queue Top Sons)
    if (typeof window !== 'undefined') {
      /* PLAYLISTS init dans state.js */
      PLAYLISTS['mp_top_sons'] = {
        theme: 'mix', label: 'Top Sons', folder: '',
        tracks: top.filter(t => t.streamUrl).map((t, i) => ({
          id:   t.id || ('mptop_' + i),
          name: t.name || 'Sans titre',
          url:  t.streamUrl,
          file: (t.name || 'track') + '.wav'
        }))
      };
    }
  }

  function _renderTopArtists() {
    const el = _state.dom.topArtists;
    if (!el) return;

    // Podium Top 3 — COMMUNAUTÉ uniquement (Smyle = vitrine, exclu). Classé
    // par écoutes (backend déjà trié). Dynamique : bouge selon les stats →
    // méritocratique, pas de favoritisme.
    const community = _state.artists.filter(a => !a.isOfficial);

    // État vide = invitation (cold start propre pour le lancement).
    if (community.length === 0) {
      el.innerHTML =
        '<li style="list-style:none">' +
          '<div style="text-align:center;padding:30px 18px;border:1px dashed rgba(255,255,255,.13);border-radius:16px;background:rgba(255,255,255,.02)">' +
            '<div style="font-size:1.8rem;margin-bottom:6px">🏆</div>' +
            '<div style="font-weight:800;color:#fff;font-size:1.02rem;margin-bottom:4px">Le podium attend ses premiers artistes</div>' +
            '<div style="font-size:.84rem;color:#a09cb8;max-width:340px;margin:0 auto 14px">Sois parmi les premiers à publier sur WATT — le classement se construit à l’écoute, à toi de grimper.</div>' +
            '<a href="/dashboard" style="display:inline-block;padding:10px 20px;border-radius:999px;background:linear-gradient(90deg,#7C3AED,#a855f7);color:#fff;font-weight:700;font-size:.86rem;text-decoration:none">Deviens artiste WATT →</a>' +
          '</div>' +
        '</li>';
      return;
    }

    const top3 = community.slice(0, 3);
    const rest = community.slice(3, 10);
    const MEDAL = ['🥇', '🥈', '🥉'];
    const _spot = (a, rankIdx) => {
      const big = rankIdx === 0;
      const sz = big ? 80 : 60;
      const href = a.slug ? '/@' + a.slug : '#';
      const name = a.artistName || 'Sans nom';
      const color = a.brandColor || '#7C3AED';
      const avatar = a.avatarUrl
        ? `<img src="${_esc(a.avatarUrl)}" alt="" style="width:100%;height:100%;object-fit:cover">`
        : `<span style="font-weight:800;color:#fff;font-size:${big ? 1.6 : 1.2}rem">${_esc(_initial(name))}</span>`;
      return (
        `<a href="${_esc(href)}" style="flex:1;max-width:130px;display:flex;flex-direction:column;align-items:center;gap:5px;text-decoration:none;${big ? 'transform:translateY(-10px)' : ''}">` +
          `<div style="font-size:${big ? 1.5 : 1.2}rem">${MEDAL[rankIdx]}</div>` +
          `<div style="width:${sz}px;height:${sz}px;border-radius:50%;overflow:hidden;background:${_esc(color)};display:flex;align-items:center;justify-content:center;border:2px solid ${big ? '#FFD700' : 'rgba(255,255,255,.2)'};box-shadow:0 4px 18px ${big ? 'rgba(255,215,0,.25)' : 'rgba(0,0,0,.3)'}">${avatar}</div>` +
          `<div style="font-weight:700;color:#fff;font-size:${big ? '.95rem' : '.85rem'};text-align:center;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(name)}</div>` +
          `<div style="font-size:.72rem;color:#a09cb8">${_fmt(a.plays || 0)} écoutes</div>` +
        `</a>`
      );
    };
    // Ordre visuel : 2e (gauche), 1er (centre, surélevé), 3e (droite).
    const spots = [];
    if (top3[1]) spots.push(_spot(top3[1], 1));
    if (top3[0]) spots.push(_spot(top3[0], 0));
    if (top3[2]) spots.push(_spot(top3[2], 2));
    const podium =
      '<li style="list-style:none;margin-bottom:14px">' +
        '<div style="display:flex;align-items:flex-end;justify-content:center;gap:14px;padding:18px 8px 8px">' + spots.join('') + '</div>' +
      '</li>';
    const list = rest.map((a, i) => {
      const href = a.slug ? '/@' + a.slug : '#';
      const name = a.artistName || 'Sans nom';
      const parts = [a.city, a.genre].filter(Boolean).map(_esc).join(' · ');
      return (
        `<li class="mp-ranking-row" onclick="window.location.href='${_esc(href)}'">` +
          `<div class="mp-ranking-rank">${i + 4}</div>` +
          `<div class="mp-ranking-main">` +
            `<div class="mp-ranking-title">${_esc(name)}</div>` +
            `<div class="mp-ranking-sub">${parts || '&nbsp;'}</div>` +
          `</div>` +
          `<div class="mp-ranking-meta">${_fmt(a.plays || 0)} écoutes</div>` +
        `</li>`
      );
    }).join('');
    el.innerHTML = podium + list;
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

    // C2 — vue /beats : seulement les sons flagués beat (drapeau is_beat
    // ou beat legacy), achetables via le même circuit recette.
    const _baseTracks = (_VIEW === 'beats')
      ? _state.tracks.filter(t => !!t.isBeat)
      : _state.tracks;

    let items = _baseTracks.filter(t => {
      if (!needle) return true;
      const hay = ((t.name || '') + ' ' + (t.artist || '') + ' ' + (t.genre || '') + ' ' + (t.tags || '')).toLowerCase();
      // Match texte classique OU match DNA (genre taggé sur l'univers gagnant)
      if (hay.includes(needle)) return true;
      if (dnaHit) {
        for (const kw of dna.keywords) {
          if (hay.includes(kw)) return true;
        }
      }
      return false;
    });

    // Filtre moods (chips DNA de la page /sons) — OR entre moods, sur les tags.
    if (_pageMoodSet.size) {
      const wanted = [..._pageMoodSet];
      items = items.filter(t => {
        const tg = (t.tags || '').toLowerCase();
        return wanted.some(m => tg.includes(m));
      });
    }

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
      el.innerHTML = (needle || _pageMoodSet.size)
        ? `<div class="mp-grid-empty">Aucun son ne correspond à ta sélection.</div>`
        : (_VIEW === 'beats'
            ? `<div class="mp-grid-empty">Aucun beat sur l'étagère pour le moment. Publie un son avec la case « 🥁 Proposer aussi comme beat ».</div>`
            : `<div class="mp-grid-empty">Aucun son dans le catalogue pour le moment.</div>`);
      return;
    }

    // Home : on ne montre que les 3 meilleurs (pas de déversement du catalogue).
    // Le catalogue complet vit sur la page dédiée /sons. En vue /sons → tout.
    let _capNote = '';
    // Cap home à 3 UNIQUEMENT hors recherche/filtre actif (mode résultats).
    if (_VIEW === 'home' && !needle && !_pageMoodSet.size && items.length > HOME_CAP) {
      const totalSons = items.length;
      items = items.slice().sort((a, b) => (b.plays || 0) - (a.plays || 0)).slice(0, HOME_CAP);
      // C4 — Beats/Voix déplacés dans la barre de catégories du haut (.mp-cat-nav,
      // mode-aware). On ne garde ici que « Voir tous les sons (N) » pour éviter
      // le doublon d'étagères en bas de grille.
      _capNote = '<div style="grid-column:1/-1;display:flex;gap:10px;justify-content:center;margin-top:14px">'
        + '<a class="mp-voir-tout" href="/sons" style="margin:0">Voir tous les sons (' + totalSons + ') →</a>'
        + '</div>';
    }

    el.innerHTML = items.map(t => {
      const color = t.color || '#7C3AED';
      const title = t.name || 'Sans titre';
      const name  = t.artist || '—';
      const plays = _fmt(t.plays || 0);
      // Pivot écoute (2026-05-05) — chaque card embarque l'URL stream et
      // le slug artiste pour click → profil. Audio toujours rendu (lecteur
      // <audio> caché par défaut, joué via le bouton play).
      const streamUrl  = t.streamUrl || '';
      const artistSlug = t.artistSlug || '';
      const coverUrl   = t.coverUrl || t.cover_url || '';
      const coverHTML  = coverUrl
        ? `<img src="${_esc(coverUrl)}" alt="" class="mp-son-card-cover-img" />`
        : `<div class="mp-son-card-cover-fallback" style="background:${_esc(color)}1a;display:flex;align-items:center;justify-content:center;width:100%;height:100%;font-size:1.8rem" aria-hidden="true">🎵</div>`;
      // Badge 🧬 si l'artiste a un ADN publié achetable
      // Badge Recette si le track a un prompt achetable
      const promptId    = t.promptId    || null;
      const promptPrice = t.promptPriceCredits != null ? t.promptPriceCredits : null;
      // Badge 🧬 si le track a un prompt achetable — bouton cliquable direct
      // ⚠️ BUG FIXÉ (2026-06-13) : l'inline onclick="event.stopPropagation()"
      // empêchait l'événement d'atteindre le délégué document (phase bulle)
      // qui ouvre le drawer → badge mort sur les cards. Le délégué fait déjà
      // son propre stopPropagation dans la branche badge.
      const recipeBtn   = (promptId && promptPrice != null)
        ? `<button type="button" class="mp-recipe-badge"
                   data-prompt-id="${_esc(String(promptId))}"
                   data-prompt-price="${promptPrice}"
                   data-track-name="${_esc(title)}"
                   title="D\u00e9bloquer la recette \u00b7 ${promptPrice} Smyles">
            \uD83E\uDDEC <span class="mp-recipe-badge-price">${promptPrice} Smyles</span>
           </button>`
        : '';
      // Lien perma vers le profil artiste
      const permalinkBtn = artistSlug
        ? `<a class="mp-son-card-permalink" href="/@${_esc(artistSlug)}" onclick="event.stopPropagation();" title="Voir le profil artiste" aria-label="Voir le profil artiste">\u2197</a>`
        : '';
      // Carte ID enrichie (avant achat) : badge plateforme/IA + chips mood.
      const _PLATFORM_LABELS = { suno: 'Suno', udio: 'Udio', riffusion: 'Riffusion', stable_audio: 'Stable Audio', autre: 'Autre' };
      const platformKey   = (t.platform || '').trim().toLowerCase();
      const platformLabel = _PLATFORM_LABELS[platformKey] || (platformKey ? platformKey : '');
      const platformBadge = platformLabel
        ? `<span class="mp-son-card-platform" title="Son g\u00e9n\u00e9r\u00e9 avec ${_esc(platformLabel)}" style="display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:9px;background:rgba(124,58,237,.16);color:#c4b5fd;font-size:.68rem;font-weight:600;">\u26a1 ${_esc(platformLabel)}</span>`
        : '';
      const moods = (t.tags || '').split(',').map(s => s.trim()).filter(Boolean).slice(0, 4);
      const moodChips = moods
        .map(m => `<span class="mp-son-card-mood" style="display:inline-block;padding:2px 7px;border-radius:9px;background:rgba(255,255,255,.07);color:#b9b3c8;font-size:.68rem;">${_esc(m)}</span>`)
        .join('');
      // C2 — chips beat : 🥁 (placement) + BPM si renseigné.
      const beatChip = t.isBeat
        ? `<span class="mp-son-card-beat" title="Proposé comme beat" style="display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:9px;background:rgba(34,197,94,.14);color:#86efac;font-size:.68rem;font-weight:600;">🥁 Beat${t.bpm ? ' · ' + t.bpm + ' BPM' : ''}</span>`
        : '';
      // ── DUALITÉ ADN (B) — 2 badges d'angle sur la CARD (hors image) ──────
      // Musique haut-gauche · Visuel haut-droite. Dégradé gracieux mono :
      // l'ADN présent est solide, la face manquante devient une INVITATION
      // (ghost) qui montre qu'il reste un ADN à créer. Zéro ADN → rien
      // (pas de bruit visuel — honnête, on n'invite pas dans le vide).
      const adnM  = t.adnMusique || null;
      const adnV  = t.adnVisuel  || null;
      const hasM  = !!(adnM && adnM.has);
      const hasV  = !!(adnV && adnV.has);
      let adnBadges = '';
      if (hasM || hasV) {
        const mInv = hasM ? '' : ' is-invitation';
        const vInv = hasV ? '' : ' is-invitation';
        const mTitle = hasM
          ? ('ADN musical' + (adnM.price != null ? ' · ' + adnM.price + ' Smyles' : ''))
          : 'Cet artiste n’a pas encore d’ADN musical';
        const vTitle = hasV
          ? ('ADN visuel' + (adnV.price != null ? ' · ' + adnV.price + ' Smyles' : ''))
          : 'Cet artiste n’a pas encore d’ADN visuel — invitez-le à le créer';
        adnBadges =
          `<div class="mp-son-card-adnrow">` +
            `<span class="mp-son-card-adn mp-son-card-adn--music${mInv}" title="${_esc(mTitle)}" aria-hidden="true">🎵<span class="mp-son-card-adn-lbl">ADN</span></span>` +
            `<span class="mp-son-card-adn mp-son-card-adn--visual${vInv}" title="${_esc(vTitle)}" aria-hidden="true">🎨<span class="mp-son-card-adn-lbl">ADN</span></span>` +
          `</div>`;
      }
      // ── Tag playlist/univers cliquable (B2) → profil artiste + deep-link ──
      const plt = t.playlistTag || null;
      const plTag = (plt && plt.playlistTitle && artistSlug)
        ? `<a class="mp-son-card-pltag" href="/@${_esc(artistSlug)}#pl-${_esc(plt.playlistId || '')}" onclick="event.stopPropagation();" title="Voir la playlist « ${_esc(plt.playlistTitle)} » sur le profil de ${_esc(name)}" style="--pltag-color:${_esc(plt.playlistColor || color)}"><span class="mp-son-card-pltag-dot" aria-hidden="true"></span>${_esc(plt.playlistTitle)}</a>`
        : '';
      const tagsRow = (plTag || platformBadge || moodChips || beatChip)
        ? `<div class="mp-son-card-tags-row" style="display:flex;flex-wrap:wrap;gap:4px;margin:4px 0 2px;">${plTag}${platformBadge}${beatChip}${moodChips}</div>`
        : '';
      return (
        `<div class="mp-son-card" data-track-id="${_esc(t.id || '')}" data-stream-url="${_esc(streamUrl)}" data-artist-slug="${_esc(artistSlug)}" style="--son-color:${_esc(color)}">` +
          adnBadges +
          `<div class="mp-son-card-cover">` +
            coverHTML +
            `<button class="mp-son-card-play" type="button" aria-label="Lire / Pause">` +
              `<svg viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>` +
            `</button>` +
          `</div>` +
          `<div class="mp-son-card-title">${_esc(title)}</div>` +
          `<div class="mp-son-card-artist">` +
            `<a class="mp-son-card-artist-name" href="/@${_esc(artistSlug)}" onclick="event.stopPropagation();">${_esc(name)}</a>` +
            permalinkBtn +
          `</div>` +
          tagsRow +
          (recipeBtn ? `<div class="mp-son-card-recipe-row">${recipeBtn}</div>` : '') +
          `<div class="mp-son-card-meta">` +
            `<span class="mp-son-card-meta-plays">${plays} \u00e9coutes</span>` +
            `<div class="mp-son-card-meta-actions">` +
              `<button class="like-btn mp-son-card-like" type="button" data-like-btn="${_esc(t.trackUuid || t.id || '')}" title="J\u0027aime / retirer" aria-label="Liker"></button>` +
              `<button class="add-to-pl-btn mp-son-card-add" type="button" data-add-to-playlist="${_esc(t.trackUuid || t.id || '')}" title="Ajouter \u00e0 une playlist" aria-label="Ajouter \u00e0 une playlist">+</button>` +
            `</div>` +
          `</div>` +
          (streamUrl
            ? `<audio preload="none" class="mp-son-card-audio" src="${_esc(streamUrl)}"></audio>`
            : ''
          ) +
        `</div>`
      );
    }).join('') + _capNote;

    // Register virtual PLAYLIST pour le player principal (queue Tous les sons)
    if (typeof window !== 'undefined') {
      /* PLAYLISTS init dans state.js */
      PLAYLISTS['mp_all_sons'] = {
        theme: 'mix', label: 'Tous les sons', folder: '',
        tracks: items.filter(t => t.streamUrl).map((t, i) => ({
          id:   t.id || ('mpall_' + i),
          name: t.name || 'Sans titre',
          url:  t.streamUrl,
          file: (t.name || 'track') + '.wav'
        }))
      };
    }
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
      // Chips CONNECT de /artistes (2026-06-11) : multi-sélection en OR —
      // un profil reste visible s'il porte AU MOINS un des rôles cochés.
      .filter(a => {
        if (!_pageRoleSet.size) return true;
        const roles = Array.isArray(a.roles) ? a.roles : [];
        for (const r of _pageRoleSet) {
          if (roles.includes(r)) return true;
        }
        return false;
      })
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
      el.innerHTML = (needle || _pageRoleSet.size)
        ? `<div class="mp-grid-empty">Aucun profil ne correspond à ta sélection.</div>`
        : `<div class="mp-grid-empty">Sois le premier artiste à publier ici. <a href="/dashboard" style="color:#c4b5fd">Deviens artiste →</a></div>`;
      return;
    }

    // Home : 3 meilleurs profils ; catalogue complet sur /artistes.
    // 2026-06-11 — le lien « Voir tous les artistes » est TOUJOURS affiché
    // sur la home (miroir de « Voir tous les sons »). Avant : seulement si
    // plus de 3 profils → avec un catalogue jeune, aucun accès visible à
    // /artistes (retour QA Tom).
    let _artNote = '';
    // Cap home à 3 UNIQUEMENT hors recherche/filtre actif (mode résultats).
    if (_VIEW === 'home' && !needle && !_pageRoleSet.size) {
      const totalArt = items.length;
      if (items.length > HOME_CAP) items = items.slice(0, HOME_CAP);
      _artNote = '<a class="mp-voir-tout" href="/artistes" style="grid-column:1/-1;margin-top:14px">Voir tous les artistes (' + totalArt + ') →</a>';
    }

    el.innerHTML = items.map(a => {
      const href  = a.slug ? '/@' + a.slug : '#';
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
    }).join('') + _artNote;
  }

  /** Re-render complet de toutes les sections dépendant de l'état. */
  function _renderAll() {
    _renderVitrine();
    _renderTopSons();
    _renderTopArtists();
    _renderGridSons('');
    _renderGridArtists('');
  }


  // ── Bindings ─────────────────────────────────────────────────────────────

  function _bindSearch() {
    // Barres inline supprimées — la recherche vit dans la loupe topbar (search.js)
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

  // Pivot écoute (2026-05-05) — click sur cards de son :
  //   - Click sur le bouton ▶/⏸ → toggle play/pause de l'audio inline
  //     (un seul son joue à la fois — on stoppe les autres)
  //   - Click sur le reste de la card (titre, artiste, cover) → redirect
  //     vers /u/<slug> de l'artiste, ancré sur le track (vue détail)
  // Délégation globale sur document — couvre les rows top + grille +
  // futures sections sans avoir à rebrancher après chaque _renderAll().
  function _bindTrackClicks() {
    let _currentlyPlaying = null;

    document.addEventListener('click', (ev) => {
      // ── ROW TOP SONS (mp-ranking-row-clickable avec stream) ──────────
      // Pivot écoute v2 — Top Sons jouable inline au lieu de juste rediriger.
      const row = ev.target.closest('.mp-ranking-row-clickable');
      if (row && row.dataset.streamUrl) {
        const playBtnRow = ev.target.closest('.mp-ranking-play');
        if (playBtnRow) {
          ev.preventDefault();
          ev.stopPropagation();
          const allRows = document.querySelectorAll('.mp-ranking-row-clickable[data-stream-url]');
          const dynTracks = Array.from(allRows).map(r => ({
            id:   r.dataset.trackId || '',
            name: r.querySelector('.mp-ranking-title')?.textContent || 'Track',
            url:  r.dataset.streamUrl || '',
            file: 'track.wav'
          })).filter(t => t.url);
          if (typeof loadTrack === 'function' && dynTracks.length > 0) {
            /* PLAYLISTS init dans state.js */
            PLAYLISTS['mp_top_sons'] = {
              theme: 'mix', label: 'Top Sons', folder: '', tracks: dynTracks
            };
            const tid = row.dataset.trackId;
            const idx = dynTracks.findIndex(t => t.id === tid);
            const safeIdx = idx >= 0 ? idx : 0;
            console.log('[marketplace] play Top Sons idx=', safeIdx, '/', dynTracks.length);
            loadTrack('mp_top_sons', safeIdx);
            return;
          }
          const audioRow = row.querySelector('audio.mp-ranking-audio');
          if (audioRow) {
            console.log('[marketplace] fallback audio inline (Top Sons)');
            if (audioRow.paused) audioRow.play().catch(e => console.error('audio inline:', e));
            else audioRow.pause();
          }
          return;
        }
        // Click sur le titre de la row → ouvre le drawer de détail
        if (ev.target.closest('.mp-ranking-title')) {
          const trackId = row.dataset.trackId;
          const track   = _state.tracks.find(t => String(t.id) === String(trackId));
          if (track) { _openTrackDetailDrawer(track); return; }
        }
        return;
      }

      const card = ev.target.closest('.mp-son-card');
      if (!card) return;

      // Click play button → joue dans le player principal (queue auto)
      const playBtn = ev.target.closest('.mp-son-card-play');
      if (playBtn) {
        ev.preventDefault();
        ev.stopPropagation();
        const allCards = document.querySelectorAll('.mp-son-card[data-stream-url]');
        const dynTracks = Array.from(allCards).map(c => ({
          id:   c.dataset.trackId || '',
          name: c.querySelector('.mp-son-card-title')?.textContent || 'Track',
          url:  c.dataset.streamUrl || '',
          file: 'track.wav'
        })).filter(t => t.url);
        if (typeof loadTrack === 'function' && dynTracks.length > 0) {
          /* PLAYLISTS init dans state.js */
          PLAYLISTS['mp_all_sons'] = {
            theme: 'mix', label: 'Tous les sons', folder: '', tracks: dynTracks
          };
          const tid = card.dataset.trackId;
          const idx = dynTracks.findIndex(t => t.id === tid);
          const safeIdx = idx >= 0 ? idx : 0;
          console.log('[marketplace] play Card idx=', safeIdx, '/', dynTracks.length);
          loadTrack('mp_all_sons', safeIdx);
          return;
        }
        const audio = card.querySelector('audio.mp-son-card-audio');
        if (!audio) {
          if (window.showToast) window.showToast('Audio indisponible.');
          return;
        }
        console.log('[marketplace] fallback audio inline card');
        if (audio.paused) audio.play().catch(e => console.error('audio inline card:', e));
        else audio.pause();
        return;
      }

      // Click sur badge recette → modale unlock directe
      const recipeBadgeEl = ev.target.closest('.mp-recipe-badge');
      if (recipeBadgeEl) {
        ev.preventDefault();
        ev.stopPropagation();
        _openRecipeUnlockModal(recipeBadgeEl);
        return;
      }

      // Click sur titre ou cover → ouvre le drawer de détail
      const isTitleClick = !!ev.target.closest('.mp-son-card-title');
      const isCoverClick = !!ev.target.closest('.mp-son-card-cover') &&
                           !ev.target.closest('.mp-son-card-play') &&
                           !ev.target.closest('.mp-recipe-badge');
      if (isTitleClick || isCoverClick) {
        ev.preventDefault();
        ev.stopPropagation();
        const trackId = card.dataset.trackId;
        const track   = _state.tracks.find(t => String(t.id) === String(trackId));
        if (track) _openTrackDetailDrawer(track);
        return;
      }
    });

    // Quand un audio se termine, on retire l'état playing visuel
    // (autant pour les cards de la grille que pour les rows Top Sons)
    document.addEventListener('ended', (ev) => {
      const audio = ev.target;
      if (!audio || !audio.matches) return;
      if (audio.matches('audio.mp-son-card-audio')) {
        const card = audio.closest('.mp-son-card');
        if (card) card.classList.remove('is-playing');
      } else if (audio.matches('audio.mp-ranking-audio')) {
        const row = audio.closest('.mp-ranking-row');
        if (row) row.classList.remove('is-playing');
      } else {
        return;
      }
      if (_currentlyPlaying === audio) _currentlyPlaying = null;
    }, true);
  }


  // ── Drawer détail track (clic sur titre ou cover d'une card son) ─────────
  function _openTrackDetailDrawer(t) {
    const existing = document.getElementById('mp-track-detail-drawer');
    if (existing) existing.parentNode.removeChild(existing);

    const color      = t.color || '#7C3AED';
    const title      = t.name || 'Sans titre';
    const artistName = t.artist || '—';
    const artistSlug = t.artistSlug || '';
    const plays      = _fmt(t.plays || 0);
    const streamUrl  = t.streamUrl || '';
    const coverUrl   = t.coverUrl  || t.cover_url || '';
    const promptId   = t.promptId  || null;
    const promptPrice = (t.promptPriceCredits != null) ? t.promptPriceCredits : null;

    const coverHTML = coverUrl
      ? `<img src="${_esc(coverUrl)}" alt="" class="mp-td-cover-img" />`
      : `<div class="mp-td-cover-fallback" style="background:${_esc(color)}"></div>`;

    const audioHTML = streamUrl
      ? `<div class="mp-td-audio-wrap">
           <div class="mp-td-audio-label">Pré-écoute</div>
           <audio controls preload="none" controlsList="nodownload noremoteplayback"
                  oncontextmenu="return false" class="mp-td-audio"
                  src="${_esc(streamUrl)}"></audio>
         </div>`
      : '';

    const recipeHTML = (promptId && promptPrice != null)
      ? `<div class="mp-td-recipe">
           <div class="mp-td-recipe-row">
             <div>
               <div class="mp-td-recipe-label">Recette Suno</div>
               <div class="mp-td-recipe-teaser" id="mp-td-recipe-teaser" style="font-size:.72rem;color:#a79fc0;margin:2px 0 4px;line-height:1.5;"></div>
               <div class="mp-td-recipe-price">${promptPrice} <span class="mp-td-recipe-unit">Smyles</span></div>
             </div>
             <button class="mp-td-recipe-btn" id="mp-td-recipe-btn"
                     data-prompt-id="${_esc(promptId)}"
                     data-prompt-price="${promptPrice}"
                     data-track-name="${_esc(title)}">
               🧬 Débloquer
             </button>
           </div>
         </div>`
      : '';

    // Carte ID enrichie (drawer détail) : badge plateforme/IA + chips mood.
    const _TD_PLATFORM_LABELS = { suno: 'Suno', udio: 'Udio', riffusion: 'Riffusion', stable_audio: 'Stable Audio', autre: 'Autre' };
    const tdPlatformKey   = (t.platform || '').trim().toLowerCase();
    const tdPlatformLabel = _TD_PLATFORM_LABELS[tdPlatformKey] || (tdPlatformKey ? tdPlatformKey : '');
    const tdPlatformBadge = tdPlatformLabel
      ? `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:10px;background:rgba(124,58,237,.16);color:#c4b5fd;font-size:.75rem;font-weight:600;">⚡ ${_esc(tdPlatformLabel)}</span>`
      : '';
    const tdMoods = (t.tags || '').split(',').map(s => s.trim()).filter(Boolean);
    const tdMoodChips = tdMoods
      .map(m => `<span style="display:inline-block;padding:3px 9px;border-radius:10px;background:rgba(255,255,255,.07);color:#cfc9db;font-size:.75rem;">${_esc(m)}</span>`)
      .join('');
    const tagsMetaHTML = (tdPlatformBadge || tdMoodChips)
      ? `<div class="mp-td-tags" style="display:flex;flex-wrap:wrap;gap:5px;margin:10px 0 2px;">${tdPlatformBadge}${tdMoodChips}</div>`
      : '';

    const overlay = document.createElement('div');
    overlay.id        = 'mp-track-detail-drawer';
    overlay.className = 'mp-td-overlay';
    const tuuid = _esc(t.trackUuid || t.id || '');
    const socialHTML = tuuid ? `
      <div class="mp-td-social-row">
        <button class="like-btn mp-td-like-btn" type="button" data-like-btn="${tuuid}" title="Ajouter à ma Wishlist"></button>
        <button class="add-to-pl-btn mp-td-addpl-btn" type="button" data-add-to-playlist="${tuuid}" title="Ajouter à une playlist">+</button>
      </div>` : '';
    overlay.innerHTML = `
      <aside class="mp-td-drawer" style="--td-color:${_esc(color)}"
             role="dialog" aria-modal="true" aria-label="Détail du son">
        <button class="mp-td-close" aria-label="Fermer">✕</button>
        <div class="mp-td-cover">${coverHTML}</div>
        <div class="mp-td-body">
          <div class="mp-td-color-bar" style="background:${_esc(color)}"></div>
          <div class="mp-td-type">Son</div>
          <h2 class="mp-td-title">${_esc(title)}</h2>
          <a class="mp-td-artist" href="/@${_esc(artistSlug)}">${_esc(artistName)}</a>
          <div class="mp-td-plays">${plays} écoutes</div>
          ${tagsMetaHTML}
          ${audioHTML}
          ${socialHTML}
          ${recipeHTML}
        </div>
      </aside>`;

    // Teaser recette (avant achat) : plateforme + modèle Suno + paroles
    // incluses. Le prompt et les réglages exacts restent gated. Un seul
    // appel à l'ouverture du drawer.
    if (promptId) {
      (async () => {
        try {
          const d = await window.apiFetch('/catalog/prompts/' + encodeURIComponent(promptId));
          const el = overlay.querySelector('#mp-td-recipe-teaser');
          if (!el || !d) return;
          const parts = [];
          const plat = (d.platform || '').trim();
          if (plat) parts.push('⚡ ' + _esc(plat.charAt(0).toUpperCase() + plat.slice(1)));
          if (d.model_version) parts.push(_esc(d.model_version));
          if (d.has_lyrics) parts.push('🎤 paroles incluses');
          parts.push('🔒 prompt + réglages débloqués à l’achat');
          el.innerHTML = parts.join(' · ');
        } catch (_) { /* silencieux */ }
      })();
    }

    document.body.appendChild(overlay);
    requestAnimationFrame(() => {
      overlay.classList.add('is-open');
      overlay.querySelector('.mp-td-drawer').classList.add('is-open');
    });

    function _close() {
      overlay.classList.remove('is-open');
      const drawer = overlay.querySelector('.mp-td-drawer');
      if (drawer) drawer.classList.remove('is-open');
      const audio = overlay.querySelector('audio');
      if (audio) { try { audio.pause(); } catch(_) {} }
      setTimeout(() => { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); }, 300);
    }

    overlay.addEventListener('click', (e) => { if (e.target === overlay) _close(); });
    overlay.querySelector('.mp-td-close').addEventListener('click', _close);
    document.addEventListener('keydown', function onEsc(e) {
      if (e.key === 'Escape') { _close(); document.removeEventListener('keydown', onEsc); }
    });

    const recipeBtn = overlay.querySelector('#mp-td-recipe-btn');
    if (recipeBtn) {
      recipeBtn.addEventListener('click', () => {
        _close();
        _openRecipeUnlockModal(recipeBtn);
      });
    }
  }

  // ── Page /voix (chantier Voix 2026-06-12) ────────────────────────────────
  // Catalogue public des voix : preview 30 s, rareté #X/N, achat via le
  // drawer unifié. Section autonome injectée à la place des cellules home.
  async function _renderVoixPage() {
    const anchor = document.querySelector('.mp-section-sons');
    if (!anchor || !anchor.parentNode) return;

    const section = document.createElement('section');
    section.className = 'mp-section mp-section-voix';
    section.innerHTML =
      '<div class="mp-section-head">' +
        '<span class="mp-section-kicker">Catalogue</span>' +
        '<h2 class="mp-section-title">🎙 Voix</h2>' +
        '<span class="mp-section-sub">Pré-écoute 30 s libre — l\'achat débloque le fichier vocal complet</span>' +
      '</div>' +
      '<div class="mp-voix-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px">' +
        '<div class="mp-grid-empty">Chargement des voix…</div>' +
      '</div>';
    anchor.parentNode.insertBefore(section, anchor);
    const grid = section.querySelector('.mp-voix-grid');

    let voices = [];
    try {
      voices = await window.apiFetch('/api/voices?limit=100') || [];
    } catch (_) {
      grid.innerHTML = '<div class="mp-grid-empty">Impossible de charger les voix. Recharge la page.</div>';
      return;
    }
    if (!voices.length) {
      grid.innerHTML = '<div class="mp-grid-empty">Aucune voix en vente pour le moment. Les artistes les publient depuis leur WATT BOARD.</div>';
      return;
    }

    grid.innerHTML = voices.map(v => {
      const name   = _esc(v.name || 'Voix');
      const style  = _esc(v.style || '');
      const artist = v.artist || {};
      const aName  = _esc(artist.artist_name || '—');
      const aSlug  = _esc(artist.slug || '');
      const color  = artist.brand_color || '#7C3AED';
      const price  = v.price_credits || 0;
      const sold   = v.editions_sold || 0;
      const supply = (v.max_supply != null) ? v.max_supply : null;
      const soldOut = supply != null && sold >= supply;
      const rarete = supply != null
        ? (supply === 1
            ? (soldOut ? '1/1 · vendue' : '1/1 vente unique')
            : (soldOut ? 'Édition épuisée' : (supply - sold) + '/' + supply + ' dispo'))
        : '';
      const rareteChip = rarete
        ? '<span style="display:inline-block;padding:2px 8px;border-radius:9px;background:rgba(255,215,0,.12);color:#ffd700;font-size:.68rem;font-weight:700">' + rarete + '</span>'
        : '';
      const preview = v.preview_url
        ? '<audio controls preload="none" controlsList="nodownload noremoteplayback" oncontextmenu="return false" style="width:100%;height:32px;margin:8px 0 4px" src="' + _esc(v.preview_url) + '"></audio><div style="font-size:10px;color:#8b84a3">🎧 Pré-écoute 30 s</div>'
        : '<div style="font-size:11px;color:#8b84a3;margin:10px 0 4px">🔒 Pré-écoute bientôt disponible</div>';
      const btn = soldOut
        ? '<button type="button" disabled style="width:100%;margin-top:10px;padding:9px;border-radius:10px;border:none;background:rgba(255,255,255,.08);color:#8b84a3;font-weight:700;cursor:default">Épuisé</button>'
        : '<button type="button" class="mp-voix-buy" data-voice-id="' + _esc(String(v.id)) + '" data-voice-price="' + price + '" data-voice-name="' + name + '" data-artist-name="' + aName + '" style="width:100%;margin-top:10px;padding:9px;border-radius:10px;border:none;background:linear-gradient(135deg,#7c5cff,#9d4dff);color:#fff;font-weight:700;cursor:pointer">Débloquer · ' + price + ' Smyles ⚡</button>';
      return (
        '<article style="border:1px solid rgba(255,255,255,.09);border-radius:14px;padding:14px;background:rgba(255,255,255,.025)">' +
          '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px">' +
            '<strong style="color:' + _esc(color) + '">🎙 ' + name + '</strong>' + rareteChip +
          '</div>' +
          '<div style="font-size:.8rem;color:#b9b3c8;margin-top:2px">' + style + '</div>' +
          (aSlug
            ? '<a href="/@' + aSlug + '" style="font-size:.75rem;color:#a09cb8;text-decoration:none">par ' + aName + '</a>'
            : '<span style="font-size:.75rem;color:#a09cb8">par ' + aName + '</span>') +
          preview + btn +
        '</article>'
      );
    }).join('');

    grid.addEventListener('click', (e) => {
      const b = e.target.closest('.mp-voix-buy');
      if (!b) return;
      if (window.PurchaseDrawer) {
        window.PurchaseDrawer.open({
          type: 'voix',
          id: b.dataset.voiceId,
          price: parseInt(b.dataset.voicePrice, 10) || null,
          title: b.dataset.voiceName || 'Voix',
          artistName: b.dataset.artistName || '',
          onSuccess: () => { b.disabled = true; b.textContent = 'À toi ✓ — fichier dans ta bibliothèque'; },
        });
      }
    });
  }

  // ── Page /images (C4 ③ — vitrine Monde Visuel) ───────────────────────────
  // Grille de cards-aperçu : aperçu en fond, titre, 4 repères (nature image ·
  // palier · rareté #X/N · provenance via SpBadges), prix. Moteur de filtres
  // partagé (façon /sons) : provenance/plateforme · rareté · prix · ratio ·
  // texte. Clic carte → fiche/drawer d'achat (circuit unlock prompt C2).
  // Règle stricte : on n'affiche QUE l'aperçu + provenance + prix + rareté.
  // La recette (prompt/réglages) n'arrive JAMAIS dans /images (endpoint
  // ImagePublicRead) — elle se débloque à l'achat (ImageOwnerRead).
  var _IMG_PLATFORMS = [
    { val: 'midjourney',       label: 'Midjourney'       },
    { val: 'dalle',            label: 'DALL·E'           },
    { val: 'flux',             label: 'Flux'             },
    { val: 'stable_diffusion', label: 'Stable Diffusion' },
    { val: 'autre',            label: 'Autre'            },
  ];
  var _IMG_RARITIES = [
    { val: 'mythic',    label: '👑 Unique 1/1' },
    { val: 'legendary', label: '⭐ Légendaire' },
    { val: 'limited',   label: '💎 Limitée'    },
    { val: 'open',      label: '🟢 Ouverte'    },
    { val: 'unlimited', label: '♾️ Illimitée'  },
  ];
  // Styles d'image (16) — CODES alignés au backend (filtre /images?style=,
  // égalité stricte). Libellés FR pour l'affichage uniquement.
  var _IMG_STYLES = [
    { val: 'realiste',    label: 'Réaliste'      },
    { val: 'cartoon',     label: 'Cartoon'       },
    { val: 'anime',       label: 'Anime'         },
    { val: '3d',          label: '3D / Render'   },
    { val: 'peinture',    label: 'Peinture'      },
    { val: 'aquarelle',   label: 'Aquarelle'     },
    { val: 'croquis',     label: 'Croquis'       },
    { val: 'pixel_art',   label: 'Pixel art'     },
    { val: 'cyberpunk',   label: 'Cyberpunk'     },
    { val: 'fantasy',     label: 'Fantasy'       },
    { val: 'minimaliste', label: 'Minimaliste'   },
    { val: 'retro',       label: 'Rétro'         },
    { val: 'abstrait',    label: 'Abstrait'      },
    { val: 'surrealiste', label: 'Surréaliste'   },
    { val: 'comics',      label: 'Comics'        },
    { val: 'photo',       label: 'Photo'         },
  ];
  // Tags d'usage (11, dont fx) — CODES alignés au backend (filtre /images?tag=,
  // présence). Libellés FR pour l'affichage uniquement.
  var _IMG_USAGE = [
    { val: 'cover',        label: 'Cover'        },
    { val: 'portrait',     label: 'Portrait'     },
    { val: 'paysage',      label: 'Paysage'      },
    { val: 'logo',         label: 'Logo'         },
    { val: 'banniere',     label: 'Bannière'     },
    { val: 'avatar',       label: 'Avatar'       },
    { val: 'wallpaper',    label: 'Wallpaper'    },
    { val: 'mockup',       label: 'Mockup'       },
    { val: 'illustration', label: 'Illustration' },
    { val: 'texture',      label: 'Texture'      },
    { val: 'fx',           label: 'FX'           },
  ];

  // URL same-origin de l'aperçu (proxy backend, sert UNIQUEMENT images/previews/).
  function _imgPreviewUrl(key) {
    if (!key) return '';
    return '/watt/images/' + String(key).split('/').map(encodeURIComponent).join('/');
  }

  // Badge rareté #X/N depuis le payload public (maxSupply + soldCount).
  function _imgRareteBadge(img) {
    if (!window.SpBadges || img.maxSupply == null) return '';
    var sold = img.soldCount || 0;
    if (img.isSoldOut) return SpBadges.rarete(img.maxSupply, img.maxSupply);
    return SpBadges.rarete(sold + 1, img.maxSupply, img.maxSupply === 1 ? 'legendaire' : '');
  }

  // Set des IDs d'images possédées par l'user courant (rempli par _renderImagesPage).
  var _ownedImageIds = new Set();
  var _myUserId = null;

  function _imgCardHtml(img) {
    var url = _imgPreviewUrl(img.previewKey);
    var cover = url
      ? '<img src="' + _esc(url) + '" alt="' + _esc(img.title || 'Image') + '" loading="lazy" class="mp-img-card-cover-img" />'
      : '<div class="mp-img-card-cover-fallback" aria-hidden="true">🖼️</div>';
    var nature = window.SpBadges ? SpBadges.nature('image') : '';
    var palier = window.SpBadges ? SpBadges.palier('standard') : '';
    var rar    = _imgRareteBadge(img);
    var prov   = window.SpBadges ? SpBadges.provenance(img.imagePlatform, img.imageModelVersion) : '';
    // C4 Œuvre complète — badge si l'image est liée à un son.
    var oeuvre = (img.isOeuvreComplete && window.SpBadges && SpBadges.oeuvre) ? SpBadges.oeuvre() : '';
    var ratioChip = img.ratio
      ? '<span class="mp-img-card-ratio">' + _esc(img.ratio) + '</span>'
      : '';
    // C4 ④ #3 — possession / auteur : on remplace « Acheter »/prix par « ✓ À toi »
    // (possédé) ou un état neutre auteur. mine = je suis le créateur de l'image.
    var owned = _ownedImageIds.has(String(img.id));
    var mine  = (_myUserId && img.artistId && String(img.artistId) === String(_myUserId));
    var priceOrState;
    if (mine) {
      priceOrState = '<div class="mp-img-card-state mine">À toi (créateur)</div>';
    } else if (owned) {
      priceOrState = '<div class="mp-img-card-state owned">✓ À toi</div>';
    } else {
      priceOrState = '<div class="mp-img-card-price">' + _esc(img.priceCredits) + ' <span>Smyles</span></div>';
    }
    // C4 ④ #4 — bouton ❤️ wishlist (UUID du prompt image). Pas d'ajout playlist.
    var likeBtn = '<button type="button" class="like-btn mp-img-card-like" data-img-like-btn="' + _esc(img.id) + '" title="Wishlist" aria-label="Ajouter à ma Wishlist" onclick="event.stopPropagation()"></button>';
    // C4 My Mix — bouton « Ajouter à un album » (calque add-to-playlist).
    var albumBtn = '<button type="button" class="add-to-pl-btn mp-img-card-album" data-add-to-album="' + _esc(img.id) + '" title="Ajouter à un album" aria-label="Ajouter à un album" onclick="event.stopPropagation()">+</button>';
    return '' +
      '<article class="mp-img-card" data-image-id="' + _esc(img.id) + '" data-owned="' + ((owned || mine) ? '1' : '0') + '" tabindex="0" role="button" title="' + ((owned || mine) ? 'Image possédée' : 'Voir la fiche') + '">' +
        '<div class="mp-img-card-cover">' + cover + ratioChip + '</div>' +
        '<div class="mp-img-card-body">' +
          '<div class="mp-img-card-title">' + _esc(img.title || 'Sans titre') + '</div>' +
          '<div class="mp-img-card-badges">' + nature + palier + rar + prov + oeuvre + '</div>' +
          '<div class="mp-img-card-foot">' + priceOrState + albumBtn + likeBtn + '</div>' +
        '</div>' +
      '</article>';
  }

  // IDs d'images possédées + id user courant (pour l'état possession/auteur).
  async function _loadOwnedImages() {
    _ownedImageIds = new Set();
    _myUserId = null;
    try {
      if (typeof getAuthToken === 'function' && !getAuthToken()) return;
    } catch (_) { /* pas de helper auth → on tente quand même */ }
    try {
      var me = await window.apiFetch('/users/me');
      if (me && me.id) _myUserId = String(me.id);
    } catch (_) { return; } // non connecté → state public, pas de possession
    try {
      var lib = await window.apiFetch('/me/library/prompts?per_page=100');
      var items = (lib && Array.isArray(lib.items)) ? lib.items : [];
      items.forEach(function (it) {
        if (it.product_type === 'image') _ownedImageIds.add(String(it.prompt_id));
      });
    } catch (_) { /* dégrade proprement */ }
  }

  function _injectImagesStyles() {
    if (document.getElementById('mp-img-style')) return;
    var st = document.createElement('style');
    st.id = 'mp-img-style';
    st.textContent =
      '.mp-img-facets{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;align-items:center;margin:6px auto 16px;width:min(760px,96%)}' +
      '.mp-img-facets input,.mp-img-facets select{font-family:inherit;font-size:.82rem;color:#fff;background:rgba(255,255,255,.04);border:1px solid rgba(124,58,237,.4);border-radius:999px;padding:8px 14px;outline:none}' +
      '.mp-img-facets input::placeholder{color:rgba(255,255,255,.4)}' +
      '.mp-img-facets input:focus,.mp-img-facets select:focus{border-color:rgba(124,58,237,.9)}' +
      '.mp-img-facets .mp-img-price{width:88px}' +
      '.mp-img-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}' +
      '.mp-img-card{border:1px solid rgba(255,255,255,.09);border-radius:16px;overflow:hidden;background:rgba(255,255,255,.025);cursor:pointer;display:flex;flex-direction:column;transition:border-color .15s,transform .15s}' +
      '.mp-img-card:hover{border-color:rgba(124,58,237,.6);transform:translateY(-2px)}' +
      '.mp-img-card-cover{position:relative;aspect-ratio:1/1;background:rgba(124,58,237,.10);overflow:hidden;display:flex;align-items:center;justify-content:center}' +
      '.mp-img-card-cover-img{width:100%;height:100%;object-fit:cover;display:block}' +
      '.mp-img-card-cover-fallback{font-size:2.4rem;opacity:.5}' +
      '.mp-img-card-ratio{position:absolute;bottom:8px;right:8px;padding:2px 8px;border-radius:999px;background:rgba(0,0,0,.6);color:#fff;font-size:.66rem;font-weight:600}' +
      '.mp-img-card-body{padding:11px 13px 13px;display:flex;flex-direction:column;gap:6px}' +
      '.mp-img-card-title{font-weight:700;color:#f3f0ff;font-size:.95rem;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.mp-img-card-badges{display:flex;flex-wrap:wrap;gap:5px;align-items:center}' +
      '.mp-img-card-price{margin-top:2px;font-size:.86rem;color:#cbb3ff;font-weight:700}' +
      '.mp-img-card-price span{font-size:.7rem;color:#8b7bd8;font-weight:600}' +
      '.mp-img-card-foot{margin-top:2px;display:flex;align-items:center;justify-content:space-between;gap:8px}' +
      '.mp-img-card-state{font-weight:700;font-size:.82rem}' +
      '.mp-img-card-state.owned{color:#4ADE80}' +
      '.mp-img-card-state.mine{color:#8b7bd8;font-size:.78rem}' +
      '.mp-img-card[data-owned="1"]{cursor:default}' +
      '.mp-img-card[data-owned="1"]:hover{transform:none}';
    document.head.appendChild(st);
  }

  // État des facettes images (page /images).
  var _imgFacets = { q: '', platform: '', rarity: '', ratio: '', style: '', tag: '', priceMin: '', priceMax: '' };

  async function _fetchImages() {
    var p = new URLSearchParams();
    if (_imgFacets.q) p.set('q', _imgFacets.q);
    if (_imgFacets.platform) p.set('platform', _imgFacets.platform);
    if (_imgFacets.rarity) p.set('rarity', _imgFacets.rarity);
    if (_imgFacets.ratio) p.set('ratio', _imgFacets.ratio);
    if (_imgFacets.style) p.set('style', _imgFacets.style);
    if (_imgFacets.tag) p.set('tag', _imgFacets.tag);
    if (_imgFacets.priceMin !== '') p.set('price_min', _imgFacets.priceMin);
    if (_imgFacets.priceMax !== '') p.set('price_max', _imgFacets.priceMax);
    try {
      var data = await window.apiFetch('/images?' + p.toString(), { auth: false });
      return (data && Array.isArray(data.images)) ? data.images : [];
    } catch (_) { return []; }
  }

  async function _renderImagesPage() {
    _injectImagesStyles();
    var anchor = document.querySelector('.mp-section-sons');
    if (!anchor || !anchor.parentNode) return;

    // C4 — deep-link : /images?tag=avatar (et &style=…) ouvre la grille DÉJÀ
    // filtrée. On lit les query params AVANT le 1er fetch et on pré-remplit les
    // facettes correspondantes (valeurs validées contre les codes backend connus
    // pour éviter d'injecter une valeur bidon dans un <select>).
    var _qp = new URLSearchParams(location.search);
    var _qpTag = (_qp.get('tag') || '').trim().toLowerCase();
    var _qpStyle = (_qp.get('style') || '').trim().toLowerCase();
    if (_qpTag && _IMG_USAGE.some(function (o) { return o.val === _qpTag; })) {
      _imgFacets.tag = _qpTag;
    }
    if (_qpStyle && _IMG_STYLES.some(function (o) { return o.val === _qpStyle; })) {
      _imgFacets.style = _qpStyle;
    }
    var _isAvatarView = _imgFacets.tag === 'avatar';

    var section = document.createElement('section');
    section.className = 'mp-section mp-section-images';
    var platformOpts = '<option value="">Toute provenance</option>' +
      _IMG_PLATFORMS.map(function (o) { return '<option value="' + o.val + '">' + _esc(o.label) + '</option>'; }).join('');
    var rarityOpts = '<option value="">Toute rareté</option>' +
      _IMG_RARITIES.map(function (o) { return '<option value="' + o.val + '">' + _esc(o.label) + '</option>'; }).join('');
    var styleOpts = '<option value="">Tous styles</option>' +
      _IMG_STYLES.map(function (o) { return '<option value="' + o.val + '">' + _esc(o.label) + '</option>'; }).join('');
    var usageOpts = '<option value="">Tous usages</option>' +
      _IMG_USAGE.map(function (o) { return '<option value="' + o.val + '">' + _esc(o.label) + '</option>'; }).join('');
    section.innerHTML =
      '<div class="mp-section-head">' +
        '<span class="mp-section-kicker">Catalogue</span>' +
        '<h2 class="mp-section-title">' + (_isAvatarView ? '🧑‍🎤 Avatars' : '🖼️ Images IA') + '</h2>' +
        '<span class="mp-section-sub">L\'aperçu est public — l\'achat débloque la recette (prompt + réglages) + l\'image originale</span>' +
      '</div>' +
      '<div class="mp-img-facets">' +
        '<input type="search" class="mp-img-q" placeholder="Titre, artiste…" autocomplete="off">' +
        '<select class="mp-img-platform" aria-label="Provenance">' + platformOpts + '</select>' +
        '<select class="mp-img-rarity" aria-label="Rareté">' + rarityOpts + '</select>' +
        '<select class="mp-img-style" aria-label="Style">' + styleOpts + '</select>' +
        '<select class="mp-img-tag" aria-label="Usage">' + usageOpts + '</select>' +
        '<input type="text" class="mp-img-ratio" placeholder="Ratio (ex 1:1)" style="width:120px">' +
        '<input type="number" min="0" class="mp-img-price mp-img-pmin" placeholder="Prix min">' +
        '<input type="number" min="0" class="mp-img-price mp-img-pmax" placeholder="Prix max">' +
      '</div>' +
      '<div class="mp-img-grid"><div class="mp-grid-empty">Chargement des images…</div></div>';
    anchor.parentNode.insertBefore(section, anchor);

    var grid = section.querySelector('.mp-img-grid');

    async function _reload() {
      var imgs = await _fetchImages();
      if (!imgs.length) {
        var anyFilter = _imgFacets.q || _imgFacets.platform || _imgFacets.rarity || _imgFacets.ratio || _imgFacets.style || _imgFacets.tag || _imgFacets.priceMin !== '' || _imgFacets.priceMax !== '';
        grid.innerHTML = '<div class="mp-grid-empty">' +
          (anyFilter
            ? 'Aucune image ne correspond à ta sélection.'
            : 'Aucune image en vente pour le moment. Les artistes les publient depuis leur WATT BOARD (monde Visuel).') +
          '</div>';
        return;
      }
      grid.innerHTML = imgs.map(_imgCardHtml).join('');
      grid._cache = {};
      imgs.forEach(function (im) { grid._cache[im.id] = im; });
      // Hydrate le cœur ❤️ (état liked) via le système wishlist partagé.
      if (window.SmylePlaylists && typeof window.SmylePlaylists.hydrateImgLikes === 'function') {
        window.SmylePlaylists.hydrateImgLikes();
      }
    }

    // Branchements facettes (debounce léger sur le texte/prix).
    var qEl = section.querySelector('.mp-img-q');
    var platEl = section.querySelector('.mp-img-platform');
    var rarEl = section.querySelector('.mp-img-rarity');
    var styleEl = section.querySelector('.mp-img-style');
    var tagEl = section.querySelector('.mp-img-tag');
    var ratioEl = section.querySelector('.mp-img-ratio');
    var pminEl = section.querySelector('.mp-img-pmin');
    var pmaxEl = section.querySelector('.mp-img-pmax');
    // C4 — reflète les facettes pré-remplies depuis l'URL dans les selects
    // (l'option « Avatar » / le style ciblé apparaissent sélectionnés d'emblée).
    if (_imgFacets.tag) tagEl.value = _imgFacets.tag;
    if (_imgFacets.style) styleEl.value = _imgFacets.style;
    var _t = null;
    function _deb() { clearTimeout(_t); _t = setTimeout(_reload, 240); }
    qEl.addEventListener('input', function () { _imgFacets.q = qEl.value.trim(); _deb(); });
    ratioEl.addEventListener('input', function () { _imgFacets.ratio = ratioEl.value.trim(); _deb(); });
    pminEl.addEventListener('input', function () { _imgFacets.priceMin = pminEl.value; _deb(); });
    pmaxEl.addEventListener('input', function () { _imgFacets.priceMax = pmaxEl.value; _deb(); });
    platEl.addEventListener('change', function () { _imgFacets.platform = platEl.value; _reload(); });
    rarEl.addEventListener('change', function () { _imgFacets.rarity = rarEl.value; _reload(); });
    styleEl.addEventListener('change', function () { _imgFacets.style = styleEl.value; _reload(); });
    tagEl.addEventListener('change', function () { _imgFacets.tag = tagEl.value; _reload(); });

    // Clic carte → fiche/drawer d'achat (recette masquée avant achat). On NE
    // rouvre PAS le drawer pour une image déjà possédée / dont on est l'auteur.
    grid.addEventListener('click', function (e) {
      var card = e.target.closest('.mp-img-card');
      if (!card) return;
      if (card.dataset.owned === '1') return; // possédé / auteur → état neutre
      var im = grid._cache && grid._cache[card.dataset.imageId];
      if (im) _openImageDetailDrawer(im);
    });

    // Possession chargée AVANT le 1er rendu (sinon flash « Acheter » sur une
    // image possédée). Auth requise ; dégrade en état public si non connecté.
    await _loadOwnedImages();
    await _reload();
  }

  // ── Monde Image sur la HOME (C4 étape 2) ─────────────────────────────────
  // Sections miroir de la musique : Top Images, Top Artistes Image, catalogue
  // images. Réutilise _imgCardHtml / _imgPreviewUrl / _openImageDetailDrawer.
  // Hydraté une seule fois (lazy) au premier passage en mode image.

  async function _fetchTopImages(limit) {
    try {
      const data = await window.apiFetch('/images/top?limit=' + (limit || 10), { auth: false });
      return (data && Array.isArray(data.images)) ? data.images : [];
    } catch (_) { return []; }
  }

  async function _fetchTopImageArtists(limit) {
    try {
      const data = await window.apiFetch('/artists/images-top?limit=' + (limit || 10), { auth: false });
      return (data && Array.isArray(data.artists)) ? data.artists : [];
    } catch (_) { return []; }
  }

  async function _fetchHomeImages() {
    try {
      // Catalogue home : on prend les plus récentes (cap home côté affichage).
      const data = await window.apiFetch('/images?limit=12', { auth: false });
      return (data && Array.isArray(data.images)) ? data.images : [];
    } catch (_) { return []; }
  }

  async function _fetchOeuvres(limit) {
    try {
      const data = await window.apiFetch('/oeuvres?limit=' + (limit || 12), { auth: false });
      return (data && Array.isArray(data.oeuvres)) ? data.oeuvres : [];
    } catch (_) { return []; }
  }

  // Top Images — liste classée (rang + vignette + titre + score ventes/likes).
  function _renderTopImages(imgs) {
    const el = document.getElementById('mp-top-images');
    if (!el) return;
    if (!imgs.length) {
      el.innerHTML = '<li class="mp-ranking-empty">Aucune image pour le moment.</li>';
      return;
    }
    el.innerHTML = imgs.map((im, i) => {
      const url   = _imgPreviewUrl(im.previewKey);
      const thumb = url
        ? '<img class="mp-ranking-thumb" src="' + _esc(url) + '" alt="" loading="lazy">'
        : '<div class="mp-ranking-thumb" style="display:flex;align-items:center;justify-content:center">🖼️</div>';
      const sold  = im.soldCount || 0;
      const likes = im.likesCount || 0;
      const sub   = [im.imagePlatform ? _esc(im.imagePlatform) : '', likes ? (likes + ' ❤️') : '']
        .filter(Boolean).join(' · ') || '&nbsp;';
      return (
        '<li class="mp-ranking-row mp-img-ranking-row" data-image-id="' + _esc(im.id) + '" style="cursor:pointer">' +
          '<div class="mp-ranking-rank">' + (i + 1) + '</div>' +
          thumb +
          '<div class="mp-ranking-main">' +
            '<div class="mp-ranking-title">' + _esc(im.title || 'Sans titre') + '</div>' +
            '<div class="mp-ranking-sub">' + sub + '</div>' +
          '</div>' +
          '<div class="mp-ranking-meta">' + _esc(im.priceCredits) + ' Smyles</div>' +
        '</li>'
      );
    }).join('') +
      '<li style="list-style:none"><a class="mp-voir-tout" href="/images">Voir toutes les images →</a></li>';

    // Cache pour le clic → drawer.
    el._imgCache = {};
    imgs.forEach(im => { el._imgCache[im.id] = im; });
    if (!el._bound) {
      el._bound = true;
      el.addEventListener('click', (e) => {
        const row = e.target.closest('.mp-img-ranking-row');
        if (!row) return;
        const im = el._imgCache && el._imgCache[row.dataset.imageId];
        if (im) _openImageDetailDrawer(im);
      });
    }
  }

  // Top Artistes Image — podium réutilisant le style du Top Artistes musique,
  // classé par imageScore (ventes + likes de leurs images).
  function _renderTopImageArtists(arts) {
    const el = document.getElementById('mp-top-artists-image');
    if (!el) return;
    const community = arts.filter(a => !a.isOfficial);
    if (community.length === 0) {
      el.innerHTML =
        '<li style="list-style:none">' +
          '<div style="text-align:center;padding:30px 18px;border:1px dashed rgba(255,255,255,.13);border-radius:16px;background:rgba(255,255,255,.02)">' +
            '<div style="font-size:1.8rem;margin-bottom:6px">🖼️</div>' +
            '<div style="font-weight:800;color:#fff;font-size:1.02rem;margin-bottom:4px">Pas encore de créateur visuel classé</div>' +
            '<div style="font-size:.84rem;color:#a09cb8;max-width:340px;margin:0 auto 14px">Publie des images IA depuis ton WATT BOARD — le classement se construit aux ventes et aux likes.</div>' +
            '<a href="/dashboard" style="display:inline-block;padding:10px 20px;border-radius:999px;background:linear-gradient(90deg,#7C3AED,#a855f7);color:#fff;font-weight:700;font-size:.86rem;text-decoration:none">Deviens créateur visuel →</a>' +
          '</div>' +
        '</li>';
      return;
    }
    const top3 = community.slice(0, 3);
    const rest = community.slice(3, 10);
    const MEDAL = ['🥇', '🥈', '🥉'];
    const _spot = (a, rankIdx) => {
      const big = rankIdx === 0;
      const sz = big ? 80 : 60;
      const href = a.slug ? '/@' + a.slug : '#';
      const name = a.artistName || 'Sans nom';
      const color = a.brandColor || '#7C3AED';
      const avatar = a.avatarUrl
        ? `<img src="${_esc(a.avatarUrl)}" alt="" style="width:100%;height:100%;object-fit:cover">`
        : `<span style="font-weight:800;color:#fff;font-size:${big ? 1.6 : 1.2}rem">${_esc(_initial(name))}</span>`;
      return (
        `<a href="${_esc(href)}" style="flex:1;max-width:130px;display:flex;flex-direction:column;align-items:center;gap:5px;text-decoration:none;${big ? 'transform:translateY(-10px)' : ''}">` +
          `<div style="font-size:${big ? 1.5 : 1.2}rem">${MEDAL[rankIdx]}</div>` +
          `<div style="width:${sz}px;height:${sz}px;border-radius:50%;overflow:hidden;background:${_esc(color)};display:flex;align-items:center;justify-content:center;border:2px solid ${big ? '#FFD700' : 'rgba(255,255,255,.2)'};box-shadow:0 4px 18px ${big ? 'rgba(255,215,0,.25)' : 'rgba(0,0,0,.3)'}">${avatar}</div>` +
          `<div style="font-weight:700;color:#fff;font-size:${big ? '.95rem' : '.85rem'};text-align:center;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(name)}</div>` +
          `<div style="font-size:.72rem;color:#a09cb8">${_fmt(a.imagesSold || 0)} ventes</div>` +
        `</a>`
      );
    };
    const spots = [];
    if (top3[1]) spots.push(_spot(top3[1], 1));
    if (top3[0]) spots.push(_spot(top3[0], 0));
    if (top3[2]) spots.push(_spot(top3[2], 2));
    const podium =
      '<li style="list-style:none;margin-bottom:14px">' +
        '<div style="display:flex;align-items:flex-end;justify-content:center;gap:14px;padding:18px 8px 8px">' + spots.join('') + '</div>' +
      '</li>';
    const list = rest.map((a, i) => {
      const href = a.slug ? '/@' + a.slug : '#';
      const name = a.artistName || 'Sans nom';
      const parts = [a.city, a.genre].filter(Boolean).map(_esc).join(' · ');
      return (
        `<li class="mp-ranking-row" onclick="window.location.href='${_esc(href)}'">` +
          `<div class="mp-ranking-rank">${i + 4}</div>` +
          `<div class="mp-ranking-main">` +
            `<div class="mp-ranking-title">${_esc(name)}</div>` +
            `<div class="mp-ranking-sub">${parts || '&nbsp;'}</div>` +
          `</div>` +
          `<div class="mp-ranking-meta">${_fmt(a.imagesSold || 0)} ventes</div>` +
        `</li>`
      );
    }).join('');
    el.innerHTML = podium + list;
  }

  // Catalogue images sur la home (cap home) — réutilise _imgCardHtml.
  function _renderHomeImagesGrid(imgs) {
    const el = document.getElementById('mp-grid-images-home');
    if (!el) return;
    if (!imgs.length) {
      el.innerHTML = '<div class="mp-grid-empty">Aucune image en vente pour le moment. Les artistes les publient depuis leur WATT BOARD (monde Visuel).</div>';
      return;
    }
    _injectImagesStyles();
    const capped = imgs.slice(0, HOME_CAP);
    el.innerHTML = capped.map(_imgCardHtml).join('') +
      (imgs.length > HOME_CAP
        ? '<a class="mp-voir-tout" href="/images" style="grid-column:1/-1;margin-top:14px">Voir toutes les images →</a>'
        : '');
    el._cache = {};
    capped.forEach(im => { el._cache[im.id] = im; });
    if (!el._bound) {
      el._bound = true;
      el.addEventListener('click', (e) => {
        const card = e.target.closest('.mp-img-card');
        if (!card) return;
        if (card.dataset.owned === '1') return;
        const im = el._cache && el._cache[card.dataset.imageId];
        if (im) _openImageDetailDrawer(im);
      });
    }
    if (window.SmylePlaylists && typeof window.SmylePlaylists.hydrateImgLikes === 'function') {
      window.SmylePlaylists.hydrateImgLikes();
    }
  }

  // ── C4 ADN Album — catalogue des génomes de style visuel en vente ─────────
  // Miroir du catalogue ADN Playlist. GET /catalog/albums-adn renvoie un teaser
  // GATÉ : { id, title, dna_description, adn_style, adn_price, owner }. Le
  // génome (seedPrompt + palette) n'est JAMAIS exposé ici — clic → fiche album
  // (openAlbumViewModal) où l'achat se fait, puis le génome est révélé.
  async function _fetchAlbumAdns() {
    try {
      const data = await window.apiFetch('/catalog/albums-adn?per_page=24', { auth: false });
      return (data && Array.isArray(data.items)) ? data.items : [];
    } catch (_) { return []; }
  }

  function _albumAdnCardHtml(a) {
    const owner = a.owner || {};
    const ownerName = owner.artist_name || owner.artistName || 'Artiste';
    const styleChip = a.adn_style
      ? '<span class="mp-adn-card-style">' + _esc(a.adn_style) + '</span>' : '';
    const desc = a.dna_description
      ? '<div class="mp-adn-card-desc">' + _esc(a.dna_description) + '</div>'
      : '<div class="mp-adn-card-desc mp-adn-card-desc--muted">Un ADN donne des résultats dans le même esprit, jamais identiques.</div>';
    return '' +
      '<article class="mp-adn-card" data-album-id="' + _esc(a.id) + '" tabindex="0" role="button" title="Voir l\'ADN de l\'album">' +
        '<div class="mp-adn-card-top">' +
          '<span class="mp-adn-card-ico">🎨</span>' +
          '<span class="mp-adn-card-title">' + _esc(a.title || 'Album') + '</span>' +
          styleChip +
        '</div>' +
        desc +
        '<div class="mp-adn-card-foot">' +
          '<span class="mp-adn-card-owner">' + _esc(ownerName) + '</span>' +
          '<span class="mp-adn-card-price">' + _esc(a.adn_price) + ' <span>Smyles</span></span>' +
        '</div>' +
      '</article>';
  }

  function _injectAlbumAdnStyles() {
    if (document.getElementById('mp-adn-style')) return;
    const st = document.createElement('style');
    st.id = 'mp-adn-style';
    st.textContent =
      '.mp-adn-card{border:1px solid rgba(204,136,255,.2);border-radius:16px;padding:14px 15px;background:rgba(204,136,255,.05);cursor:pointer;display:flex;flex-direction:column;gap:9px;transition:border-color .15s,transform .15s}' +
      '.mp-adn-card:hover{border-color:rgba(204,136,255,.6);transform:translateY(-2px)}' +
      '.mp-adn-card-top{display:flex;align-items:center;gap:7px;flex-wrap:wrap}' +
      '.mp-adn-card-ico{font-size:18px}' +
      '.mp-adn-card-title{font-weight:700;color:#f3e9ff;font-size:.98rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.mp-adn-card-style{font-size:10px;font-weight:700;color:#cc88ff;background:rgba(204,136,255,.14);border:1px solid rgba(204,136,255,.3);border-radius:999px;padding:1px 8px}' +
      '.mp-adn-card-desc{font-size:12.5px;color:#cdc7e2;line-height:1.5;min-height:36px}' +
      '.mp-adn-card-desc--muted{color:#8b86a3;font-style:italic}' +
      '.mp-adn-card-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:2px}' +
      '.mp-adn-card-owner{font-size:11.5px;color:#a09cb8}' +
      '.mp-adn-card-price{font-size:.92rem;color:#cbb3ff;font-weight:700}' +
      '.mp-adn-card-price span{font-size:.68rem;color:#8b7bd8;font-weight:600}';
    document.head.appendChild(st);
  }

  function _renderAlbumAdnCatalog(items) {
    const el = document.getElementById('mp-grid-albums-adn');
    if (!el) return;
    if (!items.length) {
      el.innerHTML = '<div class="mp-grid-empty">Aucun ADN Album en vente pour le moment. Les artistes les mettent en vente depuis leurs albums (My Mix, monde Image).</div>';
      return;
    }
    _injectAlbumAdnStyles();
    el.innerHTML = items.map(_albumAdnCardHtml).join('');
    if (!el._bound) {
      el._bound = true;
      el.addEventListener('click', (e) => {
        const card = e.target.closest('.mp-adn-card');
        if (!card) return;
        const id = card.dataset.albumId;
        // Clic → fiche album (teaser + bouton d'achat de l'ADN). Le génome
        // reste gaté côté backend tant que l'ADN n'est pas acheté.
        if (id && window.SmyleAlbums && typeof window.SmyleAlbums.openAlbumViewModal === 'function') {
          window.SmyleAlbums.openAlbumViewModal(id);
        }
      });
    }
  }

  // Section Œuvre complète — carte ID SCINDÉE son|visuel (binarité, D2 2026-07-01).
  // Réutilise renderOeuvreCard (banner-card.js) : moitié gauche = SON, moitié
  // droite = VISUEL, badges de provenance des deux côtés. Clic → drawer du son
  // (comportement conservé). Fallback ancienne double-cover si le composant
  // n'est pas chargé (dégradation gracieuse).
  function _renderOeuvres(oeuvres) {
    const section = document.getElementById('mp-section-oeuvres');
    const el = document.getElementById('mp-grid-oeuvres');
    if (!section || !el) return;
    if (!oeuvres.length) {
      // Pas d'œuvre → on masque entièrement la section (pas d'état vide bruyant).
      section.hidden = true;
      return;
    }
    section.hidden = false;
    const hasSplit = (typeof window.renderOeuvreCard === 'function');
    el.innerHTML = oeuvres.map(o => {
      const son = o.sound || {};
      const img = o.image || {};
      if (hasSplit) {
        // Mapping /oeuvres → carte scindée. Le payload liste ne porte pas la
        // plateforme IA → défauts du composant (Suno / ChatGPT), cohérents avec
        // le contenu WATT. Enrichissement backend possible en suivi.
        const card = window.renderOeuvreCard({
          title:  son.title || 'Œuvre complète',
          son:    { title: son.title || 'Son', platform: son.platform || '', color: son.color || '' },
          visuel: { title: son.title || 'Visuel', previewKey: img.previewKey || '', platform: img.platform || '' },
        }, { href: '#' });
        return '<div class="mp-oeuvre-slot" data-son-id="' + _esc(son.id || '') + '">' + card + '</div>';
      }
      // Fallback (composant absent) : ancienne carte double-cover.
      const sonCover = son.coverUrl
        ? '<img src="' + _esc(son.coverUrl) + '" alt="" loading="lazy">'
        : '<div class="mp-oeuvre-card-cover-fallback" aria-hidden="true">🎵</div>';
      const imgUrl = _imgPreviewUrl(img.previewKey);
      const imgCover = imgUrl
        ? '<img src="' + _esc(imgUrl) + '" alt="" loading="lazy">'
        : '<div class="mp-oeuvre-card-cover-fallback" aria-hidden="true">🖼️</div>';
      return (
        '<article class="mp-oeuvre-card" data-son-id="' + _esc(son.id || '') + '" tabindex="0" role="button" title="Voir l\'œuvre">' +
          '<div class="mp-oeuvre-card-covers">' +
            '<div class="mp-oeuvre-card-cover">' + sonCover + '</div>' +
            '<div class="mp-oeuvre-card-cover">' + imgCover + '</div>' +
          '</div>' +
          '<div class="mp-oeuvre-card-body">' +
            '<div class="mp-oeuvre-card-title">' + _esc(son.title || 'Œuvre complète') + '</div>' +
          '</div>' +
        '</article>'
      );
    }).join('');
    el._cache = {};
    oeuvres.forEach(o => { if (o.sound && o.sound.id) el._cache[o.sound.id] = o; });
    if (!el._bound) {
      el._bound = true;
      el.addEventListener('click', (e) => {
        const card = e.target.closest('.mp-oeuvre-slot, .mp-oeuvre-card');
        if (!card) return;
        // La carte scindée est un <a href="#"> → on neutralise le saut d'ancre.
        e.preventDefault();
        const sonId = card.dataset.sonId;
        // Clic → fiche du SON (drawer track existant). On retrouve le track
        // par son promptId (chaque track-recent porte promptId du son lié).
        const track = _state.tracks.find(t => String(t.promptId) === String(sonId));
        if (track) { _openTrackDetailDrawer(track); return; }
        // Fallback : si pas de track chargé (mode image sans tracks), ouvre la
        // fiche image partenaire (achat séparé conservé côté image).
        const o = el._cache && el._cache[sonId];
        if (o && o.image) {
          _openImageDetailDrawer({
            id: o.image.id,
            priceCredits: o.image.priceCredits,
            previewKey: o.image.previewKey,
            title: o.sound ? o.sound.title : 'Image',
            linkedSound: o.sound || null,
          });
        }
      });
    }
  }

  // Hydrate le Monde Image (Top Images + Top Artistes Image + catalogue) au
  // premier passage en mode image. Idempotent (flag _imageWorldLoaded).
  async function _loadImageWorld() {
    if (_imageWorldLoaded) return;
    _imageWorldLoaded = true;
    const [topImgs, topArts, homeImgs, albumAdns] = await Promise.all([
      _fetchTopImages(10),
      _fetchTopImageArtists(10),
      _fetchHomeImages(),
      _fetchAlbumAdns(),
    ]);
    _renderTopImages(topImgs);
    _renderTopImageArtists(topArts);
    _renderHomeImagesGrid(homeImgs);
    _renderAlbumAdnCatalog(albumAdns);
  }

  // Applique un mode (musique|image) : pose la classe body, met à jour les
  // onglets, persiste, et hydrate paresseusement le Monde Image si besoin.
  function _applyMode(mode, opts) {
    const m = (mode === 'image') ? 'image' : 'musique';
    document.body.classList.toggle('mp-mode-musique', m === 'musique');
    document.body.classList.toggle('mp-mode-image', m === 'image');
    document.querySelectorAll('.mp-mode-btn').forEach(btn => {
      const active = btn.dataset.mode === m;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    if (!opts || opts.persist !== false) _writeMode(m);
    if (m === 'image') _loadImageWorld();

    // Le panneau de filtres inline (home) dépend du mode : moods/rôles musique
    // OU styles/usages/créateurs image. On le REDESSINE au changement de mode
    // (sinon il reste figé sur la musique — bug signalé 2026-06-25). On purge
    // au passage les filtres musique actifs, sans objet en mode image.
    if (_VIEW === 'home') {
      _pageMoodSet.clear();
      _pageRoleSet.clear();
      const hint = document.querySelector('.mp-hero-search-hint');
      if (hint) { hint.dataset.searchBar = ''; _installPageSearchBar(); }
    }
  }

  // Branche le commutateur (clic onglet) + restaure le mode persisté. Appelé
  // UNIQUEMENT sur la home (guard dans _boot).
  function _bindModeSwitch() {
    const sw = document.getElementById('mp-mode-switch');
    if (!sw) return;
    sw.addEventListener('click', (e) => {
      const btn = e.target.closest('.mp-mode-btn');
      if (!btn) return;
      _applyMode(btn.dataset.mode);
    });
    // Restaure le mode persisté au chargement (défaut musique).
    _applyMode(_readMode(), { persist: false });
  }

  // Fiche/drawer image : panneau latéral (miroir du drawer son) qui AGRANDIT
  // l'aperçu en haut + métadonnées publiques + prix + rareté/œuvre. La recette
  // (prompt/réglages/original) reste MASQUÉE — débloquée à l'achat via
  // PurchaseDrawer (type 'image' → /unlocks/prompts/{id}). N'expose AUCUN champ
  // gaté : on ne lit que les champs publics de _image_public_dict.
  function _openImageDetailDrawer(im) {
    const existing = document.getElementById('mp-image-detail-drawer');
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);

    const title    = im.title || 'Image IA';
    const price    = (im.priceCredits != null) ? im.priceCredits : null;
    const previewUrl = _imgPreviewUrl(im.previewKey);
    const owned    = _ownedImageIds.has(String(im.id));
    const mine     = (_myUserId && im.artistId && String(im.artistId) === String(_myUserId));

    // Héros : grande zone d'aperçu (object-fit:contain pour respecter le ratio
    // de l'image), fond sombre. Fallback joli si pas de previewKey.
    const heroHTML = previewUrl
      ? `<img src="${_esc(previewUrl)}" alt="${_esc(title)}" class="mp-id-hero-img" loading="lazy" oncontextmenu="return false" draggable="false" />`
      : `<div class="mp-id-hero-fallback" aria-hidden="true">🖼️</div>`;

    // Badges publics : nature image · palier · rareté #X/N · provenance · œuvre.
    const bNature = window.SpBadges ? SpBadges.nature('image') : '';
    const bPalier = window.SpBadges ? SpBadges.palier('standard') : '';
    const bRar    = _imgRareteBadge(im);
    const bProv   = window.SpBadges ? SpBadges.provenance(im.imagePlatform, im.imageModelVersion) : '';
    const bOeuvre = (im.isOeuvreComplete && window.SpBadges && SpBadges.oeuvre) ? SpBadges.oeuvre() : '';
    const badgesHTML = (bNature || bPalier || bRar || bProv || bOeuvre)
      ? `<div class="mp-id-badges">${bNature}${bPalier}${bRar}${bProv}${bOeuvre}</div>`
      : '';

    // Artiste (nom + lien /@slug) — parité fiche son. Affiché seulement si le
    // payload public l'expose (artistName + artistSlug) ; sinon rien (pas de
    // « — » moche).
    const artistHTML = (im.artistName && im.artistSlug)
      ? `<a class="mp-id-artist" href="/@${_esc(im.artistSlug)}">${_esc(im.artistName)}</a>`
      : '';

    const ratioMeta = im.ratio
      ? `<div class="mp-id-meta-line">Format ${_esc(im.ratio)}</div>`
      : '';

    // C4 galerie avatar — bande d'aperçus PUBLICS (previewKey). Les originaux HD
    // ne s'obtiennent qu'à l'achat (downloadUrl gaté). En pratique, seuls les
    // avatars ont une galerie. galleryPreviews = liste de previewKey publics.
    const galCount = im.galleryCount || 0;
    const galPreviews = Array.isArray(im.galleryPreviews) ? im.galleryPreviews : [];
    const galleryBlockHTML = (galCount > 0)
      ? `<div class="mp-id-gallery">
           <div class="mp-id-gallery-label">🖼 ${galCount} visuel${galCount > 1 ? 's' : ''} inclus</div>
           <div class="mp-id-gallery-strip">
             ${galPreviews.map(k => {
               const u = _imgPreviewUrl(k);
               return u
                 ? `<img src="${_esc(u)}" alt="" class="mp-id-gallery-thumb" loading="lazy" oncontextmenu="return false" draggable="false" />`
                 : '';
             }).join('')}
           </div>
           <div class="mp-id-gallery-note">L'achat débloque tous les visuels en haute définition + la recette.</div>
         </div>`
      : '';
    const descMeta = im.description
      ? `<div class="mp-id-desc">${_esc(im.description)}</div>`
      : '';

    // Bloc « Œuvre complète » : son lié (aperçu only, achat séparé du son).
    const ls = im.linkedSound || null;
    const oeuvreBlockHTML = ls
      ? `<div class="mp-id-linked">
           <div class="mp-id-linked-label">Œuvre complète</div>
           <div class="mp-id-linked-row">
             ${ls.coverUrl
               ? `<img src="${_esc(ls.coverUrl)}" alt="" class="mp-id-linked-cover" loading="lazy" />`
               : `<div class="mp-id-linked-cover mp-id-linked-cover-fallback">🎵</div>`}
             <div class="mp-id-linked-main">
               <div class="mp-id-linked-title">${_esc(ls.title || 'Son lié')}</div>
               <div class="mp-id-linked-price">🎵 ${_esc(ls.priceCredits)} <span>Smyles</span></div>
             </div>
             <button class="mp-id-linked-btn" id="mp-id-linked-btn" type="button">Voir le son</button>
           </div>
         </div>`
      : '';

    // Bouton ❤️ wishlist image : réutilise le mécanisme global (capturing
    // listener sur [data-img-like-btn] dans playlists.js) → fonctionne et reste
    // synchro avec les cards (hydrateImgLikes applique la classe .liked).
    const likeHTML = `
      <div class="mp-id-social-row">
        <button class="like-btn mp-id-like-btn" type="button" data-img-like-btn="${_esc(im.id)}"
                title="Ajouter à ma Wishlist" aria-label="Ajouter à ma Wishlist"></button>
        <button class="add-to-pl-btn mp-id-album-btn" type="button" data-add-to-album="${_esc(im.id)}"
                title="Ajouter à un album" aria-label="Ajouter à un album">+ Album</button>
      </div>`;

    // CTA achat / état possession. On GARDE PurchaseDrawer pour la confirmation
    // d'achat ; cette fiche vient AVANT.
    let ctaHTML;
    if (mine) {
      ctaHTML = `<div class="mp-id-state mine">À toi (créateur)</div>`;
    } else if (owned) {
      ctaHTML = `<div class="mp-id-state owned">✓ Possédée — recette dans ta bibliothèque</div>`;
    } else if (im.isSoldOut) {
      ctaHTML = `<button class="mp-id-buy" type="button" disabled>Édition épuisée</button>`;
    } else {
      const priceLabel = (price != null) ? (price + ' Smyles') : 'Smyles';
      ctaHTML = `<button class="mp-id-buy" id="mp-id-buy-btn" type="button">🔓 Débloquer · ${_esc(priceLabel)}</button>`;
    }

    const overlay = document.createElement('div');
    overlay.id        = 'mp-image-detail-drawer';
    overlay.className = 'mp-id-overlay';
    overlay.innerHTML = `
      <aside class="mp-id-drawer" role="dialog" aria-modal="true" aria-label="Détail de l'image">
        <button class="mp-id-close" aria-label="Fermer">✕</button>
        <div class="mp-id-hero">${heroHTML}</div>
        <div class="mp-id-body">
          <div class="mp-id-type">Image</div>
          <h2 class="mp-id-title">${_esc(title)}</h2>
          ${artistHTML}
          ${badgesHTML}
          ${ratioMeta}
          ${descMeta}
          ${galleryBlockHTML}
          ${likeHTML}
          ${oeuvreBlockHTML}
          <div class="mp-id-cta">${ctaHTML}</div>
        </div>
      </aside>`;

    document.body.appendChild(overlay);
    // Synchronise l'état liked du cœur (classe .liked) avec le cache wishlist.
    if (window.SmylePlaylists && typeof window.SmylePlaylists.hydrateImgLikes === 'function') {
      window.SmylePlaylists.hydrateImgLikes();
    }
    requestAnimationFrame(() => {
      overlay.classList.add('is-open');
      const dr = overlay.querySelector('.mp-id-drawer');
      if (dr) dr.classList.add('is-open');
    });

    function _close() {
      overlay.classList.remove('is-open');
      const dr = overlay.querySelector('.mp-id-drawer');
      if (dr) dr.classList.remove('is-open');
      setTimeout(() => { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); }, 300);
    }

    overlay.addEventListener('click', (e) => { if (e.target === overlay) _close(); });
    overlay.querySelector('.mp-id-close').addEventListener('click', _close);
    document.addEventListener('keydown', function onEsc(e) {
      if (e.key === 'Escape') { _close(); document.removeEventListener('keydown', onEsc); }
    });

    // Achat → modale PurchaseDrawer (confirmation + débit + déblocage recette).
    const buyBtn = overlay.querySelector('#mp-id-buy-btn');
    if (buyBtn) {
      buyBtn.addEventListener('click', () => {
        if (!window.PurchaseDrawer) {
          if (window.showToast) window.showToast('Chargement du module d\'achat…');
          return;
        }
        _close();
        window.PurchaseDrawer.open({
          type: 'image',
          id: im.id,
          price: price,
          title: title,
          platform: im.imagePlatform || '',
          linkedSound: im.linkedSound || null,
        });
      });
    }

    // « Voir le son » lié → fiche du son si chargé, sinon drawer d'achat son.
    const lsBtn = overlay.querySelector('#mp-id-linked-btn');
    if (lsBtn && ls) {
      lsBtn.addEventListener('click', () => {
        const track = (_state.tracks || []).find(t => String(t.promptId) === String(ls.id));
        if (track) { _close(); _openTrackDetailDrawer(track); return; }
        if (window.PurchaseDrawer) {
          _close();
          window.PurchaseDrawer.open({
            type: 'son',
            id: ls.id,
            price: (ls.priceCredits != null ? ls.priceCredits : null),
            title: ls.title || 'Son lié',
          });
        }
      });
    }
  }

  // ── Modale achat recette (depuis badge Recette sur une track card) ────────
  // badgeEl a : data-prompt-id, data-prompt-price, data-track-name
  function _openRecipeUnlockModal(badgeEl) {
    const promptId   = badgeEl.dataset.promptId;
    const price      = parseInt(badgeEl.dataset.promptPrice, 10) || 0;
    const trackName  = badgeEl.dataset.trackName || 'ce son';

    // C2 — drawer d'achat unifié : remplace la modale locale (qui reste
    // ci-dessous en fallback si le composant n'est pas chargé).
    if (window.PurchaseDrawer) {
      window.PurchaseDrawer.open({ type: 'son', id: promptId, price: price || null, title: trackName });
      return;
    }

    if (document.getElementById('mp-recipe-modal')) return;

    const overlay = document.createElement('div');
    overlay.id = 'mp-recipe-modal';
    overlay.className = 'mp-recipe-modal-overlay';
    overlay.innerHTML = `
      <div class="mp-recipe-modal-box" role="dialog" aria-modal="true">
        <button class="mp-recipe-modal-close" aria-label="Fermer">&times;</button>
        <div class="mp-recipe-modal-icon">🔓</div>
        <h3 class="mp-recipe-modal-title">Recette · ${_esc(trackName)}</h3>
        <p class="mp-recipe-modal-desc">
          Débloque la recette Suno de <strong>${_esc(trackName)}</strong>
          pour régénérer ce son ou t’en inspirer.
        </p>
        <div class="mp-recipe-modal-price">
          <span class="mp-recipe-modal-price-val">${price}</span>
          <span class="mp-recipe-modal-price-unit">Smyles</span>
        </div>
        <div id="mp-recipe-market" style="margin:4px 0 6px;font-size:.8rem;color:#a79fc0;line-height:1.6"></div>
        <div class="mp-recipe-modal-actions">
          <button class="mp-recipe-modal-cancel">Annuler</button>
          <button class="mp-recipe-modal-confirm" id="mp-recipe-confirm-btn">
            Débloquer · ${price}
            <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
          </button>
        </div>
        <p class="mp-recipe-modal-note">
          La recette sera disponible dans ta bibliothèque après achat.
        </p>
      </div>
    `;

    document.body.appendChild(overlay);

    // Fiche CANONIQUE (modèle StockX) : on affiche l'offre primaire (stock
    // restant si édition limitée) + les offres secondaires (reventes) sur la
    // MÊME fiche. Un seul appel à l'ouverture.
    if (promptId) {
      (async () => {
        try {
          const m = await window.apiFetch('/resale/prompt/' + encodeURIComponent(promptId) + '/market');
          const el = overlay.querySelector('#mp-recipe-market');
          if (!el || !m) return;
          const parts = [];
          if (m.is_limited) {
            if (m.supply_left > 0) parts.push('🎟️ Édition limitée · <strong>' + m.supply_left + '/' + m.max_supply + '</strong> exemplaires au prix officiel');
            else parts.push('🔴 Édition limitée <strong>épuisée</strong> en primaire');
          } else {
            parts.push('♾️ Édition illimitée');
          }
          if (m.secondary && m.secondary.length) {
            parts.push('♻️ <strong>' + m.secondary.length + '</strong> en revente · à partir de <strong>' + m.secondary_from + ' Smyles</strong> (sur le profil du vendeur)');
          }
          el.innerHTML = parts.join('<br>');
          // Primaire épuisé → on bloque l'achat primaire (rediriger vers revente).
          if (m.is_limited && m.supply_left === 0) {
            const btn = overlay.querySelector('#mp-recipe-confirm-btn');
            if (btn) {
              btn.disabled = true;
              btn.style.opacity = '.5';
              btn.textContent = m.secondary && m.secondary.length ? 'Épuisé · dispo en revente' : 'Épuisé';
            }
          }
        } catch (_) { /* silencieux */ }
      })();
    }

    function _close() {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }

    overlay.querySelector('.mp-recipe-modal-close').addEventListener('click', _close);
    overlay.querySelector('.mp-recipe-modal-cancel').addEventListener('click', _close);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) _close(); });
    document.addEventListener('keydown', function onEsc(e) {
      if (e.key === 'Escape') { _close(); document.removeEventListener('keydown', onEsc); }
    });

    overlay.querySelector('#mp-recipe-confirm-btn').addEventListener('click', async () => {
      const btn = overlay.querySelector('#mp-recipe-confirm-btn');
      btn.disabled = true;
      btn.textContent = 'Déblocage…';
      try {
        const resp = await window.apiFetch(
          `/unlocks/prompts/${encodeURIComponent(promptId)}`,
          { method: 'POST' }
        );
        _close();
        const msg = (resp && resp.perk_applied)
          ? 'Recette débloquée avec perk ADN −30 % 🔓'
          : 'Recette débloquée 🔓 — retrouve-la dans ta bibliothèque';
        if (window.showToast) window.showToast(msg);
        // Marquer le badge comme owned
        document.querySelectorAll(`.mp-recipe-badge[data-prompt-id="${CSS.escape(promptId)}"]`).forEach(el => {
          el.classList.add('is-owned');
          el.title = 'Recette débloquée ✓';
        });
      } catch (err) {
        btn.disabled = false;
        btn.innerHTML = `Débloquer · ${price} <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`;
        const status = err && err.status;
        if (status === 401) {
          _close();
          if (window.showToast) window.showToast('Connecte-toi pour débloquer ce contenu.');
        } else if (status === 402) {
          const d = err.body && err.body.detail;
          const msg = (d && typeof d === 'object')
            ? `Crédits insuffisants — il te faut ${d.required}, tu en as ${d.available}.`
            : 'Crédits insuffisants.';
          if (window.showToast) window.showToast(msg);
        } else if (status === 409) {
          _close();
          if (window.showToast) window.showToast('Tu possèdes déjà cette recette.');
          document.querySelectorAll(`.mp-recipe-badge[data-prompt-id="${CSS.escape(promptId)}"]`).forEach(el => {
            el.classList.add('is-owned');
          });
        } else {
          if (window.showToast) window.showToast('Erreur lors du déblocage. Réessaie.');
          console.error('[marketplace] unlock recipe error:', err);
        }
      }
    });
  }

    // ── Boot ─────────────────────────────────────────────────────────────────

  async function _boot() {
    if (!_isMarketplacePage()) return;
    _injectViewStyles();
    if (_VIEW === 'sons')    { document.body.classList.add('mp-only-sons');    document.title = 'Tous les sons — WATT'; }
    if (_VIEW === 'beats')   {
      document.body.classList.add('mp-only-sons');
      document.title = 'Beats — WATT';
      // Tête de section adaptée à l'étagère beats.
      const _t = document.querySelector('.mp-section-sons .mp-section-title');
      if (_t) _t.innerHTML = '🥁 Beats';
      const _s = document.querySelector('.mp-section-sons .mp-section-sub');
      if (_s) _s.textContent = 'Des bases prêtes à chanter dessus — achat = fichier + recette';
    }
    if (_VIEW === 'artists') { document.body.classList.add('mp-only-artists'); document.title = 'Tous les artistes — WATT'; }
    if (_VIEW === 'voix') {
      document.body.classList.add('mp-only-voix');
      document.title = 'Voix — WATT';
      _renderVoixPage(); // async, autonome (fetch /api/voices + section dédiée)
    }
    if (_VIEW === 'images') {
      document.body.classList.add('mp-only-images');
      document.title = 'Images IA — WATT';
      _renderImagesPage(); // async, autonome (fetch /images + section + facettes)
    }
    _resolveDom();
    _bindSearch();
    _bindBus();
    _bindTrackClicks();

    // Trois fetches en parallèle — indépendants, pas de cascade.
    await Promise.all([_fetchSmyle(), _fetchArtists(), _fetchTracks()]);
    _renderAll();

    // C4 étape 2 — commutateur Musique ⇄ Image + section Œuvre complète,
    // UNIQUEMENT sur la home (les pages dédiées /sons, /images… gardent leur
    // comportement plein écran via mp-only-*). Le mode est restauré depuis
    // localStorage ; le Monde Image est hydraté paresseusement.
    if (_VIEW === 'home') {
      document.body.classList.add('mp-view-home');
      // Possession d'images chargée AVANT le rendu des cartes images (évite le
      // flash « Acheter » sur une image possédée). Dégrade en public si non co.
      await _loadOwnedImages();
      _bindModeSwitch();
      // Œuvre complète — affichée dans les deux modes (fetch indépendant).
      _fetchOeuvres(12).then(_renderOeuvres);
    }
    // 2026-06-11 — la barre de recherche vit aussi sur la HOME (dépliant
    // combiné moods DNA + rôles CONNECT), même process que /sons et
    // /artistes. Elle remplace le message « Utilise la loupe… ».
    _installPageSearchBar();
  }

  // Sur les pages dédiées (/sons, /artistes), remplace le message d'accueil
  // « Utilise la loupe… » par une vraie barre de recherche qui filtre la
  // grille en direct. La loupe topbar reste dispo pour la recherche par mood.
  function _installPageSearchBar() {
    const hint = document.querySelector('.mp-hero-search-hint');
    if (!hint || hint.dataset.searchBar === '1') return;
    const isArtists = _VIEW === 'artists';
    const isHome    = _VIEW === 'home';
    hint.dataset.searchBar = '1';
    hint.classList.add('mp-hero-search-bar');

    // Rangée de chips — repliée par défaut dans un dépliant « Filtres » :
    //   /sons     → moods DNA (filtre les sons)
    //   /artistes → rôles CONNECT (filtre les profils)
    //   home      → LES DEUX, en groupes titrés (2026-06-11) — un seul
    //               pattern de recherche sur tout le site.
    // Home : le panneau suit le MODE (Musique ⇄ Image). En image, on montre les
    // styles + usages d'image et les créateurs visuels, en miroir de la loupe.
    const _isImg = isHome && _readMode() === 'image';
    const _moodsChips = _PAGE_MOODS.map(m =>
      '<button type="button" class="mp-hsb-mood" data-mood="' + m + '">' + _esc(m) + '</button>'
    ).join('');
    const _rolesChips = _PAGE_ROLES.map(r =>
      '<button type="button" class="mp-hsb-mood" data-role="' + _esc(r.val) + '">' + _esc(r.label) + '</button>'
    ).join('');
    const _stylesChips = _IMG_STYLES.map(s =>
      '<button type="button" class="mp-hsb-mood" data-style="' + _esc(s.val) + '">' + _esc(s.label) + '</button>'
    ).join('');
    const _usageChips = _IMG_USAGE.map(u =>
      '<button type="button" class="mp-hsb-mood" data-usage="' + _esc(u.val) + '">' + _esc(u.label) + '</button>'
    ).join('');
    const _rolesImgChips = _PAGE_ROLES_IMG.map(r =>
      '<button type="button" class="mp-hsb-mood" data-role="' + _esc(r.val) + '">' + _esc(r.label) + '</button>'
    ).join('');
    const moodChipsHtml =
      '<div class="mp-hsb-moods" id="mp-hsb-moods" hidden>' +
        (isHome
          ? (_isImg
              ? '<span class="mp-hsb-group-lbl">🎨 Styles · images</span>' + _stylesChips +
                '<span class="mp-hsb-group-lbl">🏷️ Usage</span>' + _usageChips +
                '<span class="mp-hsb-group-lbl">👤 Créateurs visuels</span>' + _rolesImgChips
              : '<span class="mp-hsb-group-lbl">🧬 Moods · sons</span>' + _moodsChips +
                '<span class="mp-hsb-group-lbl">👤 Rôles · artistes</span>' + _rolesChips)
          : (isArtists ? _rolesChips : _moodsChips)) +
      '</div>';

    // Bouton dépliant (chevron + compteur de filtres actifs).
    const filterBtnHtml =
      '<button type="button" class="mp-hsb-toggle" aria-expanded="false" title="' + (isArtists ? 'Filtrer par rôle' : (isHome ? 'Filtrer par mood ou rôle' : 'Filtrer par mood')) + '">' +
        '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>' +
        '<span class="mp-hsb-toggle-lbl">' + (isArtists ? 'Rôles' : 'Filtres') + '</span>' +
        '<span class="mp-hsb-fcount" hidden>0</span>' +
        '<svg class="mp-hsb-chev" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>' +
      '</button>';

    hint.innerHTML =
      '<span class="mp-hsb-row">' +
        '<span class="mp-hsb-wrap">' +
          '<svg class="mp-hsb-ico" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="16.65" y1="16.65" x2="21" y2="21"/></svg>' +
          '<input type="search" class="mp-hsb-input" autocomplete="off" ' +
            'placeholder="' + (isArtists ? 'Filtrer les artistes…' : (isHome ? (_isImg ? 'Rechercher une image ou un artiste…' : 'Rechercher un son ou un artiste…') : 'Filtrer les sons par titre, artiste, mood…')) + '">' +
        '</span>' +
        filterBtnHtml +
      '</span>' +
      moodChipsHtml;

    if (!document.getElementById('mp-hsb-style')) {
      const st = document.createElement('style');
      st.id = 'mp-hsb-style';
      st.textContent =
        '.mp-hero-search-bar{display:flex;flex-direction:column;align-items:center;gap:10px;margin-top:4px}' +
        '.mp-hsb-row{display:flex;align-items:center;justify-content:center;gap:8px;' +
          'width:min(620px,94%);flex-wrap:wrap}' +
        '.mp-hsb-wrap{display:flex;align-items:center;gap:9px;flex:1;min-width:220px;' +
          'padding:11px 18px;border-radius:999px;border:1px solid rgba(124,58,237,.45);' +
          'background:rgba(255,255,255,.04);color:rgba(255,255,255,.55);' +
          'transition:border-color .15s,background .15s}' +
        '.mp-hsb-wrap:focus-within{border-color:rgba(124,58,237,.9);background:rgba(124,58,237,.08)}' +
        '.mp-hsb-input{flex:1;background:transparent;border:0;outline:0;color:#fff;' +
          'font-size:.92rem;font-family:inherit;min-width:0}' +
        '.mp-hsb-input::placeholder{color:rgba(255,255,255,.4)}' +
        // bouton dépliant
        '.mp-hsb-toggle{display:inline-flex;align-items:center;gap:6px;cursor:pointer;' +
          'padding:10px 14px;border-radius:999px;font-size:.82rem;font-family:inherit;' +
          'border:1px solid rgba(204,136,255,.3);background:rgba(204,136,255,.07);' +
          'color:rgba(204,136,255,.85);transition:all .12s;white-space:nowrap}' +
        '.mp-hsb-toggle:hover{border-color:rgba(204,136,255,.6);color:#cc88ff}' +
        '.mp-hsb-toggle[aria-expanded="true"]{background:rgba(204,136,255,.18);color:#fff;' +
          'border-color:rgba(204,136,255,.8)}' +
        '.mp-hsb-toggle .mp-hsb-chev{transition:transform .15s}' +
        '.mp-hsb-toggle[aria-expanded="true"] .mp-hsb-chev{transform:rotate(180deg)}' +
        '.mp-hsb-fcount{display:inline-flex;align-items:center;justify-content:center;' +
          'min-width:17px;height:17px;padding:0 4px;border-radius:999px;font-size:.68rem;' +
          'font-weight:700;background:#cc88ff;color:#1a0f2e}' +
        // dépliant moods
        '.mp-hsb-moods{display:flex;flex-wrap:wrap;justify-content:center;gap:6px;' +
          'width:min(680px,94%)}' +
        '.mp-hsb-moods[hidden]{display:none}' +
        '.mp-hsb-mood{padding:4px 11px;border-radius:999px;font-size:.74rem;cursor:pointer;' +
          'border:1px solid rgba(204,136,255,.25);background:rgba(204,136,255,.06);' +
          'color:rgba(204,136,255,.75);transition:all .12s;font-family:inherit}' +
        '.mp-hsb-mood:hover{border-color:rgba(204,136,255,.55);color:#cc88ff}' +
        '.mp-hsb-mood.is-active{border-color:rgba(204,136,255,.9);' +
          'background:rgba(204,136,255,.22);color:#fff}' +
        // titres de groupes (dépliant combiné de la home)
        '.mp-hsb-group-lbl{width:100%;text-align:center;font-size:.66rem;' +
          'letter-spacing:.1em;text-transform:uppercase;' +
          'color:rgba(255,255,255,.38);margin:7px 0 2px}';
      document.head.appendChild(st);
    }

    const input = hint.querySelector('.mp-hsb-input');
    const _apply = () => {
      const v = input.value || '';
      if (isHome) {
        // MODE RÉSULTATS : recherche/filtre actif → vitrine + podiums
        // masqués, grilles complètes (le plafond de 3 saute aussi).
        // Ciblage par groupe (fix 2026-06-11) : des rôles CONNECT seuls ne
        // doivent montrer QUE les profils — pas de musiques (et
        // réciproquement, des moods seuls ne montrent que les sons).
        const hasText  = !!v.trim();
        const hasMoods = _pageMoodSet.size > 0;
        const hasRoles = _pageRoleSet.size > 0;
        const active   = hasText || hasMoods || hasRoles;
        document.body.classList.toggle('mp-searching', active);
        document.body.classList.toggle('mp-hide-sons',    active && !hasText && !hasMoods && hasRoles);
        document.body.classList.toggle('mp-hide-artists', active && !hasText && !hasRoles && hasMoods);
        _renderGridSons(v);
        _renderGridArtists(v);
      } else if (isArtists) {
        _renderGridArtists(v);
      } else {
        _renderGridSons(v);
      }
    };
    input.addEventListener('input', _apply);

    // Dépliant + chips (multi-select) — /sons : moods · /artistes : rôles ·
    // home : les deux (le data-attribut de la chip détermine le set visé).
    {
      const toggle  = hint.querySelector('.mp-hsb-toggle');
      const moods   = hint.querySelector('#mp-hsb-moods');
      const fcount  = hint.querySelector('.mp-hsb-fcount');

      const _updateCount = () => {
        const n = isHome
          ? _pageMoodSet.size + _pageRoleSet.size
          : (isArtists ? _pageRoleSet.size : _pageMoodSet.size);
        if (!fcount) return;
        fcount.textContent = String(n);
        fcount.hidden = n === 0;
      };

      // Ouvre/ferme le dépliant.
      if (toggle && moods) {
        toggle.addEventListener('click', () => {
          const open = moods.hasAttribute('hidden');
          if (open) { moods.removeAttribute('hidden'); toggle.setAttribute('aria-expanded', 'true'); }
          else      { moods.setAttribute('hidden', '');  toggle.setAttribute('aria-expanded', 'false'); }
        });
      }

      hint.querySelectorAll('.mp-hsb-mood').forEach(chip => {
        chip.addEventListener('click', () => {
          // Mode Image — styles / usages : on ouvre la vitrine images DÉJÀ
          // filtrée (deep-link /images?style= / ?tag=, géré au chargement).
          if (chip.dataset.style !== undefined) {
            window.location.href = '/images?style=' + encodeURIComponent(chip.dataset.style);
            return;
          }
          if (chip.dataset.usage !== undefined) {
            window.location.href = '/images?tag=' + encodeURIComponent(chip.dataset.usage);
            return;
          }
          const isRole = chip.dataset.role !== undefined;
          const set    = isRole ? _pageRoleSet : _pageMoodSet;
          const key    = isRole ? chip.dataset.role : chip.dataset.mood;
          if (set.has(key)) { set.delete(key); chip.classList.remove('is-active'); }
          else              { set.add(key);    chip.classList.add('is-active'); }
          _updateCount();
          _apply();
        });
      });
    }
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
