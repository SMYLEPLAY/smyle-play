/* ═══════════════════════════════════════════════════════════════════════════
   SMYLE PLAY — artiste.js  (Phase 5 — 2026-04-20)

   La page /u/<slug> est la BOUTIQUE PUBLIQUE — 100% LECTURE SEULE.
   L'édition du profil vit UNIQUEMENT sur /dashboard#sec-identity (ATELIER).

     ► vue publique (fans)   : toujours lecture seule
     ► vue owner + publié    : preview "comme les fans" + lien "Éditer dans le dashboard"
     ► vue owner + brouillon : preview + bouton "Publier mon profil"
     ► vue owner sans nom    : redirect auto vers /dashboard#sec-identity

   Pas de mode édition inline (`toggleOwnerEdit`, `.ap-owner-editing` et
   `.ap-editable` sont conservés pour compat CSS mais neutralisés fonctionnellement).

   Backend touché :
     GET  /watt/artists/<slug>         → récupère le profil (isSelf, profilePublic…)
     POST /watt/me/profile/publish     → bascule profile_public=TRUE (bouton "Publier")
     (PATCH /users/me est désormais appelé UNIQUEMENT depuis dashboard.js.)
   ═══════════════════════════════════════════════════════════════════════════ */
'use strict';

/* ── Helpers DOM ─────────────────────────────────────────────────────────── */

function $(id) { return document.getElementById(id); }
function show(id)   { const el = $(id); if (el) el.style.display = ''; }
function hide(id)   { const el = $(id); if (el) el.style.display = 'none'; }
function setText(id, v) { const el = $(id); if (el) el.textContent = String(v ?? ''); }

