/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/events.js
   Bus d'événements cross-pages + cross-tabs.

   Pourquoi ?
   ──────────
   Jusqu'ici chaque page vit dans sa bulle : WATT BOARD publie un profil,
   la marketplace ne le sait pas, elle ne re-fetch qu'au rechargement.
   Ce bus notifie toutes les pages (et les onglets ouverts) dès qu'un
   changement d'état public a lieu, pour que les vues se resynchronisent
   sans refresh manuel.

   Utilisation
   ───────────
     // Émettre
     SmyleEvents.emit('smyle:profile-published', { artist });

     // Écouter (retourne une fonction de désinscription)
     const off = SmyleEvents.on('smyle:profile-published', (payload) => {
       // … re-render
     });
     // plus tard : off();

   Contrats d'événements (figés — ne pas inventer à côté) :
     smyle:profile-published     payload: { artist }
     smyle:profile-unpublished   payload: { artistId, slug }
     smyle:track-uploaded        payload: { track }
     smyle:track-deleted         payload: { trackId, ownerId }
     smyle:playlist-created      payload: { playlist }
     smyle:playlist-updated      payload: { playlist }
     smyle:playlist-deleted      payload: { playlistId, ownerId }

   Cross-tabs
   ──────────
   Les émissions sont rebroadcastées aux autres onglets ouverts via
   BroadcastChannel. Les handlers reçoivent le payload tel quel,
   qu'il vienne du même onglet ou d'un voisin.

   Ce fichier doit être chargé AVANT tout consommateur.
   ───────────────────────────────────────────────────────────────────────── */

(function initSmyleEvents() {
  'use strict';

  // Guard : ne jamais ré-initialiser si déjà présent (cas où plusieurs pages
  // incluent le script via plusieurs chemins).
  if (typeof window !== 'undefined' && window.SmyleEvents) return;

  // Map<eventName, Set<handler>>
  const _listeners = new Map();

  // BroadcastChannel pour cross-tabs. Fallback silencieux sur les navigateurs
  // qui ne le supportent pas (vieux Safari) — le bus continue de marcher
  // en intra-onglet.
  let _channel = null;
  try {
    if (typeof BroadcastChannel !== 'undefined') {
      _channel = new BroadcastChannel('smyle');
      _channel.addEventListener('message', (ev) => {
        const data = ev && ev.data;
        if (!data || typeof data.type !== 'string') return;
        _dispatchLocal(data.type, data.payload, /* fromRemote */ true);
      });
    }
  } catch (_) {
    _channel = null;
  }

  function _dispatchLocal(type, payload, fromRemote) {
    const set = _listeners.get(type);
    if (!set || set.size === 0) return;
    // Copie avant itération : un handler peut se désinscrire pendant le dispatch.
    const handlers = Array.from(set);
    for (const h of handlers) {
      try { h(payload, { fromRemote: !!fromRemote, type }); }
      catch (err) { console.warn('[SmyleEvents] handler error for', type, err); }
    }
  }

  const SmyleEvents = {
    /** Émet un événement localement et le rebroadcast sur BroadcastChannel. */
    emit(type, payload) {
      if (typeof type !== 'string' || !type) return;
      _dispatchLocal(type, payload, /* fromRemote */ false);
      if (_channel) {
        // Clone via JSON pour éviter les références DOM non-clonables —
        // si le clone échoue, on abandonne silencieusement le cross-tab.
        try {
          const cloned = payload === undefined ? undefined : JSON.parse(JSON.stringify(payload));
          _channel.postMessage({ type, payload: cloned });
        } catch (_) { /* noop */ }
      }
    },

    /** Abonne un handler. Retourne la fonction de désinscription. */
    on(type, handler) {
      if (typeof type !== 'string' || typeof handler !== 'function') {
        return function noop() {};
      }
      let set = _listeners.get(type);
      if (!set) {
        set = new Set();
        _listeners.set(type, set);
      }
      set.add(handler);
      return function off() {
        const s = _listeners.get(type);
        if (s) { s.delete(handler); if (s.size === 0) _listeners.delete(type); }
      };
    },

    /** Désabonne explicitement (alternative à la fonction retournée par on). */
    off(type, handler) {
      const s = _listeners.get(type);
      if (s) { s.delete(handler); if (s.size === 0) _listeners.delete(type); }
    },

    /** Debug : liste des événements écoutés et nombre de handlers. */
    _debug() {
      const out = {};
      _listeners.forEach((s, k) => { out[k] = s.size; });
      return out;
    },
  };

  // Constantes exposées — pour que les consommateurs ne fassent pas de typos
  // sur les noms d'événements. Import recommandé : SmyleEvents.TYPES.PROFILE_PUBLISHED.
  SmyleEvents.TYPES = Object.freeze({
    PROFILE_PUBLISHED:   'smyle:profile-published',
    PROFILE_UNPUBLISHED: 'smyle:profile-unpublished',
    TRACK_UPLOADED:      'smyle:track-uploaded',
    TRACK_DELETED:       'smyle:track-deleted',
    PLAYLIST_CREATED:    'smyle:playlist-created',
    PLAYLIST_UPDATED:    'smyle:playlist-updated',
    PLAYLIST_DELETED:    'smyle:playlist-deleted',
  });

  // Exposition globale.
  if (typeof window !== 'undefined') {
    window.SmyleEvents = SmyleEvents;
  }
})();
