/**
 * SMYLE SEARCH — Panneau de recherche unifié (loupe topbar)
 *
 * Design : panneau large deux colonnes
 *   Gauche  — CONNECT : profils artistes  (/watt/search/artists)
 *   Droite  — DNA     : morceaux / sons   (/watt/search/tracks)
 *
 * Les deux colonnes se mettent à jour en parallèle à chaque frappe.
 * Chips de filtre :
 *   - CONNECT : rôle (producteur, beatmaker, vocalist…)
 *   - DNA     : mood (chill, dark, énergique…)
 *
 * Auto-injection : bouton loupe dans .dash-topbar-right / .ap-topbar-right /
 *   .lib-topbar-right / .topbar-right. Présent sur toutes les pages.
 * Raccourci : Ctrl+K / Cmd+K ouvre le panneau.
 */
(function () {
  'use strict';

  if (window.__smyleSearchInstalled) return;
  window.__smyleSearchInstalled = true;

  // BUGFIX : en prod window.API_BASE vaut "" (même origine) — une chaîne
  // VIDE est falsy, donc l'ancien test `window.API_BASE ? ... : localhost`
  // retombait à tort sur localhost:8000 (→ 503 en prod). On teste le TYPE
  // pour accepter "" comme valeur valide (même origine).
  const API_BASE = (typeof window !== 'undefined' && typeof window.API_BASE === 'string')
    ? String(window.API_BASE).replace(/\/+$/, '')
    : 'http://localhost:8000';

  const DEBOUNCE_MS = 260;

  // ── SVG icons ─────────────────────────────────────────────────────────
  const ICO_SEARCH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="16.65" y1="16.65" x2="21" y2="21"/></svg>`;
  const ICO_CLOSE  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
  const ICO_USER   = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
  const ICO_DISC   = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>`;
  const ICO_PLAY   = `<svg viewBox="0 0 24 24" fill="currentColor" stroke="none" width="12" height="12"><polygon points="5,3 19,12 5,21"/></svg>`;

  // Chips connect (rôles artistes) — valeurs = ROLE_CODES backend (schemas/user.py)
  const CONNECT_CHIPS = [
    { label: 'Artiste',       val: 'artiste'       },
    { label: 'Producteur',    val: 'producteur'    },
    { label: 'Beatmaker',     val: 'beatmaker'     },
    { label: 'Compositeur',   val: 'compositeur'   },
    { label: 'Topliner',      val: 'topliner'      },
    { label: 'Parolier',      val: 'parolier'      },
    { label: 'Ghostwriter',   val: 'ghostwriter'   },
    { label: 'Arrangeur',     val: 'arrangeur'     },
    { label: 'DJ',            val: 'dj'            },
    { label: 'Ingé son',      val: 'ingenieur_son' },
    { label: 'Éditeur',       val: 'editeur'       },
    { label: 'Auditeur',      val: 'auditeur'      },
  ];

  // Chips DNA (moods) — alignées sur les data-tag de dashboard.html + étendues
  const DNA_CHIPS = [
    { label: 'chill',        val: 'chill'        },
    { label: 'énergique',    val: 'énergique'    },
    { label: 'dark',         val: 'dark'         },
    { label: 'festif',       val: 'festif'       },
    { label: 'romantique',   val: 'romantique'   },
    { label: 'mélancolique', val: 'mélancolique' },
    { label: 'instrumental', val: 'instrumental' },
    { label: 'vocal',        val: 'vocal'        },
    { label: 'groovy',       val: 'groovy'       },
    { label: 'hypnotique',   val: 'hypnotique'   },
    { label: 'agressif',     val: 'agressif'     },
    { label: 'nostalgique',  val: 'nostalgique'  },
    { label: 'euphorique',   val: 'euphorique'   },
    { label: 'cinématique',  val: 'cinématique'  },
    { label: 'loop',         val: 'loop'         },
    { label: 'acapella',     val: 'acapella'     },
  ];

  // ── C4 taxonomie visuelle ───────────────────────────────────────────────
  // Jeux de chips du MODE IMAGE. Les `val` matchent EXACTEMENT les codes
  // backend (ROLE_CODES visuels schemas/user.py · STYLES routers/images.py).
  // CONNECT image : rôles de créateurs visuels — /watt/search/artists?role=
  const CONNECT_CHIPS_IMG = [
    { label: 'Illustrateur',          val: 'illustrateur'         },
    { label: 'Graphiste',             val: 'graphiste'            },
    { label: 'Directeur artistique',  val: 'directeur_artistique' },
    { label: 'Photographe',           val: 'photographe'          },
    { label: 'Concept artist',        val: 'concept_artist'       },
    { label: 'Character designer',    val: 'character_designer'   },
    { label: 'Retoucheur',            val: 'retoucheur'           },
    { label: 'Coloriste',             val: 'coloriste'            },
    { label: 'Artiste 3D',            val: 'artiste_3d'           },
    { label: 'Prompteur',             val: 'prompteur'            },
    { label: 'Designer',              val: 'designer'             },
    { label: 'Collectionneur',        val: 'collectionneur'       },
  ];
  // DNA image : styles visuels — filtre /images?style=<code>
  const DNA_CHIPS_IMG = [
    { label: 'Réaliste',     val: 'realiste'     },
    { label: 'Cartoon',      val: 'cartoon'      },
    { label: 'Anime',        val: 'anime'        },
    { label: '3D / Render',  val: '3d'           },
    { label: 'Peinture',     val: 'peinture'     },
    { label: 'Aquarelle',    val: 'aquarelle'    },
    { label: 'Croquis',      val: 'croquis'      },
    { label: 'Pixel art',    val: 'pixel_art'    },
    { label: 'Cyberpunk',    val: 'cyberpunk'    },
    { label: 'Fantasy',      val: 'fantasy'      },
    { label: 'Minimaliste',  val: 'minimaliste'  },
    { label: 'Rétro',        val: 'retro'        },
    { label: 'Abstrait',     val: 'abstrait'     },
    { label: 'Surréaliste',  val: 'surrealiste'  },
    { label: 'Comics',       val: 'comics'       },
    { label: 'Photo',        val: 'photo'        },
  ];
  // Tags d'usage image (11, dont fx) — filtre /images?tag=<code> (présence).
  // `val` = codes backend (routers/images.py), libellés FR pour l'affichage.
  const USAGE_CHIPS_IMG = [
    { label: 'Cover',        val: 'cover'        },
    { label: 'Portrait',     val: 'portrait'     },
    { label: 'Paysage',      val: 'paysage'      },
    { label: 'Logo',         val: 'logo'         },
    { label: 'Bannière',     val: 'banniere'     },
    { label: 'Avatar',       val: 'avatar'       },
    { label: 'Wallpaper',    val: 'wallpaper'    },
    { label: 'Mockup',       val: 'mockup'       },
    { label: 'Illustration', val: 'illustration' },
    { label: 'Texture',      val: 'texture'      },
    { label: 'FX',           val: 'fx'           },
  ];

  // ── Styles ────────────────────────────────────────────────────────────
  function injectStyles() {
    if (document.getElementById('smyle-search-styles')) return;
    const s = document.createElement('style');
    s.id = 'smyle-search-styles';
    s.textContent = `
/* ── Bouton loupe ────────────────────────────────────────────────────── */
.smyle-search-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; border-radius: 50%;
  border: 1px solid rgba(255,255,255,.1);
  background: rgba(255,255,255,.04);
  color: rgba(255,255,255,.72); cursor: pointer;
  transition: all .15s ease; padding: 0;
}
.smyle-search-btn:hover {
  background: rgba(255,215,0,.1); border-color: rgba(255,215,0,.3); color: #FFD700;
}
.smyle-search-btn svg { width: 18px; height: 18px; }

/* ── Overlay ─────────────────────────────────────────────────────────── */
.smyle-search-overlay {
  position: fixed; inset: 0; z-index: 9998;
  background: rgba(0,0,0,.82);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  display: none; align-items: flex-start; justify-content: center;
  padding: 48px 16px 24px; overflow: auto;
}
.smyle-search-overlay.is-open { display: flex; }

/* ── Panneau principal ───────────────────────────────────────────────── */
.smyle-search-panel {
  background: #0f0c18;
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 16px;
  width: 100%; max-width: 960px;
  box-shadow: 0 32px 80px rgba(0,0,0,.7), 0 0 0 1px rgba(204,136,255,.06);
  overflow: hidden;
  display: flex; flex-direction: column;
}

/* ── Header : barre de recherche ─────────────────────────────────────── */
.smyle-search-header {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(255,255,255,.06);
  background: rgba(255,255,255,.02);
}
.smyle-search-header-ico {
  color: rgba(255,255,255,.35); flex-shrink: 0;
}
.smyle-search-header-ico svg { width: 18px; height: 18px; display: block; }
.smyle-search-input {
  flex: 1; background: transparent; border: 0; outline: none;
  font-size: 17px; font-weight: 500; color: #fff;
  font-family: inherit; letter-spacing: -.01em;
}
.smyle-search-input::placeholder { color: rgba(255,255,255,.28); }
.smyle-search-kbd {
  font-size: 11px; color: rgba(255,255,255,.25);
  border: 1px solid rgba(255,255,255,.1); border-radius: 5px;
  padding: 2px 6px; flex-shrink: 0; letter-spacing: .04em;
}
.smyle-search-close {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 50%;
  border: 1px solid rgba(255,255,255,.1); background: rgba(255,255,255,.04);
  color: rgba(255,255,255,.5); cursor: pointer; flex-shrink: 0;
  transition: all .12s ease; padding: 0;
}
.smyle-search-close:hover { background: rgba(255,255,255,.1); color: #fff; }
.smyle-search-close svg { width: 14px; height: 14px; }

/* ── Corps deux colonnes ─────────────────────────────────────────────── */
.smyle-search-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 480px;
  max-height: 70vh;
  overflow: hidden;
}
@media (max-width: 680px) {
  .smyle-search-body { grid-template-columns: 1fr; max-height: none; }
}

/* ── Colonne commune ─────────────────────────────────────────────────── */
.smyle-search-col {
  display: flex; flex-direction: column;
  overflow: hidden;
  border-right: 1px solid rgba(255,255,255,.05);
}
.smyle-search-col:last-child { border-right: 0; }

.smyle-search-col-hdr {
  display: flex; align-items: center; gap: 7px;
  padding: 10px 16px 8px;
  font-size: 10px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: rgba(255,255,255,.35);
  border-bottom: 1px solid rgba(255,255,255,.04);
  flex-shrink: 0;
}
.smyle-search-col-hdr svg { width: 12px; height: 12px; }
.smyle-search-col-hdr.connect { color: rgba(100,200,255,.6); }
.smyle-search-col-hdr.dna     { color: rgba(204,136,255,.7); }

/* Facette nature Sons / Images (C4 ③) */
.ss-nature-toggle { display:inline-flex; gap:4px; margin-left:auto; }
.ss-nature-btn {
  font: inherit; font-size: 10px; letter-spacing: .04em; cursor: pointer;
  padding: 2px 8px; border-radius: 999px; border: 1px solid rgba(204,136,255,.2);
  background: rgba(204,136,255,.06); color: rgba(204,136,255,.7);
  transition: all .12s ease; text-transform: none;
}
.ss-nature-btn:hover { border-color: rgba(204,136,255,.5); color:#cc88ff; }
.ss-nature-btn.is-active { border-color: rgba(204,136,255,.85); background: rgba(204,136,255,.2); color:#fff; }

/* Sous-titre « Usage » au-dessus des chips de tags d'usage (mode Images) */
.ss-usage-sub {
  padding: 2px 16px 4px; font-size: 9px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: rgba(204,136,255,.5);
}

/* Cards images dans la recherche */
.ss-img-card { display:flex; align-items:center; gap:11px; padding:8px 14px; cursor:pointer; transition:background .1s ease; }
.ss-img-card:hover { background: rgba(255,255,255,.04); }
.ss-img-thumb { width:40px; height:40px; border-radius:8px; flex-shrink:0; overflow:hidden; display:flex; align-items:center; justify-content:center; background:rgba(124,58,237,.18); }
.ss-img-thumb img { width:100%; height:100%; object-fit:cover; }
.ss-img-body { flex:1; min-width:0; }
.ss-img-title { font-size:13px; font-weight:600; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ss-img-sub { font-size:11px; color:rgba(255,255,255,.4); margin-top:1px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ss-img-meta { font-size:10px; color:#cbb3ff; font-weight:700; flex-shrink:0; }

/* Chips filtre */
.smyle-search-chips {
  display: flex; flex-wrap: wrap; gap: 5px;
  padding: 8px 14px 6px; border-bottom: 1px solid rgba(255,255,255,.04);
  flex-shrink: 0;
}
.smyle-search-chip {
  padding: 3px 10px; border-radius: 999px; font-size: 11px;
  cursor: pointer; transition: all .12s ease; border: 1px solid;
}
.smyle-search-chip.connect-chip {
  border-color: rgba(100,200,255,.2); background: rgba(100,200,255,.06);
  color: rgba(100,200,255,.7);
}
.smyle-search-chip.connect-chip:hover,
.smyle-search-chip.connect-chip.is-active {
  border-color: rgba(100,200,255,.6); background: rgba(100,200,255,.16);
  color: #64C8FF;
}
.smyle-search-chip.dna-chip {
  border-color: rgba(204,136,255,.2); background: rgba(204,136,255,.06);
  color: rgba(204,136,255,.7);
}
.smyle-search-chip.dna-chip:hover,
.smyle-search-chip.dna-chip.is-active {
  border-color: rgba(204,136,255,.6); background: rgba(204,136,255,.18);
  color: #cc88ff;
}

/* Liste résultats (scrollable) */
.smyle-search-results {
  flex: 1; overflow-y: auto; padding: 6px 0;
}
.smyle-search-results::-webkit-scrollbar { width: 4px; }
.smyle-search-results::-webkit-scrollbar-thumb { background: rgba(255,255,255,.1); border-radius: 2px; }

/* ── Cards artistes ──────────────────────────────────────────────────── */
.ss-artist-card {
  display: flex; align-items: center; gap: 11px;
  padding: 9px 14px; text-decoration: none;
  transition: background .1s ease; cursor: pointer;
}
.ss-artist-card:hover { background: rgba(255,255,255,.04); }
.ss-artist-avatar {
  width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700; color: #fff;
  overflow: hidden;
}
.ss-artist-avatar img { width: 100%; height: 100%; object-fit: cover; }
.ss-artist-body { flex: 1; min-width: 0; }
.ss-artist-name {
  font-size: 13px; font-weight: 600; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ss-artist-sub {
  font-size: 11px; color: rgba(255,255,255,.4); margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ss-artist-meta { font-size: 10px; color: rgba(255,255,255,.28); flex-shrink: 0; text-align: right; }

/* ── Cards sons ──────────────────────────────────────────────────────── */
.ss-track-card {
  display: flex; align-items: center; gap: 11px;
  padding: 8px 14px; text-decoration: none;
  transition: background .1s ease; cursor: pointer;
}
.ss-track-card:hover { background: rgba(255,255,255,.04); }
.ss-track-cover {
  width: 40px; height: 40px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; position: relative; cursor: pointer;
}
/* Hint permanent que la pochette est le bouton lecture. */
.ss-track-cover .ss-track-play-overlay { opacity: .35; }
.ss-track-cover:hover .ss-track-play-overlay { opacity: 1; }
.ss-track-cover img { width: 100%; height: 100%; object-fit: cover; }
.ss-track-cover-fallback {
  width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
  font-size: 16px;
}
.ss-track-play-overlay {
  position: absolute; inset: 0; background: rgba(0,0,0,.45);
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .12s;
  color: #fff; border-radius: 8px;
}
.ss-track-card:hover .ss-track-play-overlay { opacity: 1; }
.ss-track-card.ss-playing { background: rgba(124,58,237,.12); }
.ss-track-card.ss-playing .ss-track-play-overlay { opacity: 1; color: #c4b5fd; }
.ss-track-body { flex: 1; min-width: 0; }
.ss-track-title {
  font-size: 13px; font-weight: 600; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  cursor: pointer; display: inline; width: fit-content; max-width: 100%;
}
.ss-track-title:hover { color: #c4b5fd; text-decoration: underline; }
.ss-track-sub {
  font-size: 11px; color: rgba(255,255,255,.4); margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ss-track-tags { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 3px; }
.ss-track-tag {
  font-size: 10px; padding: 0 5px; border-radius: 99px;
  background: rgba(204,136,255,.1); border: 1px solid rgba(204,136,255,.18);
  color: rgba(204,136,255,.85);
}
.ss-track-meta { font-size: 10px; color: rgba(255,255,255,.28); flex-shrink: 0; text-align: right; }

/* ── États vide / chargement ─────────────────────────────────────────── */
.ss-empty {
  padding: 32px 16px; text-align: center;
  color: rgba(255,255,255,.3); font-size: 12px; line-height: 1.6;
}
.ss-loading { padding: 28px 16px; text-align: center; }
.ss-loading-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: rgba(255,255,255,.25); margin: 0 3px;
  animation: ssPulse 1.2s ease-in-out infinite;
}
.ss-loading-dot:nth-child(2) { animation-delay: .2s; }
.ss-loading-dot:nth-child(3) { animation-delay: .4s; }
@keyframes ssPulse { 0%,80%,100%{transform:scale(.8);opacity:.4} 40%{transform:scale(1);opacity:1} }
    `;
    document.head.appendChild(s);
  }

  // ── Injection bouton ──────────────────────────────────────────────────
  function injectButton() {
    const container = document.querySelector(
      '.dash-topbar-right, .ap-topbar-right, .lib-topbar-right, .topbar-right'
    );
    if (!container || container.querySelector('.smyle-search-btn')) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'smyle-search-btn';
    btn.setAttribute('aria-label', 'Rechercher');
    btn.title = 'Rechercher  (Ctrl+K)';
    btn.innerHTML = ICO_SEARCH;
    btn.addEventListener('click', openModal);
    container.insertBefore(btn, container.firstChild);
  }

  // ── State ─────────────────────────────────────────────────────────────
  let modalRoot    = null;
  let inputEl      = null;
  let connectEl    = null; // résultats gauche
  let dnaEl        = null; // résultats droite
  let debounce     = null;
  let lastQuery    = '';
  // Multi-select : Sets de valeurs actives par colonne
  let activeConnectChips = new Set();
  let activeDnaChips     = new Set();
  // Tags d'usage actifs (mode Images uniquement) — filtre /images?tag=
  let activeUsageChips   = new Set();
  // Facette nature de la colonne droite : 'sons' (défaut) | 'images' (C4 ③)
  let dnaNature          = 'sons';

  // ── Build modal ───────────────────────────────────────────────────────
  function buildModal() {
    if (modalRoot) return;
    modalRoot = document.createElement('div');
    modalRoot.className = 'smyle-search-overlay';
    modalRoot.setAttribute('role', 'dialog');
    modalRoot.setAttribute('aria-modal', 'true');
    modalRoot.setAttribute('aria-label', 'Recherche WATT');

    const connectChipsHtml = CONNECT_CHIPS.map(c =>
      `<button type="button" class="smyle-search-chip connect-chip" data-val="${c.val}">${c.label}</button>`
    ).join('');

    const dnaChipsHtml = DNA_CHIPS.map(c =>
      `<button type="button" class="smyle-search-chip dna-chip" data-val="${c.val}">${c.label}</button>`
    ).join('');

    modalRoot.innerHTML = `
      <div class="smyle-search-panel" role="document">

        <!-- Barre de recherche -->
        <div class="smyle-search-header">
          <span class="smyle-search-header-ico">${ICO_SEARCH}</span>
          <input type="search" class="smyle-search-input"
                 placeholder="Artiste, son, mood, ville…"
                 autocomplete="off" spellcheck="false" />
          <span class="smyle-search-kbd">ESC</span>
          <button type="button" class="smyle-search-close" aria-label="Fermer">${ICO_CLOSE}</button>
        </div>

        <!-- Corps 2 colonnes -->
        <div class="smyle-search-body">

          <!-- Colonne CONNECT -->
          <div class="smyle-search-col" id="ss-col-connect">
            <div class="smyle-search-col-hdr connect">
              ${ICO_USER} <span id="ss-connect-hdr-lbl">CONNECT — Artistes</span>
            </div>
            <div class="smyle-search-chips" id="ss-connect-chips">${connectChipsHtml}</div>
            <div class="smyle-search-results" id="ss-results-connect" aria-live="polite"></div>
          </div>

          <!-- Colonne DNA (Sons) / Images — facette nature C4 ③ -->
          <div class="smyle-search-col" id="ss-col-dna">
            <div class="smyle-search-col-hdr dna">
              ${ICO_DISC} <span id="ss-dna-hdr-lbl">DNA — Sons</span>
              <span class="ss-nature-toggle" role="tablist" aria-label="Nature">
                <button type="button" class="ss-nature-btn is-active" data-nature="sons" role="tab" aria-selected="true">🎵 Sons</button>
                <button type="button" class="ss-nature-btn" data-nature="images" role="tab" aria-selected="false">🖼️ Images</button>
              </span>
            </div>
            <div class="smyle-search-chips" id="ss-dna-chips">${dnaChipsHtml}</div>
            <!-- Tags d'usage (mode Images uniquement) — filtre complémentaire /images?tag= -->
            <div class="ss-usage-sub" id="ss-usage-sub" style="display:none">Usage</div>
            <div class="smyle-search-chips" id="ss-usage-chips" style="display:none"></div>
            <div class="smyle-search-results" id="ss-results-dna" aria-live="polite"></div>
          </div>

        </div>
      </div>
    `;

    document.body.appendChild(modalRoot);

    // Refs
    inputEl   = modalRoot.querySelector('.smyle-search-input');
    connectEl = modalRoot.querySelector('#ss-results-connect');
    dnaEl     = modalRoot.querySelector('#ss-results-dna');

    // Clic sur un morceau :
    //   - sur la POCHETTE (icône play) → lecture inline (découverte du mood) ;
    //   - partout ailleurs (titre, texte) → atterrit sur le profil du vendeur
    //     avec la carte détail du son ouverte (achat direct ou navigation).
    // Zone de navigation large (toute la carte sauf la pochette) → fiable au clic.
    dnaEl.addEventListener('click', (e) => {
      // Mode Images (C4 ③) : clic carte → fiche/drawer d'achat (recette gatée).
      const imgCard = e.target.closest('.ss-img-card');
      if (imgCard) {
        e.preventDefault();
        const id = imgCard.getAttribute('data-image-id');
        if (id && window.PurchaseDrawer) {
          window.PurchaseDrawer.open({
            type: 'image',
            id: id,
            price: parseInt(imgCard.getAttribute('data-price'), 10) || null,
            title: imgCard.getAttribute('data-title') || 'Image IA',
            platform: imgCard.getAttribute('data-platform') || '',
          });
        } else if (id) {
          window.location.href = '/images';
        }
        return;
      }
      const card = e.target.closest('.ss-track-card');
      if (!card) return;
      e.preventDefault();
      if (e.target.closest('.ss-track-cover')) {
        _ssPlayTrack(card);
        return;
      }
      const slug = card.getAttribute('data-artist-slug');
      const id   = card.getAttribute('data-track-id');
      if (slug) {
        window.location.href = '/@' + encodeURIComponent(slug) + '#son-' + encodeURIComponent(id || '');
        return;
      }
      _ssPlayTrack(card); // pas de slug → fallback lecture
    });

    // Events — overlay
    modalRoot.addEventListener('click', e => { if (e.target === modalRoot) closeModal(); });
    modalRoot.querySelector('.smyle-search-close').addEventListener('click', closeModal);

    // Input
    inputEl.addEventListener('input', onInput);
    inputEl.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); closeModal(); } });

    // Chips CONNECT + DNA — délégation (les conteneurs sont re-rendus au
    // changement de nature, donc on écoute le parent une seule fois).
    const connectChipsBox = modalRoot.querySelector('#ss-connect-chips');
    if (connectChipsBox) connectChipsBox.addEventListener('click', e => {
      const chip = e.target.closest('.smyle-search-chip');
      if (chip && connectChipsBox.contains(chip)) onChipClick(chip, 'connect');
    });
    const dnaChipsBox = modalRoot.querySelector('#ss-dna-chips');
    if (dnaChipsBox) dnaChipsBox.addEventListener('click', e => {
      const chip = e.target.closest('.smyle-search-chip');
      if (chip && dnaChipsBox.contains(chip)) onChipClick(chip, 'dna');
    });
    const usageChipsBox = modalRoot.querySelector('#ss-usage-chips');
    if (usageChipsBox) usageChipsBox.addEventListener('click', e => {
      const chip = e.target.closest('.smyle-search-chip');
      if (chip && usageChipsBox.contains(chip)) onChipClick(chip, 'usage');
    });

    // Facette nature Sons / Images (C4 ③) — bascule la colonne droite ET les
    // deux jeux de chips (CONNECT rôles + DNA styles/moods).
    modalRoot.querySelectorAll('.ss-nature-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const nat = btn.dataset.nature || 'sons';
        if (nat === dnaNature) return;
        dnaNature = nat;
        modalRoot.querySelectorAll('.ss-nature-btn').forEach(b => {
          const on = b.dataset.nature === nat;
          b.classList.toggle('is-active', on);
          b.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        applyNatureChips(nat);
        _trigger();
      });
    });

    document.addEventListener('keydown', onGlobalKey);
  }

  function onGlobalKey(e) {
    // Ctrl+K / Cmd+K — ouvre le panneau
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      if (modalRoot && modalRoot.classList.contains('is-open')) closeModal();
      else openModal();
      return;
    }
    if (!modalRoot || !modalRoot.classList.contains('is-open')) return;
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); }
  }

  // C4 — la recherche suit le MONDE de l'interface principale : le
  // commutateur marketplace (localStorage 'mp_mode') pilote la nature de la
  // recherche. Visuel → recherche en mode Images (rôles visuels + styles) ;
  // Musique → mode Sons. Re-synchronisé à CHAQUE ouverture (le mode a pu
  // changer entre deux ouvertures). Le toggle interne reste utilisable pour
  // basculer ponctuellement sans changer le monde de l'interface.
  function _syncNatureFromMpMode() {
    if (!modalRoot) return;
    let mode = 'musique';
    try { mode = localStorage.getItem('mp_mode') || 'musique'; } catch (_) {}
    const nat = (mode === 'image') ? 'images' : 'sons';
    dnaNature = nat;
    modalRoot.querySelectorAll('.ss-nature-btn').forEach(b => {
      const on = b.dataset.nature === nat;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    applyNatureChips(nat);
  }

  function openModal() {
    buildModal();
    _syncNatureFromMpMode();
    modalRoot.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    setTimeout(() => inputEl && inputEl.focus(), 30);
    _trigger();
  }

  function closeModal() {
    if (!modalRoot) return;
    _ssStop();
    modalRoot.classList.remove('is-open');
    document.body.style.overflow = '';
    // Reset chips à la fermeture
    activeConnectChips.clear();
    activeDnaChips.clear();
    activeUsageChips.clear();
    if (inputEl) inputEl.value = '';
    lastQuery = '';
  }

  function onInput() {
    lastQuery = (inputEl.value || '').trim();
    clearTimeout(debounce);
    debounce = setTimeout(_trigger, DEBOUNCE_MS);
  }

  // C4 — re-rend les chips CONNECT + DNA selon la nature et met à jour les
  // titres de colonnes. On RESET les sélections actives au passage : un code
  // audio (ex. mood 'chill') ne doit jamais fuiter dans une requête image
  // (et inversement), sinon le backend renvoie 0 résultat silencieusement.
  function chipHtml(c, cls) {
    return `<button type="button" class="smyle-search-chip ${cls}" data-val="${c.val}">${c.label}</button>`;
  }
  function applyNatureChips(nat) {
    const isImg = nat === 'images';
    activeConnectChips.clear();
    activeDnaChips.clear();
    activeUsageChips.clear();

    const connectBox = modalRoot.querySelector('#ss-connect-chips');
    if (connectBox) {
      const src = isImg ? CONNECT_CHIPS_IMG : CONNECT_CHIPS;
      connectBox.innerHTML = src.map(c => chipHtml(c, 'connect-chip')).join('');
    }
    const dnaBox = modalRoot.querySelector('#ss-dna-chips');
    if (dnaBox) {
      const src = isImg ? DNA_CHIPS_IMG : DNA_CHIPS;
      dnaBox.innerHTML = src.map(c => chipHtml(c, 'dna-chip')).join('');
      // Mode image : les chips de style FILTRENT le catalogue (≠ moods qui ne
      // s'appliquaient qu'aux sons) → on les laisse visibles.
      dnaBox.style.display = '';
    }
    // Tags d'usage : visibles UNIQUEMENT en mode Images (filtre /images?tag=).
    const usageSub = modalRoot.querySelector('#ss-usage-sub');
    const usageBox = modalRoot.querySelector('#ss-usage-chips');
    if (usageBox) {
      usageBox.innerHTML = isImg ? USAGE_CHIPS_IMG.map(c => chipHtml(c, 'dna-chip')).join('') : '';
      usageBox.style.display = isImg ? '' : 'none';
    }
    if (usageSub) usageSub.style.display = isImg ? '' : 'none';
    const connectLbl = modalRoot.querySelector('#ss-connect-hdr-lbl');
    if (connectLbl) connectLbl.textContent = isImg ? 'CONNECT — Créateurs visuels' : 'CONNECT — Artistes';
    const dnaLbl = modalRoot.querySelector('#ss-dna-hdr-lbl');
    if (dnaLbl) dnaLbl.textContent = isImg ? 'DNA — Styles' : 'DNA — Sons';
  }

  function onChipClick(chip, side) {
    const val = chip.dataset.val;
    const set  = side === 'connect' ? activeConnectChips
               : side === 'usage'   ? activeUsageChips
               : activeDnaChips;
    if (set.has(val)) {
      set.delete(val);
      chip.classList.remove('is-active');
    } else {
      set.add(val);
      chip.classList.add('is-active');
    }
    _trigger();
  }

  // Lance la recherche avec le texte + les chips actifs
  function _trigger() {
    clearTimeout(debounce);
    runSearch(lastQuery, activeConnectChips, activeDnaChips);
  }

  // ── Fetch parallèle ───────────────────────────────────────────────────
  async function runSearch(q, connectChips, dnaChips) {
    // On n'affiche QUE sur sélection (mood/rôle) ou texte tapé. Colonne vide
    // sans critère → placeholder, pas tout le catalogue (demande Tom).
    const hasQ      = !!(q && q.trim());
    const doArtists = hasQ || (connectChips && connectChips.size > 0);
    // Mode Images (C4 ③) : la colonne droite cherche des images. Les chips
    // moods ne s'appliquent pas (facette image ≠ mood) → seul le texte filtre.
    const imageMode = dnaNature === 'images';
    // Mode Images (C4) : la colonne droite cherche des images, filtrées par
    // TEXTE et/ou STYLE (les chips DNA portent désormais des codes de style).
    const doRight   = imageMode
      ? (hasQ || (dnaChips && dnaChips.size > 0) || activeUsageChips.size > 0)
      : (hasQ || (dnaChips && dnaChips.size > 0));
    if (doArtists) setLoading(connectEl); else renderArtists([], q);
    if (doRight)   setLoading(dnaEl);     else (imageMode ? renderImages([], q) : renderTracks([], q));
    const [artists, right] = await Promise.all([
      doArtists ? fetchArtists(q, connectChips) : Promise.resolve([]),
      doRight   ? (imageMode ? fetchImages(q, dnaChips, activeUsageChips) : fetchTracks(q, dnaChips)) : Promise.resolve([]),
    ]);
    if (doArtists && connectEl) renderArtists(artists, q);
    if (doRight && dnaEl) { if (imageMode) renderImages(right, q); else renderTracks(right, q); }
  }

  async function fetchImages(q, stylesSet, usageSet) {
    try {
      const params = new URLSearchParams({ q: q || '', limit: '12' });
      // C4 — filtre par STYLE (égalité stricte côté backend ?style=<code>).
      // Les chips DNA sont multi-sélection mais /images n'accepte qu'un style :
      // on envoie le 1er sélectionné (le style est la facette prioritaire).
      if (stylesSet && stylesSet.size > 0) {
        params.append('style', stylesSet.values().next().value);
      }
      // Tag d'usage (présence côté backend ?tag=<code>). Multi-sélection côté
      // UI mais on reste simple : on envoie le 1er tag sélectionné.
      if (usageSet && usageSet.size > 0) {
        params.append('tag', usageSet.values().next().value);
      }
      const res = await fetch(`${API_BASE}/images?${params}`, { credentials: 'omit' });
      if (!res.ok) return [];
      const data = await res.json();
      return data.images || [];
    } catch { return []; }
  }

  async function fetchArtists(q, rolesSet) {
    try {
      const params = new URLSearchParams({ q, limit: '12' });
      if (rolesSet && rolesSet.size > 0) {
        rolesSet.forEach(r => params.append('roles', r));
      }
      const url = `${API_BASE}/watt/search/artists?${params}`;
      const res = await fetch(url, { credentials: 'omit' });
      if (!res.ok) return [];
      const data = await res.json();
      return data.artists || [];
    } catch { return []; }
  }

  async function fetchTracks(q, moodsSet) {
    try {
      const params = new URLSearchParams({ q, limit: '12' });
      if (moodsSet && moodsSet.size > 0) {
        moodsSet.forEach(m => params.append('moods', m));
      }
      const url = `${API_BASE}/watt/search/tracks?${params}`;
      const res = await fetch(url, { credentials: 'omit' });
      if (!res.ok) return [];
      const data = await res.json();
      return data.tracks || [];
    } catch { return []; }
  }

  // ── Render ────────────────────────────────────────────────────────────
  function setLoading(el) {
    if (!el) return;
    el.innerHTML = `<div class="ss-loading"><span class="ss-loading-dot"></span><span class="ss-loading-dot"></span><span class="ss-loading-dot"></span></div>`;
  }

  function renderArtists(list, q) {
    if (!connectEl) return;
    if (!list.length) {
      connectEl.innerHTML = `<div class="ss-empty">${q ? `Aucun artiste pour "${escHtml(q)}"` : 'Explore les artistes WATT'}</div>`;
      return;
    }
    connectEl.innerHTML = list.map(a => artistCardHtml(a)).join('');
  }

  function renderTracks(list, q) {
    if (!dnaEl) return;
    if (!list.length) {
      dnaEl.innerHTML = `<div class="ss-empty">${q ? `Aucun son pour "${escHtml(q)}"` : 'Explore les sons du catalogue'}</div>`;
      return;
    }
    dnaEl.innerHTML = list.map(t => trackCardHtml(t)).join('');
  }

  function renderImages(list, q) {
    if (!dnaEl) return;
    if (!list.length) {
      dnaEl.innerHTML = `<div class="ss-empty">${q ? `Aucune image pour "${escHtml(q)}"` : 'Tape pour explorer les images IA'}</div>`;
      return;
    }
    dnaEl.innerHTML = list.map(im => imgCardHtml(im)).join('');
  }

  function imgCardHtml(im) {
    // Aperçu via proxy public (sert UNIQUEMENT images/previews/). Aucune
    // donnée de recette n'arrive ici (endpoint ImagePublicRead).
    const key = im.previewKey || '';
    const url = key ? '/watt/images/' + key.split('/').map(encodeURIComponent).join('/') : '';
    const thumb = url ? `<img src="${escAttr(url)}" alt="" />` : '🖼️';
    const platLbl = { midjourney: 'Midjourney', dalle: 'DALL·E', flux: 'Flux', stable_diffusion: 'Stable Diffusion', autre: 'Autre' }[im.imagePlatform] || (im.imagePlatform || '');
    const sub = [platLbl, im.ratio].filter(Boolean).join(' · ');
    return `
      <div class="ss-img-card" role="button" tabindex="0"
           data-image-id="${escAttr(im.id || '')}"
           data-price="${escAttr(im.priceCredits != null ? im.priceCredits : '')}"
           data-title="${escAttr(im.title || '')}"
           data-platform="${escAttr(im.imagePlatform || '')}">
        <span class="ss-img-thumb">${thumb}</span>
        <span class="ss-img-body">
          <span class="ss-img-title">${escHtml(im.title || 'Image IA')}</span>
          <span class="ss-img-sub">${escHtml(sub || 'Image IA')}</span>
        </span>
        <span class="ss-img-meta">${escHtml(im.priceCredits != null ? im.priceCredits + ' ⚡' : '')}</span>
      </div>`;
  }

  function artistCardHtml(a) {
    const color    = a.brandColor || '#7C3AED';
    const initials = (a.artistName || '?').slice(0, 2).toUpperCase();
    const avatar   = a.avatarUrl
      ? `<img src="${escAttr(a.avatarUrl)}" alt="" />`
      : initials;
    const sub  = [a.genre, a.city].filter(Boolean).join(' · ') || (a.bio || '').slice(0, 60) || 'Artiste WATT';
    const meta = `${_fmt(a.plays || 0)} écoutes`;
    const href = `/@${encodeURIComponent(a.slug || '')}`;
    return `
      <a class="ss-artist-card" href="${escAttr(href)}">
        <span class="ss-artist-avatar" style="background:${escAttr(color)};color:#fff">${avatar}</span>
        <span class="ss-artist-body">
          <span class="ss-artist-name">${escHtml(a.artistName || 'Artiste')}</span>
          <span class="ss-artist-sub">${escHtml(sub)}</span>
        </span>
        <span class="ss-artist-meta">${escHtml(meta)}</span>
      </a>`;
  }

  function trackCardHtml(t) {
    const color = t.color || '#7C3AED';
    const cover = t.coverUrl
      ? `<img src="${escAttr(t.coverUrl)}" alt="" />`
      : `<div class="ss-track-cover-fallback" style="background:${escAttr(color)}33">🎵</div>`;
    const sub  = [t.artistName, t.universe].filter(Boolean).join(' · ');
    const meta = `${_fmt(t.plays || 0)} écoutes`;
    const tags = t.tags
      ? t.tags.split(',').slice(0, 3).map(tag =>
          `<span class="ss-track-tag">${escHtml(tag.trim())}</span>`
        ).join('')
      : '';
    // Clic = lecture inline (découverte d'un mood), pas de redirection slug.
    const streamUrl = t.audioUrl || t.streamUrl || '';
    return `
      <div class="ss-track-card" role="button" tabindex="0"
           data-stream-url="${escAttr(streamUrl)}"
           data-artist-slug="${escAttr(t.artistSlug || '')}"
           data-track-id="${escAttr(t.id || '')}">
        <span class="ss-track-cover" style="background:${escAttr(color)}22" title="Écouter un extrait">
          ${cover}
          <span class="ss-track-play-overlay">${ICO_PLAY}</span>
        </span>
        <span class="ss-track-body" title="Voir la fiche du son">
          <span class="ss-track-title">${escHtml(t.title || 'Sans titre')}</span>
          <span class="ss-track-sub">${escHtml(sub)}</span>
          ${tags ? `<span class="ss-track-tags">${tags}</span>` : ''}
        </span>
        <span class="ss-track-meta">${escHtml(meta)}</span>
      </div>`;
  }

  // ── Lecture inline depuis la recherche (audio partagé) ───────────────────
  let _ssAudio = null;
  let _ssCard  = null;
  function _ssStop() {
    if (_ssAudio) { try { _ssAudio.pause(); } catch (_) {} }
    if (_ssCard) _ssCard.classList.remove('ss-playing');
    _ssCard = null;
  }
  function _ssPlayTrack(card) {
    const url = card.getAttribute('data-stream-url');
    if (!url) return;
    if (!_ssAudio) {
      _ssAudio = new Audio();
      _ssAudio.addEventListener('ended', () => { if (_ssCard) _ssCard.classList.remove('ss-playing'); _ssCard = null; });
    }
    // Re-clic sur la même carte = pause/play.
    if (_ssCard === card && !_ssAudio.paused) { _ssAudio.pause(); card.classList.remove('ss-playing'); _ssCard = null; return; }
    if (_ssCard && _ssCard !== card) _ssCard.classList.remove('ss-playing');
    _ssAudio.src = url;
    _ssAudio.play().catch(() => {});
    card.classList.add('ss-playing');
    _ssCard = card;
  }

  // ── Utils ─────────────────────────────────────────────────────────────
  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function escAttr(s) { return escHtml(s); }
  function _fmt(n) {
    const num = parseInt(n, 10) || 0;
    return num >= 1000 ? (num / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : String(num);
  }

  // ── Init ──────────────────────────────────────────────────────────────
  function init() {
    injectStyles();
    injectButton();
  }

  // API publique — ouverture depuis un autre script ou raccourci
  window.SmyleSearch = { open: openModal, close: closeModal };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
