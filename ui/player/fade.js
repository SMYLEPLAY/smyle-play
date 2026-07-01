/* ─────────────────────────────────────────────────────────────────────────
   WATT — ui/player/fade.js
   Fondu de lecture (transitions de playlist) — ADDITIF, non destructif.

   Objectif : adoucir la fin de chaque son et l'entrée du suivant, sans
   toucher aux fichiers (masters intacts) ni aux fonctions du player.
   Fonctionne sur les 3 playlists ET MY MIX : on n'écoute QUE les événements
   de l'élément `audio` global (state.js), donc tout titre chargé via
   loadTrack() / loadMixTrack() est couvert automatiquement.

   Mécanique :
     • 'loadstart' (nouveau src)  → volume = 0            (prépare le fade-in)
     • 'playing'                  → rampe 0 → 1           (fade-in)
     • 'timeupdate' proche de la fin → rampe → 0          (fade-out)
   Respecte loopMode (pas de fade-out si le titre boucle).

   Réglage (console ou avant chargement) :
     window.SMYLE_FADE = { enabled: true, seconds: 4 };

   ⚠️ Limite iOS Safari : HTMLMediaElement.volume y est en lecture seule →
   le fondu est ignoré (lecture normale). Desktop + Android : OK. Le vrai
   crossfade avec chevauchement (v2) passera par Web Audio (GainNode) +
   CORS R2 pour couvrir iOS.

   À charger APRÈS ui/core/state.js et ui/app.js.
   ───────────────────────────────────────────────────────────────────────── */

(function initSmyleFade() {
  'use strict';
  if (typeof window === 'undefined') return;

  var CFG = window.SMYLE_FADE = window.SMYLE_FADE || {};
  if (CFG.enabled === undefined) CFG.enabled = true;
  if (CFG.seconds === undefined) CFG.seconds = 4;   // durée du fondu (s)

  var raf = null;
  var fadingOut = false;

  function el() {
    return (typeof audio !== 'undefined' && audio) ? audio
         : (window.audio || null);
  }

  function isLoop() {
    return (typeof loopMode !== 'undefined' && loopMode) ? true
         : (window.loopMode === true);
  }

  function cancelRamp() {
    if (raf) { cancelAnimationFrame(raf); raf = null; }
  }

  // Rampe le volume de `a` de son niveau courant vers `to` en `dur` secondes.
  function ramp(a, to, dur, done) {
    cancelRamp();
    var from = a.volume;
    if (dur <= 0) { try { a.volume = to; } catch (_) {} if (done) done(); return; }
    var t0 = performance.now();
    (function step(now) {
      var k = Math.min(1, (now - t0) / (dur * 1000));
      var v = from + (to - from) * k;
      try { a.volume = v < 0 ? 0 : (v > 1 ? 1 : v); } catch (_) {}
      if (k < 1) { raf = requestAnimationFrame(step); }
      else { raf = null; if (done) done(); }
    })(t0);
  }

  function attach(a) {
    if (!a || a._smyleFadeBound) return;
    a._smyleFadeBound = true;

    // Nouveau titre chargé (src changé) → on part de 0 pour le fade-in.
    a.addEventListener('loadstart', function () {
      cancelRamp();
      fadingOut = false;
      if (!CFG.enabled) { try { a.volume = 1; } catch (_) {} return; }
      try { a.volume = 0; } catch (_) {}
    });

    // La lecture démarre → fade-in (seulement si on est bas, pas sur reprise).
    a.addEventListener('playing', function () {
      if (!CFG.enabled) { try { a.volume = 1; } catch (_) {} return; }
      if (a.volume < 0.99 && !fadingOut) ramp(a, 1, CFG.seconds);
    });

    // Approche de la fin → fade-out (sauf boucle).
    a.addEventListener('timeupdate', function () {
      if (!CFG.enabled || fadingOut || isLoop()) return;
      var d = a.duration;
      if (!isFinite(d) || d <= 0) return;
      // Titre trop court : on ne transforme pas tout le morceau en fondu.
      if (d < CFG.seconds * 1.5) return;
      var remain = d - a.currentTime;
      if (remain <= CFG.seconds) {
        fadingOut = true;
        ramp(a, 0, Math.max(0.15, remain));
      }
    });

    // Sécurité : si un titre finit sans être passé par le fade-out, on
    // remet le volume à plein pour le suivant.
    a.addEventListener('ended', function () { fadingOut = false; });
  }

  function boot() {
    var a = el();
    if (!a) { setTimeout(boot, 250); return; }   // attend que state.js soit prêt
    attach(a);
  }

  if (document.readyState !== 'loading') boot();
  else document.addEventListener('DOMContentLoaded', boot);
})();