function getSlugFromUrl() {
  // On accepte /u/<slug> (canonique) et /artiste/<slug> (legacy, avant
  // redirection 301) pour rester robuste si la page est servie
  // directement via l'alias ou si un vieux bookmark pointe encore ici.
  const m = window.location.pathname.match(/\/(?:u|artiste)\/([^/]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

// Slugifier à la façon du backend (_derive_artist_slug / _slugify).
// On reste simple : normalize NFD, ASCII only, lowercase, tirets.
function slugify(s) {
  return String(s || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

// Retourne l'utilisateur connecté tel que stocké en localStorage par la
// couche auth (storage.js). On lit directement la clé pour ne pas dépendre
// du chargement de storage.js sur cette page.
function getStoredUser() {
  try {
    const raw = localStorage.getItem('smyle_current_user');
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}

// Le slug dans l'URL correspond-il à l'utilisateur connecté ?
// Compatible avec le backend : slug = slugify(artist_name) ou email local-part.
function currentUserMatchesSlug(slug) {
  const u = getStoredUser();
  if (!u) return false;
  if (!slug) return false;
  const candidates = [];
  if (u.artist_name) candidates.push(slugify(u.artist_name));
  if (u.artistName)  candidates.push(slugify(u.artistName));
  if (u.email)       candidates.push(slugify(String(u.email).split('@')[0]));
  return candidates.some(c => c && c === slug);
}

// Profil "stub" pour le mode création : owner connecté sur son propre slug,
// mais le backend ne connaît pas encore ce user (migration / fraîche inscription
// / backend 404 transitoire). On affiche quand même la page en mode édition
// pour que l'owner puisse remplir et déclencher la création côté backend via
// PATCH /users/me.
function buildOwnerStubArtist(slug) {
  const u = getStoredUser() || {};
  return {
    id:                 u.id || '',
    userId:             u.id || '',
    slug:               slug,
    artistName:         u.artist_name || u.artistName || '',
    genre:              '',
    bio:                '',
    city:               '',
    brandColor:         '',
    profileBgColor:     '',
    profileBrandColor:  '',
    avatarUrl:          u.avatar_url || u.avatarUrl || '',
    coverPhotoUrl:      '',
    influences:         '',
    soundcloud:         '',
    instagram:          '',
    youtube:            '',
    tiktok:             '',
    spotify:            '',
    twitterX:           '',
    plays:              0,
    trackCount:         0,
    rank:               0,
    followersCount:     0,
    followingCount:     0,
    followersSample:    [],
    isFollowing:        false,
    isSelf:             true,
    profilePublic:      false,
    tracks:             [],
  };
}

/* ── État global de la page (source de vérité unique) ───────────────────── */
// Une seule structure mutable qui reflète le profil courant côté client.
// Après chaque PATCH réussie, on met à jour ici et on re-rend ce qu'il faut.
const state = {
  artist:   null,  // objet renvoyé par GET /watt/artists/<slug>
  editing:  false, // mode édition actif ?
  editingField: null, // champ ouvert dans le modal (avatarUrl | coverPhotoUrl)
};

/* ── Thème 2 couleurs (#RRGGBB pour bg + accent) ────────────────────────── */

const THEME_DEFAULTS = {
  bg:    '#070608',
  brand: '#8800FF',  // violet WATT par défaut (cohérent logo)
};

function hexToRgbTriplet(hex) {
  const m = String(hex || '').trim().match(/^#?([0-9a-f]{6})$/i);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return `${(n >> 16) & 0xff}, ${(n >> 8) & 0xff}, ${n & 0xff}`;
}

function normalizeHex(v) {
  const m = String(v || '').trim().match(/^#?([0-9a-f]{6})$/i);
  return m ? ('#' + m[1].toUpperCase()) : null;
}

function applyTheme(bgHex, brandHex) {
  const root   = document.documentElement;
  const bg     = normalizeHex(bgHex)    || THEME_DEFAULTS.bg;
  const brand  = normalizeHex(brandHex) || THEME_DEFAULTS.brand;
  const triplet = hexToRgbTriplet(brand) || hexToRgbTriplet(THEME_DEFAULTS.brand);
  root.style.setProperty('--bg',        bg);
  root.style.setProperty('--brand',     brand);
  root.style.setProperty('--brand-rgb', triplet);
}

/* ── Chargement initial ──────────────────────────────────────────────────── */

async function loadArtist() {
  const slug = getSlugFromUrl();
  if (!slug) {
    showError('Slug manquant', 'L\'URL ne contient pas d\'identifiant artiste.');
    return;
  }

  try {
    const json = await apiFetch(`/watt/artists/${encodeURIComponent(slug)}`);
    if (!json || !json.artist) {
      // Pas d'artist → soit l'user connecté arrive sur son propre slug
      // fraîchement créé (backend n'a pas encore de row le liant au slug
      // demandé) → on bascule en mode création stub ; sinon vraie 404.
      if (currentUserMatchesSlug(slug)) {
        state.artist = buildOwnerStubArtist(slug);
        renderProfile();
        maybePromptFirstEdit();
        return;
      }
      showError('Profil introuvable', 'Ce profil n\'existe pas ou n\'est pas encore publié.');
      return;
    }
    state.artist = json.artist;
    // P1-F9 — On charge les voix en parallèle / async sans bloquer le render
    // initial. La cellule voix apparaît dès que le fetch retourne (∼100ms),
    // pas besoin d'attendre pour render le reste du profil.
    state.artist.voices = [];  // état initial → renderVoices cache la section
    renderProfile();
    loadArtistVoices(state.artist.id);
    // Si le profil est vide ET l'utilisateur est owner, on active direct le
    // mode édition pour qu'il puisse remplir sans clic supplémentaire.
    maybePromptFirstEdit();
  } catch (err) {
    console.error('[artiste.js] Erreur chargement :', err);
    // 404 côté owner = même cas que plus haut : on construit un stub de
    // création pour que la page ne soit JAMAIS blanche pour lui.
    if (err && err.status === 404 && currentUserMatchesSlug(slug)) {
      state.artist = buildOwnerStubArtist(slug);
      renderProfile();
      maybePromptFirstEdit();
      return;
    }
    if (err && err.status === 404) {
      showError('Profil introuvable', 'Ce profil n\'existe pas ou n\'est pas encore publié.');
    } else {
      showError('Erreur', 'Impossible de charger ce profil pour le moment. Réessaie dans un instant.');
    }
  }
}

// Phase 5 (2026-04-20) — L'édition profil vit UNIQUEMENT sur /dashboard.
//   • owner sans nom           → redirect vers /dashboard#sec-identity
//     (la page publique n'a littéralement rien à afficher sans nom)
//   • owner avec nom, !publié → on reste ici (preview + bouton Publier
//     géré par renderOwnerBar)
//   • owner avec nom, publié   → vue normale, identique aux fans
// Le paramètre ?edit=1 legacy est ignoré + nettoyé silencieusement.
function maybePromptFirstEdit() {
  const a = state.artist;
  if (!a || !a.isSelf) return;

  const hasName = !!(a.artistName && a.artistName.trim());

  if (!hasName) {
    // Profil squelettique → redirige vers l'atelier pour que l'user remplisse.
    // Message d'accueil géré côté dashboard (sec-identity ouvert par défaut
    // quand artist_name est null — cf. dashboard.js initIdentityAccordion).
    window.location.href = '/dashboard#sec-identity';
    return;
  }

  // Nettoie le ?edit=1 legacy s'il traîne (ne déclenche plus rien).
  if (_hasEditIntentParam()) {
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete('edit');
      window.history.replaceState(null, '', url.toString());
    } catch (_) { /* URL API indisponible — ignore */ }
  }
}

// Détecte l'intention d'édition forcée depuis l'URL (?edit=1 | ?edit=true).
function _hasEditIntentParam() {
  try {
    const p = new URLSearchParams(window.location.search);
    const v = (p.get('edit') || '').toLowerCase();
    return v === '1' || v === 'true' || v === 'yes';
  } catch (_) {
    return false;
  }
}

/* ── Rendu principal ─────────────────────────────────────────────────────── */

function renderProfile() {
  const artist = state.artist;
  if (!artist) return;

  // ── Thème couleurs AVANT le reveal (pas de flash) ────────────────────
  applyTheme(artist.profileBgColor, artist.profileBrandColor || artist.brandColor);

  hide('ap-loading');
  hide('ap-error');
  show('ap-profile');

  const isSelf     = !!artist.isSelf;
  const isPublic   = !!artist.profilePublic;
  const trackCount = Number(artist.trackCount || 0);

  // ── Body classes — pilote toute la présentation ──────────────────────
  document.body.classList.toggle('ap-owner',   isSelf);
  document.body.classList.toggle('ap-skeleton', !isPublic && !isSelf);
  // L'état .ap-owner-editing est géré par toggleOwnerEdit(), pas ici.

  // ── Barre owner (sticky) ─────────────────────────────────────────────
  renderOwnerBar({ isSelf, isPublic, trackCount });

  // ── Contenu : avatar / nom / bio / meta ──────────────────────────────
  renderHeader(artist);

  // ── Socials (#43) ────────────────────────────────────────────────────
  renderSocials(artist, isSelf);

  // ── Stats publiques ──────────────────────────────────────────────────
  renderStats(artist);

  // ── Chantier "profil artiste vendeur" ───────────────────────────────
  // Trois sections marketplace, toutes conditionnelles :
  //   • ADN  : visible ssi artist.adn != null
  //   • Prompts : visible ssi artist.prompts.length > 0
  //   • Tracks  : visible ssi artist.tracks.length > 0
  // Règle produit : si l'user ne vend rien et n'a pas de son, RIEN ne
  // s'affiche côté marketplace (pas de placeholder vide) — c'est ce que
  // voit un fan "pur". Cf. discussion vision / organisation.
  renderDna(artist);
  renderPrompts(artist);
  renderVoices(artist);
  renderTracks(artist);
  _updateSaleDisclaimerVisibility(artist);

  // ── Onglet navigateur ────────────────────────────────────────────────
  const name = artist.artistName && artist.artistName.trim();
  if (isSelf && !isPublic) {
    document.title = 'Mon profil · WATT';
  } else {
    document.title = `${name || 'Artiste WATT'} · WATT`;
  }

  // ── Init pickers couleurs (une fois) ─────────────────────────────────
  initColorPickers();
}

/* ── Barre owner : statut + actions ──────────────────────────────────────── */

function renderOwnerBar({ isSelf, isPublic, trackCount }) {
  const bar = $('ap-owner-bar');
  if (!bar) return;

  if (!isSelf) {
    bar.style.display = 'none';
    return;
  }

  bar.style.display = '';

  // 3 états visuels : view / edit / draft (plus de gate 1-son : un compte
  // peut publier son profil sans avoir posté de son — c'est la page
  // profil "membre", pas la vitrine artiste stricto sensu).
  const editing   = !!state.editing;
  const hasName   = !!(state.artist && (state.artist.artistName || '').trim());
  const canPublish = hasName; // seule exigence : un nom
  const isArtist   = trackCount > 0;

  // Reset classes
  bar.classList.remove('ap-owner-view', 'ap-owner-edit', 'ap-owner-draft');

  let label;
  if (editing) {
    bar.classList.add('ap-owner-edit');
    label = 'Mode édition — clique sur un champ pour le modifier';
  } else if (!isPublic) {
    bar.classList.add(canPublish ? 'ap-owner-view' : 'ap-owner-draft');
    label = canPublish
      ? 'Ton profil est en brouillon — prêt à publier'
      : 'Ton profil est en brouillon — ajoute un nom pour publier';
  } else {
    bar.classList.add('ap-owner-view');
    label = isArtist
      ? 'Tu vois ta page comme les fans'
      : 'Ton profil est public — publie un son depuis le WATT BOARD pour devenir artiste';
  }
  setText('ap-owner-bar-label', label);

  // Bouton "Modifier" — Phase 5 : édition migrée sur /dashboard#sec-identity.
  // On transforme le bouton en lien vers l'atelier au lieu de lancer le mode
  // édition inline. Le onclick inline défini dans le HTML est neutralisé.
  const btnEdit = $('ap-owner-btn-edit');
  const lblEdit = $('ap-owner-btn-edit-label');
  if (lblEdit) lblEdit.textContent = 'Éditer dans le dashboard';
  if (btnEdit) {
    btnEdit.classList.remove('is-active');
    btnEdit.onclick = (ev) => {
      if (ev && ev.preventDefault) ev.preventDefault();
      window.location.href = '/dashboard#sec-identity';
    };
  }

  // Bouton "Publier mon profil" (Option B legacy) — DÉSACTIVÉ (chantier
  // "1 bouton unifié", 2026-04-21). La publication ne peut plus se faire
  // depuis /u/<slug> : elle est déclenchée automatiquement au premier
  // enregistrement de profil depuis /dashboard#sec-identity. Ça supprime
  // la distinction "save vs publish" que les users ne comprenaient pas.
  // On masque le bouton en toutes circonstances pour éviter le chemin
  // parallèle. Le HTML/DOM reste en place pour compat CSS / legacy states.
  const btnPub = $('ap-owner-btn-publish');
  if (btnPub) btnPub.style.display = 'none';

  // Lien "Gérer la visibilité" — quand le profil est DÉJÀ public, on ne
  // propose plus de (re)bascule ici : on pointe vers PLUG WATT (WATT BOARD).
  // Source unique de vérité pour la visibilité, fini les deux contrôles
  // parallèles qui peuvent diverger.
  const btnManage = $('ap-owner-btn-manage');
  if (btnManage) {
    btnManage.style.display = (isPublic && !editing) ? '' : 'none';
  }

  // Le gate banner n'a plus lieu d'être (on n'exige plus 1 son).
  const gate = $('ap-owner-bar-gate');
  if (gate) gate.style.display = 'none';
}

/* ── Header : avatar + nom + bio + meta ──────────────────────────────────── */

function renderHeader(artist) {
  // Cover photo
  const heroBg = $('ap-hero-bg');
  if (heroBg) {
    if (artist.coverPhotoUrl) {
      heroBg.style.backgroundImage = `url("${cssEscapeUrl(artist.coverPhotoUrl)}")`;
      heroBg.classList.add('has-image');
    } else {
      heroBg.style.backgroundImage = '';
      heroBg.classList.remove('has-image');
    }
  }

  // Avatar : image si URL, sinon initiale du nom, sinon silhouette ghost
  const avatarEl = $('ap-avatar');
  if (avatarEl) {
    avatarEl.innerHTML = '';
    if (artist.avatarUrl) {
      avatarEl.classList.remove('ap-avatar-ghost');
      const img = document.createElement('img');
      img.src = artist.avatarUrl;
      img.alt = artist.artistName || '';
      img.addEventListener('error', () => {
        avatarEl.classList.add('ap-avatar-ghost');
        avatarEl.textContent = (artist.artistName || '?').charAt(0).toUpperCase();
      });
      avatarEl.appendChild(img);
    } else if (artist.artistName && artist.artistName.trim()) {
      avatarEl.classList.remove('ap-avatar-ghost');
      avatarEl.textContent = artist.artistName.trim().charAt(0).toUpperCase();
    } else {
      // ghost silhouette — on laisse le SVG placeholder déjà posé par le HTML
      avatarEl.classList.add('ap-avatar-ghost');
      avatarEl.innerHTML = `
        <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="8" r="4"/>
          <path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>
        </svg>`;
    }
  }

  // Nom, genre, ville dans le hero
  fillEditable('ap-artist-name', artist.artistName);
  fillEditable('ap-genre',       artist.genre);
  fillEditable('ap-city',        artist.city);

  // Chips de casquettes (rôles déclarés par l'utilisateur).
  // Cf. ROLE_CATALOG / renderRoles() plus bas. Le body reçoit aussi
  // ap-is-artist si « artiste » est dans les casquettes — permet aux
  // règles CSS / autres pages de savoir si c'est un profil artiste.
  const roles    = Array.isArray(artist.roles) ? artist.roles : [];
  const isArtist = roles.includes('artiste');
  document.body.classList.toggle('ap-is-artist', isArtist);
  document.body.classList.toggle('ap-is-member', !isArtist);
  renderRoles(roles, !!artist.isSelf);

  // Sections longues en-dessous.
  //
  // Note architecturale (chantier "séparation profil / WATT BOARD") :
  // la page /u/<slug> n'expose QUE l'identité publique (nom, casquettes,
  // bio courte, socials). Les champs "influences musicales" et "univers"
  // existent toujours côté user (colonnes users.influences / users.universe_description)
  // mais ils ne sont plus éditables ici : ils alimentent la création de DNA
  // et de prompts (contenu vendable) et vivent donc côté WATT BOARD.
  fillEditable('ap-bio', artist.bio);

  // Pour les fans (non-self), on masque la section bio si elle est vide.
  // Pour l'owner, on la laisse visible avec son placeholder.
  toggleSectionForFans('ap-section-bio', artist.bio, artist.isSelf);
}

// Masque une section entière pour les fans si la valeur est vide.
// (L'owner voit toujours les sections pour pouvoir les remplir.)
function toggleSectionForFans(sectionId, value, isSelf) {
  const el = $(sectionId);
  if (!el) return;
  const hasContent = !!(value && String(value).trim());
  el.style.display = (hasContent || isSelf) ? '' : 'none';
}

/* ═══════════════════════════════════════════════════════════════════════════
   CASQUETTES / RÔLES DÉCLARÉS
   ═══════════════════════════════════════════════════════════════════════════

   Un utilisateur coche sur /u/<slug> les rôles qu'il endosse dans l'écosystème
   musical. Déclaratif : pas de conditions (nb de sons, ancienneté, etc.),
   juste "voilà qui je suis". Multi-select, stocké en JSON array côté DB.

   La liste canonique ROLE_CATALOG doit rester synchrone avec ROLE_CODES
   dans smyleplay-api/app/schemas/user.py — l'ordre aussi (ordre d'affichage).
   Si tu ajoutes un rôle : MAJ les 2 fichiers + migration si besoin. */

const ROLE_CATALOG = [
  { code: 'artiste',       label: 'Artiste',        desc: 'Interprète, pose sur les morceaux.'      },
  { code: 'producteur',    label: 'Producteur',     desc: 'Compose et structure les morceaux.'       },
  { code: 'beatmaker',     label: 'Beatmaker',      desc: 'Fabrique des instrus.'                    },
  { code: 'topliner',      label: 'Topliner',       desc: 'Pose mélodies et hooks sur prod.'         },
  { code: 'ghostwriter',   label: 'Ghostwriter',    desc: 'Écrit pour d\'autres artistes.'          },
  { code: 'compositeur',   label: 'Compositeur',    desc: 'Écrit musiques et arrangements.'          },
  { code: 'parolier',      label: 'Parolier',       desc: 'Spécialisé textes / lyrics.'             },
  { code: 'arrangeur',     label: 'Arrangeur',      desc: 'Arrange / orchestre un morceau.'         },
  { code: 'editeur',       label: 'Éditeur',        desc: 'Gère droits et édition.'                 },
  { code: 'dj',            label: 'DJ',             desc: 'Mix, sélection, live.'                    },
  { code: 'ingenieur_son', label: 'Ingé son',       desc: 'Mix, mastering, studio.'                  },
  { code: 'auditeur',      label: 'Auditeur',       desc: 'Écoute, suit, découvre.'                  },
];

// Accès rapide code → meta
const ROLE_BY_CODE = Object.fromEntries(ROLE_CATALOG.map(r => [r.code, r]));

// Affiche la ligne de chips de casquettes dans le hero. Appelé depuis
// renderHeader. Si aucun rôle : on affiche un CTA discret pour l'owner
// ("Ajoute tes casquettes"), rien pour les fans.
function renderRoles(roles, isSelf) {
  const wrap = $('ap-roles');
  if (!wrap) return;

  const list = Array.isArray(roles) ? roles : [];
  wrap.innerHTML = '';

  if (list.length === 0) {
    if (isSelf) {
      // CTA discret pour l'owner : le bouton + Casquettes est à côté,
      // mais on rappelle visuellement que la case est vide.
      const ghost = document.createElement('span');
      ghost.className = 'ap-role-chip ap-role-chip-ghost';
      ghost.textContent = 'Sans casquette';
      wrap.appendChild(ghost);
    }
    return;
  }

  list.forEach(code => {
    const meta = ROLE_BY_CODE[code];
    if (!meta) return; // code inconnu (ancien rôle retiré du catalog) : skip
    const chip = document.createElement('span');
    chip.className = 'ap-role-chip';
    chip.textContent = meta.label;
    chip.title = meta.desc;
    wrap.appendChild(chip);
  });
}

// Ouvre le popover "Mes casquettes" (mode owner uniquement).
function openRolesPicker() {
  if (!state.artist || !state.artist.isSelf) return;
  const picker = $('ap-roles-picker');
  if (!picker) return;
  buildRolesPicker(state.artist.roles || []);
  picker.style.display = '';
  // Focus 1ère checkbox pour accessibilité
  const firstBox = picker.querySelector('input[type="checkbox"]');
  if (firstBox) firstBox.focus();
  // Echap ferme
  document.addEventListener('keydown', _rolesPickerEscHandler);
}

function closeRolesPicker() {
  const picker = $('ap-roles-picker');
  if (picker) picker.style.display = 'none';
  document.removeEventListener('keydown', _rolesPickerEscHandler);
}

function _rolesPickerEscHandler(ev) {
  if (ev.key === 'Escape') closeRolesPicker();
}

// Construit la liste de checkboxes à partir de ROLE_CATALOG, avec
// l'état initial = roles déjà cochés.
function buildRolesPicker(currentRoles) {
  const list = $('ap-roles-picker-list');
  if (!list) return;
  const selected = new Set(currentRoles || []);
  list.innerHTML = '';
  ROLE_CATALOG.forEach(role => {
    const id = 'ap-role-cb-' + role.code;
    const row = document.createElement('label');
    row.className = 'ap-role-option';
    row.htmlFor = id;
    row.innerHTML = `
      <input type="checkbox" id="${id}" value="${role.code}" ${selected.has(role.code) ? 'checked' : ''} />
      <span class="ap-role-option-main">
        <span class="ap-role-option-label">${role.label}</span>
        <span class="ap-role-option-desc">${role.desc}</span>
      </span>
    `;
    list.appendChild(row);
  });
}

// Récupère les codes cochés et envoie un PATCH /users/me.
async function saveRolesPicker() {
  if (!state.artist || !state.artist.isSelf) return;
  const list = $('ap-roles-picker-list');
  if (!list) return;
  const boxes = list.querySelectorAll('input[type="checkbox"]');
  const picked = [];
  boxes.forEach(b => { if (b.checked) picked.push(b.value); });

  try {
    const updated = await apiFetch('/users/me', {
      method: 'PATCH',
      json:   { roles: picked },
    });
    // Le backend renvoie UserRead complet : on met à jour l'état local.
    state.artist.roles = Array.isArray(updated.roles) ? updated.roles : [];
    renderRoles(state.artist.roles, true);
    // Refresh body classes : artiste déclaré / non
    const isArtist = state.artist.roles.includes('artiste');
    document.body.classList.toggle('ap-is-artist', isArtist);
    document.body.classList.toggle('ap-is-member', !isArtist);
    closeRolesPicker();
    toast('Casquettes enregistrées');
  } catch (err) {
    console.error('[artiste.js] save roles error', err);
    toast('Impossible d\'enregistrer — réessaie.');
  }
}

/* ─── fin rôles ────────────────────────────────────────────────────────── */

/* ═══════════════════════════════════════════════════════════════════════════
   DNA / Prompts / Tracks — côté profil (marketplace vendeur)
   ═══════════════════════════════════════════════════════════════════════════

   La page profil devient un mini-store quand l'artiste a publié des items
   vendables. Trois objets côté backend (watt_compat.get_artist) :

     artist.adn             → objet {id, descriptionTeaser, priceCredits, ...}
                              ou null si pas d'ADN publié.
     artist.prompts         → array [{id, title, description, priceCredits,
                              hasLyrics}] des prompts publiés (meta only —
                              prompt_text/lyrics gated jusqu'à unlock).
     artist.promptsForSale  → int, redondant avec prompts.length côté UI.
     artist.tracks          → array [{id, name, streamUrl, plays, date}]
                              existant depuis Phase 1.

   Aucune de ces 3 sections ne s'affiche si la donnée correspondante est
   vide/null. Le fan pur (aucune vente, aucun son) n'en voit aucune.

   Les achats POST /unlocks/adns/{id} et /unlocks/prompts/{id} :
   - 201 Created + objet owned → toast "Débloqué"
   - 402 Payment Required → toast "Crédits insuffisants"
   - 401 Unauthorized    → rediriger vers login
   - 409 Conflict (already owned) → toast "Déjà débloqué"
   - 400 self-purchase   → toast silencieux (ne devrait pas arriver, le
                            bouton est masqué pour isSelf)                  */

// ═══ Item 7 · Disclaimer fiche vente ════════════════════════════════════
// Affiche le disclaimer UNIQUEMENT si l'artiste vend quelque chose.
// Critère : au moins 1 ADN OU au moins 1 prompt OU au moins 1 voix publiée.
// Voix ajoutées P1-F9 (2026-05-03) — chargées en async via loadArtistVoices,
// donc cette fonction est rappelée par renderVoices une fois les voix prêtes.
function _updateSaleDisclaimerVisibility(artist) {
  const el = document.getElementById('ap-sale-disclaimer');
  if (!el) return;
  const hasAdn     = !!(artist && artist.adn);
  const hasPrompts = Array.isArray(artist && artist.prompts) && artist.prompts.length > 0;
  const hasVoices  = Array.isArray(artist && artist.voices)  && artist.voices.length  > 0;
  el.style.display = (hasAdn || hasPrompts || hasVoices) ? '' : 'none';
}

function renderDna(artist) {
  const card = $('ap-dna-card');
  if (!card) return;
  const adn = artist && artist.adn;
  if (!adn) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';
  setText('ap-dna-price', formatCount(adn.priceCredits));
  setText('ap-dna-teaser', adn.descriptionTeaser || '');

  // Badges "Guide d'usage" / "Exemples" si fournis
  const meta = $('ap-dna-meta');
  if (meta) {
    meta.innerHTML = '';
    if (adn.hasUsageGuide) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge">📘 Guide d\'usage</span>');
    }
    if (adn.hasExampleOutputs) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge">🎧 Exemples</span>');
    }
  }

  // Masque le bouton unlock pour l'owner (pas d'auto-achat).
  const btn = $('ap-dna-unlock-btn');
  if (btn) {
    if (artist.isSelf) {
      btn.style.display = 'none';
    } else {
      btn.style.display = '';
      setText('ap-dna-unlock-label',
        `Débloquer · ${formatCount(adn.priceCredits)} crédits`);
    }
  }
}

// P1-F4 (2026-05-04) — libellés humains des enums backend pour les
// réglages de génération exposés sur les cards prompts publiques.
// Aligned avec PromptPlatform / PromptVocalGender (smyleplay-api).
const _PROMPT_PLATFORM_LBL = {
  suno:         'Suno',
  udio:         'Udio',
  riffusion:    'Riffusion',
  stable_audio: 'Stable Audio',
  autre:        'Autre',
};
function _voicePromptPlatformLbl(key) {
  return _PROMPT_PLATFORM_LBL[key] || (key || '');
}

const _PROMPT_VOCAL_GENDER_LBL = {
  masculin:     '🎙 Voix masculine',
  feminin:      '🎙 Voix féminine',
  instrumental: '🎵 Instrumental',
};
function _promptVocalGenderLbl(key) {
  return _PROMPT_VOCAL_GENDER_LBL[key] || (key || '');
}

function renderPrompts(artist) {
  const section = $('ap-prompts-section');
  const list    = $('ap-prompts-list');
  if (!section || !list) return;

  const prompts = Array.isArray(artist && artist.prompts) ? artist.prompts : [];
  if (prompts.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';
  setText('ap-prompts-count',
    `${prompts.length} recette${prompts.length > 1 ? 's' : ''}`);

  list.innerHTML = '';
  prompts.forEach(p => {
    const card = document.createElement('article');
    card.className = 'ap-prompt-card';
    const safeTitle = (p.title || '').replace(/</g, '&lt;');
    const safeDesc  = (p.description || '').replace(/</g, '&lt;');
    const priceStr  = formatCount(p.priceCredits);
    const lyricsBadge = p.hasLyrics
      ? '<span class="ap-prompt-badge">🎤 Avec paroles</span>'
      : '';
    // P1-F4 (2026-05-04) — badges réglages génération.
    // Visibles publiquement pour donner confiance à l'acheteur (il sait
    // qu'il a tout ce qu'il faut pour reproduire). Ne révèlent pas le
    // prompt_text — juste les paramètres.
    const platformBadge = p.promptPlatform
      ? `<span class="ap-prompt-badge">${_voicePromptPlatformLbl(p.promptPlatform)}</span>`
      : '';
    const modelBadge = p.promptModelVersion
      ? `<span class="ap-prompt-badge">${(p.promptModelVersion || '').replace(/</g, '&lt;')}</span>`
      : '';
    const vocalBadge = p.promptVocalGender
      ? `<span class="ap-prompt-badge">${_promptVocalGenderLbl(p.promptVocalGender)}</span>`
      : '';
    const settingsBlock = (p.promptWeirdness || p.promptStyleInfluence)
      ? `<div class="ap-prompt-settings">
           ${p.promptWeirdness ? `<div class="ap-prompt-setting"><span class="ap-prompt-setting-key">Weirdness</span> ${(p.promptWeirdness || '').replace(/</g, '&lt;')}</div>` : ''}
           ${p.promptStyleInfluence ? `<div class="ap-prompt-setting"><span class="ap-prompt-setting-key">Influence</span> ${(p.promptStyleInfluence || '').replace(/</g, '&lt;')}</div>` : ''}
         </div>`
      : '';
    // Pas de bouton unlock pour l'owner (évite l'auto-achat 400).
    const unlockBtn = artist.isSelf
      ? '<span class="ap-prompt-owner-note">Ton prompt</span>'
      : `<button type="button" class="ap-prompt-unlock-btn"
                 data-prompt-id="${p.id}" data-price="${p.priceCredits}">
          🔓 Débloquer · ${priceStr} crédits
        </button>`;
    card.innerHTML = `
      <div class="ap-prompt-card-top">
        <h3 class="ap-prompt-card-title">${safeTitle}</h3>
        ${lyricsBadge}
      </div>
      ${safeDesc ? `<p class="ap-prompt-card-desc">${safeDesc}</p>` : ''}
      <div class="ap-prompt-card-meta">
        ${platformBadge}
        ${modelBadge}
        ${vocalBadge}
      </div>
      ${settingsBlock}
      <div class="ap-prompt-card-actions">${unlockBtn}</div>
    `;
    list.appendChild(card);
  });

  // Délégation : un seul listener pour toute la liste (re-rendue souvent)
  list.onclick = (ev) => {
    const btn = ev.target.closest('.ap-prompt-unlock-btn');
    if (!btn) return;
    const id = btn.dataset.promptId;
    if (id) unlockPromptFromProfile(id, btn);
  };
}

function renderTracks(artist) {
  const section = $('ap-tracks-section');
  const list    = $('ap-tracks-list');
  if (!section || !list) return;

  const tracks = Array.isArray(artist && artist.tracks) ? artist.tracks : [];
  if (tracks.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';
  setText('ap-tracks-count',
    `${tracks.length} son${tracks.length > 1 ? 's' : ''}`);

  // Item 1 — libellé lisible des plateformes d'origine
  const PLATFORM_LBL = {
    suno:         'Suno',
    udio:         'Udio',
    riffusion:    'Riffusion',
    stable_audio: 'Stable Audio',
    autre:        'Autre',
  };

  list.innerHTML = '';
  tracks.forEach(t => {
    const card = document.createElement('article');
    card.className = 'ap-track-card';
    const safeName = (t.name || 'Sans titre').replace(/</g, '&lt;');
    const plays    = formatCount(t.plays);
    const date     = t.date || '';
    const audio    = t.streamUrl
      ? `<audio controls preload="none" src="${t.streamUrl}" class="ap-track-audio"></audio>`
      : '';
    // Item 1 — badge plateforme (si connu). Gracieusement absent tant que le
    // backend ne renvoie pas le champ `platform` sur /api/artists/{slug}.
    const platformBadge = (t.platform && PLATFORM_LBL[t.platform])
      ? `<span class="ap-track-card-platform" title="Plateforme d'origine">
          <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 4c4 4 12 12 16 16M20 4c-4 4-12 12-16 16"/>
          </svg>
          ${PLATFORM_LBL[t.platform]}
        </span>`
      : '';
    card.innerHTML = `
      <div class="ap-track-card-top">
        <h3 class="ap-track-card-title">${safeName}</h3>
        <div class="ap-track-card-meta">
          <span>▶ ${plays}</span>
          ${date ? `<span>· ${date}</span>` : ''}
          ${platformBadge}
        </div>
      </div>
      ${audio}
    `;
    list.appendChild(card);
  });
}

// ── Unlock ADN depuis le profil ────────────────────────────────────────
async function unlockDnaFromProfile() {
  const artist = state.artist;
  if (!artist || !artist.adn || artist.isSelf) return;
  const btn = $('ap-dna-unlock-btn');
  if (btn) btn.disabled = true;
  try {
    await apiFetch(`/unlocks/adns/${encodeURIComponent(artist.adn.id)}`, {
      method: 'POST',
    });
    toast('ADN débloqué · -30 % sur toutes les recettes 🎉');
    // On rafraîchit le profil pour que l'état du bouton reflète le owned
    setTimeout(() => loadArtist(), 400);
  } catch (err) {
    handleUnlockError(err);
    if (btn) btn.disabled = false;
  }
}

// ── Unlock prompt depuis le profil ─────────────────────────────────────
async function unlockPromptFromProfile(promptId, btn) {
  if (!promptId) return;
  if (btn) btn.disabled = true;
  try {
    const resp = await apiFetch(
      `/unlocks/prompts/${encodeURIComponent(promptId)}`,
      { method: 'POST' },
    );
    // resp.perk_applied signale le bonus -30 % via possession ADN
    const msg = resp && resp.perk_applied
      ? 'Recette débloquée avec perk ADN -30 % 🔓'
      : 'Recette débloquée 🔓';
    toast(msg);
    // Reload pour que l'UI reflète l'état "déjà débloqué" (Phase 10 : n/a ici).
    setTimeout(() => loadArtist(), 400);
  } catch (err) {
    handleUnlockError(err);
    if (btn) btn.disabled = false;
  }
}

// ═══ P1-F9 — Voix (cellule profil public) ═══════════════════════════════
//
// Charge les voix publiées de l'artiste depuis GET /api/voices/by-artist/{id}
// (endpoint dédié — voix ne sont pas dans le payload /watt/artists/<slug>
// par design, voir la règle Tom project_voice_separation_rule).
//
// Le sample_url n'est JAMAIS retourné par cet endpoint public — on n'a que
// des VoicePublicRead (gating strict). Le sample arrive uniquement après
// /unlocks/voices/{id} dans le payload de réponse, et via /api/voices/me/unlocked
// pour la page /library.
async function loadArtistVoices(artistId) {
  if (!artistId) return;
  if (typeof apiFetch !== 'function') return;
  try {
    const list = await apiFetch(
      `/api/voices/by-artist/${encodeURIComponent(artistId)}`,
      { auth: false },  // endpoint public — pas besoin de JWT
    );
    state.artist.voices = Array.isArray(list) ? list : [];
  } catch (err) {
    // 404/500 → on cache la cellule, pas de message d'erreur user (la cellule
    // voix est secondaire ; un échec ne doit pas dégrader le reste du profil).
    console.warn('[artiste.js] loadArtistVoices error', err);
    state.artist.voices = [];
  }
  renderVoices(state.artist);
  // Recalcule la visibilité du disclaimer maintenant que voices est connu.
  _updateSaleDisclaimerVisibility(state.artist);
}

// Libellés humains des licences (alignés sur le backend VoiceLicense).
const VOICE_LICENSE_LBL = {
  personnel:  'Personnel',
  commercial: 'Commercial',
  exclusif:   'Exclusif',
};

// Mapping des keys de genres vers leurs labels affichés.
// (Source de vérité : DASH_VOICE_GENRES côté dashboard.js. On duplique ici
// volontairement parce que artiste.js n'a pas accès au scope dashboard.js,
// et la liste change rarement. À garder synchronisé si on ajoute un genre.)
const VOICE_GENRES_LBL = {
  rnb:    'RnB',     pop:    'Pop',     trap:   'Trap',     rap: 'Rap',
  electro:'Electro', house:  'House',   afro:   'Afro',     jazz:'Jazz',
  soul:   'Soul',    rock:   'Rock',    autre:  'Autre',
};

function _voiceGenresStr(keys) {
  if (!Array.isArray(keys) || !keys.length) return '';
  return keys.map(k => VOICE_GENRES_LBL[k] || k).join(' · ');
}

function renderVoices(artist) {
  const section = $('ap-voices-section');
  const list    = $('ap-voices-list');
  if (!section || !list) return;

  const voices = Array.isArray(artist && artist.voices) ? artist.voices : [];
  if (voices.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';
  setText('ap-voices-count',
    `${voices.length} voix`);

  list.innerHTML = '';
  voices.forEach(v => {
    const card = document.createElement('article');
    card.className = 'ap-voice-card';
    const safeName  = (v.name  || '').replace(/</g, '&lt;');
    const safeStyle = (v.style || '').replace(/</g, '&lt;');
    const priceStr  = formatCount(v.price_credits);
    const licenseLbl = VOICE_LICENSE_LBL[v.license] || v.license || '';
    const licenseClass = (v.license === 'exclusif')
      ? 'ap-voice-badge ap-voice-license-badge is-exclusif'
      : 'ap-voice-badge ap-voice-license-badge';
    const genresStr = _voiceGenresStr(v.genres);
    const genresBadge = genresStr
      ? `<span class="ap-voice-badge">${genresStr.replace(/</g, '&lt;')}</span>`
      : '';
    // P1-F9 enhancement (2026-05-03) : pré-écoute publique du sample pour
    // permettre à l'acheteur de juger la voix AVANT d'acheter. Sans ça,
    // taux de conversion ≈ 0 (personne ne paye 200 SMYLES à l'aveugle).
    // Le bouton télécharger reste gated jusqu'à l'unlock (côté /library).
    const previewBlock = v.sample_url
      ? `<audio controls preload="none" class="ap-voice-preview"
                src="${(v.sample_url + '').replace(/"/g, '&quot;')}"></audio>`
      : '';
    // Pas de bouton unlock pour l'owner (évite l'auto-achat 400).
    const unlockBtn = artist.isSelf
      ? '<span class="ap-voice-owner-note">Ta voix</span>'
      : `<button type="button" class="ap-voice-unlock-btn"
                 data-voice-id="${v.id}" data-price="${v.price_credits}">
          🔓 Débloquer · ${priceStr} crédits
        </button>`;
    card.innerHTML = `
      <div class="ap-voice-card-top">
        <h3 class="ap-voice-card-title">${safeName}</h3>
        <span class="${licenseClass}">${licenseLbl}</span>
      </div>
      ${safeStyle ? `<p class="ap-voice-card-style">${safeStyle}</p>` : ''}
      <div class="ap-voice-card-meta">
        ${genresBadge}
      </div>
      ${previewBlock}
      <div class="ap-voice-card-actions">${unlockBtn}</div>
    `;
    list.appendChild(card);
  });

  // Délégation click — un seul listener pour la liste re-rendue souvent.
  list.onclick = (ev) => {
    const btn = ev.target.closest('.ap-voice-unlock-btn');
    if (!btn) return;
    const id = btn.dataset.voiceId;
    if (id) unlockVoiceFromProfile(id, btn);
  };
}

// ── Unlock voix depuis le profil ───────────────────────────────────────
async function unlockVoiceFromProfile(voiceId, btn) {
  if (!voiceId) return;
  if (btn) btn.disabled = true;
  try {
    const resp = await apiFetch(
      `/unlocks/voices/${encodeURIComponent(voiceId)}`,
      { method: 'POST' },
    );
    // resp.sample_url contient l'URL R2 du sample maintenant débloqué.
    // Pour la 1re version on affiche un toast, et l'user retrouve sa voix
    // dans /library (onglet Voix — autre PR). Pas de player inline ici pour
    // garder la cellule compacte côté visuel.
    toast('Voix débloquée 🎙 — retrouve-la dans ta bibliothèque');
    // Pas besoin de reload du profil entier : la voix reste publique (les
    // autres user peuvent toujours l'acheter). On laisse l'UI inchangée.
    if (btn) {
      btn.disabled = true;
      btn.textContent = '✓ Débloquée';
    }
  } catch (err) {
    handleUnlockError(err);
    if (btn) btn.disabled = false;
  }
}

// Traduction centralisée des erreurs /unlocks/* → toast humain.
function handleUnlockError(err) {
  console.error('[artiste.js] unlock error', err);
  if (err && err.status === 401) {
    toast('Connecte-toi pour débloquer ce contenu.');
    return;
  }
  if (err && err.status === 402) {
    // body.detail = { message, required, available }
    const d = err.body && err.body.detail;
    if (d && typeof d === 'object') {
      toast(`Crédits insuffisants — il te faut ${d.required}, tu en as ${d.available}.`);
    } else {
      toast('Crédits insuffisants.');
    }
    return;
  }
  if (err && err.status === 409) {
    toast('Déjà débloqué.');
    return;
  }
  if (err && err.status === 400) {
    toast("Tu ne peux pas acheter ton propre contenu.");
    return;
  }
  toast('Impossible de débloquer — réessaie dans un instant.');
}

// Remplit un élément .ap-editable : valeur réelle OU placeholder visuel (pour
// les fans on masque les champs vides ; pour l'owner on affiche le placeholder).
function fillEditable(id, value) {
  const el = $(id);
  if (!el) return;
  const v = (value == null ? '' : String(value)).trim();
  if (v) {
    el.textContent = v;
    el.classList.remove('ap-editable-empty');
  } else {
    // Valeur vide : mode owner → placeholder visible en gris.
    el.textContent = el.dataset.placeholder || '';
    el.classList.add('ap-editable-empty');
  }
}

// Échappe les caractères problématiques d'une URL pour un `url("...")` CSS.
function cssEscapeUrl(u) {
  return String(u).replace(/"/g, '\\"');
}

/* ── Socials ─────────────────────────────────────────────────────────────── */

const SOCIAL_FIELDS = [
  { key: 'instagram',  label: 'Instagram',  emoji: '📸', field: 'instagram'  },
  { key: 'tiktok',     label: 'TikTok',     emoji: '🎵', field: 'tiktok'     },
  { key: 'youtube',    label: 'YouTube',    emoji: '▶️', field: 'youtube'    },
  { key: 'spotify',    label: 'Spotify',    emoji: '🟢', field: 'spotify'    },
  { key: 'soundcloud', label: 'SoundCloud', emoji: '☁️', field: 'soundcloud' },
  { key: 'twitterX',   label: 'X',          emoji: '✖️', field: 'twitter_x'  },
];

function renderSocials(artist, isSelf) {
  const wrap = $('ap-socials');
  if (!wrap) return;
  wrap.innerHTML = '';

  let hasAny = false;
  SOCIAL_FIELDS.forEach(s => {
    const val = (artist[s.key] || '').trim();
    if (val) {
      hasAny = true;
      const a = document.createElement('a');
      a.className = 'ap-social-chip';
      a.href   = val;
      a.target = '_blank';
      a.rel    = 'noopener noreferrer';
      a.title  = s.label;
      a.innerHTML = `<span class="ap-social-emoji">${s.emoji}</span><span class="ap-social-label">${s.label}</span>`;
      wrap.appendChild(a);
    } else if (isSelf) {
      // Owner : chip "+ ajouter" qui ouvre le modal URL
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ap-social-chip ap-social-add';
      btn.title = `Ajouter ${s.label}`;
      btn.innerHTML = `<span class="ap-social-emoji">${s.emoji}</span><span class="ap-social-label">+ ${s.label}</span>`;
      btn.addEventListener('click', () => openOwnerField(s.field, s.label));
      wrap.appendChild(btn);
    }
  });

  // Masque la section pour les fans si aucun réseau n'est renseigné
  wrap.style.display = (hasAny || isSelf) ? '' : 'none';
}

/* ── Stats publiques ─────────────────────────────────────────────────────── */

function formatCount(n) {
  const v = Number(n || 0);
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (v >= 1_000)     return (v / 1_000).toFixed(1).replace(/\.0$/, '') + 'k';
  return String(v);
}

function renderStats(artist) {
  const statsEl = $('ap-stats');
  if (!statsEl) return;

  const trackCount = Number(artist.trackCount || 0);
  const isSelf     = !!artist.isSelf;
  const isArtist   = trackCount > 0;

  // Fan (pas encore artiste) : on garde le strict minimum — abonnés.
  // Les tuiles "écoutes / sons / rang WATT" n'ont pas de sens pour
  // quelqu'un qui n'a jamais publié un son. Un fan connecté (owner)
  // voit aussi juste « abonnés » : s'il veut voir plus, il devient
  // artiste en postant un son depuis le WATT BOARD.
  const cellPlays     = $('ap-stat-cell-plays');
  const cellTracks    = $('ap-stat-cell-tracks');
  const cellRank      = $('ap-stat-cell-rank');
  const cellFollowers = $('ap-stat-cell-followers');

  if (cellPlays)     cellPlays.style.display     = isArtist ? '' : 'none';
  if (cellTracks)    cellTracks.style.display    = isArtist ? '' : 'none';
  if (cellRank)      cellRank.style.display      = isArtist ? '' : 'none';
  if (cellFollowers) cellFollowers.style.display = '';

  // Fan qui n'est pas l'owner et n'a pas encore d'abonnés : on cache
  // tout le bandeau, évite l'effet "section vide".
  if (!isArtist && !isSelf && !Number(artist.followersCount || 0)) {
    statsEl.style.display = 'none';
    return;
  }

  setText('ap-stat-plays',     formatCount(artist.plays));
  setText('ap-stat-tracks',    String(trackCount));
  setText('ap-stat-followers', formatCount(artist.followersCount));
  setText('ap-stat-rank',      artist.rank ? '#' + artist.rank : '—');
  statsEl.style.display = '';
}

/* ═══════════════════════════════════════════════════════════════════════════
   MODE OWNER — édition inline (DÉSACTIVÉ Phase 5 — 2026-04-20)

   L'édition inline sur /u/<slug> est désactivée. Toute tentative redirige
   vers /dashboard#sec-identity (atelier). Les fonctions sont conservées
   pour compat ascendante (appels externes, handlers legacy) mais short-
   circuitées en tête. Le code en dessous reste pour le jour où on voudrait
   re-réactiver (pas de suppression brutale → pas de casse git blame).
   ═══════════════════════════════════════════════════════════════════════════ */

// No-op : redirige vers le dashboard au lieu d'ouvrir le mode édition inline.
function toggleOwnerEdit() {
  if (!state.artist || !state.artist.isSelf) return;
  // Phase 5 : édition déléguée au dashboard.
  window.location.href = '/dashboard#sec-identity';
  return;
  // eslint-disable-next-line no-unreachable
  state.editing = !state.editing;

  document.body.classList.toggle('ap-owner-editing', state.editing);

  // Affichage des boutons d'édition "média" (avatar / cover)
  const avatarBtn = $('ap-avatar-edit');
  const coverBtn  = $('ap-hero-bg-edit');
  if (avatarBtn) avatarBtn.style.display = state.editing ? '' : 'none';
  if (coverBtn)  coverBtn.style.display  = state.editing ? '' : 'none';

  // Bouton "+ Casquettes" — visible uniquement quand on édite.
  const rolesBtn = $('ap-roles-edit-btn');
  if (rolesBtn) rolesBtn.style.display = state.editing ? '' : 'none';

  // Pickers couleurs
  const colors = $('ap-colors');
  if (colors) colors.style.display = state.editing ? '' : 'none';

  // Active/désactive contenteditable sur tous les .ap-editable
  const editables = document.querySelectorAll('.ap-editable');
  editables.forEach(el => {
    if (state.editing) {
      el.setAttribute('contenteditable', 'true');
      // Si on affichait le placeholder, on vide pour que l'utilisateur tape frais.
      if (el.classList.contains('ap-editable-empty')) {
        el.textContent = '';
      }
    } else {
      el.removeAttribute('contenteditable');
      // On a quitté l'édition : restaurer le rendu propre (placeholder si vide)
      const field = el.dataset.field;
      const val = state.artist[field] || '';
      fillEditable(el.id, val);
    }
  });

  // Relance l'affichage de la barre (label + bouton Modifier/Terminer)
  renderOwnerBar({
    isSelf: true,
    isPublic:  !!state.artist.profilePublic,
    trackCount: Number(state.artist.trackCount || 0),
  });
}

// Sauvegarde un champ éditable (appelé sur blur)
async function saveEditableField(el) {
  if (!state.artist || !state.artist.isSelf) return;
  const field = el.dataset.field;
  if (!field) return;

  const raw = (el.innerText || '').trim();
  // Mapping front (camelCase) → backend (snake_case) pour le payload PATCH.
  // Toutes les clés listées ici sont reconnues par UserUpdate côté FastAPI.
  //
  // On n'expose PLUS `influences` ni `universe_description` ici : ces champs
  // sont éditables exclusivement depuis le WATT BOARD (création DNA / prompt),
  // car leur contenu alimente des produits vendables de la marketplace.
  const API_FIELDS = {
    artistName: 'artist_name',
    bio:        'bio',
    genre:      'genre',
    city:       'city',
  };
  const apiField = API_FIELDS[field];
  if (!apiField) return;

  // Comparer à la valeur précédente pour éviter un PATCH inutile
  const current = (state.artist[field] || '').trim();
  if (raw === current) {
    // Juste rafraîchir l'affichage si l'utilisateur a laissé vide
    if (!raw) fillEditable(el.id, '');
    return;
  }

  // Certains champs ne peuvent pas être vidés (artist_name refuse la chaîne vide).
  // On envoie null pour "effacer", sauf pour artist_name qu'on garde non vide côté UI.
  const payload = {};
  if (raw === '' && field === 'artistName') {
    // On refuse de vider artist_name : on restaure l'ancienne valeur.
    fillEditable(el.id, current);
    toast('Le nom d\'artiste ne peut pas être vide.');
    return;
  }
  payload[apiField] = raw === '' ? null : raw;

  try {
    el.classList.add('ap-editable-saving');
    const updated = await apiFetch('/users/me', { method: 'PATCH', json: payload });
    // Met à jour l'état local (le backend renvoie UserRead — snake_case)
    state.artist[field] = updated[apiField] || '';
    fillEditable(el.id, state.artist[field]);
    toast('Enregistré');
    // Nom/bio modifiés → rafraîchir title et avatar ghost
    if (field === 'artistName') {
      renderHeader(state.artist);
      document.title = `${state.artist.artistName || 'Mon profil'} · WATT`;
      // Le bouton « Publier mon profil » dépend de canPublish = !!artistName.
      // On re-render la barre owner pour déverrouiller le bouton dès que
      // le nom est rempli.
      renderOwnerBar({
        isSelf:     true,
        isPublic:   !!state.artist.profilePublic,
        trackCount: Number(state.artist.trackCount || 0),
      });
    }
  } catch (err) {
    console.error('[artiste.js] PATCH error', err);
    toast('Impossible d\'enregistrer — réessaie.');
    // Restaurer la valeur précédente dans l'UI
    el.innerText = current;
  } finally {
    el.classList.remove('ap-editable-saving');
  }
}

/* ── Modal URL (avatar / cover / socials) ────────────────────────────────── */

// Quel label afficher dans le modal pour chaque champ
const FIELD_LABELS = {
  avatarUrl:     { title: 'Photo de profil',     hint: 'Colle l\'URL publique d\'une image (https://…).' },
  coverPhotoUrl: { title: 'Photo de couverture', hint: 'Colle l\'URL publique d\'une image large (https://…).' },
  instagram:     { title: 'Instagram',           hint: 'URL complète de ton profil (https://instagram.com/…)' },
  tiktok:        { title: 'TikTok',              hint: 'URL complète de ton profil (https://tiktok.com/@…)' },
  youtube:       { title: 'YouTube',             hint: 'URL de ta chaîne (https://youtube.com/@…)' },
  spotify:       { title: 'Spotify',             hint: 'URL de ton profil artiste Spotify' },
  soundcloud:    { title: 'SoundCloud',          hint: 'URL de ton profil SoundCloud' },
  twitter_x:     { title: 'X (ex-Twitter)',      hint: 'URL de ton profil X (https://x.com/…)' },
};

// Mapping front → backend (clé API) pour les champs du modal
const FIELD_API_KEYS = {
  avatarUrl:     'avatar_url',
  coverPhotoUrl: 'cover_photo_url',
  instagram:     'instagram',
  tiktok:        'tiktok',
  youtube:       'youtube',
  spotify:       'spotify',
  soundcloud:    'soundcloud',
  twitter_x:     'twitter_x',
};

// Mapping front → clé dans state.artist (camelCase renvoyé par l'API GET)
const FIELD_STATE_KEYS = {
  avatarUrl:     'avatarUrl',
  coverPhotoUrl: 'coverPhotoUrl',
  instagram:     'instagram',
  tiktok:        'tiktok',
  youtube:       'youtube',
  spotify:       'spotify',
  soundcloud:    'soundcloud',
  twitter_x:     'twitterX',
};

function openOwnerField(fieldName, customLabel) {
  if (!state.artist || !state.artist.isSelf) return;
  const modal = $('ap-modal');
  if (!modal) return;

  state.editingField = fieldName;
  const meta = FIELD_LABELS[fieldName] || { title: customLabel || 'Modifier', hint: 'Colle une URL (https://…)' };

  setText('ap-modal-title', meta.title);
  setText('ap-modal-hint',  meta.hint);

  // Section upload fichier : visible uniquement pour avatar + cover.
  const uploadBlock = $('ap-modal-upload');
  const statusEl    = $('ap-modal-upload-status');
  const isImageField = (fieldName === 'avatarUrl' || fieldName === 'coverPhotoUrl');
  if (uploadBlock) {
    uploadBlock.style.display = isImageField ? '' : 'none';
  }
  if (statusEl) { statusEl.textContent = ''; statusEl.className = 'ap-modal-upload-status'; }
  // Reset l'input file pour que le même fichier puisse être re-sélectionné
  const fileInput = $('ap-modal-file');
  if (fileInput) fileInput.value = '';

  const input = $('ap-modal-input');
  const stateKey = FIELD_STATE_KEYS[fieldName];
  if (input) {
    input.value = stateKey ? (state.artist[stateKey] || '') : '';
    modal.style.display = '';
    setTimeout(() => input.focus(), 50);
  }
}

/* ── Upload d'image depuis les fichiers (avatar / cover) ─────────────────
   Flow :
     1. User clique "Importer depuis mes fichiers" → déclenche l'input file
     2. User sélectionne une image → on POST /api/watt/upload-image
     3. Backend upload sur R2, retourne { url }
     4. On fait PATCH /users/me avec l'URL (avatar_url ou cover_photo_url)
     5. On ferme le modal + on rafraîchit l'affichage
   Validations côté client (avant upload pour UX) :
     - Type image/* uniquement
     - Taille max 5 MB
     (le backend re-valide, c'est juste pour éviter l'upload inutile). */

const IMAGE_UPLOAD_MAX = 5 * 1024 * 1024;

async function handleImageFileUpload(file) {
  const field = state.editingField;
  if (!field || (field !== 'avatarUrl' && field !== 'coverPhotoUrl')) return;
  if (!file) return;

  const statusEl = $('ap-modal-upload-status');

  // ── Validations client ──
  if (!/^image\//.test(file.type)) {
    if (statusEl) {
      statusEl.textContent = 'Ce fichier n\'est pas une image.';
      statusEl.className = 'ap-modal-upload-status is-error';
    }
    return;
  }
  if (file.size > IMAGE_UPLOAD_MAX) {
    if (statusEl) {
      statusEl.textContent = `Image trop lourde (${Math.round(file.size / 1024)} KB) — max 5 MB.`;
      statusEl.className = 'ap-modal-upload-status is-error';
    }
    return;
  }

  const u = getStoredUser();
  if (!u || !u.id) {
    if (statusEl) {
      statusEl.textContent = 'Tu dois être connecté pour uploader.';
      statusEl.className = 'ap-modal-upload-status is-error';
    }
    return;
  }

  if (statusEl) {
    statusEl.textContent = 'Upload en cours…';
    statusEl.className = 'ap-modal-upload-status is-loading';
  }

  // ── POST /api/watt/upload-image (Flask, même origine — pas apiFetch) ──
  // On tape directement sur Flask car l'upload R2 vit côté Flask (infra
  // boto3 déjà configurée), pas dans FastAPI. Donc pas d'API_BASE.
  const kind = (field === 'avatarUrl') ? 'avatar' : 'cover';
  const fd = new FormData();
  fd.append('file',   file);
  fd.append('userId', u.id);
  fd.append('kind',   kind);

  let uploadJson;
  try {
    const resp = await fetch('/api/watt/upload-image', { method: 'POST', body: fd });
    uploadJson = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const msg = uploadJson.error || `Upload impossible (HTTP ${resp.status}).`;
      throw new Error(msg);
    }
    if (!uploadJson.url) {
      throw new Error(uploadJson.error || 'Le serveur n\'a pas renvoyé d\'URL.');
    }
  } catch (err) {
    console.error('[artiste.js] upload-image error', err);
    if (statusEl) {
      statusEl.textContent = String(err.message || err) + ' Colle une URL à la place.';
      statusEl.className = 'ap-modal-upload-status is-error';
    }
    return;
  }

  // ── Pré-remplir le champ URL du modal — l'utilisateur peut relire ou éditer ──
  const input = $('ap-modal-input');
  if (input) input.value = uploadJson.url;

  // ── PATCH /users/me avec la nouvelle URL ──
  const apiKey   = FIELD_API_KEYS[field];
  const stateKey = FIELD_STATE_KEYS[field];
  try {
    const updated = await apiFetch('/users/me', {
      method: 'PATCH',
      json: { [apiKey]: uploadJson.url },
    });
    state.artist[stateKey] = updated[apiKey] || uploadJson.url;
    if (statusEl) {
      statusEl.textContent = 'Image enregistrée ✓';
      statusEl.className = 'ap-modal-upload-status is-ok';
    }
    // Ferme le modal après un court délai pour que l'user voie la confirmation
    setTimeout(() => {
      closeOwnerField();
      renderHeader(state.artist);
      toast('Image enregistrée');
    }, 500);
  } catch (err) {
    console.error('[artiste.js] PATCH après upload error', err);
    if (statusEl) {
      statusEl.textContent = 'Image uploadée mais pas sauvegardée — réessaie "Enregistrer".';
      statusEl.className = 'ap-modal-upload-status is-error';
    }
  }
}

function closeOwnerField() {
  state.editingField = null;
  const modal = $('ap-modal');
  if (modal) modal.style.display = 'none';
}

async function saveOwnerField() {
  const field = state.editingField;
  if (!field) return;
  const input = $('ap-modal-input');
  if (!input) return;

  const raw = (input.value || '').trim();
  const apiKey  = FIELD_API_KEYS[field];
  const stateKey = FIELD_STATE_KEYS[field];
  if (!apiKey || !stateKey) return closeOwnerField();

  // Payload : string vide → null (effacer)
  const payload = {};
  payload[apiKey] = raw === '' ? null : raw;

  try {
    const updated = await apiFetch('/users/me', { method: 'PATCH', json: payload });
    state.artist[stateKey] = updated[apiKey] || '';
    closeOwnerField();
    toast('Enregistré');

    // Rafraîchir les parties concernées
    if (field === 'avatarUrl' || field === 'coverPhotoUrl') {
      renderHeader(state.artist);
    } else {
      renderSocials(state.artist, true);
    }
  } catch (err) {
    console.error('[artiste.js] PATCH modal error', err);
    const msg = (err && err.body && err.body.detail) || 'URL invalide ou erreur réseau.';
    toast(typeof msg === 'string' ? msg : 'Erreur — réessaie.');
  }
}

/* ── Pickers couleurs (bg + accent) ──────────────────────────────────────── */

let _colorSaveTimer = null;
let _colorPickersInited = false;

function initColorPickers() {
  if (_colorPickersInited) return;
  _colorPickersInited = true;

  const bgInput    = $('ap-color-bg');
  const brandInput = $('ap-color-brand');
  if (!bgInput || !brandInput) return;

  // Pré-remplir avec les valeurs actuelles (ou defaults)
  const bgNow    = normalizeHex(state.artist && state.artist.profileBgColor)    || THEME_DEFAULTS.bg;
  const brandNow = normalizeHex(state.artist && (state.artist.profileBrandColor || state.artist.brandColor)) || THEME_DEFAULTS.brand;
  bgInput.value    = bgNow;
  brandInput.value = brandNow;
  setText('ap-color-bg-hex',    bgNow);
  setText('ap-color-brand-hex', brandNow);

  // Live preview + save débouncé
  bgInput.addEventListener('input',    () => onColorChange());
  brandInput.addEventListener('input', () => onColorChange());
}

function onColorChange() {
  const bgInput    = $('ap-color-bg');
  const brandInput = $('ap-color-brand');
  if (!bgInput || !brandInput) return;

  const bg    = normalizeHex(bgInput.value)    || THEME_DEFAULTS.bg;
  const brand = normalizeHex(brandInput.value) || THEME_DEFAULTS.brand;

  // Preview immédiat
  applyTheme(bg, brand);
  setText('ap-color-bg-hex',    bg);
  setText('ap-color-brand-hex', brand);

  // Debounced save (on évite de patcher 200x pendant le drag du color wheel)
  clearTimeout(_colorSaveTimer);
  _colorSaveTimer = setTimeout(() => saveColors(bg, brand), 400);
}

async function saveColors(bg, brand) {
  if (!state.artist || !state.artist.isSelf) return;
  try {
    const updated = await apiFetch('/users/me', {
      method: 'PATCH',
      json: { profile_bg_color: bg, profile_brand_color: brand },
    });
    state.artist.profileBgColor    = updated.profile_bg_color    || '';
    state.artist.profileBrandColor = updated.profile_brand_color || '';
    toast('Couleurs enregistrées');
  } catch (err) {
    console.error('[artiste.js] PATCH colors error', err);
    toast('Impossible d\'enregistrer les couleurs.');
  }
}

function resetOwnerColors() {
  const bgInput    = $('ap-color-bg');
  const brandInput = $('ap-color-brand');
  if (bgInput)    bgInput.value    = THEME_DEFAULTS.bg;
  if (brandInput) brandInput.value = THEME_DEFAULTS.brand;
  onColorChange(); // preview + debounced save
}

/* ── Publication / Dépublication du profil ──────────────────────────────── */

/*
  Contrat (chantier "architecture principale") :

  Au moment où l'utilisateur clique sur "Publier mon profil" :
    1. On POST /watt/me/profile/publish et le backend renvoie l'ARTIST COMPLET
       (même shape que GET /watt/artists/{slug}). Pas de 2e fetch à faire.
    2. On re-hydrate state.artist avec cette réponse → plus de drift entre le
       state local et le backend (c'est ça qui provoquait le bug "l'interface
       revient à création" : on ne stockait que profilePublic:true sans tenir
       compte du reste).
    3. On SORT du mode édition : l'utilisateur voit immédiatement sa page
       comme les fans la verront, conformément à son feedback explicite :
       « je veux rester sur la vue du profil maintenant publié comme
         quelqu'un le verrait ».
    4. On re-render TOUT via renderProfile(), pas juste la barre owner :
       le titre onglet, les stats, les sections DNA/Prompts/Tracks peuvent
       avoir changé (notamment l'état du skeleton/ap-skeleton).
    5. On émet smyle:profile-published pour que la marketplace, le WATT
       BOARD et tous les autres onglets ouverts se resynchronisent sans
       refresh manuel.

  L'inverse (ownerUnpublish) suit exactement la même mécanique.
*/

async function ownerPublish() {
  if (!state.artist || !state.artist.isSelf) return;

  // Plus de gate « 1 son requis ». Un fan (compte sans son publié) peut
  // rendre son profil public pour exister socialement : être trouvé en
  // recherche, recevoir des follows, etc. Le statut « artiste » est
  // acquis à la publication du premier morceau — pas à ce moment-ci.

  const btn = $('ap-owner-btn-publish');
  if (btn) btn.disabled = true;

  try {
    const resp = await apiFetch('/watt/me/profile/publish', { method: 'POST' });

    // Re-hydrate complet depuis la réponse. Le backend renvoie désormais
    // { ok, profilePublic, artistSlug, artist: { … shape complète … } } —
    // on consomme `artist` en priorité, fallback manuel si vieille API.
    if (resp && resp.artist) {
      state.artist = resp.artist;
    } else if (resp) {
      // Fallback défensif pour ne pas casser si le back n'est pas encore
      // à jour. On patche a minima profilePublic, le reste reste cohérent.
      state.artist.profilePublic = true;
    }

    // Sortie automatique du mode édition : le user voit sa page "comme
    // les fans la voient". Cf. décision produit (Vinted : profil publié
    // = vitrine de boutique visible, pas formulaire de création).
    if (state.editing) {
      // On désactive directement le flag plutôt que d'appeler toggleOwnerEdit
      // pour éviter un double renderOwnerBar. renderProfile() ci-dessous
      // s'occupe de tout reconstruire proprement.
      state.editing = false;
      document.body.classList.remove('ap-owner-editing');
    }

    // Re-render complet (header, stats, sections marketplace, owner bar, titre).
    renderProfile();

    // Toast explicite (pas juste "Profil publié 🎉" : l'utilisateur doit
    // comprendre QUE faire ensuite — sa page est désormais trouvable par
    // les fans via la marketplace).
    toast('Profil publié — tu es visible dans la marketplace');

    // Bus events : la marketplace, le WATT BOARD et les autres onglets
    // se re-synchronisent sans refresh. Payload = artist complet pour
    // permettre aux consommateurs d'insérer directement sans refetch.
    if (window.SmyleEvents && state.artist) {
      window.SmyleEvents.emit(
        window.SmyleEvents.TYPES.PROFILE_PUBLISHED,
        { artist: state.artist }
      );
    }
  } catch (err) {
    console.error('[artiste.js] publish error', err);
    // Le backend renvoie 422 avec { detail: { message, missing:[…] } }
    // quand artist_name est vide. C'est le seul champ requis désormais.
    if (err && err.status === 422 && err.body && err.body.detail) {
      const d = err.body.detail;
      const missing = Array.isArray(d.missing) ? d.missing : [];
      const lookup = {
        artist_name: 'un nom',
      };
      const parts = missing.map(k => lookup[k] || k).filter(Boolean);
      const msg = parts.length
        ? 'Il te manque ' + parts.join(' + ') + ' pour publier ton profil.'
        : (d.message || 'Profil incomplet.');
      toast(msg);
    } else {
      toast('Impossible de publier — réessaie.');
    }
    if (btn) btn.disabled = false;
  }
}

async function ownerUnpublish() {
  if (!state.artist || !state.artist.isSelf) return;
  if (!state.artist.profilePublic) return; // déjà non publié

  // Double confirmation — dépublier c'est retirer son profil de la vitrine,
  // des résultats de recherche, et rompre la visibilité des followers.
  // Les données (tracks, ADN, followers) restent en base, rien n'est perdu.
  const ok = (typeof window !== 'undefined' && typeof window.confirm === 'function')
    ? window.confirm('Retirer ton profil de la marketplace ? Il redeviendra privé, uniquement visible par toi.')
    : true;
  if (!ok) return;

  const btn = $('ap-owner-btn-unpublish');
  if (btn) btn.disabled = true;

  try {
    const resp = await apiFetch('/watt/me/profile/unpublish', { method: 'POST' });

    if (resp && resp.artist) {
      state.artist = resp.artist;
    } else if (resp) {
      state.artist.profilePublic = false;
    }

    // On reste en mode lecture (pas d'auto-activation édition) : si le user
    // voulait éditer, il cliquera sur "Modifier". L'UX doit refléter l'état
    // "brouillon" calmement, pas précipiter vers un formulaire.
    if (state.editing) {
      state.editing = false;
      document.body.classList.remove('ap-owner-editing');
    }

    renderProfile();

    toast('Profil retiré de la marketplace');

    if (window.SmyleEvents && state.artist) {
      window.SmyleEvents.emit(
        window.SmyleEvents.TYPES.PROFILE_UNPUBLISHED,
        { artistId: state.artist.id, slug: state.artist.slug }
      );
    }
  } catch (err) {
    console.error('[artiste.js] unpublish error', err);
    toast('Impossible de dépublier — réessaie.');
    if (btn) btn.disabled = false;
  }
}

/* ── Toast ───────────────────────────────────────────────────────────────── */

let _toastTimer = null;
function toast(msg) {
  const el = $('ap-toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 2400);
}

/* ── Erreur ──────────────────────────────────────────────────────────────── */

function showError(title, msg) {
  setText('ap-error-title', title);
  setText('ap-error-msg',   msg);
  hide('ap-loading');
  hide('ap-profile');
  show('ap-error');
}

/* ── Init ────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  loadArtist();

  // Écoute globale des blurs sur les champs éditables — un seul listener
  // (délégation) plutôt qu'un par champ, et ne déclenche que si on est
  // bien en mode édition owner.
  document.addEventListener('focusout', (ev) => {
    if (!state.editing) return;
    const el = ev.target;
    if (!el || !el.classList || !el.classList.contains('ap-editable')) return;
    saveEditableField(el);
  });

  // Au focus d'un champ éditable vide : on vide le placeholder ET on retire
  // la classe ap-editable-empty pour que le texte saisi s'affiche en couleur
  // normale (blanche) au lieu du gris italique placeholder.
  document.addEventListener('focusin', (ev) => {
    if (!state.editing) return;
    const el = ev.target;
    if (!el || !el.classList || !el.classList.contains('ap-editable')) return;
    if (el.classList.contains('ap-editable-empty')) {
      el.textContent = '';
      el.classList.remove('ap-editable-empty');
    }
  });

  // Input : dès que l'utilisateur commence à taper, on s'assure que la
  // classe "empty" est bien retirée (ceinture + bretelles — au cas où
  // le paste avant focus aurait contourné le focusin).
  document.addEventListener('input', (ev) => {
    if (!state.editing) return;
    const el = ev.target;
    if (!el || !el.classList || !el.classList.contains('ap-editable')) return;
    if (el.classList.contains('ap-editable-empty')) {
      el.classList.remove('ap-editable-empty');
    }
  });

  // Enter dans un .ap-editable = valider (blur), pas de retour à la ligne
  // (exception : .ap-bio accepte les retours à la ligne).
  document.addEventListener('keydown', (ev) => {
    if (!state.editing) return;
    const el = ev.target;
    if (!el || !el.classList || !el.classList.contains('ap-editable')) return;
    if (ev.key === 'Enter' && !ev.shiftKey && el.id !== 'ap-bio') {
      ev.preventDefault();
      el.blur();
    }
    if (ev.key === 'Escape') {
      ev.preventDefault();
      // Restaurer la valeur précédente + blur
      const field = el.dataset.field;
      const val = (state.artist && state.artist[field]) || '';
      fillEditable(el.id, val);
      el.blur();
    }
  });

  // Fermer le modal sur Escape / clic en dehors
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && state.editingField) closeOwnerField();
  });
  const modal = $('ap-modal');
  if (modal) {
    modal.addEventListener('click', (ev) => {
      if (ev.target === modal) closeOwnerField();
    });
  }

  // Upload d'image depuis les fichiers : le bouton visible déclenche
  // l'input file caché, qui à sa sélection appelle handleImageFileUpload.
  const uploadBtn  = $('ap-modal-upload-btn');
  const fileInput  = $('ap-modal-file');
  if (uploadBtn && fileInput) {
    uploadBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (ev) => {
      const file = ev.target.files && ev.target.files[0];
      if (file) handleImageFileUpload(file);
    });
  }
});

/* ── Expose window pour les onclick HTML ─────────────────────────────────── */
if (typeof window !== 'undefined') {
  window.toggleOwnerEdit  = toggleOwnerEdit;
  window.ownerPublish     = ownerPublish;
  window.ownerUnpublish   = ownerUnpublish;
  window.openOwnerField   = openOwnerField;
  window.closeOwnerField  = closeOwnerField;
  window.saveOwnerField   = saveOwnerField;
  window.resetOwnerColors = resetOwnerColors;
  // Casquettes / rôles (popover /u/<slug>)
  window.openRolesPicker  = openRolesPicker;
  window.closeRolesPicker = closeRolesPicker;
  window.saveRolesPicker  = saveRolesPicker;
  // DNA / prompts unlock depuis le profil vendeur
  window.unlockDnaFromProfile    = unlockDnaFromProfile;
  window.unlockPromptFromProfile = unlockPromptFromProfile;
}
