/* ═══════════════════════════════════════════════════════════════════════════
   WATT — artiste.js  (Phase 5 — 2026-04-20)

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
  // On accepte /u/<slug> (canonique), /@<slug> (C3 ① — 2026-06-13) et
  // /artiste/<slug> (legacy, avant redirection 301) pour rester robuste
  // si la page est servie via un alias ou un vieux bookmark.
  const m = window.location.pathname.match(/^\/(?:(?:u|artiste)\/|@)([^/?#]+)/);
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
    loadArtistResale(state.artist.id);
    loadArtistImages(state.artist.slug);   // C4 ③ — section visuelle du profil
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
  renderVisualDna(artist);    // C4 — relique ADN visuel (jumelle de l'ADN musical)
  renderAdnChip(artist);      // U8 — chip ADN inline hero
  // C3 ① — renderBioPreview supprimée (la bio vit dans le bloc identité)
  renderPlayAllBtn(artist);   // U8 — bouton écouter tout
  renderPrompts(artist);
  renderVoices(artist);
  renderTracks(artist);
  _updateSaleDisclaimerVisibility(artist);
  _openSonFromHash();         // recherche → #son-{id} ouvre la carte détail

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
    // C3 v3 (2026-06-13) — #ap-hero-bg est désormais une VRAIE bannière de
    // flux (.ap-hero-banner, 260px) : plus de div inset:0 derrière le texte.
    // .has-image affiche la cover (background-size:cover), sinon le CSS
    // peint un dégradé discret à partir de la couleur de marque.
    // ap-has-cover reste posé sur .ap-hero pour les règles dépendantes.
    const hero = heroBg.closest('.ap-hero');
    if (hero) hero.classList.toggle('ap-has-cover', !!artist.coverPhotoUrl);
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

  // C3 v3 — Pilule palier créateur (C0 badges.js). Le payload n'expose pas
  // encore de palier (abonnements post-Stripe) : rendu défensif, la pilule
  // s'allumera toute seule le jour où le champ arrivera côté backend.
  const palierEl = $('ap-palier-pill');
  if (palierEl) {
    const tier = artist.palier || artist.subscriptionTier || artist.tier || '';
    const html = (tier && window.SpBadges && typeof SpBadges.palier === 'function')
      ? SpBadges.palier(tier) : '';
    if (html) {
      palierEl.innerHTML = html;
      palierEl.style.display = '';
    } else {
      palierEl.style.display = 'none';
    }
  }

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

  // C3 ① fix double-bio — LA bio vit dans le bloc identité (#ap-bio déplacé).
  // Fans : masquée si vide · owner : visible avec placeholder (édition).
  toggleSectionForFans('ap-bio', artist.bio, artist.isSelf);
  _setupFollowButton(artist).catch(e => console.warn('[follow]', e));
}

// ── Follow + Message buttons (Phase A1 + U1) ─────────────────────────────
async function _setupFollowButton(artist) {
  const wrap    = document.getElementById('ap-social-actions');
  const btn     = document.getElementById('ap-follow-btn');
  const msgBtn  = document.getElementById('ap-message-btn');
  const countEl = document.getElementById('ap-followers-count');
  if (!wrap || !btn) return;
  if (countEl) {
    const n = Number(artist.followersCount || 0);
    countEl.textContent = n + ' follower' + (n !== 1 ? 's' : '');
  }
  if (artist.isSelf) { wrap.style.display = 'none'; return; }
  const isAuth = typeof getAuthToken === 'function' && !!getAuthToken();
  // Si non connecté : on masque tout le bloc pour éviter l'espace blanc
  if (!isAuth) { wrap.style.display = 'none'; return; }
  // C3 v3 — la direction (colonne desktop / ligne mobile) est gérée par le
  // CSS .ap-hero-actions, plus de flexDirection forcé en inline.
  wrap.style.display = 'flex';
  btn.style.display = '';

  // ── Bouton Message ──────────────────────────────────────────────────────
  if (msgBtn && artist.id) {
    msgBtn.style.display = '';
    msgBtn.onclick = () => {
      if (window.SmyleMessaging) {
        window.SmyleMessaging.open(artist.id);
      } else if (window.openAuthModal) {
        window.openAuthModal('login');
      }
    };
  }

  // ── Bouton "Proposer un échange" (entrée principale du trade) ────────────
  // Visible sur le profil d'un autre artiste connecté. Le clic ouvre le modal
  // à double sélection. Si l'artiste n'a aucun prompt échangeable, le modal
  // l'explique (au lieu de disparaître silencieusement).
  const tradeBtn = document.getElementById('ap-trade-btn');
  if (tradeBtn && artist.id) {
    tradeBtn.style.display = '';
    tradeBtn.onclick = () => openTradeModalProfile();
  }

  const slug = artist.slug || (window.location.pathname.match(/^\/(?:u\/|@)([^/?#]+)/) || [])[1];
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
    // On ne force PLUS background/border en inline → le contour couleur-profil
    // (CSS, --brand) reste visible comme sur Message/Échange. On distingue
    // seulement l'état suivi/non-suivi par l'opacité du texte (plateforme).
    btn.style.background = '';
    btn.style.color = isFollowing ? 'rgba(204,136,255,.6)' : '#cc88ff';
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
   dans watt-api/app/schemas/user.py — l'ordre aussi (ordre d'affichage).
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
    const href = `/@${encodeURIComponent(slug)}`;
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

// Ouvre la carte détail d'un son depuis l'URL (#son-<id>), utilisé quand on
// arrive depuis la recherche en cliquant sur le titre. Le hash peut porter
// l'UUID FastAPI ; on retrouve la bonne entrée par clé directe OU par
// trackUuid/trackId/id dans le cache (les clés du cache sont des legacy ids).
function _openSonFromHash() {
  const m = (location.hash || '').match(/^#son-(.+)$/);
  if (!m) return;
  const wanted = decodeURIComponent(m[1]);
  let key = _trackDetailCache[wanted] ? wanted : null;
  if (!key) {
    key = Object.keys(_trackDetailCache).find((k) => {
      const d = _trackDetailCache[k] || {};
      return String(d.trackUuid) === wanted
          || String(d.trackId)  === wanted
          || String(d.id)       === wanted;
    });
  }
  if (!key) return;
  openTrackDetailById(key);
  // Nettoie le hash pour ne pas rouvrir la carte à chaque reload.
  try { history.replaceState(null, '', location.pathname + location.search); } catch (_) {}
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
    // C4 Œuvre complète — bloc « Visuel lié » (achat séparé de l'image).
    if (data.linkedImage && data.linkedImage.id) {
      const li = data.linkedImage;
      const prevU = li.previewKey ? `/watt/images/${(li.previewKey + '').replace(/"/g,'&quot;')}` : '';
      const priceTxt = (li.priceCredits != null) ? `${li.priceCredits} Smyles` : '';
      html += `<div class="bd-linked-image" data-linked-image-id="${(li.id + '').replace(/"/g,'&quot;')}"
                    data-linked-image-price="${li.priceCredits != null ? li.priceCredits : ''}"
                    style="display:flex;align-items:center;gap:10px;margin-top:10px;padding:8px 10px;border:1px solid rgba(0,85,255,.4);border-radius:12px;background:rgba(0,85,255,.08);cursor:pointer">
        ${prevU ? `<img src="${prevU}" alt="" loading="lazy" style="width:42px;height:42px;border-radius:8px;object-fit:cover;flex:0 0 auto" />` : '<span style="font-size:18px">🖼</span>'}
        <div style="flex:1;min-width:0">
          <div style="font-size:.66rem;font-weight:700;letter-spacing:.04em;color:#6da4ff;text-transform:uppercase">🖼 Visuel lié · œuvre complète</div>
          <div style="font-size:.78rem;color:#a09cb8">${priceTxt}</div>
        </div>
        <span style="font-size:.74rem;color:#9dc0ff;font-weight:600">Voir l'image →</span>
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
  // C4 Œuvre complète — clic sur le visuel lié → drawer image (achat séparé).
  const liEl = body.querySelector('.bd-linked-image');
  if (liEl) {
    liEl.addEventListener('click', () => {
      const iid = liEl.dataset.linkedImageId;
      if (iid && window.PurchaseDrawer) {
        closeBoutiqueDrawer();
        window.PurchaseDrawer.open({
          type:  'image',
          id:    iid,
          price: parseInt(liEl.dataset.linkedImagePrice, 10) || null,
          title: 'Visuel lié',
        });
      }
    });
  }
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

// ── U8 — Bouton "Écouter tout" ────────────────────────────────────────────────
function renderPlayAllBtn(artist) {
  const btn = document.getElementById('ap-play-all-btn');
  if (!btn) return;
  const tracks = (artist && artist.tracks || []).filter(t => t.streamUrl);
  // Masqué pour l'owner (il gère depuis le dashboard) et si pas de tracks audio
  if (artist.isSelf || tracks.length === 0) { btn.style.display = 'none'; return; }
  btn.style.display = '';
}

/* ── C3 ② — MOTEUR AUDIO PARTAGÉ (section Sons publiés) ────────────────────
   UN SEUL <audio> pour toute la liste (fini les 81 lecteurs natifs).
   Le wrapper caché porte data-track-id / data-track-name / img.ap-track-cover
   / span.ap-artist-name : la mini-bar globale (ui/player/mini-bar.js) capte
   l'event play en capture et lit ces métadonnées en remontant le DOM depuis
   l'audio — zéro modification de mini-bar.js. Le compteur d'écoutes global
   (data-track-id) est couvert par le même wrapper. */

const _AP_PLAY_SVG  = '<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>';
const _AP_PAUSE_SVG = '<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>';

let _apAudio     = null;  // l'unique HTMLAudioElement de la section Sons
let _apAudioWrap = null;  // div porteur des métadonnées lues par la mini-bar
let _apQueue     = [];    // [{id, name, streamUrl, coverUrl, color}] ordre d'affichage
let _apCurrentId = null;  // id du track actuellement chargé

