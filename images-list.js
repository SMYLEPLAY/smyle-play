/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — images-list.js
   C4 Monde Visuel V1 — livraison ③ (2026-06-15).

   Écran « Mes images » du WattBoard (tuile Images IA → bouton « Voir »).
   Grille de cards-aperçu OWNER : aperçu public + provenance + rareté #X/N +
   état (publié / brouillon). Alimenté par GET /artist/me/images (ImageOwnerRead).

   Règle stricte : l'aperçu (previewKey) est servi par le proxy public
   /watt/images/<key>. L'original n'est JAMAIS exposé ici — le téléchargement
   passe par GET /images/{id}/download (gaté possession).

   Édition / suppression : le circuit prompts générique n'expose pas encore de
   PATCH/DELETE dédié aux images en livraison ③ → HORS PÉRIMÈTRE (noté). La
   carte affiche l'état mais ne propose pas encore éditer/supprimer.

   Dépendances : window.apiFetch (ui/core/api.js), window.SpBadges
   (ui/core/badges.js). Chargé en defer APRÈS wattboard-v3.js.
   ───────────────────────────────────────────────────────────────────────── */
(function initImagesList() {
  'use strict';
  if (typeof window === 'undefined') return;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Construit l'URL same-origin de l'aperçu depuis sa clé R2. Le proxy
  // /watt/images/<key> ne sert QUE le préfixe images/previews/ (gate backend).
  function previewUrl(key) {
    if (!key) return '';
    return '/watt/images/' + String(key).split('/').map(encodeURIComponent).join('/');
  }

  // Badge rareté #X/N depuis maxSupply (mythic = 1/1). Le prochain exemplaire
  // minté = soldCount + 1. SpBadges gère l'échappement + le mapping tier.
  function rareteBadge(img) {
    if (!window.SpBadges || img.maxSupply == null) return '';
    var sold = img.soldCount || 0;
    if (img.isSoldOut) return SpBadges.rarete(img.maxSupply, img.maxSupply);
    return SpBadges.rarete(sold + 1, img.maxSupply, img.maxSupply === 1 ? 'legendaire' : '');
  }

  function injectCss() {
    if (document.getElementById('imgl-styles')) return;
    var s = document.createElement('style');
    s.id = 'imgl-styles';
    s.textContent =
      '.imgl-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px;margin-top:6px}' +
      '.imgl-empty{grid-column:1/-1;text-align:center;color:var(--sp-text-dim,#a09cb8);font-size:.86rem;padding:28px 12px;border:1px dashed rgba(255,255,255,.13);border-radius:14px;background:rgba(255,255,255,.02)}' +
      '.imgl-card{position:relative;border:1px solid rgba(255,255,255,.09);border-radius:14px;overflow:hidden;background:rgba(255,255,255,.025);display:flex;flex-direction:column}' +
      '.imgl-card-cover{position:relative;aspect-ratio:1/1;background:rgba(124,58,237,.10);overflow:hidden;display:flex;align-items:center;justify-content:center}' +
      '.imgl-card-cover img{width:100%;height:100%;object-fit:cover;display:block}' +
      '.imgl-card-cover-fallback{font-size:2rem;opacity:.5}' +
      '.imgl-state{position:absolute;top:8px;left:8px;padding:2px 9px;border-radius:999px;font-size:.66rem;font-weight:700;letter-spacing:.02em}' +
      '.imgl-state.is-pub{background:rgba(34,197,94,.85);color:#04210f}' +
      '.imgl-state.is-draft{background:rgba(148,163,184,.85);color:#0b1220}' +
      '.imgl-card-body{padding:10px 12px 12px;display:flex;flex-direction:column;gap:6px}' +
      '.imgl-card-title{font-weight:700;color:#f3f0ff;font-size:.92rem;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.imgl-card-badges{display:flex;flex-wrap:wrap;gap:5px;align-items:center}' +
      '.imgl-card-price{margin-top:2px;font-size:.82rem;color:#cbb3ff;font-weight:700}' +
      '.imgl-card-price span{font-size:.7rem;color:#8b7bd8;font-weight:600}';
    document.head.appendChild(s);
  }

  function cardHtml(img) {
    var url = previewUrl(img.previewKey);
    var cover = url
      ? '<img src="' + esc(url) + '" alt="' + esc(img.title || 'Image') + '" loading="lazy" />'
      : '<span class="imgl-card-cover-fallback" aria-hidden="true">🖼️</span>';
    var nature = window.SpBadges ? SpBadges.nature('image') : '';
    var prov   = window.SpBadges ? SpBadges.provenance(img.imagePlatform, img.imageModelVersion) : '';
    var rar    = rareteBadge(img);
    var stateCls = img.isPublished ? 'is-pub' : 'is-draft';
    var stateTxt = img.isPublished ? 'Publié' : 'Brouillon';
    return '' +
      '<article class="imgl-card" data-image-id="' + esc(img.id) + '">' +
        '<div class="imgl-card-cover">' +
          '<span class="imgl-state ' + stateCls + '">' + stateTxt + '</span>' +
          cover +
        '</div>' +
        '<div class="imgl-card-body">' +
          '<div class="imgl-card-title" title="' + esc(img.title || '') + '">' + esc(img.title || 'Sans titre') + '</div>' +
          '<div class="imgl-card-badges">' + nature + rar + prov + '</div>' +
          '<div class="imgl-card-price">' + esc(img.priceCredits) + ' <span>Smyles</span></div>' +
        '</div>' +
      '</article>';
  }

  function render(list) {
    var grid = document.getElementById('imgl-grid');
    if (!grid) return;
    if (!Array.isArray(list) || list.length === 0) {
      grid.innerHTML =
        '<div class="imgl-empty">Tu n\'as pas encore d\'image. Utilise « Créer » sur la tuile Images IA pour publier ton premier visuel.</div>';
      return;
    }
    grid.innerHTML = list.map(cardHtml).join('');
  }

  // ImageOwnerRead expose snake_case côté Pydantic (preview_r2_key, etc.).
  // On normalise vers le camelCase utilisé par les cards.
  function normalize(o) {
    return {
      id:               o.id,
      title:            o.title,
      priceCredits:     o.price_credits != null ? o.price_credits : o.priceCredits,
      maxSupply:        o.max_supply != null ? o.max_supply : (o.maxSupply != null ? o.maxSupply : null),
      isPublished:      !!(o.is_published != null ? o.is_published : o.isPublished),
      imagePlatform:    o.image_platform || o.imagePlatform || '',
      imageModelVersion: o.image_model_version || o.imageModelVersion || '',
      previewKey:       o.preview_r2_key || o.previewKey || '',
      soldCount:        o.soldCount || 0,
      isSoldOut:        !!o.isSoldOut,
    };
  }

  var _loading = false;
  function refresh() {
    if (typeof window.apiFetch !== 'function') return;
    if (_loading) return;
    _loading = true;
    window.apiFetch('/artist/me/images')
      .then(function (list) {
        render(Array.isArray(list) ? list.map(normalize) : []);
      })
      .catch(function (e) {
        var grid = document.getElementById('imgl-grid');
        if (grid) {
          grid.innerHTML = (e && e.status === 401)
            ? '<div class="imgl-empty">Connecte-toi pour voir tes images.</div>'
            : '<div class="imgl-empty">Impossible de charger tes images. Réessaie.</div>';
        }
      })
      .finally(function () { _loading = false; });
  }

  function init() {
    injectCss();
    // Charge la liste quand l'écran « Mes images » s'ouvre (lazy, pas au boot).
    var sec = document.getElementById('sec-image-list');
    if (sec) {
      var mo = new MutationObserver(function () {
        if (sec.classList.contains('wb3-open')) refresh();
      });
      mo.observe(sec, { attributes: true, attributeFilter: ['class'] });
      // Si déjà ouvert (deep-link), charge tout de suite.
      if (sec.classList.contains('wb3-open')) refresh();
    }
  }

  window.ImagesList = { refresh: refresh, render: render };

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
