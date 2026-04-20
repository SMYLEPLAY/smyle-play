/* ─────────────────────────────────────────────────────────────────────────
   SMYLE PLAY — ui/core/api.js
   Helper unique pour tous les appels au backend FastAPI.
   Gère : URL de base, token JWT dans localStorage, parsing JSON, erreurs.

   Ce fichier doit être chargé AVANT tout consommateur (dashboard.js,
   artiste.js, et les modules ui/hub, ui/panels, ui/modals).

   Nouveau — pas encore appelé par le code existant. Il sera utilisé à partir
   de l'étape 4 du plan de migration (mapping des fetch read-only).
   ───────────────────────────────────────────────────────────────────────── */

// ── 1. BASE URL ─────────────────────────────────────────────────────────────
// On détecte l'environnement via le hostname.
// - dev local              → http://localhost:8000
// - prod Railway (plus tard) → override via window.SMYLE_API_BASE dans le HTML
//
// Pour forcer une URL spécifique, définir AVANT le chargement de ce script :
//   <script>window.SMYLE_API_BASE = "https://api.smyleplay.com";</script>

const API_BASE = (function resolveApiBase() {
  if (typeof window !== 'undefined' && window.SMYLE_API_BASE) {
    return String(window.SMYLE_API_BASE).replace(/\/+$/, '');
  }
  const host = (typeof location !== 'undefined' && location.hostname) || '';
  if (host === 'localhost' || host === '127.0.0.1' || host === '') {
    return 'http://localhost:8000';
  }
  // Fallback prod : même origine que le site Flask (si on met FastAPI derrière
  // un reverse-proxy sur le même domaine, ex. /api/* → FastAPI).
  return '';
})();


// ── 2. TOKEN JWT (localStorage) ─────────────────────────────────────────────

const _TOKEN_KEY = 'smyle_api_token';

function getAuthToken() {
  try { return localStorage.getItem(_TOKEN_KEY) || null; }
  catch (_) { return null; }
}

function setAuthToken(token) {
  try {
    if (token) localStorage.setItem(_TOKEN_KEY, token);
    else       localStorage.removeItem(_TOKEN_KEY);
  } catch (_) { /* quota / mode privé → silent */ }
}

function clearAuthToken() { setAuthToken(null); }


// ── 3. ERREUR DÉDIÉE ────────────────────────────────────────────────────────
// On wrappe les erreurs HTTP dans une classe dédiée pour permettre aux
// consommateurs de lire status/body/url proprement :
//
//   try { await apiFetch('/tracks/') }
//   catch (e) {
//     if (e instanceof ApiError && e.status === 401) { /* relogin */ }
//   }

class ApiError extends Error {
  constructor(message, { status, statusText, body, url, isNetworkError = false, cause = null }) {
    super(message);
    this.name           = 'ApiError';
    this.status         = status;
    this.statusText     = statusText;
    this.body           = body;
    this.url            = url;
    // Chantier résilience — distingue une erreur HTTP (serveur a répondu
    // avec un 4xx/5xx, status défini) d'une erreur réseau (fetch a rejeté
    // avant même d'avoir une réponse : API down, DNS KO, CORS, offline…).
    // Les consommateurs peuvent ainsi afficher un message pertinent
    // ("Serveur injoignable" vs "Email ou mot de passe incorrect").
    this.isNetworkError = isNetworkError;
    this.cause          = cause;
  }
}


// ── 4. APIFETCH ─────────────────────────────────────────────────────────────
// Helper principal. Préfixe l'URL avec API_BASE, ajoute le header JWT si
// on est connecté, parse le JSON, lève ApiError sur 4xx/5xx.
//
// Signature :
//   apiFetch(path, options?) → Promise<any>   // JSON parsé
//   apiFetch(path, { raw: true })            → Promise<Response>  // brut
//
// Options :
//   - tout ce qui marche dans fetch() (method, body, headers, …)
//   - auth   : true (défaut) → inclut le JWT. false → l'omet.
//   - json   : objet → JSON.stringify + Content-Type application/json
//   - raw    : true → retourne la Response brute au lieu du JSON
//
// Exemples :
//   const tracks  = await apiFetch('/tracks/');
//   const me      = await apiFetch('/users/me');
//   const created = await apiFetch('/auth/register', {
//     method: 'POST', json: { email, password },
//   });

// ── Helpers internes pour la couche réseau ──────────────────────────────────
// `_fetchWithTimeout` pose un AbortController pour ne pas laisser une
// requête pendre indéfiniment (ex: API injoignable → fetch qui tourne 2min).
async function _fetchWithTimeout(url, opts, timeoutMs) {
  if (!timeoutMs) return fetch(url, opts);
  const controller = new AbortController();
  const tid = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(tid);
  }
}