// Détection MIME par extension — R2 renvoie parfois application/octet-stream
// qui empêche le play sur Chrome (héritée de l'ancien renderTracks).
function _apMimeFor(url) {
  const ext = (String(url || '').split('.').pop() || '').toLowerCase();
  return ext === 'mp3' ? 'audio/mpeg'
       : ext === 'm4a' ? 'audio/mp4'
       : 'audio/wav';  // .wav par défaut
}

function _ensureSharedAudio() {
  if (_apAudio && _apAudioWrap && document.body.contains(_apAudioWrap)) return _apAudio;
  const wrap = document.createElement('div');
  wrap.id = 'ap-shared-audio';
  wrap.hidden = true;  // l'UI vit dans les rows + la mini-bar globale
  // Métadonnées lues par mini-bar._readMeta (remontée DOM depuis l'audio).
  const img = document.createElement('img');
  img.className = 'ap-track-cover';
  img.alt = '';
  const artistEl = document.createElement('span');
  artistEl.className = 'ap-artist-name';
  const audio = document.createElement('audio');
  audio.preload = 'none';
  wrap.appendChild(img);
  wrap.appendChild(artistEl);
  wrap.appendChild(audio);
  document.body.appendChild(wrap);
  audio.addEventListener('play',  () => _apSyncRows(true));
  audio.addEventListener('pause', () => _apSyncRows(false));
  audio.addEventListener('ended', _apPlayNext);
  _apAudioWrap = wrap;
  _apAudio = audio;
  return audio;
}

// Pattern promesse anti-AbortError (Tom 2026-05-05) : play/pause rapprochés
// rejettent une AbortError bénigne qu'on avale silencieusement.
function _apSafePlay(audio) {
  const p = audio.play();
  if (p !== undefined) {
    p.catch(err => {
      if (err && err.name === 'AbortError') return;  // benign
      console.error('[artiste] audio.play() rejected:', err);
      const errMsg = err && (err.message || err.name) || 'erreur audio inconnue';
      const audioErr = audio.error
        ? ` (code ${audio.error.code}: ${audio.error.message || ''})`
        : '';
      toast('Lecture impossible : ' + errMsg + audioErr);
    });
  }
}

// Lance (ou met en pause si re-clic sur la même row) un track de la queue.
function _apPlayTrack(trackId, forcePlay) {
  const t = _apQueue.find(q => String(q.id) === String(trackId));
  if (!t) return;
  if (!t.streamUrl) {
    toast('Audio en cours de traitement, réessaie dans quelques secondes.');
    return;
  }
  const audio = _ensureSharedAudio();

  // Re-clic sur la row en cours → toggle pause/lecture.
  if (String(_apCurrentId) === String(trackId)) {
    if (audio.paused) _apSafePlay(audio);
    else if (!forcePlay) audio.pause();
    return;
  }

  _apCurrentId = String(trackId);

  // Métadonnées à jour AVANT le play : la mini-bar les lit sur l'event.
  // trackId (legacy) reste pour le compteur d'écoutes (storage.js) ;
  // trackUuid sert au ❤️/➕ de la mini-bar (fix QA C3 ②).
  _apAudioWrap.dataset.trackId   = t.id || '';
  _apAudioWrap.dataset.trackUuid = t.trackUuid || t.id || '';
  _apAudioWrap.dataset.trackName = t.name || '';
  const img = _apAudioWrap.querySelector('img.ap-track-cover');
  if (img) img.src = t.coverUrl || '';
  const artistEl = _apAudioWrap.querySelector('.ap-artist-name');
  if (artistEl) artistEl.textContent = (state.artist && state.artist.artistName) || '';
  if (t.color) _apAudioWrap.style.setProperty('--son-color', t.color);
  else _apAudioWrap.style.removeProperty('--son-color');

  // Source via <source type=...> pour forcer le MIME.
  audio.pause();
  audio.innerHTML = '';
  audio.removeAttribute('src');
  const src = document.createElement('source');
  src.src  = t.streamUrl;
  src.type = _apMimeFor(t.streamUrl);
  audio.appendChild(src);
  audio.load();
  _apSafePlay(audio);
}

// Enchaînement : à `ended`, joue la prochaine row qui a un audio.
function _apPlayNext() {
  if (_apCurrentId == null || !_apQueue.length) return;
  const idx = _apQueue.findIndex(q => String(q.id) === String(_apCurrentId));
  for (let i = idx + 1; i < _apQueue.length; i++) {
    if (_apQueue[i].streamUrl) { _apPlayTrack(_apQueue[i].id, true); return; }
  }
  _apSyncRows(false);  // fin de liste
}

// Reflète l'état play/pause sur les rows (row active + icône du bouton).
function _apSyncRows(playing) {
  document.querySelectorAll('.ap-track-row').forEach(row => {
    const active = _apCurrentId != null && String(row.dataset.trackId) === String(_apCurrentId);
    row.classList.toggle('is-active',  active);
    row.classList.toggle('is-playing', active && !!playing);
    const btn = row.querySelector('.ap-track-play-btn');
    if (btn) btn.innerHTML = (active && playing) ? _AP_PAUSE_SVG : _AP_PLAY_SVG;
  });
}

// U8 — « Écouter tout » pilote le même audio partagé.
window.playAllTracks = function() {
  const first = _apQueue.find(t => t.streamUrl);
  if (!first) return;
  _apPlayTrack(first.id, true);
  const n = _apQueue.filter(t => t.streamUrl).length;
  toast('Lecture en cours ▶ ' + n + ' son' + (n > 1 ? 's' : ''));
};

// ── U8 — Chip ADN inline dans le hero ────────────────────────────────────────
function renderAdnChip(artist) {
  const chip = document.getElementById('ap-adn-chip');
  const priceEl = document.getElementById('ap-adn-chip-price');
  if (!chip) return;
  const adn = artist && artist.adn;
  if (!adn || artist.isSelf) { chip.style.display = 'none'; return; }
  chip.style.display = '';
  if (priceEl) priceEl.textContent = formatCount(adn.priceCredits) + ' cr.';
}

window.scrollToAdnCard = function() {
  const card = document.getElementById('ap-dna-card');
  if (!card) return;
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  // Highlight bref
  card.style.transition = 'box-shadow .3s';
  card.style.boxShadow = '0 0 0 2px rgba(204,136,255,.6), 0 0 32px rgba(204,136,255,.25)';
  setTimeout(() => { card.style.boxShadow = ''; }, 1200);
};

// ── C3 ① — renderBioPreview SUPPRIMÉE (fix double-bio, retour QA Tom) :
// la bio unique et éditable vit dans le bloc identité (#ap-bio).

// ── C3 v3 — RELIQUE ADN (spec C3 ① — 2026-06-13) ─────────────────────────────
// États : visiteur sans ADN → caché · owner sans ADN → relique incitative ·
// ADN en vente → relique pleine largeur · possédé → bord doré sans bouton.
// Règle absolue : le contenu ADN n'est JAMAIS visible sans achat.
function renderDna(artist) {
  const card = $('ap-dna-card');
  if (!card) return;
  const adn = artist && artist.adn;
  const isSelf = !!(artist && artist.isSelf);

  // Reset des états visuels (la fonction est ré-appelée après chaque loadArtist)
  card.classList.remove('ap-relic--owned', 'ap-relic--empty');
  hide('ap-relic-owned');
  hide('ap-relic-empty');
  show('ap-relic-actions');

  if (!adn) {
    if (!isSelf) {
      // Visiteur : pas d'ADN en vente → la section n'est pas rendue du tout.
      card.style.display = 'none';
      return;
    }
    // Owner : relique grisée incitative → CTA WATT BOARD.
    card.style.display = '';
    card.classList.add('ap-relic--empty');
    setText('ap-relic-artist', artist.artistName || '');
    hide('ap-relic-actions');
    hide('ap-relic-edition');
    setText('ap-dna-teaser', '');
    const metaEmpty = $('ap-dna-meta');
    if (metaEmpty) metaEmpty.innerHTML = '';
    show('ap-relic-empty');
    return;
  }

  card.style.display = '';
  setText('ap-relic-artist', artist.artistName || '');
  setText('ap-dna-price', formatCount(adn.priceCredits));

  // Édition #X/N en évidence si édition limitée (le prochain exemplaire minté).
  const editionEl = $('ap-relic-edition');
  if (editionEl) {
    if (adn.maxSupply != null) {
      const sold = Number(adn.soldCount || 0);
      editionEl.textContent = adn.isSoldOut
        ? `#${adn.maxSupply}/${adn.maxSupply}`
        : `#${sold + 1}/${adn.maxSupply}`;
      editionEl.style.display = '';
    } else {
      editionEl.style.display = 'none';
    }
  }

  // Pas de teaser textuel — afficher uniquement longueur (ordre complexité).
  var charCount = adn.characterCount || 0;
  var teaserEl = document.getElementById('ap-dna-teaser');
  if (teaserEl) {
    teaserEl.textContent = charCount > 0
      ? charCount.toLocaleString('fr-FR') + ' caractères · contenu verrouillé'
      : 'Contenu verrouillé';
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
    // C3 ② — rareté via tokens C0 (SpBadges.rarete) : fini les badges tiers
    // codés à la main avec couleurs en dur. Le #X/N « prochain exemplaire »
    // reste affiché en grand par #ap-relic-edition ; ici la pilule porte la
    // rareté canonique (mythic/legendary→légendaire, limited→épique,
    // open→rare via _rarityTierToToken). Nature 🧬 = la relique elle-même.
    if (adn.isSoldOut) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge ap-dna-badge-soldout">Épuisé</span>');
    } else if (window.SpBadges) {
      const rToken = _rarityTierToToken(adn.rarityTier);
      const rHtml = (adn.rarityTier === 'mythic' && adn.maxSupply != null)
        ? SpBadges.rarete(1, adn.maxSupply, rToken)
        : (rToken ? SpBadges.rarete(null, null, rToken) : '');
      if (rHtml) meta.insertAdjacentHTML('beforeend', rHtml);
    }
    // rarityTier 'unlimited' → pas de pilule rareté affichée
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
      setText('ap-dna-unlock-label', 'Débloquer');
    }
  }

  // État possédé (async, best-effort) : si le visiteur connecté détient déjà
  // cet ADN, la relique passe en bord doré sans bouton d'achat.
  if (!isSelf) {
    _applyAdnOwnedState(card, adn.id).catch(() => { /* silencieux */ });
  }
}

