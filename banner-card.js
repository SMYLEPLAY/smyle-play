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
     href   : '/u/smyle'                     // sinon fallback `/u/${slug}`
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
    const href = opts.href || (artist.slug ? `/u/${_escape(artist.slug)}` : '#');

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

  // Exposé global pour utilisation inline dans les pages
  window.renderArtistBanner = renderArtistBanner;
  window.renderArtistBannerList = renderArtistBannerList;
})();
