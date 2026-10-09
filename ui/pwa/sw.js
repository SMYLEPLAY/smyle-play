/* ─────────────────────────────────────────────────────────────────────────
   WATT — service worker (application installable).  Servi à /sw.js par
   app/routers/pages.py, qui remplace les deux marqueurs ci-dessous :
     VERSION : change à chaque déploiement → nouvelle installation, anciens
               caches supprimés ;
     ACTIF   : false quand PWA_ACTIVE=false sur Railway → ce fichier devient
               un « interrupteur d'arrêt » qui vide ses caches, se désinscrit
               et recharge les pages ouvertes. Un bug de cache ne peut donc
               jamais bloquer les utilisateurs.

   RÈGLES (volontairement minimales et sûres) :
     • Mis en cache : UNIQUEMENT les fichiers statiques VERSIONNÉS (adresse
       avec « ?v= ») en CSS / JS / images / polices, et les icônes de l'app,
       en « stale-while-revalidate ».
     • JAMAIS mis en cache : l'API, l'authentification, l'audio, les images
       des créateurs, les pages HTML, toute requête avec en-tête
       Authorization, toute réponse privée (no-store / private).
     • Pages HTML : réseau d'abord ; sans réseau → page « hors ligne ».
   ───────────────────────────────────────────────────────────────────────── */
'use strict';

const VERSION = '__WATT_SW_VERSION__';
const ACTIF = __WATT_SW_ACTIF__;
const CACHE_STATIQUES = 'watt-statiques-' + VERSION;
const CACHE_HORS_LIGNE = 'watt-hors-ligne-' + VERSION;
const PAGE_HORS_LIGNE = '/ui/pwa/hors-ligne.html';
const FICHIERS_HORS_LIGNE = [
  PAGE_HORS_LIGNE,
  '/ui/pwa/hors-ligne.css',
  '/ui/pwa/icones/icone-192.png',
];

// Fichiers statiques du site : un seul segment à la racine (/style.css) ou
// sous /ui/ — exactement la liste blanche du serveur. Aucune route d'API ne
// prend cette forme (l'API vit sous /watt/, /auth/, /users/, /images/…).
const STATIQUE = /^\/(?:[A-Za-z0-9._-]+|ui\/[A-Za-z0-9._\/-]+)\.(?:css|js|mjs|png|jpe?g|webp|gif|svg|ico|woff2?|ttf|otf)$/;
// Exclusions explicites : drapeaux de lancement (dynamiques) et le worker.
const JAMAIS = ['/ui/core/launch-flags.js', '/sw.js'];

function estStatiqueVersionne(url) {
  if (url.origin !== self.location.origin) return false;
  if (JAMAIS.includes(url.pathname)) return false;
  if (!STATIQUE.test(url.pathname)) return false;
  // Versionné = « ?v=… » dans l'adresse, ou icône de l'application.
  return url.searchParams.has('v') || url.pathname.startsWith('/ui/pwa/icones/');
}

function reponseCachable(rep) {
  if (!rep || !rep.ok || rep.type !== 'basic' || rep.status !== 200) return false;
  const cc = (rep.headers.get('Cache-Control') || '').toLowerCase();
  if (cc.includes('no-store') || cc.includes('private')) return false;
  if (rep.headers.has('Set-Cookie')) return false;
  return true;
}

// ── Installation / activation ────────────────────────────────────────────

self.addEventListener('install', (event) => {
  // Remplace immédiatement l'ancienne version : c'est ce qui permet de
  // corriger (ou d'éteindre) un worker défectueux sans attendre.
  self.skipWaiting();
  if (!ACTIF) return;
  event.waitUntil(
    caches.open(CACHE_HORS_LIGNE)
      .then((c) => c.addAll(FICHIERS_HORS_LIGNE.map((u) => new Request(u, { cache: 'reload' }))))
      .catch(() => { /* hors ligne non disponible : sans gravité */ })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const noms = await caches.keys();
    await Promise.all(noms
      .filter((n) => n.startsWith('watt-') && (!ACTIF || (n !== CACHE_STATIQUES && n !== CACHE_HORS_LIGNE)))
      .map((n) => caches.delete(n)));
    if (!ACTIF) {
      // Interrupteur d'arrêt : on se retire et on recharge les onglets, qui
      // repartent alors directement sur le réseau, sans worker.
      await self.registration.unregister();
      const fenetres = await self.clients.matchAll({ type: 'window' });
      fenetres.forEach((f) => { try { f.navigate(f.url); } catch (e) { /* */ } });
      return;
    }
    await self.clients.claim();
  })());
});

// ── Requêtes ─────────────────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  if (!ACTIF) return;
  const req = event.request;
  if (req.method !== 'GET') return;
  if (req.headers.has('Authorization')) return;
  if (req.headers.has('Range')) return;

  // Pages : réseau d'abord, jamais mises en cache ; secours hors ligne.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(async () => {
        const c = await caches.open(CACHE_HORS_LIGNE);
        return (await c.match(PAGE_HORS_LIGNE)) || Response.error();
      })
    );
    return;
  }

  let url;
  try { url = new URL(req.url); } catch (e) { return; }

  // Ressources de la page hors ligne : réseau, puis copie installée.
  if (url.origin === self.location.origin && FICHIERS_HORS_LIGNE.includes(url.pathname) && !url.search) {
    event.respondWith(fetch(req).catch(async () => {
      const c = await caches.open(CACHE_HORS_LIGNE);
      return (await c.match(url.pathname)) || Response.error();
    }));
    return;
  }

  if (!estStatiqueVersionne(url)) return; // tout le reste : réseau, sans worker

  // Statiques versionnés : stale-while-revalidate.
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_STATIQUES);
    const enCache = await cache.match(req);
    const reseau = fetch(req).then((rep) => {
      if (reponseCachable(rep)) cache.put(req, rep.clone()).catch(() => {});
      return rep;
    });
    if (enCache) {
      event.waitUntil(reseau.catch(() => {}));
      return enCache;
    }
    return reseau;
  })());
});