// Vérifie la possession de l'ADN via la bibliothèque du visiteur connecté
// (GET /me/library/adns — auth requis). Résultat mis en cache sur state
// pour éviter un fetch à chaque re-render.
async function _applyAdnOwnedState(card, adnId) {
  if (!adnId) return;
  if (typeof getAuthToken !== 'function' || !getAuthToken()) return;
  if (typeof apiFetch !== 'function') return;

  if (state.ownedAdnIds === undefined) {
    try {
      const resp = await apiFetch('/me/library/adns?per_page=100');
      state.ownedAdnIds = (resp && Array.isArray(resp.items))
        ? resp.items.map(it => String(it.adn_id || it.adnId || ''))
        : [];
    } catch (_) {
      state.ownedAdnIds = undefined; // re-tentera au prochain render
      return;
    }
  }
  if (!state.ownedAdnIds || !state.ownedAdnIds.includes(String(adnId))) return;

  card.classList.add('ap-relic--owned');
  show('ap-relic-owned');
  hide('ap-relic-actions');
}

/* ═══════════════════════════════════════════════════════════════════════════
   ADN VISUEL artiste — relique #ap-vdna-card (jumelle de renderDna)
   ─────────────────────────────────────────────────────────────────────────
   Lit artist.visualAdn (payload PUBLIC GATÉ : id, characterCount, priceCredits,
   style, hasUsageGuide/hasExampleOutputs, rareté). Le génome (description /
   palette / usage_guide / example_outputs) n'est JAMAIS exposé ici — le backend
   ne l'envoie pas. États identiques à l'ADN musical.                          */
function renderVisualDna(artist) {
  const card = $('ap-vdna-card');
  if (!card) return;
  const adn = artist && artist.visualAdn;
  const isSelf = !!(artist && artist.isSelf);

  card.classList.remove('ap-relic--owned', 'ap-relic--empty');
  hide('ap-vdna-owned');
  hide('ap-vdna-empty');
  show('ap-vdna-actions');

  if (!adn) {
    if (!isSelf) {
      // Visiteur : pas d'ADN visuel en vente → carte masquée.
      card.style.display = 'none';
      return;
    }
    // Owner : relique grisée incitative → CTA WATT BOARD.
    card.style.display = '';
    card.classList.add('ap-relic--empty');
    setText('ap-vdna-artist', artist.artistName || '');
    hide('ap-vdna-actions');
    hide('ap-vdna-edition');
    setText('ap-vdna-teaser', '');
    const metaEmpty = $('ap-vdna-meta');
    if (metaEmpty) metaEmpty.innerHTML = '';
    show('ap-vdna-empty');
    return;
  }

  card.style.display = '';
  setText('ap-vdna-artist', artist.artistName || '');
  setText('ap-vdna-price', formatCount(adn.priceCredits));

  const editionEl = $('ap-vdna-edition');
  if (editionEl) {
    if (adn.maxSupply != null) {
      const sold = Number(adn.soldCount || 0);
      editionEl.textContent = adn.isSoldOut
        ? `#${adn.maxSupply}/${adn.maxSupply}`
        : `#${sold + 1}/${adn.maxSupply}`;
      editionEl.style.display = '';
    } else {
      editionEl.style.display = 'none';
    }
  }

  // Pas de teaser textuel — longueur seulement (génome gaté).
  var charCount = adn.characterCount || 0;
  var teaserEl = $('ap-vdna-teaser');
  if (teaserEl) {
    teaserEl.textContent = charCount > 0
      ? charCount.toLocaleString('fr-FR') + ' caractères · contenu verrouillé'
      : 'Contenu verrouillé';
  }

  // Badges : style (public), Guide, Exemples, IA, rareté.
  const meta = $('ap-vdna-meta');
  if (meta) {
    meta.innerHTML = '';
    if (adn.style) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge">🎨 ' + _visualStyleLabel(adn.style) + '</span>');
    }
    if (adn.hasUsageGuide) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge">📘 Guide d\'usage</span>');
    }
    if (adn.hasExampleOutputs) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge">🖼️ Exemples</span>');
    }
    const AI_LBL = {
      chatgpt: '🤖 ChatGPT', claude: '🤖 Claude', grok: '🤖 Grok',
      gemini: '🤖 Gemini', mistral: '🤖 Mistral',
      perplexity: '🤖 Perplexity', autre: '🤖 IA'
    };
    if (adn.aiReference && AI_LBL[adn.aiReference]) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge">' + AI_LBL[adn.aiReference] + '</span>');
    }
    if (adn.isSoldOut) {
      meta.insertAdjacentHTML('beforeend',
        '<span class="ap-dna-badge ap-dna-badge-soldout">Épuisé</span>');
    } else if (window.SpBadges) {
      const rToken = _rarityTierToToken(adn.rarityTier);
      const rHtml = (adn.rarityTier === 'mythic' && adn.maxSupply != null)
        ? SpBadges.rarete(1, adn.maxSupply, rToken)
        : (rToken ? SpBadges.rarete(null, null, rToken) : '');
      if (rHtml) meta.insertAdjacentHTML('beforeend', rHtml);
    }
  }

  const btn = $('ap-vdna-unlock-btn');
  if (btn) {
    if (isSelf) {
      btn.style.display = 'none';
    } else if (adn.isSoldOut) {
      btn.style.display = '';
      btn.disabled = true;
      btn.style.opacity = '0.5';
      btn.style.cursor = 'not-allowed';
      setText('ap-vdna-unlock-label', 'Sold out');
    } else {
      btn.style.display = '';
      btn.disabled = false;
      btn.style.opacity = '';
      btn.style.cursor = '';
      setText('ap-vdna-unlock-label', 'Débloquer');
    }
  }

  if (!isSelf) {
    _applyVisualAdnOwnedState(card, adn.id).catch(() => { /* silencieux */ });
  }
}

// Libellés FR des 16 codes de style (mirror backend / dashboard).
const _VISUAL_STYLE_LABELS = {
  realiste: 'Réaliste', cartoon: 'Cartoon', anime: 'Anime', '3d': '3D / Render',
  peinture: 'Peinture', aquarelle: 'Aquarelle', croquis: 'Croquis',
  pixel_art: 'Pixel art', cyberpunk: 'Cyberpunk', fantasy: 'Fantasy',
  minimaliste: 'Minimaliste', retro: 'Rétro', abstrait: 'Abstrait',
  surrealiste: 'Surréaliste', comics: 'Comics', photo: 'Photo',
};
function _visualStyleLabel(code) {
  return _VISUAL_STYLE_LABELS[code] || code;
}

// Vérifie la possession de l'ADN visuel via /me/library/visual-adns.
async function _applyVisualAdnOwnedState(card, visualAdnId) {
  if (!visualAdnId) return;
  if (typeof getAuthToken !== 'function' || !getAuthToken()) return;
  if (typeof apiFetch !== 'function') return;

  if (state.ownedVisualAdnIds === undefined) {
    try {
      const resp = await apiFetch('/me/library/visual-adns?per_page=100');
      state.ownedVisualAdnIds = (resp && Array.isArray(resp.items))
        ? resp.items.map(it => String(it.visual_adn_id || it.visualAdnId || ''))
        : [];
    } catch (_) {
      state.ownedVisualAdnIds = undefined; // re-tentera au prochain render
      return;
    }
  }
  if (!state.ownedVisualAdnIds || !state.ownedVisualAdnIds.includes(String(visualAdnId))) return;

  card.classList.add('ap-relic--owned');
  show('ap-vdna-owned');
  hide('ap-vdna-actions');
}

// P1-F4 (2026-05-04) — libellés humains des enums backend pour les
// réglages de génération exposés sur les cards prompts publiques.
// Aligned avec PromptPlatform / PromptVocalGender (watt-api).
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

