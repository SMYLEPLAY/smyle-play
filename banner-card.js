/* ═════════════════════════════════════════════════════════════════════════
   BANNER CARD — helper de rendu
   ─────────────────────────────────────────────────────────────────────────
   Point d'entrée unique pour générer une bannière artiste.
   Usage : container.innerHTML = renderArtistBanner(artist, opts)

   artist : {
     slug          : 'smyle'
     displayName   : 'Smyle'
     genre         : 'Deep House'            // optionnel, affiché en chip
     subLine       : 'Officiel · 12 sons'    // optionnel, sous le nom
     avatarUrl     : '/avatars/smyle.png'    // optionnel, fallback = initiale
     verified      : true                    // badge bleu électrique
     stats         : [                       // optionnel — méta à droite
       { label: '♪', value: 12 },
       { label: 'fans', value: '1.2k' },
     ]
   }

   opts : {
     size   : 'compact' | 'default' | 'hero'
     rank   : 1                              // si présent → layout avec rang
     href   : '/@smyle'                     // sinon fallback `/@${slug}`
   }
   ═════════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  function _escape(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _initial(name) {
    if (!name) return '?';
    return String(name).trim().charAt(0).toUpperCase();
  }

  function _rankClass(rank) {
    if (rank === 1) return 'banner-card__rank--gold';
    if (rank === 2) return 'banner-card__rank--silver';
    if (rank === 3) return 'banner-card__rank--bronze';
    return '';
  }

  function _renderAvatar(artist) {
    const initial = _initial(artist.displayName || artist.slug);
    const verified = artist.verified
      ? '<span class="banner-card__badge" title="Vérifié">✓</span>'
      : '';
    if (artist.avatarUrl) {
      return `<div class="banner-card__avatar">
        <img src="${_escape(artist.avatarUrl)}" alt="${_escape(artist.displayName || '')}"/>
        ${verified}
      </div>`;
    }
    return `<div class="banner-card__avatar">
      ${_escape(initial)}
      ${verified}
    </div>`;
  }

  function _renderSubLine(artist) {
    if (!artist.subLine && !artist.genre) return '';
    const parts = [];
    if (artist.genre) {
      parts.push(`<span class="banner-card__chip">${_escape(artist.genre)}</span>`);
    }
    if (artist.subLine) {
      parts.push(`<span>${_escape(artist.subLine)}</span>`);
    }
    return `<div class="banner-card__sub">${parts.join('<span class="banner-card__sub-sep">·</span>')}</div>`;
  }

  function _renderMeta(artist) {
    if (!Array.isArray(artist.stats) || artist.stats.length === 0) return '';
    const items = artist.stats.map(s => {
      const label = s.label ? `<span style="opacity:.6">${_escape(s.label)}</span>` : '';
      const value = `<strong>${_escape(s.value)}</strong>`;
      return `<span class="banner-card__meta-item">${value}${label}</span>`;
    }).join('');
    return `<div class="banner-card__meta">${items}</div>`;
  }

  function _renderRank(rank) {
    if (rank == null) return '';
    const cls = _rankClass(rank);
    return `<div class="banner-card__rank ${cls}">${_escape(rank)}</div>`;
  }

  /**
   * Retourne le HTML d'une bannière artiste prête à injecter.
   * @param {Object} artist  données artiste
   * @param {Object} [opts]  { size, rank, href }
   * @returns {string} HTML
   */
  function renderArtistBanner(artist, opts) {
    opts = opts || {};
    const size = opts.size || 'default';
    const rank = (typeof opts.rank === 'number') ? opts.rank : null;
    const href = opts.href || (artist.slug ? `/@${_escape(artist.slug)}` : '#');

    const classes = ['banner-card', `banner-card--${size}`];
    if (rank != null) classes.push('banner-card--with-rank');

    const rankHtml = _renderRank(rank);
    const avatarHtml = _renderAvatar(artist);
    const titleHtml = `<div class="banner-card__title">${_escape(artist.displayName || artist.slug || '—')}</div>`;
    const subHtml = _renderSubLine(artist);
    const metaHtml = _renderMeta(artist);

    return `<a class="${classes.join(' ')}" href="${href}">
      ${rankHtml}
      ${avatarHtml}
      <div class="banner-card__body">
        ${titleHtml}
        ${subHtml}
      </div>
      ${metaHtml}
    </a>`;
  }

  /**
   * Rend une liste de bannières dans un container.
   * @param {HTMLElement} container
   * @param {Array} artists
   * @param {Object} [opts]  options communes à toutes les bannières
   */
  function renderArtistBannerList(container, artists, opts) {
    if (!container) return;
    if (!Array.isArray(artists) || artists.length === 0) {
      container.innerHTML = '<div class="banner-card-empty" style="padding:24px;text-align:center;font-size:13px;color:rgba(255,255,255,.35)">Aucun résultat</div>';
      return;
    }
    const o = opts || {};
    const html = artists.map((a, i) => {
      const perItemOpts = Object.assign({}, o);
      if (o.autoRank) perItemOpts.rank = i + 1;
      return renderArtistBanner(a, perItemOpts);
    }).join('');
    container.innerHTML = html;
  }

  /* ═══════════════════════════════════════════════════════════════════════
     CARTE ID SCINDÉE — ŒUVRE binaire (C4b)
     ─────────────────────────────────────────────────────────────────────
     Une œuvre = deux faces. La carte est coupée en deux moitiés strictement
     symétriques : gauche = SON (playlist + badge IA audio, ex. Suno) ·
     droite = VISUEL (cover album + badge IA visuel, ex. ChatGPT). Clic →
     page binaire /oeuvre/<slug>. Les badges réutilisent SpBadges.provenance
     des DEUX côtés (même composant son & visuel).

     oeuvre : {
       slug, title,                          // titre de l'œuvre (optionnel)
       son:    { title, platform:'suno',    color, version },     // ou null
       visuel: { title, platform:'chatgpt', previewKey, version } // ou null
     }
     opts : { href }                         // défaut /oeuvre/<slug>
     ═══════════════════════════════════════════════════════════════════════ */

  function _imgPreviewUrl(key) {
    if (!key) return '';
    return '/watt/images/' + String(key).split('/').map(encodeURIComponent).join('/');
  }

  function _provenanceBadge(platform, version) {
    if (window.SpBadges && typeof window.SpBadges.provenance === 'function') {
      return window.SpBadges.provenance(platform, version);
    }
    if (!platform) return '';
    return '<span class="sp-provenance">⚡ ' + _escape(platform) + '</span>';
  }

  function _oeuvreSonHalf(son) {
    if (!son) {
      return '<div class="oeuvre-card__half oeuvre-card__half--son is-empty">' +
        '<span class="oeuvre-card__empty">Son à venir</span></div>';
    }
    const color = son.color || '#7c5cff';
    return '' +
      '<div class="oeuvre-card__half oeuvre-card__half--son" style="--oeuvre-son-color:' + _escape(color) + '">' +
        '<span class="oeuvre-card__face-tag">SON</span>' +
        '<span class="oeuvre-card__wave" aria-hidden="true">🎵</span>' +
        '<div class="oeuvre-card__half-title">' + _escape(son.title || 'Playlist') + '</div>' +
        '<div class="oeuvre-card__prov">' + _provenanceBadge(son.platform || 'suno', son.version) + '</div>' +
      '</div>';
  }

  function _oeuvreVisuelHalf(visuel) {
    if (!visuel) {
      return '<div class="oeuvre-card__half oeuvre-card__half--visuel is-empty">' +
        '<span class="oeuvre-card__empty">Visuel à venir</span></div>';
    }
    const url = _imgPreviewUrl(visuel.previewKey);
    const cover = url
      ? '<img class="oeuvre-card__cover" src="' + _escape(url) + '" alt="" loading="lazy"/>'
      : '<span class="oeuvre-card__wave" aria-hidden="true">🖼️</span>';
    return '' +
      '<div class="oeuvre-card__half oeuvre-card__half--visuel">' +
        cover +
        '<span class="oeuvre-card__face-tag">VISUEL</span>' +
        '<div class="oeuvre-card__half-title">' + _escape(visuel.title || 'Album') + '</div>' +
        '<div class="oeuvre-card__prov">' + _provenanceBadge(visuel.platform || 'chatgpt', visuel.version) + '</div>' +
      '</div>';
  }

  /**
   * Retourne le HTML d'une carte d'œuvre binaire (son | visuel).
   * @param {Object} oeuvre  { slug, title, son, visuel }
   * @param {Object} [opts]  { href }
   * @returns {string} HTML
   */
  function renderOeuvreCard(oeuvre, opts) {
    oeuvre = oeuvre || {};
    opts = opts || {};
    const slug = oeuvre.slug || '';
    const href = opts.href || (slug ? '/oeuvre/' + _escape(slug) : '#');
    const complete = !!(oeuvre.son && oeuvre.visuel);
    const seal = complete
      ? '<span class="oeuvre-card__seal" title="Œuvre complète">◆</span>'
      : '';
    const title = oeuvre.title
      ? '<div class="oeuvre-card__title">' + _escape(oeuvre.title) + seal + '</div>'
      : '';

    return '' +
      '<a class="oeuvre-card' + (complete ? ' is-complete' : '') + '" href="' + href + '">' +
        '<div class="oeuvre-card__split">' +
          _oeuvreSonHalf(oeuvre.son) +
          '<span class="oeuvre-card__seam" aria-hidden="true"></span>' +
          _oeuvreVisuelHalf(oeuvre.visuel) +
        '</div>' +
        title +
      '</a>';
  }

  /**
   * Rend une liste de cartes d'œuvres dans un container.
   * @param {HTMLElement} container
   * @param {Array} oeuvres
   * @param {Object} [opts]
   */
  function renderOeuvreCardList(container, oeuvres, opts) {
    if (!container) return;
    if (!Array.isArray(oeuvres) || oeuvres.length === 0) {
      container.innerHTML = '<div class="banner-card-empty" style="padding:24px;text-align:center;font-size:13px;color:rgba(255,255,255,.35)">Aucune œuvre</div>';
      return;
    }
    container.innerHTML = oeuvres.map(o => renderOeuvreCard(o, opts)).join('');
  }

  // Exposé global pour utilisation inline dans les pages
  window.renderArtistBanner = renderArtistBanner;
  window.renderArtistBannerList = renderArtistBannerList;
  window.renderOeuvreCard = renderOeuvreCard;
  window.renderOeuvreCardList = renderOeuvreCardList;
})();
