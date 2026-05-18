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
  renderPlaylistsAdn(artist);
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
  _setupFollowButton(artist).catch(e => console.warn('[follow]', e));
}

// ── Follow button logic (Phase A1) ────────────────────────────────────────
async function _setupFollowButton(artist) {
  const wrap = document.getElementById('ap-social-actions');
  const btn = document.getElementById('ap-follow-btn');
  const countEl = document.getElementById('ap-followers-count');
  if (!wrap || !btn) return;
  if (countEl) {
    const n = Number(artist.followersCount || 0);
    countEl.textContent = n + ' follower' + (n !== 1 ? 's' : '');
  }
  if (artist.isSelf) { wrap.style.display = 'none'; return; }
  const isAuth = typeof getAuthToken === 'function' && !!getAuthToken();
  // Si non connecté : on masque tout le bloc pour éviter l'espace blanc
  // (le bouton follow serait caché mais le wrapper resterait visible).
  if (!isAuth) { wrap.style.display = 'none'; return; }
  wrap.style.display = 'block';
  btn.style.display = '';
  const slug = artist.slug || (window.location.pathname.match(/^\/u\/([^/?#]+)/) || [])[1];
  if (!slug) { wrap.style.display = 'none'; return; }
  function _hdr() {
    const h = { 'Accept': 'application/json' };
    if (typeof getAuthToken === 'function') {
      const t = getAuthToken();
      if (t) h['Authorization'] = 'Bearer ' + t;
    }
    return h;
  }
  let following = false;
  try {
    const r = await fetch('/watt/me/following', { credentials: 'same-origin', headers: _hdr() });
    if (r.ok) {
      const list = await r.json();
      following = Array.isArray(list) && list.some(f => f.slug === slug || f.artistSlug === slug);
    }
  } catch (_) {}
  function _setBtnState(isFollowing) {
    btn.textContent = isFollowing ? 'Suivi ✓' : 'Suivre';
    btn.dataset.following = isFollowing ? '1' : '0';
    if (isFollowing) {
      btn.style.background = 'rgba(204,136,255,.06)';
      btn.style.color = 'rgba(204,136,255,.7)';
    } else {
      btn.style.background = 'rgba(204,136,255,.14)';
      btn.style.color = '#cc88ff';
    }
  }
  _setBtnState(following);
  btn.onclick = async () => {
    const wasFollowing = btn.dataset.following === '1';
    btn.disabled = true;
    btn.style.opacity = '.6';
    try {
      const method = wasFollowing ? 'DELETE' : 'POST';
      const r = await fetch('/watt/artists/' + encodeURIComponent(slug) + '/follow', {
        method: method, credentials: 'same-origin', headers: _hdr()
      });
      if (r.ok || r.status === 204) {
        _setBtnState(!wasFollowing);
        if (countEl) {
          const cur = Number(artist.followersCount || 0);
          const newN = wasFollowing ? Math.max(0, cur - 1) : cur + 1;
          artist.followersCount = newN;
          countEl.textContent = newN + ' follower' + (newN !== 1 ? 's' : '');
        }
      } else {
        if (typeof showToast === 'function') showToast('Action impossible.');
      }
    } catch (e) {
      if (typeof showToast === 'function') showToast('Erreur réseau.');
    } finally {
      btn.disabled = false;
      btn.style.opacity = '';
    }
  };
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

// ═══════════════════════════════════════════════════════════════════════════
// BOUTIQUE v2 — Cards compactes + Drawer de détail
// Clic sur une card → openBoutiqueDrawer(type, data)
// 2 types dans la grille boutique : son · voix
// ADN Artiste → ap-dna-card (compact, sous hero)
// ADN Playlists → ap-playlists-adn (accordéon, sous dna-card)
// ═══════════════════════════════════════════════════════════════════════════

var _boutiqueArtist = null;
// Cache des données track/voix pour le drawer — évite d'encoder du JSON en HTML
const _trackDetailCache = {};
const _voiceDetailCache = {};

// ── Accordéon Playlists ADN — sous la card ADN ──────────────────────────────

function renderPlaylistsAdn(artist) {
  const section = $('ap-playlists-adn');
  const list    = $('ap-playlists-adn-list');
  if (!section || !list) return;

  const playlists  = Array.isArray(artist && artist.playlistsForSale) ? artist.playlistsForSale : [];
  const brandColor = (artist && artist.brandColor) || '#cc88ff';
  const slug       = (artist && artist.slug) || '';

  if (playlists.length === 0) { section.style.display = 'none'; return; }
  section.style.display = '';
  setText('ap-playlists-adn-count', playlists.length + ' playlist' + (playlists.length > 1 ? 's' : ''));

  list.innerHTML = playlists.map(pl => {
    const safeTitle = (pl.title || '').replace(/</g, '&lt;');
    const color     = pl.color || brandColor;
    const price     = formatCount(pl.adnPrice || 0);
    // Lien vers la page playlist (unlock se fait depuis le slug playlist)
    const href = `/u/${encodeURIComponent(slug)}`;
    return `
      <details class="ap-pl-adn-item" style="--pl-color:${color}">
        <summary class="ap-pl-adn-summary">
          <span class="ap-pl-adn-icon">🎚</span>
          <span class="ap-pl-adn-name">${safeTitle}</span>
          <span class="ap-pl-adn-badge">🧬 ADN · ${price} crédits</span>
          <span class="ap-pl-adn-chevron">▾</span>
        </summary>
        <div class="ap-pl-adn-body">
          <p class="ap-pl-adn-desc">Le code génératif de cette playlist — reproduis son univers musical.</p>
          <a href="${href}" class="ap-pl-adn-goto">→ Voir la playlist</a>
        </div>
      </details>`;
  }).join('');
}

// ── Helpers d'accès au cache — appelés depuis les onclick HTML ────────────

function openTrackDetailById(trackId) {
  const data = _trackDetailCache[trackId];
  if (!data) return;
  openBoutiqueDrawer('son', JSON.stringify(data));
}

function openVoiceDetailById(voiceId) {
  const data = _voiceDetailCache[voiceId];
  if (!data) return;
  openBoutiqueDrawer('voix', JSON.stringify(data));
}

// ── Drawer — ouvre le panneau de détail ──────────────────────────────────

function openBoutiqueDrawer(type, dataStr) {
  const drawer  = $('boutique-drawer');
  const body    = $('boutique-drawer-body');
  const overlay = $('boutique-overlay');
  if (!drawer || !body || !overlay) return;

  let data;
  try { data = JSON.parse(dataStr); } catch (e) { return; }

  const artist  = (typeof state !== 'undefined' && state.artist) || _boutiqueArtist || {};
  const isSelf  = !!artist.isSelf;
  const LICENSE_LBL = { personnel: '🎧 Personnel', commercial: '💼 Commercial', exclusif: '👑 Exclusif' };

  let html = '';

  // ── Barre de couleur + type + nom ────────────────────────────────────────
  const color = data.color || (artist.brandColor) || '#cc88ff';
  const typeLabel = type === 'adn-artist' ? 'ADN Artiste'
    : type === 'son' ? 'Son · Recette Suno'
    : type === 'voix' ? 'Voix'
    : 'ADN Playlist';
  const nameLabel = type === 'adn-artist' ? 'Signature créative'
    : type === 'son'      ? (data.title || '')
    : type === 'voix'     ? (data.name  || '')
    : (data.title || '');
  const price = type === 'playlist' ? data.adnPrice : data.priceCredits;

  // Cover image en haut du drawer (son uniquement, si disponible)
  if (type === 'son' && data.coverUrl) {
    html += `<div class="bd-cover"><img src="${(data.coverUrl+'').replace(/"/g,'&quot;')}" alt="" class="bd-cover-img" /></div>`;
  }
  html += `<div class="bd-color-bar" style="background:${color}"></div>`;
  html += `<div><div class="bd-type">${typeLabel}</div><div class="bd-name">${(nameLabel + '').replace(/</g,'&lt;')}</div></div>`;

  // ── Contenu spécifique par type ──────────────────────────────────────────
  if (type === 'adn-artist') {
    if (data.descriptionTeaser) {
      html += `<p class="bd-desc">${(data.descriptionTeaser + '').replace(/</g,'&lt;')}</p>`;
    }
    const chips = [];
    if (data.hasUsageGuide)     chips.push('📘 Guide d\'usage');
    if (data.hasExampleOutputs) chips.push('🎧 Exemples sonores');
    chips.push('−30 % sur toutes les recettes de cet artiste');
    html += `<div class="bd-chips">${chips.map(c => `<span class="bd-chip">${c}</span>`).join('')}</div>`;

  } else if (type === 'son') {
    const chips = [];
    if (data.platform) chips.push(data.platform);
    if (chips.length) html += `<div class="bd-chips">${chips.map(c => `<span class="bd-chip">${c}</span>`).join('')}</div>`;
    if (data.audioUrl) {
      html += `<div>
        <div class="bd-preview-label">Pré-écoute du son</div>
        <audio class="bd-audio" controls preload="none" controlsList="nodownload noremoteplayback"
               oncontextmenu="return false"
               src="${(data.audioUrl + '').replace(/"/g,'&quot;')}"></audio>
      </div>`;
    }
    const tuuid = (data.trackUuid || data.trackId || '').replace(/"/g,'&quot;');
    if (tuuid) {
      html += `<div class="bd-social-row">
        <button class="like-btn bd-like-btn" type="button" data-like-btn="${tuuid}" title="Ajouter à ma Wishlist"></button>
        <button class="add-to-pl-btn bd-addpl-btn" type="button" data-add-to-playlist="${tuuid}" title="Ajouter à une playlist">+</button>
      </div>`;
    }

  } else if (type === 'voix') {
    const lic = LICENSE_LBL[data.license] || data.license || '';
    const genres = Array.isArray(data.genres) && data.genres.length
      ? data.genres.map(g => `<span class="bd-chip">${(g+'').replace(/</g,'&lt;')}</span>`).join('') : '';
    if (data.style) html += `<p class="bd-desc">${(data.style+'').replace(/</g,'&lt;')}</p>`;
    html += `<div class="bd-chips">${lic ? `<span class="bd-chip">${lic}</span>` : ''}${genres}</div>`;
    if (data.previewUrl) {
      html += `<div>
        <div class="bd-preview-label">Pré-écoute 30 s</div>
        <audio class="bd-audio" controls preload="none" controlsList="nodownload noremoteplayback"
               oncontextmenu="return false"
               src="${(data.previewUrl+'').replace(/"/g,'&quot;')}"></audio>
      </div>`;
    }

  } else if (type === 'playlist') {
    html += `<p class="bd-desc">Accède au code génératif de cette playlist — reproduis son univers musical avec les mêmes outils IA.</p>`;
  }

  // ── Prix + unlock — masqués si pas d'id (track sans recette) ──────────────
  const hasPurchasable = data.id && (price !== null && price !== undefined);
  if (hasPurchasable) {
    html += `<div class="bd-price-row">
      <div>
        <span class="bd-price-amount">${formatCount(price)}</span>
        <span class="bd-price-unit">crédits</span>
      </div>
      ${type === 'adn-artist' ? '<span class="bd-perk-hint">Possède cet ADN → −30 % sur toutes les recettes</span>' : ''}
    </div>`;

    if (isSelf) {
      html += `<p class="bd-self-note">C'est ton contenu — tu ne peux pas l'acheter.</p>`;
    } else {
      const unlockLabel = type === 'adn-artist' ? '🧬 Débloquer l\'ADN'
        : type === 'son'      ? '🧬 Débloquer la recette'
        : type === 'voix'     ? '🎙 Débloquer la voix'
        : '🎚 Débloquer l\'ADN Playlist';
      html += `<button type="button" class="bd-unlock-btn"
                       id="boutique-drawer-unlock-btn"
                       onclick="boutiqueDrawerUnlock('${type}','${data.id}')">${unlockLabel}</button>`;
    }
  }

  body.innerHTML = html;
  overlay.classList.add('is-open');
  drawer.classList.add('is-open');
  drawer.setAttribute('aria-hidden', 'false');
}

function closeBoutiqueDrawer() {
  const drawer  = $('boutique-drawer');
  const overlay = $('boutique-overlay');
  if (!drawer || !overlay) return;
  // Stoppe l'audio si en lecture
  drawer.querySelectorAll('audio').forEach(a => { a.pause(); a.currentTime = 0; });
  drawer.classList.remove('is-open');
  overlay.classList.remove('is-open');
  drawer.setAttribute('aria-hidden', 'true');
}

async function boutiqueDrawerUnlock(type, id) {
  const btn = $('boutique-drawer-unlock-btn');
  if (btn) btn.disabled = true;
  const ENDPOINTS = {
    'adn-artist': '/unlocks/adns/',
    'son':        '/unlocks/prompts/',
    'voix':       '/unlocks/voices/',
    'playlist':   '/unlocks/playlist-adn/',
  };
  const TOASTS = {
    'adn-artist': 'ADN débloqué 🧬 — retrouve-le dans ta bibliothèque',
    'son':        'Recette débloquée 🧬 — retrouve-la dans ta bibliothèque',
    'voix':       'Voix débloquée 🎙 — retrouve-la dans ta bibliothèque',
    'playlist':   'ADN Playlist débloqué 🎚 — retrouve-le dans ta bibliothèque',
  };
  try {
    await apiFetch(`${ENDPOINTS[type]}${encodeURIComponent(id)}`, { method: 'POST' });
    toast(TOASTS[type] || 'Débloqué ✓');
    closeBoutiqueDrawer();
  } catch (err) {
    handleUnlockError(err);
    if (btn) btn.disabled = false;
  }
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
  // Pas de teaser textuel — afficher uniquement longueur (ordre complexité).
  var charCount = adn.characterCount || 0;
  var teaserEl = document.getElementById('ap-dna-teaser');
  if (teaserEl) {
    teaserEl.textContent = charCount > 0
      ? charCount.toLocaleString('fr-FR') + ' caractères · contenu verrouillé'
      : 'Contenu verrouillé';
    teaserEl.style.fontStyle = 'italic';
    teaserEl.style.opacity = '0.7';
  }

  // Badges "Guide d'usage" / "Exemples" / IA / rareté
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
    // 2026-05-13 — IA source (badge informatif)
    const AI_LBL = {
      chatgpt: '🤖 ChatGPT', claude: '🤖 Claude', grok: '🤖 Grok',
      gemini: '🤖 Gemini', mistral: '🤖 Mistral',
      perplexity: '🤖 Perplexity', autre: '🤖 IA'
    };
    if (adn.aiReference && AI_LBL[adn.aiReference]) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge">' + AI_LBL[adn.aiReference] + '</span>');
    }
    // 2026-05-13 v2 — Rareté 4 tiers (mythic/legendary/limited/open)
    const tier = adn.rarityTier || 'unlimited';
    const left = (adn.availableCount != null) ? adn.availableCount : '?';
    const tot  = (adn.maxSupply != null) ? adn.maxSupply : '?';
    if (adn.isSoldOut) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge" style="background:#7f1d1d;color:#fff;">SOLD OUT</span>');
    } else if (tier === 'mythic') {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge" style="background:#FFD700;color:#000;font-weight:600;">👑 Mythic · Pièce unique (1/1)</span>');
    } else if (tier === 'legendary') {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge" style="background:#FBBF24;color:#000;font-weight:600;">⭐ Legendary · Drop VIP ' + left + '/' + tot + '</span>');
    } else if (tier === 'limited') {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge" style="background:#A78BFA;color:#000;font-weight:600;">💎 Limited · ' + left + '/' + tot + ' restants</span>');
    } else if (tier === 'open') {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge" style="background:#4ADE80;color:#000;font-weight:600;">🟢 Open · ' + left + '/' + tot + '</span>');
    }
    // tier === 'unlimited' → pas de badge rareté affiché
  }

  // Masque le bouton unlock pour l'owner (pas d'auto-achat).
  const btn = $('ap-dna-unlock-btn');
  if (btn) {
    if (artist.isSelf) {
      btn.style.display = 'none';
    } else if (adn.isSoldOut) {
      btn.style.display = '';
      btn.disabled = true;
      btn.style.opacity = '0.5';
      btn.style.cursor = 'not-allowed';
      setText('ap-dna-unlock-label', 'Sold out');
    } else {
      btn.style.display = '';
      btn.disabled = false;
      btn.style.opacity = '';
      btn.style.cursor = '';
      setText('ap-dna-unlock-label',
        `🧬 ADN · ${formatCount(adn.priceCredits)} crédits`);
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

  // Décision Tom 2026-05-05 v3 (FINALE) : sur le profil public, UN SEUL
  // format = la bande "Sons publiés" (renderTracks) qui contient tout
  // (cover + audio + bouton "Débloquer la recette" + supprimer si owner).
  // La cellule "Recettes Suno" est définitivement cachée — pas de
  // doublon visuel, pas de melange.
  // Le format card riche est conservé UNIQUEMENT dans /library (vue
  // après achat — cf library.js renderPrompts).
  section.style.display = 'none';
  return;
  // eslint-disable-next-line no-unreachable
  const prompts = Array.isArray(artist && artist.prompts) ? artist.prompts : [];
  const tracks = Array.isArray(artist && artist.tracks) ? artist.tracks : [];
  const trackByPromptId = {};
  tracks.forEach(t => {
    if (t && t.promptId) trackByPromptId[String(t.promptId)] = t;
  });

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
    // P1-F4 publique partielle (révision 2026-05-04 PR3) — SEULS les
    // réglages non-reproductibles seuls sont visibles. Weirdness +
    // Style Influence sont gated jusqu'à l'unlock (le payload backend
    // ne les renvoie même plus pour la vue publique).
    const platformBadge = p.promptPlatform
      ? `<span class="ap-prompt-badge">${_voicePromptPlatformLbl(p.promptPlatform)}</span>`
      : '';
    const modelBadge = p.promptModelVersion
      ? `<span class="ap-prompt-badge">${(p.promptModelVersion || '').replace(/</g, '&lt;')}</span>`
      : '';
    const vocalBadge = p.promptVocalGender
      ? `<span class="ap-prompt-badge">${_promptVocalGenderLbl(p.promptVocalGender)}</span>`
      : '';
    // Bloc weirdness/style supprimé du rendu public — ces 2 infos
    // apparaissent dans /library après achat (cf library.js renderPrompts).
    const settingsBlock = '';
    // Pas de bouton unlock pour l'owner (évite l'auto-achat 400).
    const unlockBtn = artist.isSelf
      ? '<span class="ap-prompt-owner-note">Ton prompt</span>'
      : `<button type="button" class="ap-prompt-unlock-btn"
                 data-prompt-id="${p.id}" data-price="${p.priceCredits}">
          🧬 Recette · ${priceStr} crédits
        </button>`;
    // Audio player du track lié (revert 2026-05-05) — pré-écoute avant
    // achat pour augmenter la conversion. Si pas de track lié, pas
    // d'audio (cas des prompts orphelins, rare).
    const linkedTrack = trackByPromptId[String(p.id)] || null;
    const linkedStreamUrl = (linkedTrack && linkedTrack.streamUrl) || '';
    const audioBlock = linkedStreamUrl
      ? `<audio controls preload="none" class="ap-prompt-audio" src="${linkedStreamUrl.replace(/"/g, '&quot;')}"></audio>`
      : '';
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
      ${audioBlock}
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
    if (artist && artist.isSelf) {
      // L'artiste voit sa propre page vide : on lui propose d'aller poster
      section.style.display = '';
      list.innerHTML = `
        <div class="ap-tracks-empty-state" style="
          text-align:center;padding:2.5rem 1rem;
          color:var(--txt-muted,rgba(255,255,255,.45));
          font-size:.9rem;line-height:1.6;">
          <div style="font-size:2rem;margin-bottom:.75rem">🎵</div>
          <p style="margin:0 0 1.25rem">Tu n'as pas encore posté de sons.</p>
          <a href="/dashboard" style="
            display:inline-block;padding:.55rem 1.4rem;
            background:var(--brand,#7C3AED);color:#fff;
            border-radius:8px;text-decoration:none;font-weight:600;
            font-size:.85rem;">
            Poster ton premier son → WATT BOARD
          </a>
        </div>`;
    } else {
      section.style.display = 'none';
    }
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

  // Sprint 1 PR3 (2026-05-04) — pivot écoute. Le track devient le produit
  // visible : cover + audio public + bouton "Débloquer le prompt" si
  // un prompt est lié (track.promptId). Pour matcher le prompt avec
  // ses metadonnées (prix, nom, etc), on indexe la liste artist.prompts
  // par id.
  const promptsById = {};
  const allPrompts = Array.isArray(artist && artist.prompts) ? artist.prompts : [];
  allPrompts.forEach(p => { if (p && p.id) promptsById[String(p.id)] = p; });

  list.innerHTML = '';
  tracks.forEach(t => {
    const card = document.createElement('article');
    card.className = 'ap-track-card';
    card.dataset.trackId   = t.id || '';
    card.dataset.trackName = t.name || '';
    const safeName = (t.name || 'Sans titre').replace(/</g, '&lt;');
    const plays    = formatCount(t.plays);
    const date     = t.date || '';
    // Sprint 1 PR3 fix audio v2 (2026-05-05) — robustesse maximale :
    // 1. <source> avec type explicite (force le MIME pour Chrome qui
    //    refuse parfois de jouer un fichier dont le content-type R2
    //    serait application/octet-stream au lieu de audio/wav)
    // 2. Pas de filter CSS (retiré dans v1, controls natifs visibles)
    // 3. Click handler sur la card entière qui force le play via JS
    //    (data-stream-url) — fallback si controls natifs cliquables
    //    mais inactifs pour une raison (CSP, focus, autre)
    let audio = '';
    if (t.streamUrl) {
      const safeUrl = t.streamUrl.replace(/"/g, '&quot;');
      // Détection MIME basique sur l'extension (R2 retourne parfois
      // application/octet-stream qui empêche le play). On lui force
      // un type audio/wav ou audio/mpeg.
      const ext = (t.streamUrl.split('.').pop() || '').toLowerCase();
      const mime = ext === 'mp3' ? 'audio/mpeg'
                  : ext === 'm4a' ? 'audio/mp4'
                  : 'audio/wav';  // .wav par défaut
      audio = `<audio controls preload="metadata" class="ap-track-audio" controlsList="nodownload noplaybackrate">
        <source src="${safeUrl}" type="${mime}" />
      </audio>`;
    } else {
      audio = `<div class="ap-track-audio-disabled">Audio en cours de traitement…</div>`;
    }
    // Cover image (Sprint 1 PR1+PR2). Fallback sur la couleur si absent.
    const _coverU = t.coverUrl || t.cover_url || '';
    const coverHTML = _coverU
      ? `<img src="${_coverU.replace(/"/g, '&quot;')}" alt="" class="ap-track-cover" />`
      : `<div class="ap-track-cover ap-track-cover-fallback"
              style="background:${t.color || '#FFD700'}"></div>`;
    // Item 1 — badge plateforme
    const platformBadge = (t.platform && PLATFORM_LBL[t.platform])
      ? `<span class="ap-track-card-platform" title="Plateforme d'origine">
          ${PLATFORM_LBL[t.platform]}
        </span>`
      : '';
    // Bouton débloquer prompt — si ce track a un prompt vendable lié.
    // On retrouve les métadonnées du prompt (prix, vocal, etc.) dans
    // artist.prompts (déjà chargé pour la cellule ap-prompts-section).
    let unlockBlock = '';
    const linkedPrompt = t.promptId ? promptsById[String(t.promptId)] : null;
    if (linkedPrompt && !artist.isSelf) {
      const priceStr = formatCount(linkedPrompt.priceCredits);
      const vocalLbl = linkedPrompt.promptVocalGender
        ? _promptVocalGenderLbl(linkedPrompt.promptVocalGender)
        : '';
      const platformLbl = linkedPrompt.promptPlatform
        ? _voicePromptPlatformLbl(linkedPrompt.promptPlatform)
        : '';
      const promptMetaLine = [vocalLbl, platformLbl, linkedPrompt.promptModelVersion]
        .filter(Boolean).join(' · ');
      unlockBlock = `
        <div class="ap-track-prompt-block">
          ${promptMetaLine ? `<div class="ap-track-prompt-meta">${promptMetaLine.replace(/</g, '&lt;')}</div>` : ''}
          <button type="button" class="ap-track-unlock-btn"
                  data-prompt-id="${linkedPrompt.id}"
                  data-price="${linkedPrompt.priceCredits}">
            🧬 Recette · ${priceStr} crédits
          </button>
        </div>`;
    } else if (linkedPrompt && artist.isSelf) {
      unlockBlock = '<span class="ap-prompt-owner-note">Recette en vente</span>';
    }
    // Bouton supprimer — visible uniquement quand l'owner regarde son
    // propre profil. Le DELETE backend vérifie aussi l'owner (defense
    // in depth), donc même si un visiteur arrive à invoquer le click,
    // il aura un 403.
    const deleteBtn = artist.isSelf
      ? `<button type="button" class="ap-track-delete-btn"
                 data-track-id="${t.id}"
                 data-track-name="${(t.name || '').replace(/"/g, '&quot;')}"
                 title="Supprimer ce son">🗑</button>`
      : '';
    // Couleur de la card : priorité playlist > couleur propre du track > défaut
    const tc    = t.playlistColor || t.color || '';
    const tcRgb = tc ? hexToRgbTriplet(tc) : '255,215,0';
    // Badge playlist cliquable (si le track appartient à une playlist publique)
    const artistSlug = (typeof state !== 'undefined' && state.artist && state.artist.slug) || '';
    const plBadge = t.playlistTitle
      ? `<a class="ap-track-pl-badge"
              href="/u/${encodeURIComponent(artistSlug)}"
              style="color:${tc};border-color:rgba(${tcRgb},.4);background:rgba(${tcRgb},.1)"
              onclick="event.stopPropagation()">${(t.playlistTitle + '').replace(/</g,'&lt;')}</a>`
      : '';
    // data-stream-url permet au click handler de retrouver l'URL
    // pour le fallback play JS sur la card entière.
    const streamAttr = t.streamUrl ? ` data-stream-url="${t.streamUrl.replace(/"/g, '&quot;')}"` : '';
    // Stocke les données dans le cache — évite le problème des " en HTML
    _trackDetailCache[t.id] = {
      id:           linkedPrompt ? linkedPrompt.id : null,
      trackId:      t.id,
      trackUuid:    t.trackUuid || t.id,
      title:        t.name || t.title || '',
      priceCredits: linkedPrompt ? linkedPrompt.priceCredits : null,
      color:        t.color || '',
      platform:     t.platform || '',
      audioUrl:     t.streamUrl || t.audioUrl || '',
      coverUrl:     t.coverUrl || t.cover_url || '',
      hasPrompt:    !!linkedPrompt,
    };

    if (tc) card.style.cssText = `--tc:${tc};--tc-rgb:${tcRgb}`;
    card.innerHTML = `
      <div class="ap-track-card-inner" data-track-id="${t.id}"${streamAttr}${tc ? ` style="background:rgba(${tcRgb},.07);border-left:3px solid rgba(${tcRgb},.55)"` : ''}>
        ${coverHTML}
        <div class="ap-track-card-body">
          <div class="ap-track-card-top">
            <h3 class="ap-track-card-title ap-track-detail-trigger"
                style="cursor:pointer${tc ? `;color:${tc};text-shadow:0 0 8px rgba(${tcRgb},.6),0 0 20px rgba(${tcRgb},.25)` : ''}"
                onclick="openTrackDetailById('${t.id}')">${safeName}</h3>
            <div class="ap-track-card-actions">
              <button class="like-btn ap-track-like" type="button" data-like-btn="${t.trackUuid || t.id}" title="J&#39;aime / retirer" aria-label="Liker"></button>
              <button class="add-to-pl-btn ap-track-add-pl" type="button" data-add-to-playlist="${t.trackUuid || t.id}" title="Ajouter à une playlist" aria-label="Ajouter à une playlist">+</button>
              ${deleteBtn}
            </div>
          </div>
          <div class="ap-track-card-meta">
            <span class="ap-track-meta-plays">▶ ${plays}</span>
            ${date ? `<span class="ap-track-meta-date">· ${date}</span>` : ''}
            ${platformBadge}
            ${plBadge}
          </div>
          ${audio}
          ${unlockBlock}
        </div>
      </div>
    `;
    list.appendChild(card);
  });

  // ── Accordéon : 6 tracks visibles par défaut ────────────────────────────
  const TRACKS_FOLD = 6;
  const _prevTT = list.nextElementSibling;
  if (_prevTT && _prevTT.classList && _prevTT.classList.contains('ap-accordion-toggle')) _prevTT.remove();
  if (tracks.length > TRACKS_FOLD) {
    const allCards = list.querySelectorAll('.ap-track-card');
    allCards.forEach((c, i) => { c.style.display = i >= TRACKS_FOLD ? 'none' : ''; });
    const tb = document.createElement('button');
    tb.type = 'button'; tb.className = 'ap-accordion-toggle';
    tb.textContent = `Voir tout (${tracks.length}) ▼`;
    let _exp = false;
    tb.onclick = () => {
      _exp = !_exp;
      allCards.forEach((c, i) => { c.style.display = (!_exp && i >= TRACKS_FOLD) ? 'none' : ''; });
      tb.textContent = _exp ? 'Réduire ▲' : `Voir tout (${tracks.length}) ▼`;
    };
    list.insertAdjacentElement('afterend', tb);
  }

  // ── Accordéon EXTERNE — fermé par défaut (comme l'onglet Playlists) ─────
  {
    const hdr = section.querySelector('.ap-tracks-hdr');
    if (hdr && !hdr.dataset.acc) {
      hdr.dataset.acc = '1';
      hdr.style.cursor = 'pointer';
      hdr.style.userSelect = 'none';
      const arrow = document.createElement('span');
      arrow.className = 'ap-section-arrow';
      arrow.textContent = '▼';
      hdr.appendChild(arrow);

      // Enveloppe tout le contenu (list + bouton "Voir tout") dans un body
      const body = document.createElement('div');
      body.className = 'ap-tracks-body';
      // body inséré juste après le header, avant la liste
      hdr.parentNode.insertBefore(body, list);
      body.appendChild(list);
      // "Voir tout" est maintenant frère de body — on le ramène dedans
      const togBtn = body.parentNode.querySelector('.ap-accordion-toggle');
      if (togBtn) body.appendChild(togBtn);

      hdr.addEventListener('click', () => {
        const open = body.classList.toggle('is-open');
        arrow.style.transform = open ? 'rotate(180deg)' : '';
      });
    }
  }

  // Délégation click + gestion robuste de play/pause via pattern promise
  // (suggéré par Tom 2026-05-05 — évite AbortError quand play/pause
  // s'enchaînent rapidement avant la résolution de la promesse de play).
  // Une seule track joue à la fois sur la page (les autres se mettent
  // en pause automatiquement).
  list.onclick = (ev) => {
    // Cas 1 : bouton supprimer track (owner uniquement)
    const delBtn = ev.target.closest('.ap-track-delete-btn');
    if (delBtn) {
      ev.preventDefault();
      ev.stopPropagation();
      const tid = delBtn.dataset.trackId;
      const tname = delBtn.dataset.trackName || 'ce son';
      if (tid && confirm(`Supprimer "${tname}" ?\n\nCette action est définitive (le fichier audio R2 + la recette liée seront aussi supprimés).`)) {
        deleteTrackFromProfile(tid, delBtn);
      }
      return;
    }
    // Cas 2 : bouton unlock prompt
    const unlockBtn = ev.target.closest('.ap-track-unlock-btn');
    if (unlockBtn) {
      const id = unlockBtn.dataset.promptId;
      if (id) unlockPromptFromProfile(id, unlockBtn);
      return;
    }
    // Cas 3 : click sur card pour play/pause
    const inner = ev.target.closest('.ap-track-card-inner');
    if (!inner) return;
    if (ev.target.closest('audio')) return;
    const url = inner.dataset.streamUrl;
    if (!url) {
      toast('Audio en cours de traitement, réessaie dans quelques secondes.');
      return;
    }
    const audioEl = inner.querySelector('audio');
    if (!audioEl) return;

    // Logging détaillé pour diagnostic prod (à retirer une fois stable).
    console.log('[artiste] click play. url=', url, 'paused=', audioEl.paused, 'readyState=', audioEl.readyState, 'error=', audioEl.error);

    if (audioEl.paused) {
      // Stoppe les autres lecteurs en cours sur la page (un seul son
      // joue à la fois — UX cohérente avec marketplace).
      list.querySelectorAll('audio').forEach(a => {
        if (a !== audioEl && !a.paused) {
          try { a.pause(); } catch (_) {}
        }
      });
      // Pattern Tom — on stocke la promesse pour pouvoir l'await en pause
      const playPromise = audioEl.play();
      if (playPromise !== undefined) {
        playPromise.catch(err => {
          if (err && err.name === 'AbortError') return;  // benign
          console.error('[artiste] audio.play() rejected:', err);
          // Message d'erreur le plus parlant possible pour Tom
          const errMsg = err && (err.message || err.name) || 'erreur audio inconnue';
          const audioErr = audioEl.error
            ? ` (code ${audioEl.error.code}: ${audioEl.error.message || ''})`
            : '';
          toast('Lecture impossible : ' + errMsg + audioErr);
        });
      }
    } else {
      audioEl.pause();
    }
  };
}

// ── Unlock ADN depuis le profil ────────────────────────────────────────
async function unlockDnaFromProfile() {
  const artist = state.artist;
  if (!artist || !artist.adn || artist.isSelf) return;
  // Redirige vers la connexion si non authentifié
  if (typeof getAuthToken === 'function' && !getAuthToken()) {
    const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/?auth=login&return=${returnUrl}`;
    return;
  }
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

// ── Suppression d'un track depuis le profil (owner uniquement) ────────
// Utilise l'endpoint Flask DELETE /api/watt/tracks/{public_id} qui
// purge aussi le fichier R2 + le row tracks FastAPI (CASCADE depuis la
// PR Sprint 1 PR3 R2 cleanup). Le backend vérifie l'owner — un visiteur
// qui invoquerait l'endpoint reçoit 403, le bouton est juste caché côté
// front pour ne pas exposer une action qui ne marcherait pas.
async function deleteTrackFromProfile(trackId, btn) {
  if (!trackId) return;
  if (btn) btn.disabled = true;
  try {
    if (typeof apiFetch === 'function') {
      // L'endpoint principal côté FastAPI ne fait PAS encore la suppression
      // R2 via le path /watt/tracks/<id>. On passe par l'endpoint Flask
      // qui supprime à la fois en DB et en R2 (cf flask_app.py
      // /api/watt/tracks/<int:track_id>).
      // Note : l'ID public peut être un UUID FastAPI ou un int legacy.
      // Le fetch direct gère les 2.
      const token = (typeof getAuthToken === 'function') ? getAuthToken() : null;
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(`/watt/tracks/${encodeURIComponent(trackId)}`, {
        method: 'DELETE',
        headers,
      });
      if (!res.ok && res.status !== 204) {
        let detail = `${res.status}`;
        try { const j = await res.json(); detail = j.detail || j.message || detail; } catch (_) {}
        throw new Error(detail);
      }
    }
    toast('Son supprimé');
    setTimeout(() => loadArtist(), 400);
  } catch (err) {
    console.error('[artiste] delete track error', err);
    toast('Suppression impossible : ' + (err && err.message || 'erreur'));
    if (btn) btn.disabled = false;
  }
}

// ── Unlock prompt depuis le profil ─────────────────────────────────────
async function unlockPromptFromProfile(promptId, btn) {
  if (!promptId) return;
  // Redirige vers la connexion si l'utilisateur n'est pas authentifié
  if (typeof getAuthToken === 'function' && !getAuthToken()) {
    const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/?auth=login&return=${returnUrl}`;
    return;
  }
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
    // 2026-05-13 — chantier preview 30s :
    //   - owner/unlocked reçoit sample_url (full) → player full
    //   - visiteur reçoit preview_url (30s) → player preview
    //   - voix legacy sans preview → placeholder verrouillé
    const audioSrc = v.sample_url || v.preview_url || null;
    const audioLbl = v.sample_url ? '' : (v.preview_url ? ' · 30s preview' : '');
    const previewBlock = audioSrc
      ? `<audio controls preload="none" controlsList="nodownload noremoteplayback"
                oncontextmenu="return false" class="ap-voice-preview"
                src="${(audioSrc + '').replace(/"/g, '&quot;')}"></audio>
         <div class="ap-voice-preview-label" style="font-size:11px;color:#a09cb8;margin-top:4px;">${audioLbl ? '🎧 Pré-écoute' + audioLbl : ''}</div>`
      : `<div class="ap-voice-locked"
              style="display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px dashed rgba(204,136,255,.3);border-radius:8px;color:#a09cb8;font-size:12px;font-style:italic">
           🔒 Pré-écoute après achat
         </div>`;
    // Pas de bouton unlock pour l'owner (évite l'auto-achat 400).
    const unlockBtn = artist.isSelf
      ? '<span class="ap-voice-owner-note">Ta voix</span>'
      : `<button type="button" class="ap-voice-unlock-btn"
                 data-voice-id="${v.id}" data-price="${v.price_credits}">
          🎙 Voix · ${priceStr} crédits
        </button>`;
    // Phase B metadata 2026-05-13 : badges origine + lien track
    const _originLabel = (function(o) {
      if (o === 'personal') return '🎙️ Voix personnelle';
      if (o === 'ai') return '🤖 Créée par IA';
      if (o === 'known_artist') return '🌟 Voix d\'artiste connu';
      return '';
    })(v.voice_origin);
    const originBadge = _originLabel
      ? `<span class="ap-voice-origin" style="display:inline-block;padding:3px 8px;border-radius:999px;background:rgba(204,136,255,.1);color:#cc88ff;font-size:11px;letter-spacing:.02em;margin-right:6px">${_originLabel}</span>`
      : '';
    const linkedTrackBadge = v.linked_track_id
      ? `<span class="ap-voice-linked" style="display:inline-block;padding:3px 8px;border-radius:999px;background:rgba(255,215,0,.1);color:#FFD700;font-size:11px;letter-spacing:.02em">🎵 Démo dans un morceau</span>`
      : '';

    _voiceDetailCache[v.id] = {
      id:           v.id,
      name:         v.name || '',
      style:        v.style || '',
      priceCredits: v.price_credits || v.priceCredits || 0,
      license:      v.license || '',
      genres:       v.genres || [],
      previewUrl:   v.preview_url || v.previewUrl || '',
    };

    card.innerHTML = `
      <div class="ap-voice-card-top" style="cursor:pointer"
           onclick="openVoiceDetailById('${v.id}')"
        <h3 class="ap-voice-card-title">${safeName}</h3>
        <span class="${licenseClass}">${licenseLbl}</span>
      </div>
      ${safeStyle ? `<p class="ap-voice-card-style">${safeStyle}</p>` : ''}
      ${(originBadge || linkedTrackBadge) ? `<div class="ap-voice-card-badges" style="margin-bottom:6px">${originBadge}${linkedTrackBadge}</div>` : ''}
      <div class="ap-voice-card-meta">
        ${genresBadge}
      </div>
      ${previewBlock}
      <div class="ap-voice-card-actions">${unlockBtn}</div>
    `;
    list.appendChild(card);
  });

  // ── Accordéon : 4 voix visibles par défaut ──────────────────────────────
  const VOICES_FOLD = 4;
  const _prevVT = list.nextElementSibling;
  if (_prevVT && _prevVT.classList && _prevVT.classList.contains('ap-accordion-toggle')) _prevVT.remove();
  if (voices.length > VOICES_FOLD) {
    const allVC = list.querySelectorAll('.ap-voice-card');
    allVC.forEach((c, i) => { c.style.display = i >= VOICES_FOLD ? 'none' : ''; });
    const tbV = document.createElement('button');
    tbV.type = 'button'; tbV.className = 'ap-accordion-toggle';
    tbV.textContent = `Voir tout (${voices.length}) ▼`;
    let _expV = false;
    tbV.onclick = () => {
      _expV = !_expV;
      allVC.forEach((c, i) => { c.style.display = (!_expV && i >= VOICES_FOLD) ? 'none' : ''; });
      tbV.textContent = _expV ? 'Réduire ▲' : `Voir tout (${voices.length}) ▼`;
    };
    list.insertAdjacentElement('afterend', tbV);
  }

  // ── Accordéon EXTERNE — fermé par défaut (comme l'onglet Playlists) ─────
  {
    const hdrV = section.querySelector('.ap-voices-hdr');
    if (hdrV && !hdrV.dataset.acc) {
      hdrV.dataset.acc = '1';
      hdrV.style.cursor = 'pointer';
      hdrV.style.userSelect = 'none';
      const arrowV = document.createElement('span');
      arrowV.className = 'ap-section-arrow';
      arrowV.textContent = '▼';
      hdrV.appendChild(arrowV);

      const bodyV = document.createElement('div');
      bodyV.className = 'ap-voices-body';
      hdrV.parentNode.insertBefore(bodyV, list);
      bodyV.appendChild(list);
      const togBtnV = bodyV.parentNode.querySelector('.ap-accordion-toggle');
      if (togBtnV) bodyV.appendChild(togBtnV);

      hdrV.addEventListener('click', () => {
        const open = bodyV.classList.toggle('is-open');
        arrowV.style.transform = open ? 'rotate(180deg)' : '';
      });
    }
  }

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
  // Redirige vers la connexion si non authentifié
  if (typeof getAuthToken === 'function' && !getAuthToken()) {
    const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/?auth=login&return=${returnUrl}`;
    return;
  }
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
     2. User sélectionne une image → on POST /watt/upload-image
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

  // ── POST /watt/upload-image (FastAPI, même origine — pas apiFetch) ──
  // Upload multipart FormData → R2 via l'endpoint FastAPI dédié.
  const kind = (field === 'avatarUrl') ? 'avatar' : 'cover';
  const fd = new FormData();
  fd.append('file',   file);
  fd.append('userId', u.id);
  fd.append('kind',   kind);

  let uploadJson;
  try {
    const resp = await fetch('/watt/upload-image', { method: 'POST', body: fd });
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