// C3 ② — passerelle entre les tiers de rareté backend (mythic / legendary /
// limited / open / unlimited) et les 4 raretés canoniques du design system
// C0 (SpBadges.rarete : commune / rare / epique / legendaire). 'unlimited'
// → '' (pas de pilule). mythic = pièce unique → classe légendaire + #1/1.
const _RARITY_TIER_TOKEN = {
  mythic:     'legendaire',
  legendary:  'legendaire',
  limited:    'epique',
  open:       'rare',
  legendaire: 'legendaire',
  epique:     'epique',
  rare:       'rare',
  commune:    'commune',
  common:     'commune',
  epic:       'epique',
};
function _rarityTierToToken(tier) {
  return _RARITY_TIER_TOKEN[String(tier || '').toLowerCase()] || '';
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
    // Rareté/supply (2026-06-08) — badge édition limitée, comme les ADN.
    // unlimited → pas de badge. maxSupply renseigne le nb d'exemplaires.
    let rarityBadge = '';
    const _pmax = (p.maxSupply != null) ? p.maxSupply : '?';
    if (p.rarityTier === 'mythic') {
      rarityBadge = '<span class="ap-prompt-badge" style="background:#FFD700;color:#000;font-weight:600;">👑 Mythique · 1/1</span>';
    } else if (p.rarityTier === 'legendary') {
      rarityBadge = `<span class="ap-prompt-badge" style="background:#FBBF24;color:#000;font-weight:600;">⭐ Légendaire · ${_pmax} ex.</span>`;
    } else if (p.rarityTier === 'limited') {
      rarityBadge = `<span class="ap-prompt-badge" style="background:#A78BFA;color:#000;font-weight:600;">💎 Limité · ${_pmax} ex.</span>`;
    } else if (p.rarityTier === 'open') {
      rarityBadge = `<span class="ap-prompt-badge" style="background:#4ADE80;color:#000;font-weight:600;">🟢 Ouvert · ${_pmax} ex.</span>`;
    }
    // Bloc weirdness/style supprimé du rendu public — ces 2 infos
    // apparaissent dans /library après achat (cf library.js renderPrompts).
    const settingsBlock = '';
    // Pas de bouton unlock pour l'owner (évite l'auto-achat 400).
    const unlockBtn = artist.isSelf
      ? '<span class="ap-prompt-owner-note">Ton prompt</span>'
      : `<button type="button" class="ap-prompt-unlock-btn"
                 data-prompt-id="${p.id}" data-price="${p.priceCredits}">
          🧬 Recette · ${priceStr} crédits
        </button>
        <button type="button" class="ap-prompt-trade-btn"
                data-prompt-id="${p.id}"
                data-prompt-title="${(p.title||'').replace(/"/g,'&quot;')}"
                data-prompt-price="${p.priceCredits || 0}"
                data-artist-id="${artist.id || ''}"
                data-artist-name="${(artist.artistName||'').replace(/"/g,'&quot;')}">
          🔄 Échanger
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
        ${rarityBadge}
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
    const unlockBtn = ev.target.closest('.ap-prompt-unlock-btn');
    if (unlockBtn) {
      const id = unlockBtn.dataset.promptId;
      if (id) unlockPromptFromProfile(id, unlockBtn);
      return;
    }
    const tradeBtn = ev.target.closest('.ap-prompt-trade-btn');
    if (tradeBtn) {
      openTradeModal({
        promptId:    tradeBtn.dataset.promptId,
        promptTitle: tradeBtn.dataset.promptTitle,
        promptPrice: parseInt(tradeBtn.dataset.promptPrice, 10) || 0,
        receiverId:  tradeBtn.dataset.artistId,
        receiverName:tradeBtn.dataset.artistName,
      });
    }
  };
}

// ── Modal d'échange ADN ────────────────────────────────────────────────────

async function openTradeModal({ promptId, promptTitle, promptPrice, receiverId, receiverName }) {
  // Vérifie auth
  if (typeof window.getAuthToken === 'function' && !window.getAuthToken()) {
    if (window.openAuthModal) window.openAuthModal('login');
    return;
  }

  // Supprime modal précédente si existe
  const prev = document.getElementById('smyle-trade-modal');
  if (prev) prev.remove();

  // Charge mes produits échangeables (sons ET images — parité visuel C4).
  // Un produit = une ligne `prompts` ; les images publiées sont offrables au
  // même titre que les recettes.
  let myPrompts = [];
  try {
    const data = await apiFetch('/artist/me/prompts?limit=50');
    myPrompts = (data.items || data || []).map(p => ({ id: p.id, title: p.title, price_credits: p.price_credits, kind: 'son' }));
  } catch (_) {}
  try {
    const data = await apiFetch('/artist/me/images');
    const imgs = Array.isArray(data) ? data : ((data && data.items) || []);
    myPrompts = myPrompts.concat(imgs.filter(p => p.is_published).map(p => ({ id: p.id, title: p.title, price_credits: p.price_credits, kind: 'image' })));
  } catch (_) {}

  const _tradeIc = (k) => k === 'image' ? '🖼 ' : '🎵 ';
  const promptOptions = myPrompts.length
    ? myPrompts.map(p => `<option value="${p.id}">${_tradeIc(p.kind)}${p.title || 'Sans titre'} · ${p.price_credits || 0} crédits</option>`).join('')
    : '<option value="" disabled>Aucun produit à proposer</option>';

  const el = document.createElement('div');
  el.id = 'smyle-trade-modal';
  el.className = 'trade-modal-backdrop';
  el.innerHTML = `
    <div class="trade-modal-box" role="dialog" aria-label="Proposer un échange">
      <div class="trade-modal-header">
        <span class="trade-modal-title">🔄 Proposer un échange</span>
        <button class="trade-modal-close" onclick="document.getElementById('smyle-trade-modal').remove()">✕</button>
      </div>
      <div class="trade-modal-body">
        <div class="trade-field">
          <label class="trade-label">Tu demandes</label>
          <div class="trade-target-info">
            <strong>${promptTitle || 'Prompt sans titre'}</strong>
            <span class="trade-price-tag">${promptPrice} crédits</span>
          </div>
          <span class="trade-from">de <strong>${receiverName || 'l\'artiste'}</strong></span>
        </div>
        <div class="trade-field">
          <label class="trade-label">Tu proposes</label>
          <select class="trade-select" id="trade-offered-id">
            <option value="">-- Choisir un de tes prompts --</option>
            ${promptOptions}
          </select>
        </div>
        <div class="trade-field">
          <label class="trade-label">Complément en crédits <span class="trade-hint">(optionnel · 0 si équitable)</span></label>
          <input type="number" class="trade-input" id="trade-supplement" min="0" value="0" />
        </div>
        <div class="trade-field">
          <label class="trade-label">Message <span class="trade-hint">(optionnel)</span></label>
          <textarea class="trade-textarea" id="trade-message" rows="2"
            placeholder="Pourquoi tu veux échanger…"></textarea>
        </div>
        <p class="trade-rules">
          ⚠️ Les échanges sont limités à tes propres créations. L'offre expire sous 7 jours.
        </p>
        <button class="trade-submit-btn" id="trade-submit-btn"
                onclick="submitTradeOffer('${promptId}', '${receiverId}')">
          Envoyer la proposition
        </button>
      </div>
    </div>`;

  document.body.appendChild(el);
  el.addEventListener('click', ev => { if (ev.target === el) el.remove(); });
}

async function submitTradeOffer(requestedPromptId, receiverId) {
  const offeredId   = (document.getElementById('trade-offered-id')  || {}).value || '';
  const supplement  = parseInt((document.getElementById('trade-supplement') || {}).value || '0', 10);
  const message     = ((document.getElementById('trade-message') || {}).value || '').trim();
  const btn         = document.getElementById('trade-submit-btn');

  if (!offeredId) { alert('Choisis un prompt à proposer.'); return; }

  if (btn) { btn.textContent = 'Envoi…'; btn.disabled = true; }

  try {
    await apiFetch('/trades/offers', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        receiver_id:          receiverId,
        offered_prompt_id:    offeredId,
        requested_prompt_id:  requestedPromptId,
        credit_supplement:    Math.max(0, supplement || 0),
        message:              message || null,
      }),
    });
    document.getElementById('smyle-trade-modal').remove();
    alert('✅ Proposition envoyée ! L\'artiste recevra une notification.');
  } catch (err) {
    if (btn) { btn.textContent = 'Envoyer la proposition'; btn.disabled = false; }
    const detail = (err && err.body && err.body.detail) || err.message || 'Erreur inconnue';
    alert('Erreur : ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)));
  }
}

// ── Modal d'échange depuis le PROFIL (double sélection) ──────────────────────
// Entrée principale du trade : on choisit un prompt de l'artiste consulté ET
// un des siens. Gère explicitement le cas "aucun prompt échangeable".
async function openTradeModalProfile() {
  const artist = state && state.artist;
  if (!artist) return;
  if (artist.isSelf) { alert("C'est ton profil — tu ne peux pas échanger avec toi-même."); return; }

  if (typeof window.getAuthToken === 'function' && !window.getAuthToken()) {
    if (window.openAuthModal) window.openAuthModal('login');
    return;
  }

  // Parité visuel (C4) : un produit échangeable = une ligne `prompts` (son OU
  // image). Côté artiste consulté, on agrège ses sons (déjà en state) et ses
  // images publiques (/images?artist_id=...). Côté moi, sons + images publiées.
  let theirPrompts = (Array.isArray(artist.prompts) ? artist.prompts : [])
    .map(p => ({ id: p.id, title: p.title, price_credits: p.priceCredits, kind: 'son' }));
  try {
    const aid = artist.id || artist.userId || '';
    if (aid) {
      const d = await apiFetch(`/images?artist_id=${encodeURIComponent(aid)}&limit=50`);
      const imgs = (d && d.images) || [];
      theirPrompts = theirPrompts.concat(imgs.map(p => ({ id: p.id, title: p.title, price_credits: p.priceCredits, kind: 'image' })));
    }
  } catch (_) {}

  if (theirPrompts.length === 0) {
    alert("Cet artiste n'a pas encore de produit échangeable. Reviens quand il en aura publié un.");
    return;
  }

  const prev = document.getElementById('smyle-trade-modal');
  if (prev) prev.remove();

  let myPrompts = [];
  try {
    const data = await apiFetch('/artist/me/prompts?limit=50');
    myPrompts = (data.items || data || []).map(p => ({ id: p.id, title: p.title, price_credits: p.price_credits, kind: 'son' }));
  } catch (_) {}
  try {
    const data = await apiFetch('/artist/me/images');
    const imgs = Array.isArray(data) ? data : ((data && data.items) || []);
    myPrompts = myPrompts.concat(imgs.filter(p => p.is_published).map(p => ({ id: p.id, title: p.title, price_credits: p.price_credits, kind: 'image' })));
  } catch (_) {}

  const esc = (s) => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  const _tradeIc = (k) => k === 'image' ? '🖼 ' : '🎵 ';
  const theirOptions = theirPrompts.map(p =>
    `<option value="${p.id}">${_tradeIc(p.kind)}${esc(p.title) || 'Sans titre'} · ${p.price_credits || 0} crédits</option>`
  ).join('');
  const myOptions = myPrompts.length
    ? myPrompts.map(p => `<option value="${p.id}">${_tradeIc(p.kind)}${esc(p.title) || 'Sans titre'} · ${p.price_credits || 0} crédits</option>`).join('')
    : '<option value="" disabled>Aucun produit à proposer — publie d\'abord un son ou une image</option>';

  const el = document.createElement('div');
  el.id = 'smyle-trade-modal';
  el.className = 'trade-modal-backdrop';
  el.innerHTML = `
    <div class="trade-modal-box" role="dialog" aria-label="Proposer un échange">
      <div class="trade-modal-header">
        <span class="trade-modal-title">🔄 Proposer un échange à ${esc(artist.artistName) || 'cet artiste'}</span>
        <button class="trade-modal-close" onclick="document.getElementById('smyle-trade-modal').remove()">✕</button>
      </div>
      <div class="trade-modal-body">
        <div class="trade-field">
          <label class="trade-label">Tu demandes <span class="trade-hint">(son son ou son image)</span></label>
          <select class="trade-select" id="trade-requested-id">
            <option value="">-- Choisir un de ses produits --</option>
            ${theirOptions}
          </select>
        </div>
        <div class="trade-field">
          <label class="trade-label">Tu proposes <span class="trade-hint">(ton son ou ton image)</span></label>
          <select class="trade-select" id="trade-offered-id">
            <option value="">-- Choisir un de tes produits --</option>
            ${myOptions}
          </select>
        </div>
        <div class="trade-field">
          <label class="trade-label">Complément en crédits <span class="trade-hint">(optionnel · 0 si équitable)</span></label>
          <input type="number" class="trade-input" id="trade-supplement" min="0" value="0" />
        </div>
        <div class="trade-field">
          <label class="trade-label">Message <span class="trade-hint">(optionnel)</span></label>
          <textarea class="trade-textarea" id="trade-message" rows="2"
            placeholder="Pourquoi tu veux échanger…"></textarea>
        </div>
        <p class="trade-rules">
          ⚠️ Échanges limités à tes propres créations. Un frais de 20% (brûlé) s'applique de chaque côté. L'offre expire sous 7 jours.
        </p>
        <button class="trade-submit-btn" id="trade-submit-btn"
                onclick="submitTradeOfferProfile('${artist.id || ''}')">
          Envoyer la proposition
        </button>
      </div>
    </div>`;

  document.body.appendChild(el);
  el.addEventListener('click', ev => { if (ev.target === el) el.remove(); });
}

async function submitTradeOfferProfile(receiverId) {
  const requestedId = (document.getElementById('trade-requested-id') || {}).value || '';
  const offeredId   = (document.getElementById('trade-offered-id')   || {}).value || '';
  const supplement  = parseInt((document.getElementById('trade-supplement') || {}).value || '0', 10);
  const message     = ((document.getElementById('trade-message') || {}).value || '').trim();
  const btn         = document.getElementById('trade-submit-btn');

  if (!requestedId) { alert('Choisis le prompt que tu veux récupérer.'); return; }
  if (!offeredId)   { alert('Choisis un de tes prompts à proposer.'); return; }

  if (btn) { btn.textContent = 'Envoi…'; btn.disabled = true; }

  try {
    await apiFetch('/trades/offers', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        receiver_id:          receiverId,
        offered_prompt_id:    offeredId,
        requested_prompt_id:  requestedId,
        credit_supplement:    Math.max(0, supplement || 0),
        message:              message || null,
      }),
    });
    document.getElementById('smyle-trade-modal').remove();
    alert('✅ Proposition envoyée ! L\'artiste recevra une notification.');
  } catch (err) {
    if (btn) { btn.textContent = 'Envoyer la proposition'; btn.disabled = false; }
    const detail = (err && err.body && err.body.detail) || err.message || 'Erreur inconnue';
    alert('Erreur : ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)));
  }
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

  // C3 ② — rows légères sur le player global. Le track reste le produit
  // visible : prompt lié (recette) = bouton prix, écoute = audio PARTAGÉ
  // (un seul <audio> pour toute la liste — cf. moteur _apPlayTrack).
  // On indexe artist.prompts par id pour retrouver prix / rareté.
  const promptsById = {};
  const allPrompts = Array.isArray(artist && artist.prompts) ? artist.prompts : [];
  allPrompts.forEach(p => { if (p && p.id) promptsById[String(p.id)] = p; });

  list.innerHTML = '';
  _apQueue = [];
  tracks.forEach(t => {
    const row = document.createElement('article');
    row.className = 'ap-track-row';
    row.dataset.trackId   = t.id || '';
    row.dataset.trackName = t.name || '';
    const safeName = (t.name || 'Sans titre').replace(/</g, '&lt;');
    const plays    = formatCount(t.plays);

    // Queue du moteur audio partagé — ordre d'affichage = ordre de lecture.
    _apQueue.push({
      id:        t.id,
      // Fix QA C3 ② — UUID requis par like/wishlist et ajout playlist
      // (la mini-bar le lit via data-track-uuid sur le wrapper).
      trackUuid: t.trackUuid || t.id,
      name:      t.name || '',
      streamUrl: t.streamUrl || '',
      coverUrl:  t.coverUrl || t.cover_url || '',
      color:     t.playlistColor || t.color || '',
    });

    // Cover mini. Fallback sur la couleur du track si pas d'image.
    const _coverU = t.coverUrl || t.cover_url || '';
    const coverHTML = _coverU
      ? `<img src="${_coverU.replace(/"/g, '&quot;')}" alt="" loading="lazy" />`
      : `<div class="ap-track-mini-fallback"${t.color ? ` style="background:${t.color}"` : ''}></div>`;

    // Repères C0 — nature toujours, palier/rareté seulement si la donnée
    // existe (pas de palier dans le payload tant que les abos ne sont pas
    // branchés : rendu défensif, s'allumera tout seul).
    const linkedPrompt = t.promptId ? promptsById[String(t.promptId)] : null;
    const natureBadge = window.SpBadges
      ? SpBadges.nature((t.beatId || t.beat_id) ? 'beat' : 'son-ia') : '';
    const tier = t.palier || t.creatorTier || t.subscriptionTier || '';
    const palierBadge = (tier && window.SpBadges) ? SpBadges.palier(tier) : '';
    let rareteBadge = '';
    if (window.SpBadges && linkedPrompt) {
      const rToken = _rarityTierToToken(linkedPrompt.rarityTier);
      if (linkedPrompt.rarityTier === 'mythic' && linkedPrompt.maxSupply != null) {
        rareteBadge = SpBadges.rarete(1, linkedPrompt.maxSupply, rToken);
      } else if (rToken) {
        rareteBadge = SpBadges.rarete(null, null, rToken);
      }
    }
    // Provenance ⚡ plateforme (token C0, remplace l'ancien badge maison).
    const provenance = window.SpBadges ? SpBadges.provenance(t.platform) : '';
    // C4 Œuvre complète — badge + chip « visuel lié » si une image est liée.
    const linkedImage = (t.linkedImage && t.linkedImage.id) ? t.linkedImage : null;
    const oeuvreBadge = (linkedImage && window.SpBadges && SpBadges.oeuvre) ? SpBadges.oeuvre() : '';
    let linkedImgChip = '';
    if (linkedImage) {
      const _prevU = linkedImage.previewKey ? `/watt/images/${String(linkedImage.previewKey).replace(/"/g, '&quot;')}` : '';
      linkedImgChip = `<button type="button" class="ap-track-linked-img"
                data-linked-image-id="${linkedImage.id}"
                data-linked-image-price="${linkedImage.priceCredits != null ? linkedImage.priceCredits : ''}"
                title="Visuel lié — voir l'image (achat séparé)">🖼${_prevU ? ` <img src="${_prevU}" alt="" loading="lazy" />` : ''}</button>`;
    }

    // Prix recette — badge 🧬 si un prompt vendable est lié.
    let unlockBlock = '';
    if (linkedPrompt && !artist.isSelf) {
      const priceStr = formatCount(linkedPrompt.priceCredits);
      unlockBlock = `<button type="button" class="ap-track-unlock-btn"
                data-prompt-id="${linkedPrompt.id}"
                data-price="${linkedPrompt.priceCredits}"
                title="Débloquer la recette">🧬 ${priceStr} crédits</button>`;
    } else if (linkedPrompt && artist.isSelf) {
      unlockBlock = '<span class="ap-prompt-owner-note">Recette en vente</span>';
    }

    // Bouton supprimer — owner uniquement (le backend re-vérifie : 403 sinon).
    const deleteBtn = artist.isSelf
      ? `<button type="button" class="ap-track-delete-btn"
                 data-track-id="${t.id}"
                 data-track-uuid="${t.trackUuid || t.id}"
                 data-track-name="${(t.name || '').replace(/"/g, '&quot;')}"
                 title="Supprimer ce son">🗑</button>`
      : '';

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
      // C4 Œuvre complète — image liée (aperçu only) pour le drawer son.
      linkedImage:  linkedImage || null,
    };

    row.innerHTML = `
      <button type="button" class="ap-track-play-btn" data-play-track="${t.id}"
              aria-label="Écouter"${t.streamUrl ? '' : ' disabled title="Audio en cours de traitement…"'}>${_AP_PLAY_SVG}</button>
      <div class="ap-track-mini-cover">${coverHTML}</div>
      <div class="ap-track-row-main">
        <div class="ap-track-row-title">${safeName}</div>
        <div class="ap-track-row-badges">
          ${natureBadge}${palierBadge}${rareteBadge}${provenance}${oeuvreBadge}
          <span class="ap-track-row-plays">▶ ${plays}</span>
        </div>
      </div>
      <div class="ap-track-row-actions">
        ${linkedImgChip}
        ${unlockBlock}
        <button class="like-btn ap-track-like" type="button" data-like-btn="${t.trackUuid || t.id}" title="J&#39;aime / retirer" aria-label="Liker"></button>
        <button class="add-to-pl-btn ap-track-add-pl" type="button" data-add-to-playlist="${t.trackUuid || t.id}" title="Ajouter à une playlist" aria-label="Ajouter à une playlist">+</button>
        ${deleteBtn}
      </div>
    `;
    list.appendChild(row);
  });

  // Re-render pendant une lecture en cours → re-marque la row active.
  _apSyncRows(_apAudio && !_apAudio.paused);

  // ── Accordéon : 6 tracks visibles par défaut ────────────────────────────
  const TRACKS_FOLD = 6;
  const _prevTT = list.nextElementSibling;
  if (_prevTT && _prevTT.classList && _prevTT.classList.contains('ap-accordion-toggle')) _prevTT.remove();
  if (tracks.length > TRACKS_FOLD) {
    const allCards = list.querySelectorAll('.ap-track-row');
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

  // Délégation click — un seul listener pour la liste (re-rendue souvent).
  // Play/pause passe par le moteur audio partagé (_apPlayTrack, pattern
  // promesse anti-AbortError inclus). Clic sur la row = fiche détail.
  list.onclick = (ev) => {
    // Cas 0 : like-btn et add-to-pl-btn — délégués à playlists.js (capture)
    if (ev.target.closest('[data-like-btn]') || ev.target.closest('[data-add-to-playlist]')) {
      ev.stopPropagation();
      return;
    }
    // Cas 1 : bouton supprimer track (owner uniquement)
    const delBtn = ev.target.closest('.ap-track-delete-btn');
    if (delBtn) {
      ev.preventDefault();
      ev.stopPropagation();
      const tid = delBtn.dataset.trackUuid || delBtn.dataset.trackId;
      const tname = delBtn.dataset.trackName || 'ce son';
      if (tid && confirm(`Supprimer "${tname}" ?\n\nLe son disparaît de ton profil et du catalogue, et sa recette est retirée de la vente. Les personnes qui l'ont déjà achetée gardent leur exemplaire.`)) {
        deleteTrackFromProfile(tid, delBtn);
      }
      return;
    }
    // Cas 2 : bouton unlock prompt (prix recette)
    const unlockBtn = ev.target.closest('.ap-track-unlock-btn');
    if (unlockBtn) {
      const id = unlockBtn.dataset.promptId;
      if (id) unlockPromptFromProfile(id, unlockBtn);
      return;
    }
    // Cas 2bis : chip « visuel lié » (œuvre complète) → drawer image (achat séparé)
    const linkedImgBtn = ev.target.closest('.ap-track-linked-img');
    if (linkedImgBtn) {
      ev.preventDefault();
      ev.stopPropagation();
      const iid = linkedImgBtn.dataset.linkedImageId;
      if (iid && window.PurchaseDrawer) {
        window.PurchaseDrawer.open({
          type:  'image',
          id:    iid,
          price: parseInt(linkedImgBtn.dataset.linkedImagePrice, 10) || null,
          title: 'Visuel lié',
        });
      }
      return;
    }
    // Cas 3 : bouton play rond → audio partagé (re-clic même row = pause)
    const playBtn = ev.target.closest('.ap-track-play-btn');
    if (playBtn) {
      ev.stopPropagation();
      const tid = playBtn.dataset.playTrack;
      if (tid) _apPlayTrack(tid);
      return;
    }
    // Cas 4 : clic sur la row → fiche détail / déblocage
    const row = ev.target.closest('.ap-track-row');
    if (row && row.dataset.trackId) openTrackDetailById(row.dataset.trackId);
  };
}

