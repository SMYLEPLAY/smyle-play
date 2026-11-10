/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/refonte/accueil.js · refonte, lot 3 (accueil).

   Chargé par le serveur UNIQUEMENT quand l'interrupteur `refonte` est ouvert
   et que la page contient la vitrine (#smyle-vitrine). Ne renomme et ne
   supprime rien : il déplace le bloc du haut et change son contenu.

     1. Le bloc d'identité (la vitrine) remonte juste sous le titre WATT,
        sur une couverture animée.
     2. Règle du bloc : par défaut c'est SMYLE. Si la personne est connectée
        ET que son profil est en ligne, son propre profil prend la place
        (« Poster un son » / « Voir ma page »). Sinon SMYLE reste.
     3. Connecté : la ligne de réassurance disparaît (classe rf-connecte).
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (!(window.WATT_LAUNCH && window.WATT_LAUNCH.refonte)) return;

  var ids = {
    racine: 'smyle-vitrine', avatar: 'smyle-vitrine-avatar', nom: 'smyle-vitrine-name',
    bio: 'smyle-vitrine-bio', abonnes: 'smyle-vitrine-followers',
    sons: 'smyle-vitrine-tracks', ecoutes: 'smyle-vitrine-plays', lien: 'smyle-vitrine-link',
  };
  var el = {};
  var moi = null;        // profil de la personne connectée, s'il est en ligne
  var smyle = null;      // contenu SMYLE mémorisé avant remplacement
  var enCours = false;   // évite de réagir à nos propres écritures

  function $(id) { return document.getElementById(id); }
  function fmt(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.0', '') + ' M';
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace('.0', '') + ' k';
    return String(n);
  }
  function utilisateur() {
    try { return (typeof getCurrentUser === 'function') ? getCurrentUser() : null; } catch (_) { return null; }
  }
  function connecte() {
    try { return !!localStorage.getItem('smyle_api_token'); } catch (_) { return false; }
  }

  function installer() {
    Object.keys(ids).forEach(function (k) { el[k] = $(ids[k]); });
    if (!el.racine) return false;
    el.racine.classList.add('rf-bloc');

    // Couverture animée, derrière le contenu.
    if (!el.racine.querySelector('.rf-bloc-couverture')) {
      var c = document.createElement('div');
      c.className = 'rf-bloc-couverture';
      c.setAttribute('aria-hidden', 'true');
      el.racine.insertBefore(c, el.racine.firstChild);
      el.couverture = c;
    }
    // Deuxième bouton (« Poster un son »), montré seulement pour son profil.
    if (el.lien && !$('rf-bloc-poster')) {
      var b = document.createElement('a');
      b.id = 'rf-bloc-poster';
      b.className = 'rf-bloc-poster';
      b.href = '/dashboard';
      b.textContent = 'Poster un son';
      b.hidden = true;
      var groupe = document.createElement('div');
      groupe.className = 'rf-bloc-actions';
      el.lien.parentNode.insertBefore(groupe, el.lien);
      groupe.appendChild(b);
      groupe.appendChild(el.lien);
      el.poster = b;
    }
    // Le bloc remonte juste sous le titre WATT (après le hero).
    var hero = document.querySelector('.mp-hero');
    if (hero && hero.parentNode && hero.nextElementSibling !== el.racine) {
      hero.parentNode.insertBefore(el.racine, hero.nextSibling);
    }
    return true;
  }

  function memoriserSmyle() {
    if (smyle || !el.nom) return;
    if (moi && el.nom.textContent === moi.artistName) return;
    smyle = {
      avatar: el.avatar ? el.avatar.innerHTML : '',
      nom: el.nom.textContent,
      bio: el.bio ? el.bio.textContent : '',
      abonnes: el.abonnes ? el.abonnes.textContent : '',
      sons: el.sons ? el.sons.textContent : '',
      ecoutes: el.ecoutes ? el.ecoutes.textContent : '',
      href: el.lien ? el.lien.getAttribute('href') : '/@smyle',
      texte: el.lien ? el.lien.textContent : '',
      marque: el.racine.style.getPropertyValue('--smyle-brand'),
    };
  }

  function couverture(url) {
    if (!el.couverture) return;
    el.couverture.style.backgroundImage = url ? 'url("' + String(url).replace(/"/g, '%22') + '")' : '';
    el.couverture.classList.toggle('rf-avec-image', !!url);
  }

  function afficherMoi() {
    if (!moi || !el.nom) return;
    enCours = true;
    el.racine.classList.add('rf-bloc-moi');
    el.racine.style.display = '';
    if (moi.brandColor) el.racine.style.setProperty('--smyle-brand', moi.brandColor);
    if (el.avatar) {
      el.avatar.textContent = '';
      if (moi.avatarUrl) {
        var img = document.createElement('img');
        img.src = moi.avatarUrl; img.alt = moi.artistName || '';
        el.avatar.appendChild(img);
      } else {
        el.avatar.textContent = (moi.artistName || '?').trim().charAt(0).toUpperCase();
      }
    }
    el.nom.textContent = moi.artistName || '';
    if (el.bio) el.bio.textContent = moi.bio || '';
    if (el.abonnes) el.abonnes.textContent = fmt(moi.followersCount);
    if (el.sons) el.sons.textContent = fmt(moi.trackCount);
    if (el.ecoutes) el.ecoutes.textContent = fmt(moi.plays);
    if (el.lien) { el.lien.href = '/@' + moi.slug; el.lien.textContent = 'Voir ma page →'; }
    if (el.poster) el.poster.hidden = false;
    couverture(moi.coverPhotoUrl);
    enCours = false;
  }

  function afficherSmyle() {
    el.racine.classList.remove('rf-bloc-moi');
    if (el.poster) el.poster.hidden = true;
    couverture('');
    if (!smyle) return;
    enCours = true;
    if (el.avatar) el.avatar.innerHTML = smyle.avatar;
    el.nom.textContent = smyle.nom;
    if (el.bio) el.bio.textContent = smyle.bio;
    if (el.abonnes) el.abonnes.textContent = smyle.abonnes;
    if (el.sons) el.sons.textContent = smyle.sons;
    if (el.ecoutes) el.ecoutes.textContent = smyle.ecoutes;
    if (el.lien) { el.lien.href = smyle.href; el.lien.textContent = smyle.texte; }
    if (smyle.marque) el.racine.style.setProperty('--smyle-brand', smyle.marque);
    enCours = false;
  }

  function appliquer() {
    document.body.classList.toggle('rf-connecte', connecte());
    var u = connecte() ? utilisateur() : null;
    // Le cache du membre ne dit pas si le profil est en ligne : c'est la
    // fiche publique de l'artiste (profilePublic) qui fait foi, plus bas.
    if (!u || !u.slug || !u.artist_name) {
      moi = null; afficherSmyle(); return;
    }
    var slug = u.slug;
    var appel = (typeof apiFetch === 'function')
      ? apiFetch('/watt/artists/' + encodeURIComponent(slug))
      : fetch('/watt/artists/' + encodeURIComponent(slug)).then(function (r) { return r.ok ? r.json() : null; });
    Promise.resolve(appel).then(function (data) {
      var a = data && data.artist ? data.artist : data;
      if (!a || !a.profilePublic || a.isOfficial) { moi = null; afficherSmyle(); return; }
      memoriserSmyle();
      moi = a;
      afficherMoi();
    }).catch(function () { moi = null; afficherSmyle(); });
  }

  function demarrer() {
    if (!installer()) return;
    memoriserSmyle();
    // marketplace.js réécrit la vitrine avec SMYLE quand ses données
    // arrivent : on mémorise sa version, puis on remet le bon profil.
    if (el.nom && window.MutationObserver) {
      new MutationObserver(function () {
        if (enCours) return;
        if (moi && el.nom.textContent !== moi.artistName) { smyle = null; memoriserSmyle(); afficherMoi(); }
        else if (!moi) { smyle = null; memoriserSmyle(); }
      }).observe(el.racine, { childList: true, subtree: true, characterData: true });
    }
    appliquer();
    if (window.SmyleEvents && window.SmyleEvents.on) {
      window.SmyleEvents.on('smyle:auth-changed', function () { setTimeout(appliquer, 0); });
      window.SmyleEvents.on('smyle:profile-published', function () { setTimeout(appliquer, 0); });
    }
    // Le cache du membre peut arriver après le chargement (GET /users/me).
    setTimeout(appliquer, 1500);
    setTimeout(appliquer, 4000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', demarrer);
  else demarrer();
})();
