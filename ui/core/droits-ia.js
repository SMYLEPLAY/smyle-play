/* Lot I — confirmation des droits commerciaux avant la première publication.
 *
 * Les CGU demandent au créateur de détenir les droits commerciaux de ce qu'il
 * publie (pour Suno et la plupart des outils d'IA : un abonnement payant au
 * moment de la création). Avant sa PREMIÈRE publication, on lui demande de le
 * confirmer ; la date est enregistrée (preuve) et la question ne revient plus.
 *
 *   const ok = await window.SmyleDroitsIA.ensure();
 *   if (!ok) return;   // annulé : on ne publie pas
 */
(function () {
  'use strict';
  let _confirme = false;

  function _modale() {
    return new Promise((resolve) => {
      const back = document.createElement('div');
      back.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:10050;display:flex;align-items:center;justify-content:center;padding:16px';
      const box = document.createElement('div');
      box.setAttribute('role', 'dialog');
      box.setAttribute('aria-modal', 'true');
      box.style.cssText = 'background:#16121f;color:#eee;border:1px solid #3a3150;border-radius:16px;max-width:440px;width:100%;padding:22px;line-height:1.5;font-size:14.5px';
      const h = document.createElement('h3');
      h.textContent = 'Avant ta première publication';
      h.style.cssText = 'margin:0 0 10px;font-size:18px';
      const p = document.createElement('p');
      p.textContent = "Sur WATT, ce qui est mis en vente est réutilisable : l'acheteur peut s'en servir dans ses propres créations, même publiées ou vendues (mais pas le revendre tel quel). " +
        "Tu dois donc en détenir les droits commerciaux. Avec Suno, c'est le cas si tu avais un abonnement payant (Pro ou Premier) au moment de la création.";
      const lbl = document.createElement('label');
      lbl.style.cssText = 'display:flex;gap:8px;align-items:flex-start;margin:14px 0;cursor:pointer';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.style.cssText = 'margin-top:3px;flex:none';
      const t = document.createElement('span');
      t.textContent = "Je confirme détenir les droits commerciaux de ce que je publie sur WATT (abonnement payant de l'outil d'IA utilisé) et j'autorise les acheteurs à le réutiliser, conformément aux CGU.";
      lbl.append(cb, t);
      const lien = document.createElement('a');
      lien.href = '/legal#cgu'; lien.target = '_blank'; lien.rel = 'noopener';
      lien.textContent = 'Lire les CGU';
      lien.style.cssText = 'color:#8ab4ff;font-size:13px';
      const msg = document.createElement('p');
      msg.style.cssText = 'color:#ff8a9a;font-size:13px;min-height:1em;margin:8px 0 0';
      const btns = document.createElement('div');
      btns.style.cssText = 'display:flex;gap:10px;justify-content:flex-end;margin-top:14px';
      const non = document.createElement('button');
      non.type = 'button'; non.textContent = 'Annuler';
      non.style.cssText = 'background:transparent;color:#ccc;border:1px solid #555;border-radius:10px;padding:9px 14px;cursor:pointer';
      const oui = document.createElement('button');
      oui.type = 'button'; oui.textContent = 'Je confirme'; oui.disabled = true;
      oui.style.cssText = 'background:#6c4cf0;color:#fff;border:0;border-radius:10px;padding:9px 16px;font-weight:700;cursor:pointer';
      btns.append(non, oui);
      box.append(h, p, lbl, lien, msg, btns);
      back.appendChild(box);
      document.body.appendChild(back);
      cb.addEventListener('change', () => { oui.disabled = !cb.checked; });
      const fin = (v) => { back.remove(); resolve(v); };
      non.addEventListener('click', () => fin(false));
      oui.addEventListener('click', async () => {
        oui.disabled = true;
        try {
          await window.apiFetch('/users/me/droits-ia', { method: 'POST', json: { confirme: true } });
          _confirme = true;
          fin(true);
        } catch (_) {
          msg.textContent = 'Enregistrement impossible. Vérifie ta connexion et réessaie.';
          oui.disabled = false;
        }
      });
    });
  }

  async function ensure() {
    if (_confirme) return true;
    try {
      const r = await window.apiFetch('/users/me/droits-ia');
      if (r && r.confirme) { _confirme = true; return true; }
    } catch (_) {
      // Lecture impossible : on pose la question quand même (l'envoi de la
      // confirmation dira s'il y a un vrai problème de connexion).
    }
    return _modale();
  }

  window.SmyleDroitsIA = { ensure };
})();