// ── Unlock ADN depuis le profil ────────────────────────────────────────
async function unlockDnaFromProfile() {
  const artist = state.artist;
  if (!artist || !artist.adn || artist.isSelf) return;
  const adn = artist.adn;

  // C2/C3 — chemin canonique : drawer d'achat unifié (récap + confirmation +
  // erreurs humanisées). Le drawer gère lui-même le cas non-connecté (401 →
  // openAuthModal). Fallback : achat direct historique si le composant
  // n'est pas chargé sur la page.
  if (window.PurchaseDrawer && typeof window.PurchaseDrawer.open === 'function') {
    window.PurchaseDrawer.open({
      type:       'adn-artist',
      id:         adn.id,
      price:      adn.priceCredits,
      title:      'ADN · ' + (artist.artistName || 'Artiste'),
      artistName: artist.artistName || '',
      onSuccess:  () => {
        state.ownedAdnIds = undefined; // invalide le cache possession
        setTimeout(() => loadArtist(), 400);
      },
    });
    return;
  }

  // ── Fallback historique (sans drawer) ────────────────────────────────────
  // Redirige vers la connexion si non authentifié
  if (typeof getAuthToken === 'function' && !getAuthToken()) {
    const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/?auth=login&return=${returnUrl}`;
    return;
  }
  const btn = $('ap-dna-unlock-btn');
  if (btn) btn.disabled = true;
  try {
    await apiFetch(`/unlocks/adns/${encodeURIComponent(adn.id)}`, {
      method: 'POST',
    });
    toast('ADN débloqué · -30 % sur toutes les recettes 🎉');
    // On rafraîchit le profil pour que l'état du bouton reflète le owned
    state.ownedAdnIds = undefined;
    setTimeout(() => loadArtist(), 400);
  } catch (err) {
    handleUnlockError(err);
    if (btn) btn.disabled = false;
  }
}

// ── Unlock ADN VISUEL depuis le profil (mirror de unlockDnaFromProfile) ──
async function unlockVisualDnaFromProfile() {
  const artist = state.artist;
  if (!artist || !artist.visualAdn || artist.isSelf) return;
  const adn = artist.visualAdn;

  if (window.PurchaseDrawer && typeof window.PurchaseDrawer.open === 'function') {
    window.PurchaseDrawer.open({
      type:       'visual-adn',
      id:         adn.id,
      price:      adn.priceCredits,
      title:      'ADN visuel · ' + (artist.artistName || 'Artiste'),
      artistName: artist.artistName || '',
      onSuccess:  () => {
        state.ownedVisualAdnIds = undefined; // invalide le cache possession
        setTimeout(() => loadArtist(), 400);
      },
    });
    return;
  }

  // ── Fallback historique (sans drawer) ────────────────────────────────────
  if (typeof getAuthToken === 'function' && !getAuthToken()) {
    const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/?auth=login&return=${returnUrl}`;
    return;
  }
  const btn = $('ap-vdna-unlock-btn');
  if (btn) btn.disabled = true;
  try {
    await apiFetch(`/unlocks/visual-adns/${encodeURIComponent(adn.id)}`, {
      method: 'POST',
    });
    toast('ADN visuel débloqué · -30 % sur les images 🎨');
    state.ownedVisualAdnIds = undefined;
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
async function deleteTrackFromProfile(trackUuid, btn) {
  if (!trackUuid) return;
  if (btn) btn.disabled = true;
  try {
    // Suppression via l'endpoint canonique FastAPI DELETE /tracks/{uuid}
    // (02/07) : SOFT delete symétrique du delete image — le son disparaît
    // du profil et du catalogue, la recette liée est retirée de la vente,
    // l'œuvre complète est détachée (le visuel survivant reste vendable),
    // et les acheteurs GARDENT leur exemplaire en bibliothèque.
    // (Remplace l'ancien appel /watt/tracks/<id> : hard delete DB+R2 porté
    // du Flask historique — destructeur pour les acheteurs et fragile.)
    const token = (typeof getAuthToken === 'function') ? getAuthToken() : null;
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`/tracks/${encodeURIComponent(trackUuid)}`, {
      method: 'DELETE',
      headers,
    });
    if (!res.ok && res.status !== 204) {
      let detail = `${res.status}`;
      try { const j = await res.json(); detail = j.detail || j.message || detail; } catch (_) {}
      throw new Error(detail);
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

// ── Section REVENTE (marché secondaire) sur le profil ────────────────────────
// Les exemplaires que cet artiste remet en vente. Chaque item est attribué à
// son CRÉATEUR d'origine (lien vers son profil). Public.
async function loadArtistResale(artistId) {
  if (!artistId || typeof apiFetch !== 'function') return;
  let list = [];
  try {
    list = await apiFetch('/resale/by-seller/' + encodeURIComponent(artistId), { auth: false });
  } catch (e) { console.warn('[artiste.js] loadArtistResale', e); list = []; }
  renderResale(Array.isArray(list) ? list : []);
}

function renderResale(items) {
  const _e = s => { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; };
  let section = document.getElementById('ap-resale-section');
  if (!section) {
    section = document.createElement('section');
    section.id = 'ap-resale-section';
    section.className = 'ap-section';
    section.style.cssText = 'max-width:760px;margin:0 auto;padding:18px 20px';
    const anchor = document.getElementById('ap-voices-section') || document.getElementById('ap-profile');
    if (anchor && anchor.id === 'ap-profile') anchor.appendChild(section);
    else if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(section, anchor.nextSibling);
    else document.body.appendChild(section);
  }
  if (!items.length) { section.style.display = 'none'; return; }
  section.style.display = '';
  const rows = items.map(it => {
    const author = it.original_artist_name
      ? '<a href="/@' + _e(it.original_artist_slug || '') + '" style="color:#c4b5fd;text-decoration:none">créé par ' + _e(it.original_artist_name) + ' →</a>'
      : '<span style="color:#888">créateur inconnu</span>';
    const editionBadge = (it.edition_number != null && it.max_supply != null)
      ? ' <span title="Exemplaire #' + _e(it.edition_number) + ' sur ' + _e(it.max_supply) + ' — édition limitée" style="display:inline-block;margin-left:4px;padding:1px 7px;border-radius:999px;background:rgba(124,77,255,.18);color:#cbb3ff;font-size:11px;font-weight:700;vertical-align:middle">#' + _e(it.edition_number) + '/' + _e(it.max_supply) + '</span>'
      : '';
    // C4 ④ — une revente d'IMAGE affiche une vignette d'aperçu + label image
    // (au lieu de la ligne audio). preview_r2_key est non gaté (aperçu public).
    const isImage = it.product_type === 'image';
    const thumb = (isImage && it.preview_r2_key)
      ? '<img src="' + _e(_apImgPreviewUrl(it.preview_r2_key)) + '" alt="" loading="lazy" style="width:42px;height:42px;object-fit:cover;border-radius:8px;border:1px solid rgba(255,255,255,.1);flex:0 0 auto">'
      : (isImage ? '<span style="width:42px;height:42px;display:inline-flex;align-items:center;justify-content:center;border-radius:8px;background:rgba(124,77,255,.12);flex:0 0 auto">🖼</span>' : '');
    const natureLbl = isImage ? '<span style="display:inline-block;margin-right:6px;font-size:.7rem;color:#cbb3ff">🖼 Image</span>' : '';
    return '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:rgba(255,255,255,.02);margin-bottom:8px">' +
      '<div style="display:flex;align-items:center;gap:10px;min-width:0">' + thumb +
        '<div style="min-width:0"><div style="font-weight:700;color:#fff">' + natureLbl + _e(it.title) + editionBadge + '</div>' +
        '<div style="font-size:.78rem;margin-top:2px">' + author + '</div></div></div>' +
      '<div style="display:flex;align-items:center;gap:10px">' +
        '<div style="font-weight:700;color:#fff">' + Number(it.resale_price) + ' <span style="font-size:.72rem;color:#a09cb8">Smyles</span></div>' +
        '<button class="ap-resale-buy" data-up-id="' + _e(it.unlocked_prompt_id) + '" style="padding:8px 14px;border-radius:999px;background:rgba(124,58,237,.18);border:1px solid rgba(124,58,237,.5);color:#c4b5fd;font-size:.8rem;font-weight:700;cursor:pointer">Acheter</button>' +
      '</div></div>';
  }).join('');
  section.innerHTML =
    '<div style="margin-bottom:10px"><h2 class="ap-section-title" style="margin:0">♻️ Revente</h2>' +
    '<span style="font-size:.8rem;color:#a09cb8">Exemplaires remis en vente — le créateur d\'origine touche une royaltie</span></div>' + rows;
  section.querySelectorAll('.ap-resale-buy').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true; const orig = btn.textContent; btn.textContent = 'Achat…';
      try {
        await apiFetch('/resale/' + encodeURIComponent(btn.dataset.upId) + '/buy', { method: 'POST' });
        if (window.showToast) window.showToast('Acheté en revente 🔓 — dans ta bibliothèque');
        loadArtistResale(state.artist && state.artist.id);
      } catch (e) {
        btn.disabled = false; btn.textContent = orig;
        const st = e && e.status;
        const msg = st === 401 ? 'Connecte-toi pour acheter.' : st === 402 ? 'Crédits insuffisants.' : st === 409 ? 'Tu possèdes déjà cette recette.' : 'Erreur lors de l’achat.';
        if (window.showToast) window.showToast(msg);
      }
    });
  });
}

