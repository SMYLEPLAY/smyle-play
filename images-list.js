/* ─────────────────────────────────────────────────────────────────────────
   WATT — images-list.js
   C4 Monde Visuel V1 — livraison ③ (2026-06-15).

   Écran « Mes images » du WattBoard (tuile Images IA → bouton « Voir »).
   Grille de cards-aperçu OWNER : aperçu public + provenance + rareté #X/N +
   état (publié / brouillon). Alimenté par GET /artist/me/images (ImageOwnerRead).

   Règle stricte : l'aperçu (previewKey) est servi par le proxy public
   /watt/images/<key>. L'original n'est JAMAIS exposé ici — le téléchargement
   passe par GET /images/{id}/download (gaté possession).

   Édition / suppression (C4 ④) : chaque card owner expose « Éditer » (modale
   légère : titre, description, prix, toggle publié → PATCH /artist/me/images/{id})
   et « Supprimer » (confirm → DELETE soft-delete). Le compteur WattBoard est
   recâblé après chaque action.

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
      '.imgl-card-price span{font-size:.7rem;color:#8b7bd8;font-weight:600}' +
      '.imgl-card-actions{display:flex;gap:8px;margin-top:8px}' +
      '.imgl-act{flex:1;padding:7px 0;border-radius:8px;font-size:.76rem;font-weight:700;cursor:pointer;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#cbb3ff;transition:border-color .12s,background .12s}' +
      '.imgl-act:hover{border-color:rgba(124,58,237,.6);background:rgba(124,58,237,.12)}' +
      '.imgl-act.danger{color:#ff9aa8}' +
      '.imgl-act.danger:hover{border-color:rgba(255,85,119,.5);background:rgba(255,85,119,.1)}' +
      '.imgl-modal-ov{position:fixed;inset:0;z-index:9999;background:rgba(8,6,18,.72);display:flex;align-items:center;justify-content:center;padding:18px}' +
      '.imgl-modal{width:min(420px,96%);background:#16121f;border:1px solid rgba(124,58,237,.4);border-radius:16px;padding:20px;box-shadow:0 18px 48px rgba(0,0,0,.6)}' +
      '.imgl-modal h3{margin:0 0 14px;color:#f3f0ff;font-size:1.05rem}' +
      '.imgl-field{margin-bottom:12px;display:flex;flex-direction:column;gap:5px}' +
      '.imgl-field label{font-size:.76rem;color:#a09cb8;font-weight:600}' +
      '.imgl-field input[type=text],.imgl-field input[type=number],.imgl-field textarea{font-family:inherit;font-size:.86rem;color:#fff;background:rgba(255,255,255,.04);border:1px solid rgba(124,58,237,.4);border-radius:9px;padding:9px 11px;outline:none}' +
      '.imgl-field input:focus,.imgl-field textarea:focus{border-color:rgba(124,58,237,.9)}' +
      '.imgl-field textarea{resize:vertical;min-height:54px}' +
      '.imgl-toggle{display:flex;align-items:center;gap:9px;font-size:.84rem;color:#e6e1f5}' +
      '.imgl-modal-actions{display:flex;gap:10px;margin-top:16px}' +
      '.imgl-modal-actions button{flex:1;padding:10px 0;border-radius:9px;font-size:.84rem;font-weight:700;cursor:pointer;border:none}' +
      '.imgl-cancel{background:rgba(255,255,255,.07);color:#cbb3ff}' +
      '.imgl-save{background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff}' +
      '.imgl-save:disabled{opacity:.55;cursor:default}' +
      '.imgl-oeuvre-hint{display:block;font-size:.72rem;color:#a09cb8;margin-top:5px;line-height:1.4}' +
      '.imgl-oeuvre-link{padding:8px 14px;border-radius:9px;font-size:.8rem;font-weight:700;cursor:pointer;border:1px solid rgba(124,58,237,.45);background:rgba(124,58,237,.1);color:#cbb3ff}' +
      '.imgl-oeuvre-link:hover{background:rgba(124,58,237,.18)}' +
      '.imgl-oeuvre-link:disabled{opacity:.55;cursor:default}' +
      '.imgl-oeuvre-linked{display:flex;align-items:center;gap:9px;padding:8px 11px;border:1px solid rgba(124,58,237,.4);border-radius:10px;background:rgba(124,58,237,.08)}' +
      '.imgl-oeuvre-linked-title{flex:1;font-size:.82rem;font-weight:700;color:#cbb3ff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.imgl-oeuvre-unlink{padding:5px 12px;border-radius:8px;font-size:.74rem;font-weight:700;cursor:pointer;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#ff9aa8}' +
      '.imgl-oeuvre-unlink:hover{border-color:rgba(255,85,119,.5);background:rgba(255,85,119,.1)}' +
      '.imgl-oeuvre-unlink:disabled{opacity:.55;cursor:default}' +
      '.imgl-oeuvre-cands{display:flex;flex-direction:column;gap:6px;margin-top:8px;max-height:220px;overflow-y:auto}' +
      '.imgl-oeuvre-cand{display:flex;align-items:center;gap:10px;width:100%;padding:6px 10px;border:1px solid rgba(255,255,255,.12);border-radius:9px;background:rgba(255,255,255,.03);color:#e6e1f5;cursor:pointer;text-align:left;transition:border-color .12s,background .12s}' +
      '.imgl-oeuvre-cand:hover{border-color:rgba(124,58,237,.6);background:rgba(124,58,237,.12)}' +
      '.imgl-oeuvre-cand:disabled{opacity:.5;cursor:default}' +
      '.imgl-oeuvre-thumb{width:36px;height:36px;flex:0 0 36px;border-radius:7px;object-fit:cover;display:flex;align-items:center;justify-content:center;background:rgba(124,58,237,.12);font-size:1.05rem}' +
      '.imgl-oeuvre-thumb-ph{color:#8b7bd8}' +
      '.imgl-oeuvre-cand-title{flex:1;font-size:.82rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.imgl-oeuvre-cand-price{font-size:.74rem;color:#cbb3ff;font-weight:700;white-space:nowrap}';
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
          '<div class="imgl-card-actions">' +
            '<button type="button" class="imgl-act" data-imgl-edit="' + esc(img.id) + '">Éditer</button>' +
            '<button type="button" class="imgl-act danger" data-imgl-del="' + esc(img.id) + '">Supprimer</button>' +
          '</div>' +
        '</div>' +
      '</article>';
  }

  // Cache de la liste courante (normalisée) — alimente la modale d'édition.
  var _byId = {};

  function render(list) {
    var grid = document.getElementById('imgl-grid');
    if (!grid) return;
    _byId = {};
    (Array.isArray(list) ? list : []).forEach(function (im) { _byId[String(im.id)] = im; });
    if (!Array.isArray(list) || list.length === 0) {
      grid.innerHTML =
        '<div class="imgl-empty">Tu n\'as pas encore d\'image. Utilise « Créer » sur la tuile Images IA pour publier ton premier visuel.</div>';
      return;
    }
    grid.innerHTML = list.map(cardHtml).join('');
  }

  function toast(msg, type) {
    if (window.smyleToast) window.smyleToast(msg, { type: type || 'info' });
    else if (window.showToast) window.showToast(msg);
  }

  // Recâble le compteur de la tuile « Images IA » du WattBoard après action.
  // Source de vérité : WattBoardV3.refresh() (rappelle /artist/me/images/count).
  function refreshCount() {
    try {
      if (window.WattBoardV3 && typeof window.WattBoardV3.refresh === 'function') {
        window.WattBoardV3.refresh();
      }
    } catch (_) {}
  }

  // ── Modale d'édition légère (titre / description / prix / publié) ──────────
  function openEditModal(img) {
    if (!img) return;
    var ov = document.createElement('div');
    ov.className = 'imgl-modal-ov';
    ov.innerHTML =
      '<div class="imgl-modal" role="dialog" aria-modal="true">' +
        '<h3>Éditer l\'image</h3>' +
        '<div class="imgl-field"><label>Titre</label>' +
          '<input type="text" id="imgl-e-title" maxlength="120" value="' + esc(img.title || '') + '"></div>' +
        '<div class="imgl-field"><label>Description</label>' +
          '<textarea id="imgl-e-desc" maxlength="2000">' + esc(img.description || '') + '</textarea></div>' +
        '<div class="imgl-field"><label>Prix (Smyles · 3 à 500)</label>' +
          '<input type="number" id="imgl-e-price" min="3" max="500" value="' + esc(img.priceCredits != null ? img.priceCredits : '') + '"></div>' +
        '<label class="imgl-toggle"><input type="checkbox" id="imgl-e-pub"' + (img.isPublished ? ' checked' : '') + '> Publié (visible à la vente)</label>' +
        '<div class="imgl-field"><label>Galerie de l\'avatar <span style="font-weight:400;opacity:.7">(visuels livrés à l\'achat — 10 recommandés)</span></label>' +
          '<div id="imgl-e-gallery"></div>' +
          '<label class="imgl-btn-sec" style="cursor:pointer;display:inline-block;margin-top:6px">' +
            '<input type="file" id="imgl-e-gallery-file" accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" multiple style="display:none">' +
            'Ajouter des visuels' +
          '</label></div>' +
        '<div class="imgl-field"><label>Œuvre complète</label><div id="imgl-e-oeuvre"></div></div>' +
        '<div class="imgl-modal-actions">' +
          '<button type="button" class="imgl-cancel">Annuler</button>' +
          '<button type="button" class="imgl-save">Enregistrer</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(ov);

    // C4 « Œuvre complète » — rend le bloc lien/délien (pivot = img.id, le
    // prompt de l'image elle-même). Nature opposée → on lie à un SON.
    renderOeuvreComplete(ov.querySelector('#imgl-e-oeuvre'), img);

    // C4 galerie avatar — gestion add/remove des visuels supplémentaires via les
    // endpoints owner (GET pour lister, POST multipart pour ajouter, DELETE pour
    // retirer). Réservé aux avatars en UX, mais l'endpoint est générique.
    setupGalleryEditor(ov, img.id);

    function close() { if (ov.parentNode) ov.parentNode.removeChild(ov); }
    ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
    ov.querySelector('.imgl-cancel').addEventListener('click', close);

    ov.querySelector('.imgl-save').addEventListener('click', function () {
      var btn = ov.querySelector('.imgl-save');
      var title = ov.querySelector('#imgl-e-title').value.trim();
      var desc  = ov.querySelector('#imgl-e-desc').value;
      var price = parseInt(ov.querySelector('#imgl-e-price').value, 10);
      var pub   = ov.querySelector('#imgl-e-pub').checked;
      if (!title) { toast('Le titre est obligatoire.', 'error'); return; }
      if (!Number.isInteger(price) || price < 3 || price > 500) {
        toast('Le prix doit être entre 3 et 500 Smyles.', 'error'); return;
      }
      btn.disabled = true; btn.textContent = 'Enregistrement…';
      window.apiFetch('/artist/me/images/' + encodeURIComponent(img.id), {
        method: 'PATCH',
        json: { title: title, description: desc, price_credits: price, is_published: pub },
      })
        .then(function () {
          toast('Image mise à jour ✓', 'success');
          close();
          refresh();
          refreshCount();
        })
        .catch(function (e) {
          btn.disabled = false; btn.textContent = 'Enregistrer';
          toast((e && e.status === 422) ? 'Champs invalides.' : 'Échec de la mise à jour.', 'error');
        });
    });
  }

  function deleteImage(id) {
    if (!window.confirm('Supprimer cette image ? Les exemplaires déjà vendus restent dans la bibliothèque de leurs acheteurs.')) return;
    window.apiFetch('/artist/me/images/' + encodeURIComponent(id), { method: 'DELETE', raw: true })
      .then(function () {
        toast('Image supprimée ✓', 'success');
        refresh();
        refreshCount();
      })
      .catch(function () { toast('Échec de la suppression.', 'error'); });
  }

  // ── C4 galerie avatar — éditeur (lister / ajouter / retirer) ──────────────
  function setupGalleryEditor(ov, imageId) {
    var box = ov.querySelector('#imgl-e-gallery');
    var fileInput = ov.querySelector('#imgl-e-gallery-file');
    if (!box) return;

    function paint(items) {
      var n = items.length;
      var hint = n
        ? (n + ' visuel' + (n > 1 ? 's' : '') + (n < 10 ? ' · ' + (10 - n) + ' de plus recommandé' + (10 - n > 1 ? 's' : '') : ' · 👍'))
        : 'Aucun visuel pour l\'instant.';
      var thumbs = items.map(function (g) {
        var u = g.previewKey ? previewUrl(g.previewKey) : '';
        return '<div style="position:relative;width:60px;height:60px;border-radius:8px;overflow:hidden;border:1px solid rgba(255,255,255,.12);background:#1a1730">' +
          (u ? '<img src="' + esc(u) + '" alt="" style="width:100%;height:100%;object-fit:cover;display:block">' : '<span style="display:flex;width:100%;height:100%;align-items:center;justify-content:center">🖼</span>') +
          '<button type="button" class="imgl-gal-rm" data-gid="' + esc(g.id) + '" title="Retirer" ' +
          'style="position:absolute;top:2px;right:2px;width:18px;height:18px;line-height:16px;padding:0;border:none;border-radius:50%;background:rgba(0,0,0,.65);color:#fff;font-size:11px;cursor:pointer">✕</button>' +
          '</div>';
      }).join('');
      box.innerHTML = '<div class="imgl-help" style="font-size:11px;color:#a09cb8;margin-bottom:6px">' + esc(hint) + '</div>' +
        '<div style="display:flex;flex-wrap:wrap;gap:8px">' + thumbs + '</div>';
    }

    function load() {
      box.innerHTML = '<div class="imgl-help" style="font-size:11px;color:#a09cb8">Chargement…</div>';
      window.apiFetch('/artist/me/images/' + encodeURIComponent(imageId) + '/gallery')
        .then(function (r) { paint((r && r.gallery) || []); })
        .catch(function () { box.innerHTML = '<div class="imgl-help" style="font-size:11px;color:#a09cb8">Galerie indisponible.</div>'; });
    }

    box.addEventListener('click', function (e) {
      var rm = e.target.closest && e.target.closest('.imgl-gal-rm');
      if (!rm) return;
      var gid = rm.getAttribute('data-gid');
      rm.disabled = true;
      window.apiFetch('/artist/me/images/' + encodeURIComponent(imageId) + '/gallery/' + encodeURIComponent(gid), { method: 'DELETE', raw: true })
        .then(function () { load(); })
        .catch(function () { rm.disabled = false; toast('Échec du retrait.', 'error'); });
    });

    if (fileInput) {
      fileInput.addEventListener('change', function (ev) {
        var files = ev.target.files;
        if (!files || !files.length) return;
        var fd = new FormData();
        Array.prototype.forEach.call(files, function (f) { fd.append('files', f); });
        ev.target.value = '';
        box.innerHTML = '<div class="imgl-help" style="font-size:11px;color:#a09cb8">Envoi…</div>';
        window.apiFetch('/artist/me/images/' + encodeURIComponent(imageId) + '/gallery', { method: 'POST', body: fd })
          .then(function (r) { paint((r && r.gallery) || []); })
          .catch(function () { toast('Échec de l\'ajout.', 'error'); load(); });
      });
    }

    load();
  }

  // ── C4 « Œuvre complète » (lien rétroactif image <-> son) ────────────────
  // Construit l'URL same-origin de l'aperçu d'une image candidate (previewKey).
  function candThumb(c) {
    if (c.coverUrl) {
      return '<img src="' + esc(c.coverUrl) + '" alt="" class="imgl-oeuvre-thumb">';
    }
    if (c.previewKey) {
      return '<img src="' + esc(previewUrl(c.previewKey)) + '" alt="" class="imgl-oeuvre-thumb">';
    }
    return '<span class="imgl-oeuvre-thumb imgl-oeuvre-thumb-ph">🎵</span>';
  }

  // Rend le bloc : si l'image est liée → partenaire + Délier ; sinon →
  // « Lier à un son » + sélecteur de candidats (/linkable). POST link en
  // bundle_exclusive=false (rétroactif : les deux restent vendables séparément).
  function renderOeuvreComplete(box, img) {
    if (!box) return;
    if (img.isOeuvreComplete && img.linkedSound) {
      var s = img.linkedSound;
      box.innerHTML =
        '<div class="imgl-oeuvre-linked">' +
          candThumb({ coverUrl: s.coverUrl }) +
          '<span class="imgl-oeuvre-linked-title">🔗 ' + esc(s.title || 'Son lié') + '</span>' +
          '<button type="button" class="imgl-oeuvre-unlink">Délier</button>' +
        '</div>' +
        '<span class="imgl-oeuvre-hint">Les deux produits restent vendables séparément.</span>';
      box.querySelector('.imgl-oeuvre-unlink').addEventListener('click', function () {
        var b = box.querySelector('.imgl-oeuvre-unlink');
        b.disabled = true;
        window.apiFetch('/artist/me/prompts/' + encodeURIComponent(img.id) + '/link',
          { method: 'DELETE', raw: true })
          .then(function () {
            toast('Œuvre déliée ✓', 'success');
            img.isOeuvreComplete = false; img.linkedSound = null;
            renderOeuvreComplete(box, img);
          })
          .catch(function () { b.disabled = false; toast('Échec de la déliaison.', 'error'); });
      });
      return;
    }
    box.innerHTML =
      '<button type="button" class="imgl-oeuvre-link">🔗 Lier à un son</button>' +
      '<span class="imgl-oeuvre-hint">Réunis cette image avec un de tes sons en « Œuvre complète » (les deux restent vendables séparément).</span>' +
      '<div class="imgl-oeuvre-cands" style="display:none"></div>';
    var linkBtn = box.querySelector('.imgl-oeuvre-link');
    var cands   = box.querySelector('.imgl-oeuvre-cands');
    linkBtn.addEventListener('click', function () {
      linkBtn.disabled = true;
      cands.style.display = 'block';
      cands.innerHTML = '<span class="imgl-oeuvre-hint">Chargement…</span>';
      window.apiFetch('/artist/me/prompts/' + encodeURIComponent(img.id) + '/linkable')
        .then(function (list) {
          list = Array.isArray(list) ? list : [];
          if (list.length === 0) {
            cands.innerHTML = '<span class="imgl-oeuvre-hint">Aucun son disponible à lier — crée-en un d\'abord.</span>';
            linkBtn.disabled = false;
            return;
          }
          cands.innerHTML = list.map(function (c) {
            return '<button type="button" class="imgl-oeuvre-cand" data-cand="' + esc(c.id) + '">' +
              candThumb(c) +
              '<span class="imgl-oeuvre-cand-title">' + esc(c.title || 'Sans titre') + '</span>' +
              '<span class="imgl-oeuvre-cand-price">' + esc(String(c.priceCredits)) + ' Smyles</span>' +
            '</button>';
          }).join('');
          Array.prototype.forEach.call(cands.querySelectorAll('.imgl-oeuvre-cand'), function (cb) {
            cb.addEventListener('click', function () {
              var otherId = cb.getAttribute('data-cand');
              Array.prototype.forEach.call(cands.querySelectorAll('.imgl-oeuvre-cand'),
                function (x) { x.disabled = true; });
              // bundle_exclusive=false EN DUR (lien rétroactif).
              window.apiFetch('/artist/me/prompts/' + encodeURIComponent(img.id) + '/link', {
                method: 'POST',
                json: { other_prompt_id: otherId, bundle_exclusive: false },
                raw: true,
              })
                .then(function () {
                  toast('Œuvre complète créée ✓', 'success');
                  img.isOeuvreComplete = true;
                  // On marque lié ; le détail du partenaire sera ré-hydraté au
                  // prochain refresh de la liste. Affiche l'état lié générique.
                  img.linkedSound = img.linkedSound || { title: '' };
                  renderOeuvreComplete(box, img);
                  refresh();
                  refreshCount();
                })
                .catch(function (e) {
                  var msg = (e && e.status === 409)
                    ? 'Lien impossible (déjà lié ou natures incompatibles).'
                    : 'Échec du lien.';
                  toast(msg, 'error');
                  Array.prototype.forEach.call(cands.querySelectorAll('.imgl-oeuvre-cand'),
                    function (x) { x.disabled = false; });
                });
            });
          });
        })
        .catch(function () {
          cands.innerHTML = '<span class="imgl-oeuvre-hint">Erreur de chargement des candidats.</span>';
          linkBtn.disabled = false;
        });
    });
  }

  // Délégation des actions Éditer / Supprimer sur la grille.
  function wireActions() {
    if (window.__imgl_actions_wired) return;
    window.__imgl_actions_wired = true;
    document.addEventListener('click', function (e) {
      var ed = e.target.closest('[data-imgl-edit]');
      if (ed) { e.preventDefault(); openEditModal(_byId[String(ed.getAttribute('data-imgl-edit'))]); return; }
      var dl = e.target.closest('[data-imgl-del]');
      if (dl) { e.preventDefault(); deleteImage(dl.getAttribute('data-imgl-del')); return; }
    });
  }

  // ImageOwnerRead expose snake_case côté Pydantic (preview_r2_key, etc.).
  // On normalise vers le camelCase utilisé par les cards.
  function normalize(o) {
    return {
      id:               o.id,
      title:            o.title,
      description:      o.description != null ? o.description : '',
      priceCredits:     o.price_credits != null ? o.price_credits : o.priceCredits,
      maxSupply:        o.max_supply != null ? o.max_supply : (o.maxSupply != null ? o.maxSupply : null),
      isPublished:      !!(o.is_published != null ? o.is_published : o.isPublished),
      imagePlatform:    o.image_platform || o.imagePlatform || '',
      imageModelVersion: o.image_model_version || o.imageModelVersion || '',
      previewKey:       o.preview_r2_key || o.previewKey || '',
      soldCount:        o.soldCount || 0,
      isSoldOut:        !!o.isSoldOut,
      // C4 « Œuvre complète » — état de lien (apercu public du son partenaire).
      isOeuvreComplete: !!o.isOeuvreComplete,
      linkedSound:      o.linkedSound || null,
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
    wireActions();
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
