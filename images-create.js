/* ─────────────────────────────────────────────────────────────────────────
   WATT — images-create.js
   Chantier C4 (Monde Visuel V1) — livraison ② : FRONT de création d'image.

   Pilote l'écran #sec-image-create (ouvert par le WattBoard via la tuile
   « Images IA » ou le menu « + Créer » du monde Visuel). Mirroir du flux
   audio : champs tronc commun + champs spécifiques par plateforme assemblés
   dans `image_settings` (JSON), upload multipart vers POST /artist/me/images.

   AUCUN backend touché : l'endpoint existe (livraison ①). On réutilise le
   helper d'auth global apiFetch (api.js) — qui pose le Bearer JWT et, comme
   le body est un FormData, NE force PAS de Content-Type (boundary auto).

   Dépendances globales : apiFetch (ui/core/api.js) · dashToast /
   _humanizeApiError (dashboard.js) · WattBoardV3.bumpImages (wattboard-v3.js).
   ───────────────────────────────────────────────────────────────────────── */

(function initImageCreate() {
  'use strict';
  if (typeof window === 'undefined') return;

  /* Valeurs enum backend (app/schemas/image.py → ImagePlatform). Toute autre
     valeur = 422. On garde cette liste pour valider AVANT l'envoi. */
  var PLATFORMS = ['midjourney', 'dalle', 'chatgpt', 'stable_diffusion', 'flux', 'autre'];

  var IMAGE_MAX_BYTES = 20 * 1024 * 1024;     /* 20 Mo (= IMAGE_MAX_BYTES API) */
  var ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
  var PRICE_MIN = 3, PRICE_MAX = 500;          /* PROMPT_PRICE_MIN/MAX */

  function $(id) { return document.getElementById(id); }
  function val(id) { var el = $(id); return el ? String(el.value || '').trim() : ''; }

  /* C4 — codes de tags d'usage actuellement sélectionnés (chips .is-on).
     Ordre = ordre du DOM. Optionnel : peut renvoyer []. */
  function selectedImageTags() {
    var box = $('imgcTags');
    if (!box) return [];
    var on = box.querySelectorAll('.imgc-tag-chip.is-on');
    return Array.prototype.map.call(on, function (b) {
      return b.getAttribute('data-img-tag');
    }).filter(Boolean);
  }

  /* C4 — l'usage « avatar » est-il actuellement sélectionné ? Conditionne
     l'affichage du bloc galerie et l'envoi de la galerie à la publication. */
  function avatarTagOn() {
    var box = $('imgcTags');
    if (!box) return false;
    var chip = box.querySelector('.imgc-tag-chip[data-img-tag="avatar"]');
    return !!(chip && chip.classList.contains('is-on'));
  }

  /* État local : le fichier choisi (pas encore envoyé). */
  var pendingFile = null;

  /* C4 galerie avatar — fichiers de galerie choisis (pas encore envoyés).
     Uploadés APRÈS la création de l'image, et UNIQUEMENT si le tag avatar
     est actif (bloc masqué sinon). 10 visuels = reco non bloquante. */
  var galleryFiles = [];

  /* C4 Œuvre complète — flag "sons chargés" pour le dropdown de liaison. */
  var soundsLoaded = false;

  /* ── Affichage dynamique des blocs selon la plateforme ────────────────── */
  function applyPlatform() {
    var sec = $('sec-image-create');
    if (!sec) return;
    var p = val('imgcPlatform');
    sec.setAttribute('data-img-platform', p);   /* le CSS montre le bon bloc */
  }

  /* ── Aperçu fichier local (FileReader) + garde-fous type/taille ───────── */
  function humanSize(bytes) {
    if (bytes < 1024) return bytes + ' o';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko';
    return (bytes / 1024 / 1024).toFixed(1) + ' Mo';
  }

  function clearPreview() {
    pendingFile = null;
    var img = $('imgcPreview'), ph = $('imgcPreviewPh'), info = $('imgcFileInfo');
    if (img) { img.hidden = true; img.removeAttribute('src'); }
    if (ph) ph.style.display = '';
    if (info) info.textContent = 'PNG, JPG ou WebP — 20 Mo max';
  }

  function handleFile(file) {
    var info = $('imgcFileInfo');
    if (!file) { clearPreview(); return; }

    var type = (file.type || '').toLowerCase();
    var name = (file.name || '').toLowerCase();
    var extOk = /\.(png|jpe?g|webp)$/.test(name);
    if (ALLOWED_TYPES.indexOf(type) === -1 && !extOk) {
      pendingFile = null;
      if (info) info.textContent = 'Format non supporté — utilise PNG, JPG ou WebP.';
      var im0 = $('imgcPreview'), ph0 = $('imgcPreviewPh');
      if (im0) { im0.hidden = true; im0.removeAttribute('src'); }
      if (ph0) ph0.style.display = '';
      return;
    }
    if (file.size > IMAGE_MAX_BYTES) {
      pendingFile = null;
      if (info) info.textContent = 'Trop lourd (' + humanSize(file.size) + ') — limite 20 Mo.';
      return;
    }

    pendingFile = file;
    if (info) info.textContent = file.name + ' · ' + humanSize(file.size);
    try {
      var reader = new FileReader();
      reader.onload = function (e) {
        var img = $('imgcPreview'), ph = $('imgcPreviewPh');
        if (img) { img.src = e.target.result; img.hidden = false; }
        if (ph) ph.style.display = 'none';
      };
      reader.readAsDataURL(file);
    } catch (_) { /* aperçu best-effort */ }
  }

  /* ── Assemblage des champs spécifiques → image_settings (objet) ───────── */
  function num(id) {
    var v = val(id);
    if (v === '') return undefined;
    var n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  }
  function str(id) { var v = val(id); return v === '' ? undefined : v; }
  function put(obj, key, v) { if (v !== undefined && v !== '') obj[key] = v; }

  function buildSettings(platform) {
    var s = {};
    if (platform === 'midjourney') {
      put(s, 'version', str('imgcMjVersion'));
      put(s, 'stylize', num('imgcMjStylize'));
      put(s, 'chaos', num('imgcMjChaos'));
      put(s, 'weird', num('imgcMjWeird'));
      put(s, 'seed', str('imgcMjSeed'));
      put(s, 'quality', str('imgcMjQuality'));
      var raw = $('imgcMjStyleRaw');
      if (raw && raw.checked) s.style_raw = true;
    } else if (platform === 'dalle') {
      put(s, 'model', str('imgcDalleModel'));
      put(s, 'quality', str('imgcDalleQuality'));
      put(s, 'style', str('imgcDalleStyle'));
      put(s, 'size', str('imgcDalleSize'));
    } else if (platform === 'flux') {
      put(s, 'variant', str('imgcFluxVariant'));
      put(s, 'guidance', num('imgcFluxGuidance'));
      put(s, 'steps', num('imgcFluxSteps'));
      put(s, 'seed', str('imgcFluxSeed'));
    } else if (platform === 'stable_diffusion') {
      put(s, 'checkpoint', str('imgcSdCheckpoint'));
      put(s, 'sampler', str('imgcSdSampler'));
      put(s, 'steps', num('imgcSdSteps'));
      put(s, 'cfg_scale', num('imgcSdCfg'));
      put(s, 'seed', str('imgcSdSeed'));
      put(s, 'resolution', str('imgcSdResolution'));
      put(s, 'loras', str('imgcSdLoras'));
      /* NB : le prompt négatif part dans son champ DÉDIÉ (negative_prompt),
         JAMAIS dans image_settings. */
    } else if (platform === 'autre') {
      put(s, 'version', str('imgcOtherVersion'));
      put(s, 'seed', str('imgcOtherSeed'));
    }
    /* Champ libre commun à toutes les plateformes. */
    put(s, 'extra', str('imgcExtraSettings'));
    return s;
  }

  /* ── Soumission ───────────────────────────────────────────────────────── */
  function setBusy(busy) {
    var btn = $('imgcSaveBtn'), lbl = $('imgcSaveLbl');
    if (btn) btn.disabled = busy;
    if (lbl) lbl.textContent = busy ? 'Envoi…' : "Enregistrer l'image";
  }

  function toast(msg) {
    if (typeof window.dashToast === 'function') window.dashToast(msg);
    else alert(msg);
  }

  function visibility() {
    var checked = document.querySelector('input[name="imgcVisibility"]:checked');
    return checked && checked.value === 'published';
  }

  function reset() {
    [
      'imgcTitle', 'imgcPlatform', 'imgcModelVersion', 'imgcPrompt', 'imgcRatio',
      'imgcDescription', 'imgcMjVersion', 'imgcMjStylize', 'imgcMjChaos',
      'imgcMjWeird', 'imgcMjSeed', 'imgcMjQuality', 'imgcDalleModel',
      'imgcDalleQuality', 'imgcDalleStyle', 'imgcDalleSize', 'imgcFluxVariant',
      'imgcFluxGuidance', 'imgcFluxSteps', 'imgcFluxSeed', 'imgcSdCheckpoint',
      'imgcSdSampler', 'imgcSdSteps', 'imgcSdCfg', 'imgcSdSeed',
      'imgcSdResolution', 'imgcSdLoras', 'imgcNegativePrompt', 'imgcOtherVersion',
      'imgcOtherSeed', 'imgcExtraSettings', 'imgcMaxSupply', 'imgcStyle'
    ].forEach(function (id) { var el = $(id); if (el) el.value = ''; });
    /* C4 — désélectionne tous les chips de tags d'usage. */
    var tagsBox = $('imgcTags');
    if (tagsBox) {
      tagsBox.querySelectorAll('.imgc-tag-chip.is-on').forEach(function (c) {
        c.classList.remove('is-on');
        c.setAttribute('aria-pressed', 'false');
      });
    }
    var price = $('imgcPrice'); if (price) price.value = '50';
    var raw = $('imgcMjStyleRaw'); if (raw) raw.checked = false;
    var draft = document.querySelector('input[name="imgcVisibility"][value="draft"]');
    if (draft) draft.checked = true;
    var fileEl = $('imgcFile'); if (fileEl) fileEl.value = '';
    /* C4 — remet le bloc liaison son à l'état initial. */
    var linkChk = $('imgcLinkSound'); if (linkChk) linkChk.checked = false;
    var linkWrap = $('imgcLinkSoundWrap'); if (linkWrap) linkWrap.hidden = true;
    var linkSel = $('imgcLinkSoundSelect'); if (linkSel) linkSel.value = '';
    /* C4 — vide les fichiers de galerie et masque le bloc (chips déjà reset). */
    resetGallery();
    clearPreview();
    applyPlatform();
  }

  /* ── C4 Œuvre complète — liaison à un son ─────────────────────────────── */
  function linkSoundEnabled() {
    var c = $('imgcLinkSound');
    return !!(c && c.checked);
  }

  function escHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* Peuple le dropdown avec MES sons NON ENCORE liés (recipe/beat,
     linked_prompt_id == null). Source : /artist/me/prompts (PromptRead). */
  function loadSounds() {
    var sel = $('imgcLinkSoundSelect');
    var help = $('imgcLinkSoundHelp');
    if (!sel || typeof window.apiFetch !== 'function') return;
    sel.disabled = true;
    window.apiFetch('/artist/me/prompts?per_page=100')
      .then(function (resp) {
        var items = (resp && resp.items) || [];
        var sounds = items.filter(function (p) {
          var t = p.product_type || 'recipe';
          return (t === 'recipe' || t === 'beat') && !p.linked_prompt_id;
        });
        /* garde la 1re option placeholder, repeuple le reste */
        sel.innerHTML = '<option value="">— Choisis un son non encore lié —</option>';
        sounds.forEach(function (p) {
          var o = document.createElement('option');
          o.value = p.id;
          o.textContent = p.title || '(sans titre)';
          sel.appendChild(o);
        });
        sel.disabled = false;
        soundsLoaded = true;
        if (help) {
          help.textContent = sounds.length
            ? 'Seuls tes sons pas encore liés sont proposés.'
            : "Aucun son liable (tu n'as pas de son, ou ils sont déjà tous liés).";
        }
      })
      .catch(function () {
        sel.disabled = false;
        if (help) help.textContent = 'Impossible de charger tes sons — réessaie.';
      });
  }

  function toggleLinkSound() {
    var wrap = $('imgcLinkSoundWrap');
    var on = linkSoundEnabled();
    if (wrap) wrap.hidden = !on;
    if (on && !soundsLoaded) loadSounds();
  }

  /* ── C4 galerie avatar — choix multi-fichiers + aperçus retirables ────── */
  /* Affiche/masque le bloc galerie selon l'état du chip « avatar ». */
  function toggleGalleryBlock() {
    var block = $('imgcGalleryBlock');
    if (!block) return;
    var on = avatarTagOn();
    block.hidden = !on;
    /* Si l'avatar est désélectionné, on oublie les fichiers déjà choisis :
       une image non-avatar n'a pas de galerie. */
    if (!on && galleryFiles.length) { galleryFiles = []; renderGalleryThumbs(); }
  }

  /* Ajoute les fichiers valides (type/taille) à galleryFiles, puis re-rend. */
  function addGalleryFiles(fileList) {
    if (!fileList || !fileList.length) return;
    Array.prototype.forEach.call(fileList, function (f) {
      var type = (f.type || '').toLowerCase();
      var name = (f.name || '').toLowerCase();
      var extOk = /\.(png|jpe?g|webp)$/.test(name);
      if (ALLOWED_TYPES.indexOf(type) === -1 && !extOk) return;
      if (f.size > IMAGE_MAX_BYTES) return;
      galleryFiles.push(f);
    });
    renderGalleryThumbs();
  }

  function removeGalleryFile(idx) {
    if (idx < 0 || idx >= galleryFiles.length) return;
    galleryFiles.splice(idx, 1);
    renderGalleryThumbs();
  }

  /* Rend les miniatures (FileReader) + bouton de retrait + compteur reco. */
  function renderGalleryThumbs() {
    var wrap = $('imgcGalleryThumbs');
    var count = $('imgcGalleryCount');
    if (count) {
      var n = galleryFiles.length;
      count.textContent = n
        ? (n + ' visuel' + (n > 1 ? 's' : '') + ' ajouté' + (n > 1 ? 's' : '') +
           (n < 10 ? ' · ' + (10 - n) + ' de plus recommandé' + (10 - n > 1 ? 's' : '') : ' · 👍'))
        : '';
    }
    if (!wrap) return;
    wrap.innerHTML = '';
    galleryFiles.forEach(function (f, idx) {
      var cell = document.createElement('div');
      cell.style.cssText = 'position:relative;width:64px;height:64px;border-radius:8px;overflow:hidden;border:1px solid rgba(255,255,255,.12);background:#1a1730';
      var img = document.createElement('img');
      img.alt = '';
      img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block';
      try {
        var r = new FileReader();
        r.onload = function (e) { img.src = e.target.result; };
        r.readAsDataURL(f);
      } catch (_) {}
      var rm = document.createElement('button');
      rm.type = 'button';
      rm.textContent = '✕';
      rm.title = 'Retirer';
      rm.style.cssText = 'position:absolute;top:2px;right:2px;width:18px;height:18px;line-height:16px;padding:0;border:none;border-radius:50%;background:rgba(0,0,0,.65);color:#fff;font-size:11px;cursor:pointer';
      rm.addEventListener('click', function () { removeGalleryFile(idx); });
      cell.appendChild(img);
      cell.appendChild(rm);
      wrap.appendChild(cell);
    });
  }

  function resetGallery() {
    galleryFiles = [];
    var fileEl = $('imgcGalleryFile'); if (fileEl) fileEl.value = '';
    renderGalleryThumbs();
    var block = $('imgcGalleryBlock'); if (block) block.hidden = true;
  }

  function submit() {
    /* Validation client (miroir des bornes Pydantic — évite des 422). */
    var errs = [];
    var title = val('imgcTitle');
    var platform = val('imgcPlatform');
    var modelVersion = val('imgcModelVersion');
    var prompt = val('imgcPrompt');
    var price = parseInt(val('imgcPrice'), 10);

    if (!title) errs.push('Titre');
    /* Provenance OBLIGATOIRE — plateforme + version. */
    if (!platform) errs.push('Plateforme');
    else if (PLATFORMS.indexOf(platform) === -1) errs.push('Plateforme (valeur invalide)');
    if (!modelVersion) errs.push('Version / modèle');
    if (!prompt) errs.push('Prompt');
    if (platform === 'stable_diffusion' && !val('imgcSdCheckpoint')) {
      errs.push('Modèle / checkpoint (Stable Diffusion)');
    }
    if (!pendingFile) errs.push('Fichier image');
    if (!Number.isInteger(price) || price < PRICE_MIN || price > PRICE_MAX) {
      errs.push('Prix (' + PRICE_MIN + '-' + PRICE_MAX + ')');
    }

    /* max_supply : entier >= 1 ou vide (illimité). */
    var supplyRaw = val('imgcMaxSupply');
    var maxSupply = null;
    if (supplyRaw !== '') {
      var ns = parseInt(supplyRaw, 10);
      if (Number.isInteger(ns) && ns >= 1) maxSupply = ns;
      else errs.push("Nombre d'exemplaires (entier >= 1, ou vide)");
    }

    /* C4 — si "lier à un son" est coché, un son doit être sélectionné. */
    var linkSoundId = null;
    if (linkSoundEnabled()) {
      linkSoundId = val('imgcLinkSoundSelect');
      if (!linkSoundId) errs.push('Son à lier (œuvre complète)');
    }

    if (errs.length) {
      alert('Champs manquants ou invalides :\n- ' + errs.join('\n- '));
      return;
    }

    if (typeof window.apiFetch !== 'function') {
      alert('API indisponible. Recharge la page.');
      return;
    }

    var settings = buildSettings(platform);
    var negative = val('imgcNegativePrompt');     /* champ DÉDIÉ */

    var fd = new FormData();
    fd.append('file', pendingFile);
    fd.append('title', title);
    fd.append('image_platform', platform);
    fd.append('image_model_version', modelVersion);
    fd.append('prompt_text', prompt);
    fd.append('price_credits', String(price));
    fd.append('is_published', visibility() ? 'true' : 'false');
    if (Object.keys(settings).length) fd.append('image_settings', JSON.stringify(settings));
    if (negative) fd.append('negative_prompt', negative);
    var desc = val('imgcDescription'); if (desc) fd.append('description', desc);
    var ratio = val('imgcRatio'); if (ratio) fd.append('ratio', ratio);
    if (maxSupply !== null) fd.append('max_supply', String(maxSupply));

    /* C4 — taxonomie visuelle : style (1 valeur) + tags d'usage (CSV).
       Optionnels ; codes alignés sur STYLES / USAGE_TAGS backend. */
    var imgStyle = val('imgcStyle');
    if (imgStyle) fd.append('image_style', imgStyle);
    var imgTags = selectedImageTags();
    if (imgTags.length) fd.append('image_tags', imgTags.join(','));

    setBusy(true);
    /* apiFetch ajoute le Bearer JWT ; body FormData => pas de Content-Type
       forcé (le navigateur pose le boundary multipart lui-même). */
    /* C4 galerie avatar — n'uploade la galerie QUE si le tag avatar est actif
       ET que des fichiers ont été choisis. Snapshot des fichiers au moment de
       l'envoi (reset() les videra ensuite). */
    var galleryToSend = (avatarTagOn() && galleryFiles.length)
      ? galleryFiles.slice() : [];

    window.apiFetch('/artist/me/images', { method: 'POST', body: fd })
      .then(function (created) {
        /* C4 galerie avatar — après création, pousse tous les visuels d'un coup
           (multipart, champ `files`). L'image existe déjà : si la galerie
           échoue, on informe sans bloquer (l'image reste créée). */
        var galleryStep = Promise.resolve();
        if (galleryToSend.length && created && created.id) {
          var gfd = new FormData();
          galleryToSend.forEach(function (f) { gfd.append('files', f); });
          galleryStep = window.apiFetch(
            '/artist/me/images/' + encodeURIComponent(created.id) + '/gallery',
            { method: 'POST', body: gfd }
          ).then(function () {
            toast('🖼 Galerie ajoutée — ' + galleryToSend.length + ' visuel' +
              (galleryToSend.length > 1 ? 's' : '') + ' livré' +
              (galleryToSend.length > 1 ? 's' : '') + ' à l\'achat.');
          }).catch(function (ge) {
            var gm = (typeof window._humanizeApiError === 'function')
              ? window._humanizeApiError(ge) : (ge && ge.message) || '';
            toast('Image créée, mais ajout de la galerie échoué' + (gm ? ' : ' + gm : '') + '. Tu pourras réessayer plus tard.');
          });
        }

        return galleryStep.then(function () { return created; });
      })
      .then(function (created) {
        /* C4 Œuvre complète — si demandé, lier l'image au son choisi. L'image
           est déjà créée : si la liaison échoue, on informe sans laisser
           d'état incohérent (l'image existe, juste non liée). */
        if (linkSoundId && created && created.id) {
          // Flux B « lié après coup » : on lie une NOUVELLE image à un son
          // qui PRÉEXISTAIT. On omet bundle_exclusive (défaut false) → les
          // deux produits restent visibles individuellement ET forment une
          // œuvre. (Le flux A « né ensemble » de dashboard.js passe
          // bundle_exclusive:true pour masquer les cartes individuelles.)
          return window.apiFetch(
            '/artist/me/prompts/' + encodeURIComponent(created.id) + '/link',
            { method: 'POST', json: { other_prompt_id: linkSoundId } }
          ).then(function () {
            toast('🎨 Œuvre complète créée — image liée à ton son.');
          }).catch(function (le) {
            var lm = (typeof window._humanizeApiError === 'function')
              ? window._humanizeApiError(le) : (le && le.message) || '';
            toast('Image créée, mais liaison au son échouée' + (lm ? ' : ' + lm : '') + '. Tu peux réessayer la liaison plus tard.');
          });
        }
        toast(visibility()
          ? 'Image publiée et en vente.'
          : 'Image enregistrée en brouillon — publie-la quand tu veux.');
      })
      .then(function () {
        reset();
        soundsLoaded = false;
        try {
          if (window.WattBoardV3 && typeof window.WattBoardV3.bumpImages === 'function') {
            window.WattBoardV3.bumpImages();
          }
        } catch (_) {}
      })
      .catch(function (e) {
        var msg = (typeof window._humanizeApiError === 'function')
          ? window._humanizeApiError(e)
          : (e && e.message) || 'Erreur inconnue';
        /* Messages lisibles sur les cas attendus. */
        if (e && e.status === 413) msg = 'Image trop lourde — limite 20 Mo.';
        else if (e && e.status === 400 && !msg) msg = 'Requête invalide.';
        alert("Échec de l'enregistrement : " + msg);
      })
      .finally(function () { setBusy(false); });
  }

  /* ── Câblage (idempotent : init peut courir après injection tardive) ──── */
  function wire() {
    var sec = $('sec-image-create');
    if (!sec || sec.dataset.imgcWired) return;
    sec.dataset.imgcWired = '1';

    var platSel = $('imgcPlatform');
    if (platSel) platSel.addEventListener('change', applyPlatform);

    var fileEl = $('imgcFile');
    if (fileEl) {
      fileEl.addEventListener('change', function (ev) {
        var f = ev.target.files && ev.target.files[0];
        handleFile(f);
      });
    }
    var linkChk = $('imgcLinkSound');
    if (linkChk) linkChk.addEventListener('change', toggleLinkSound);

    /* C4 — chips tags d'usage : toggle .is-on au clic (délégation). */
    var tagsBox = $('imgcTags');
    if (tagsBox) {
      tagsBox.addEventListener('click', function (ev) {
        var chip = ev.target.closest && ev.target.closest('.imgc-tag-chip');
        if (!chip || !tagsBox.contains(chip)) return;
        var on = chip.classList.toggle('is-on');
        chip.setAttribute('aria-pressed', on ? 'true' : 'false');
        /* C4 — le bloc galerie suit l'état du chip « avatar ». */
        if (chip.getAttribute('data-img-tag') === 'avatar') toggleGalleryBlock();
      });
    }

    /* C4 galerie avatar — input multi-fichiers (additif, garde l'historique). */
    var galFileEl = $('imgcGalleryFile');
    if (galFileEl) {
      galFileEl.addEventListener('change', function (ev) {
        addGalleryFiles(ev.target.files);
        ev.target.value = '';   /* permet de re-sélectionner les mêmes fichiers */
      });
    }

    var saveBtn = $('imgcSaveBtn');
    if (saveBtn) saveBtn.addEventListener('click', submit);
    var resetBtn = $('imgcResetBtn');
    if (resetBtn) resetBtn.addEventListener('click', reset);

    applyPlatform();
  }

  function init() { wire(); }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }

  /* C4 — pré-coche un chip de tag d'usage (réutilise le mécanisme .is-on).
     Le code passé doit correspondre à un data-img-tag existant (ex. 'avatar').
     La soumission lit déjà selectedImageTags() → le tag sera envoyé. */
  function preselectTag(code) {
    if (!code) return;
    var box = $('imgcTags');
    if (!box) return;
    var chip = box.querySelector('.imgc-tag-chip[data-img-tag="' + code + '"]');
    if (!chip || chip.classList.contains('is-on')) return;
    chip.classList.add('is-on');
    chip.setAttribute('aria-pressed', 'true');
    /* C4 — si on pré-coche « avatar », révèle le bloc galerie. */
    if (code === 'avatar') toggleGalleryBlock();
  }

  /* API publique : le WattBoard appelle focus() à l'ouverture de l'écran.
     focus(opts) accepte opts.tag pour pré-cocher un tag d'usage (ex. avatar). */
  window.ImageCreate = {
    focus: function (opts) {
      wire();
      if (opts && opts.tag) preselectTag(opts.tag);
      var t = $('imgcTitle');
      if (t) { try { t.focus(); } catch (_) {} }
    },
    preselectTag: preselectTag,
    reset: reset,
  };
})();