// ── C4 ③ — Section visuelle du profil (images IA) ────────────────────────────
// Miroir des rows audio C3 : une section de plus dans la MÊME page, pas de
// double interface. Grille de cards-aperçu alimentée par
// GET /watt/users/{slug}/images. Aperçu public ; recette/original gatés à
// l'achat (jamais exposés ici — payload ImagePublicRead). Clic → drawer C2.
async function loadArtistImages(slug) {
  if (!slug || typeof apiFetch !== 'function') return;
  let images = [];
  try {
    const data = await apiFetch('/watt/users/' + encodeURIComponent(slug) + '/images', { auth: false });
    images = (data && Array.isArray(data.images)) ? data.images : [];
  } catch (e) {
    console.warn('[artiste.js] loadArtistImages', e);
    images = [];
  }
  await _ensureOwnedImageIds();
  renderArtistImages(images);
}

// C4 ④ — IDs d'images POSSÉDÉES par l'user courant (miroir de ownedAdnIds).
// Mise en cache sur state ; utilisé pour afficher « ✓ À toi » + download au
// lieu de « Acheter » sur les cards image du profil et de /images.
async function _ensureOwnedImageIds() {
  if (state.ownedImageIds !== undefined) return;
  if (typeof getAuthToken === 'function' && !getAuthToken()) {
    state.ownedImageIds = [];
    return;
  }
  try {
    const resp = await apiFetch('/me/library/prompts?per_page=100');
    const items = (resp && Array.isArray(resp.items)) ? resp.items : [];
    state.ownedImageIds = items
      .filter(it => it.product_type === 'image')
      .map(it => String(it.prompt_id));
  } catch (_) {
    state.ownedImageIds = []; // dégrade proprement (pas de blocage)
  }
}