// Sleep utilitaire (promisified setTimeout).
function _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function apiFetch(path, options = {}) {
  const {
    auth    = true,
    json,
    raw     = false,
    headers: userHeaders = {},
    // Chantier résilience — timeout/retry configurables mais avec des
    // valeurs par défaut raisonnables pour l'UX.
    //   timeoutMs : coupure auto si le serveur ne répond pas (8s).
    //   retries   : nombre de retries sur erreurs RÉSEAU uniquement (0 par
    //               défaut — on active 1 retry sur les cas critiques type
    //               login où une blip transitoire ne doit pas ruiner l'UX).
    //   retryDelayMs : délai avant le retry (600ms).
    timeoutMs     = 8000,
    retries       = 0,
    retryDelayMs  = 600,
    // Callback optionnel : reçoit { attempt, retries, willRetry, error }
    // dès qu'un essai échoue côté réseau. Permet aux consommateurs
    // (ex: modal login) d'afficher "Nouvelle tentative…" plutôt que
    // de laisser l'utilisateur face à un spinner figé.
    onAttempt     = null,
    ...rest
  } = options;

  const url = (path.startsWith('http') ? path : API_BASE + (path.startsWith('/') ? '' : '/') + path);

  const headers = Object.assign({ 'Accept': 'application/json' }, userHeaders);

  // Corps JSON automatique
  let body = rest.body;
  if (json !== undefined) {
    body = JSON.stringify(json);
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }

  // Header Authorization si JWT présent
  if (auth) {
    const token = getAuthToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  // ── Couche réseau avec retry sur erreurs réseau uniquement ────────────
  // On ne retry PAS les 4xx/5xx — si le serveur répond 400 ou 500, il
  // répondra pareil au second coup, ça ne sert qu'à doubler l'attente
  // utilisateur. On retry UNIQUEMENT quand fetch rejette avant d'avoir
  // une réponse (API down, offline transitoire, DNS, CORS).
  let resp;
  let lastNetworkError = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      resp = await _fetchWithTimeout(url, { ...rest, body, headers }, timeoutMs);
      lastNetworkError = null;
      break;
    } catch (fetchErr) {
      lastNetworkError = fetchErr;
      const aborted = fetchErr && (fetchErr.name === 'AbortError');
      const msgLower = String(fetchErr && fetchErr.message || '').toLowerCase();
      const isOffline = (typeof navigator !== 'undefined' && navigator.onLine === false);
      // Si plus de retries dispos → on throw
      if (attempt >= retries) {
        let friendly;
        if (isOffline) {
          friendly = 'Pas de connexion internet — vérifie ton wifi puis réessaie.';
        } else if (aborted) {
          friendly = 'Le serveur est trop lent à répondre. Réessaie dans un instant.';
        } else if (msgLower.includes('failed to fetch') || msgLower.includes('networkerror') || msgLower.includes('load failed')) {
          friendly = 'Serveur injoignable — l\'API ne répond pas. Vérifie qu\'elle est bien démarrée, ou réessaie dans un instant.';
        } else {
          friendly = 'Problème réseau — réessaie dans un instant.';
        }
        throw new ApiError(friendly, {
          status:         0,
          statusText:     'Network Error',
          body:           null,
          url,
          isNetworkError: true,
          cause:          fetchErr,
        });
      }
      // Sinon : on notifie le consommateur puis petite pause avant retry
      if (typeof onAttempt === 'function') {
        try {
          onAttempt({ attempt: attempt + 1, retries, willRetry: true, error: fetchErr });
        } catch (_) { /* noop */ }
      }
      await _sleep(retryDelayMs);
    }
  }

  if (raw) return resp;

  // Parser la réponse (JSON si possible, sinon texte)
  const text = await resp.text();
  let parsed = null;
  if (text) {
    try { parsed = JSON.parse(text); }
    catch (_) { parsed = text; }
  }

  if (!resp.ok) {
    const msg = (parsed && parsed.detail) || (parsed && parsed.error) || resp.statusText || 'API error';
    const err = new ApiError(`${resp.status} ${msg}`, {
      status:     resp.status,
      statusText: resp.statusText,
      body:       parsed,
      url,
    });

    // ── Chantier UX — Détection session expirée ─────────────────────────
    // Quand on a envoyé un JWT mais que le serveur répond 401, c'est que
    // le token est invalide (expiré / révoqué / clé serveur changée). On
    // purge le token périmé (sinon on boucle) et on émet un event global
    // que l'UI écoute pour afficher un toast "Session expirée". L'event
    // n'est émis qu'une fois par "fenêtre" de 10s — évite le spam si
    // plusieurs requêtes parallèles se prennent le même 401 simultanément.
    if (resp.status === 401 && auth) {
      const hadToken = !!getAuthToken();
      if (hadToken) clearAuthToken();
      // On purge aussi l'user mis en cache (localStorage "smyle_current_user").
      // Sans ça, `getCurrentUser()` continue de retourner l'ancien user, et
      // `openAuthModal('login')` fait un return silencieux (guard "si déjà
      // connecté, on ne rouvre pas le modal") — ce qui casse le bouton
      // "Reconnecter" du bandeau session expirée. Cf. storage.js.
      if (hadToken && typeof window !== 'undefined' && typeof window.clearCurrentUser === 'function') {
        try { window.clearCurrentUser(); } catch (_) { /* noop */ }
      }
      if (hadToken && typeof window !== 'undefined') {
        const now = Date.now();
        const last = window.__smyleSessionExpiredAt || 0;
        if (now - last > 10_000) {
          window.__smyleSessionExpiredAt = now;
          try {
            window.dispatchEvent(new CustomEvent('smyle:session-expired', {
              detail: { url, status: resp.status },
            }));
          } catch (_) { /* CustomEvent manquant sur navigateurs antiques */ }
        }
      }
    }

    throw err;
  }

  return parsed;
}


// ── 5. EXPOSITION GLOBALE ───────────────────────────────────────────────────
// Ce fichier est chargé en <script> classique (non-module) dans index.html,
// dashboard.html, artiste.html, library.html. Les symboles sont donc déjà
// globaux sans qu'on fasse rien. On les référence ici pour lint-friendly.

if (typeof window !== 'undefined') {
  window.API_BASE        = API_BASE;
  window.apiFetch        = apiFetch;
  window.ApiError        = ApiError;
  window.getAuthToken    = getAuthToken;
  window.setAuthToken    = setAuthToken;
  window.clearAuthToken  = clearAuthToken;
}
