/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/badges.js
   Helpers de rendu des 3 repères constants (chantier C0, blueprint VF).

   Usage (script classique, expose window.SpBadges) :
     SpBadges.nature('beat')                 → '<span class="sp-pill …">🥁 Beat</span>'
     SpBadges.palier('premium')              → '<span …>Palier premium</span>'
     SpBadges.rarete(3, 20, 'legendaire')    → '<span …>#3/20 · Légendaire</span>'
     SpBadges.provenance('suno', 'V5.5')     → '<span class="sp-provenance">⚡ Suno · V5.5</span>'

   Toutes les valeurs passent par un échappement HTML. Toute entrée inconnue
   retourne '' (jamais de pilule cassée à l'écran).
   Requiert ui/core/tokens.css + ui/core/badges.css.
   ───────────────────────────────────────────────────────────────────────── */

(function initSpBadges() {
  'use strict';
  if (typeof window === 'undefined' || window.SpBadges) return;

  // S-01 (2026-09-02) — échappeur HTML complet (& < > " ' `), copie de
  // ui/albums.js (l'apostrophe et le backtick manquaient).
  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c];
    });
  }

  var NATURES = {
    adn:      { label: 'ADN',    icon: '🧬' },
    'son-ia': { label: 'Son IA', icon: '🤖' },
    son_ia:   { label: 'Son IA', icon: '🤖' },
    beat:     { label: 'Beat',   icon: '🥁' },
    voix:     { label: 'Voix',   icon: '🎙️' },
    image:    { label: 'Image',  icon: '🖼️' },
    reel:     { label: 'Réel',   icon: '🎤' },
  };

  var PALIERS = { free: 'free', standard: 'standard', premium: 'premium', mythique: 'mythique' };

  var RARETES = {
    commune:     'Commune',
    rare:        'Rare',
    epique:      'Épique',
    legendaire:  'Légendaire',
    /* alias EN rencontrés dans les données existantes (drop VIP etc.) */
    common:      'Commune',
    epic:        'Épique',
    legendary:   'Légendaire',
  };
  var RARETE_CLASS = {
    common: 'commune', epic: 'epique', legendary: 'legendaire',
    commune: 'commune', rare: 'rare', epique: 'epique', legendaire: 'legendaire',
  };

  var PLATFORMS = {
    suno: 'Suno', udio: 'Udio', riffusion: 'Riffusion', stable_audio: 'Stable Audio',
    midjourney: 'Midjourney', dalle: 'DALL-E', 'dall-e': 'DALL-E', flux: 'Flux',
    stable_diffusion: 'Stable Diffusion', autre: 'Autre',
  };

  window.SpBadges = {

    /** Repère 1 — nature : 'adn' | 'son-ia' | 'beat' | 'voix' | 'image' | 'reel' */
    nature: function (type) {
      var key = String(type || '').toLowerCase().replace('_', '-');
      var n = NATURES[key] || NATURES[String(type || '').toLowerCase()];
      if (!n) return '';
      var cls = key === 'son_ia' ? 'son-ia' : key;
      return '<span class="sp-pill sp-pill--nature-' + cls + '" title="Nature : ' + _esc(n.label) + '">' +
             n.icon + ' ' + _esc(n.label) + '</span>';
    },

    /** Repère 2 — palier : 'free' | 'standard' | 'premium' | 'mythique' */
    palier: function (tier) {
      var key = PALIERS[String(tier || '').toLowerCase()];
      if (!key) return '';
      var label = key.charAt(0).toUpperCase() + key.slice(1);
      return '<span class="sp-pill sp-pill--palier-' + key + '" title="Palier créateur">' +
             'Palier ' + _esc(label.toLowerCase()) + '</span>';
    },

    /** Repère 3 — rareté : numéro, tirage total, label optionnel.
        rarete(3, 20)               → #3/20
        rarete(3, 20, 'legendary')  → #3/20 · Légendaire
        rarete(null, null, 'rare')  → Rare                                  */
    rarete: function (num, supply, label) {
      var key = String(label || '').toLowerCase();
      var cls = RARETE_CLASS[key] || 'commune';
      var txt = '';
      if (num != null && supply != null) txt = '#' + _esc(num) + '/' + _esc(supply);
      if (RARETES[key]) txt += (txt ? ' · ' : '') + RARETES[key];
      if (!txt) return '';
      return '<span class="sp-pill sp-pill--rarete-' + cls + '" title="Rareté (édition limitée)">' +
             txt + '</span>';
    },

    /** Œuvre (taxonomie 2026-07-15) — plus de label spécial « Œuvre complète » :
     *  la présence de la cover suffit à reconnaître une œuvre (son + image).
     *  Conservé comme no-op pour ne pas casser les appels existants. */
    oeuvre: function () {
      return '';
    },

    /** Provenance IA discrète : provenance('suno', 'V5.5') → ⚡ Suno · V5.5 */
    provenance: function (platform, version) {
      var key = String(platform || '').trim().toLowerCase();
      var label = PLATFORMS[key] || (key ? key.charAt(0).toUpperCase() + key.slice(1) : '');
      if (!label) return '';
      // S-01 (2026-09-02) — `platform` hors liste PLATFORMS est une chaîne
      // libre (String(20) sans CHECK) : le label dérivé est échappé lui aussi.
      var txt = _esc(label) + (version ? ' · ' + _esc(version) : '');
      return '<span class="sp-provenance" title="Générée avec ' + _esc(label) + '">⚡ ' + txt + '</span>';
    },
  };
})();