function _apImgEsc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function _apImgPreviewUrl(key) {
  if (!key) return '';
  return '/watt/images/' + String(key).split('/').map(encodeURIComponent).join('/');
}

function renderArtistImages(images) {
  const isSelf = !!(state.artist && state.artist.isSelf);
  let section = document.getElementById('ap-images-section');
  if (!section) {
    section = document.createElement('section');
    section.id = 'ap-images-section';
    section.className = 'ap-section ap-images';
    section.style.cssText = 'max-width:760px;margin:0 auto;padding:18px 20px';
    // Placée juste après les voix (ou rattachée au profil) — cohérent C3.
    const anchor = document.getElementById('ap-voices-section') || document.getElementById('ap-profile');
    if (anchor && anchor.id === 'ap-profile') anchor.appendChild(section);
    else if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(section, anchor.nextSibling);
    else document.body.appendChild(section);
  }

  if (!images.length) {
    // État vide soigné : owner = invitation à publier ; visiteur = section masquée.
    if (isSelf) {
      section.style.display = '';
      section.innerHTML =
        '<div style="margin-bottom:10px"><h2 class="ap-section-title" style="margin:0">🖼️ Images IA</h2></div>' +
        '<div style="text-align:center;padding:24px 16px;border:1px dashed rgba(255,255,255,.13);border-radius:14px;background:rgba(255,255,255,.02);color:#a09cb8;font-size:.86rem">' +
          'Tu n\'as pas encore publié d\'image. Crée-en une depuis ton <a href="/dashboard#sec-image-create" style="color:#c4b5fd">WATT BOARD (monde Visuel)</a>.' +
        '</div>';
    } else {
      section.style.display = 'none';
    }
    return;
  }

  section.style.display = '';
  const B = window.SpBadges;
  const ownedSet = new Set((state.ownedImageIds || []).map(String));
  const cards = images.map(im => {
    const url = _apImgPreviewUrl(im.previewKey);
    const cover = url
      ? '<img src="' + _apImgEsc(url) + '" alt="' + _apImgEsc(im.title || 'Image') + '" loading="lazy" style="width:100%;height:100%;object-fit:cover;display:block" />'
      : '<div style="font-size:2.2rem;opacity:.5;display:flex;align-items:center;justify-content:center;width:100%;height:100%">🖼️</div>';
    const nature = B ? B.nature('image') : '';
    const prov   = B ? B.provenance(im.imagePlatform, im.imageModelVersion) : '';
    // C4 Œuvre complète — badge si l'image est liée à un son.
    const oeuvre = (im.isOeuvreComplete && B && B.oeuvre) ? B.oeuvre() : '';
    let rar = '';
    if (B && im.maxSupply != null) {
      const sold = im.soldCount || 0;
      rar = im.isSoldOut
        ? B.rarete(im.maxSupply, im.maxSupply)
        : B.rarete(sold + 1, im.maxSupply, im.maxSupply === 1 ? 'legendaire' : '');
    }
    // C4 ④ #3 — état possession / auteur : on n'affiche « Acheter » que si
    // l'user ne possède PAS l'image et n'en est PAS l'auteur.
    const owned = ownedSet.has(String(im.id));
    const mine  = isSelf; // toutes les images de cette page appartiennent à l'artiste affiché
    let priceOrState;
    if (mine) {
      priceOrState = '<div style="font-size:.78rem;color:#8b7bd8;font-weight:700">À toi (créateur)</div>';
    } else if (owned) {
      priceOrState = '<div style="font-size:.82rem;color:#4ADE80;font-weight:700">✓ À toi</div>';
    } else {
      priceOrState = '<div style="font-size:.84rem;color:#cbb3ff;font-weight:700">' + _apImgEsc(im.priceCredits) + ' <span style="font-size:.7rem;color:#8b7bd8;font-weight:600">Smyles</span></div>';
    }
    // C4 ④ #4 — bouton ❤️ wishlist (pas d'ajout playlist : non pertinent pour
    // une image). data-img-like-btn = UUID du prompt image.
    const likeBtn = '<button type="button" class="like-btn ap-img-like" data-img-like-btn="' + _apImgEsc(im.id) + '" title="Wishlist" aria-label="Ajouter à ma Wishlist" onclick="event.stopPropagation()"></button>';
    const clickable = (mine || owned) ? '' : 'cursor:pointer;';
    return '' +
      '<article class="ap-img-card" data-image-id="' + _apImgEsc(im.id) + '" ' +
        'data-price="' + _apImgEsc(im.priceCredits != null ? im.priceCredits : '') + '" ' +
        'data-title="' + _apImgEsc(im.title || '') + '" ' +
        'data-platform="' + _apImgEsc(im.imagePlatform || '') + '" ' +
        'data-linked-sound="' + (im.linkedSound ? _apImgEsc(JSON.stringify(im.linkedSound)) : '') + '" ' +
        'data-owned="' + (owned || mine ? '1' : '0') + '" ' +
        'tabindex="0" role="button" title="' + ((mine || owned) ? 'Image possédée' : 'Voir la fiche') + '" ' +
        'style="border:1px solid rgba(255,255,255,.09);border-radius:14px;overflow:hidden;background:rgba(255,255,255,.025);' + clickable + 'display:flex;flex-direction:column">' +
        '<div style="position:relative;aspect-ratio:1/1;background:rgba(124,58,237,.10);overflow:hidden">' + cover +
          (mine ? '<button type="button" class="ap-img-del" data-del-image-id="' + _apImgEsc(im.id) + '" title="Supprimer cette image de mon profil" aria-label="Supprimer" style="position:absolute;top:8px;right:8px;width:30px;height:30px;border-radius:8px;border:1px solid rgba(255,255,255,.18);background:rgba(10,8,14,.72);color:#ff6b6b;font-size:14px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)">🗑</button>' : '') +
        '</div>' +
        '<div style="padding:10px 12px 12px;display:flex;flex-direction:column;gap:6px">' +
          '<div style="font-weight:700;color:#f3f0ff;font-size:.92rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + _apImgEsc(im.title || 'Sans titre') + '</div>' +
          '<div style="display:flex;flex-wrap:wrap;gap:5px;align-items:center">' + nature + rar + prov + oeuvre + '</div>' +
          '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px">' + priceOrState + likeBtn + '</div>' +
        '</div>' +
      '</article>';
  }).join('');

  section.innerHTML =
    '<div style="margin-bottom:10px"><h2 class="ap-section-title" style="margin:0">🖼️ Images IA</h2>' +
      '<span style="font-size:.8rem;color:#a09cb8">L\'aperçu est public — l\'achat débloque la recette + l\'image originale</span></div>' +
    '<div class="ap-img-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:14px">' + cards + '</div>';

  // Hydrate l'état liked (cœur plein) via le système wishlist partagé.
  if (window.SmylePlaylists && typeof window.SmylePlaylists.hydrateImgLikes === 'function') {
    window.SmylePlaylists.hydrateImgLikes();
  }

  // Clic carte → drawer d'achat unifié (recette gatée). On NE rouvre PAS le
  // drawer d'achat pour une image déjà possédée / dont on est l'auteur.
  section.querySelectorAll('.ap-img-card').forEach(card => {
    card.addEventListener('click', () => {
      if (card.dataset.owned === '1') return; // possédé / auteur → état neutre
      const id = card.dataset.imageId;
      if (id && window.PurchaseDrawer) {
        // C4 Œuvre complète — son lié (depuis data-linked-sound).
        let linkedSound = null;
        try {
          if (card.dataset.linkedSound) linkedSound = JSON.parse(card.dataset.linkedSound);
        } catch (_) {}
        window.PurchaseDrawer.open({
          type: 'image',
          id: id,
          price: parseInt(card.dataset.price, 10) || null,
          title: card.dataset.title || 'Image IA',
          platform: card.dataset.platform || '',
          linkedSound: linkedSound,
        });
      }
    });
  });

  // Owner — bouton Supprimer sur chaque carte (soft-delete ; les acheteurs
  // conservent leur accès en bibliothèque). stopPropagation pour ne pas
  // déclencher l'ouverture du drawer.
  section.querySelectorAll('.ap-img-del').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const id = btn.dataset.delImageId;
      if (!id) return;
      if (!confirm('Supprimer cette image de ton profil ?\nLes acheteurs gardent leur accès dans leur bibliothèque.')) return;
      btn.disabled = true;
      try {
        await apiFetch('/artist/me/images/' + encodeURIComponent(id), { method: 'DELETE', raw: true });
        if (typeof showToast === 'function') showToast('Image supprimée');
        loadArtistImages(state.artist.slug);   // refresh la grille
      } catch (err) {
        btn.disabled = false;
        if (typeof showToast === 'function') showToast('Suppression impossible. Réessaie.');
      }
    });
  });
}

// C3 ② — VOICE_LICENSE_LBL supprimé : le vocabulaire « licence » a disparu
// des capsules publiques (remplacé par la rareté #X/N). Le drawer garde son
// propre LICENSE_LBL local (openBoutiqueDrawer).

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

  // C3 ② — CAPSULES VOCALES : cards horizontales couleur nature voix
  // (orange C0, --sp-nature-voix), lecteur de preview ROND, rareté #X/N
  // via tokens. Impossible à confondre avec les rows de tracks.
  // Règle stricte (voix séparées du flux musical) : preview 30s public,
  // JAMAIS le full — sample_url n'arrive que pour owner/unlocked (router).
  list.innerHTML = '';
  voices.forEach(v => {
    const card = document.createElement('article');
    card.className = 'ap-voice-capsule';
    card.dataset.voiceId = v.id;
    const safeName  = (v.name  || '').replace(/</g, '&lt;');
    const safeStyle = (v.style || '').replace(/</g, '&lt;');
    const priceStr  = formatCount(v.price_credits);

    // Rareté #X/N — le payload public expose max_supply + editions_sold
    // (audit watt-api routers/voices.py + services/voices.py 2026-06-12).
    // Prochain exemplaire minté = editions_sold + 1. 1/1 = légendaire.
    const _vSold   = v.editions_sold || 0;
    const _vSupply = (v.max_supply != null) ? v.max_supply : null;
    let rareteBadge  = '';
    let soldOutBadge = '';
    if (_vSupply != null && window.SpBadges) {
      if (_vSold >= _vSupply) {
        rareteBadge  = SpBadges.rarete(_vSupply, _vSupply);
        soldOutBadge = '<span class="ap-voice-soldout">Épuisée</span>';
      } else {
        rareteBadge = SpBadges.rarete(_vSold + 1, _vSupply, _vSupply === 1 ? 'legendaire' : '');
      }
    }

    const natureBadge = window.SpBadges ? SpBadges.nature('voix') : '';
    const genresStr = _voiceGenresStr(v.genres);
    const genresChip = genresStr
      ? `<span class="ap-voice-chip">${genresStr.replace(/</g, '&lt;')}</span>`
      : '';
    // Origine déclarée (Phase B metadata 2026-05-13)
    const _originLabel = (function(o) {
      if (o === 'personal') return '🎙️ Voix personnelle';
      if (o === 'ai') return '🤖 Créée par IA';
      if (o === 'known_artist') return '🌟 Voix d\'artiste connu';
      return '';
    })(v.voice_origin);
    const originChip = _originLabel
      ? `<span class="ap-voice-chip">${_originLabel}</span>`
      : '';

    // Preview : owner/unlocked = sample_url (full), visiteur = preview_url
    // (30s), legacy sans preview = bouton verrouillé. Audio CACHÉ piloté
    // par le bouton rond (un seul lecteur visible : le bouton).
    const audioSrc  = v.sample_url || v.preview_url || null;
    const isPreview = !v.sample_url && !!v.preview_url;
    const playBlock = audioSrc
      ? `<button type="button" class="ap-voice-play" aria-label="Pré-écoute"
                 title="${isPreview ? 'Pré-écoute 30s' : 'Écouter'}">${_AP_PLAY_SVG}</button>
         <audio class="ap-voice-audio" preload="none" hidden
                src="${(audioSrc + '').replace(/"/g, '&quot;')}"></audio>`
      : `<button type="button" class="ap-voice-play" disabled
                 title="Pré-écoute après achat">🔒</button>`;
    const previewTag = isPreview
      ? '<span class="ap-voice-chip ap-voice-chip-30s">🎧 30s</span>'
      : '';

    // Pas de bouton unlock pour l'owner (évite l'auto-achat 400).
    const unlockBtn = artist.isSelf
      ? '<span class="ap-voice-owner-note">Ta voix</span>'
      : `<button type="button" class="ap-voice-unlock-btn"
                 data-voice-id="${v.id}" data-price="${v.price_credits}">
          🎙 ${priceStr} crédits
        </button>`;

    _voiceDetailCache[v.id] = {
      id:           v.id,
      name:         v.name || '',
      style:        v.style || '',
      priceCredits: v.price_credits || v.priceCredits || 0,
      license:      v.license || '',
      genres:       v.genres || [],
      previewUrl:   v.preview_url || v.previewUrl || '',
    };

    // data-track-name : la mini-bar globale affiche le nom de la voix
    // pendant la pré-écoute (pas de data-track-id : une voix n'est pas
    // likable/playlistable — règle de séparation voix/flux musical).
    card.dataset.trackName = (v.name || 'Voix') + ' · pré-écoute';
    card.innerHTML = `
      ${playBlock}
      <div class="ap-voice-main">
        <div class="ap-voice-top">
          <h3 class="ap-voice-name">${safeName}</h3>
          ${rareteBadge}${soldOutBadge}
        </div>
        ${safeStyle ? `<p class="ap-voice-style">${safeStyle}</p>` : ''}
        <div class="ap-voice-badges">
          ${natureBadge}${originChip}${genresChip}${previewTag}
        </div>
      </div>
      <div class="ap-voice-side">${unlockBtn}</div>
    `;
    list.appendChild(card);
  });

  // États play/pause des capsules — une seule voix joue à la fois, et la
  // pré-écoute coupe le player de tracks partagé (jamais l'inverse en
  // shuffle : les voix restent hors du flux musical).
  list.querySelectorAll('.ap-voice-audio').forEach(a => {
    a.addEventListener('play', () => {
      list.querySelectorAll('.ap-voice-audio').forEach(o => {
        if (o !== a && !o.paused) { try { o.pause(); } catch (_) {} }
      });
      if (_apAudio && !_apAudio.paused) { try { _apAudio.pause(); } catch (_) {} }
      const cap = a.closest('.ap-voice-capsule');
      if (cap) {
        cap.classList.add('is-playing');
        const btn = cap.querySelector('.ap-voice-play');
        if (btn) btn.innerHTML = _AP_PAUSE_SVG;
      }
    });
    const onStop = () => {
      const cap = a.closest('.ap-voice-capsule');
      if (cap) {
        cap.classList.remove('is-playing');
        const btn = cap.querySelector('.ap-voice-play');
        if (btn) btn.innerHTML = _AP_PLAY_SVG;
      }
    };
    a.addEventListener('pause', onStop);
    a.addEventListener('ended', onStop);
  });

  // ── Accordéon : 4 voix visibles par défaut ──────────────────────────────
  const VOICES_FOLD = 4;
  const _prevVT = list.nextElementSibling;
  if (_prevVT && _prevVT.classList && _prevVT.classList.contains('ap-accordion-toggle')) _prevVT.remove();
  if (voices.length > VOICES_FOLD) {
    const allVC = list.querySelectorAll('.ap-voice-capsule');
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
  // Bouton rond = play/pause preview · bouton prix = unlock (flux existant)
  // · clic capsule = fiche détail (drawer).
  list.onclick = (ev) => {
    const playBtn = ev.target.closest('.ap-voice-play');
    if (playBtn) {
      ev.stopPropagation();
      const cap = playBtn.closest('.ap-voice-capsule');
      const audio = cap && cap.querySelector('.ap-voice-audio');
      if (!audio) return;
      if (audio.paused) _apSafePlay(audio);
      else audio.pause();
      return;
    }
    const btn = ev.target.closest('.ap-voice-unlock-btn');
    if (btn) {
      const id = btn.dataset.voiceId;
      if (id) unlockVoiceFromProfile(id, btn);
      return;
    }
    const cap = ev.target.closest('.ap-voice-capsule');
    if (cap && cap.dataset.voiceId) openVoiceDetailById(cap.dataset.voiceId);
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
  window.unlockVisualDnaFromProfile = unlockVisualDnaFromProfile;
  window.unlockPromptFromProfile = unlockPromptFromProfile;
}
