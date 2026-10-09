// Test de charge WATT — trois parcours : accueil, connexion, achat.
// Mode d'emploi : ops/k6/README.md. NE JAMAIS lancer contre la production.
//
//   k6 run ops/k6/watt.js                              (serveur local :8000)
//   BASE_URL=http://127.0.0.1:8000 PROFIL=fumee k6 run ops/k6/watt.js
//
// Le script crée lui-même ses comptes de test (setup) : un vendeur avec
// quelques recettes à 3 Smyles, et un lot d'acheteurs (bonus de bienvenue).

import http from 'k6/http';
import { check, group, sleep, fail } from 'k6';
import { Rate } from 'k6/metrics';
import exec from 'k6/execution';

const BASE = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const PROFIL = __ENV.PROFIL || 'charge';          // fumee | charge | pic
const NB_ACHETEURS = parseInt(__ENV.NB_ACHETEURS || '40', 10);
const NB_RECETTES = 4;
const PRIX = 3;                                   // minimum autorisé (PROMPT_PRICE_MIN)
const MOT_DE_PASSE = 'K6-Charge-123456';

// ── Garde-fou : cible locale uniquement, sauf autorisation explicite ──────
const hote = BASE.replace(/^https?:\/\//, '').split(/[/:]/)[0];
const LOCAL = ['localhost', '127.0.0.1', '0.0.0.0', '::1'].includes(hote);
if (!LOCAL && __ENV.K6_CIBLE_AUTORISEE !== 'oui') {
  throw new Error(
    `Cible « ${hote} » refusée : ce test crée des comptes et des achats. ` +
    'Seul un serveur local ou de pré-production est permis, avec ' +
    'K6_CIBLE_AUTORISEE=oui (voir README). Jamais la production.'
  );
}

// ── Profils de charge (utilisateurs virtuels simultanés) ──────────────────
function rampe(max) {
  return [
    { duration: '30s', target: Math.ceil(max / 3) },
    { duration: '1m', target: max },
    { duration: '2m', target: max },
    { duration: '30s', target: 0 },
  ];
}
const PROFILS = {
  fumee: { accueil: [{ duration: '20s', target: 2 }], connexion: [{ duration: '20s', target: 1 }], achat: [{ duration: '20s', target: 1 }] },
  charge: { accueil: rampe(60), connexion: rampe(10), achat: rampe(10) },
  pic: { accueil: rampe(200), connexion: rampe(30), achat: rampe(30) },
};
const P = PROFILS[PROFIL] || PROFILS.charge;

// Erreur « technique » = 5xx, délai dépassé, connexion refusée. Les refus
// métier attendus (solde insuffisant 402, déjà acheté 409) n'en sont pas.
const erreursTechniques = new Rate('erreurs_techniques');

export const options = {
  setupTimeout: '3m',
  scenarios: {
    accueil: { executor: 'ramping-vus', exec: 'accueil', stages: P.accueil, gracefulRampDown: '10s' },
    connexion: { executor: 'ramping-vus', exec: 'connexion', stages: P.connexion, gracefulRampDown: '10s' },
    achat: { executor: 'ramping-vus', exec: 'achat', stages: P.achat, gracefulRampDown: '10s' },
  },
  thresholds: {
    erreurs_techniques: ['rate<0.01'],                                   // < 1 %
    'http_req_duration{scenario:accueil}': ['p(95)<800'],
    'http_req_duration{scenario:connexion}': ['p(95)<1500'],             // bcrypt : plus lent
    'http_req_duration{scenario:achat}': ['p(95)<1500'],
  },
};

const JSON_H = { headers: { 'Content-Type': 'application/json' } };
function authH(token) {
  return { headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` } };
}
function suivre(res, attendus) {
  const technique = res.status === 0 || res.status >= 500;
  erreursTechniques.add(technique);
  return check(res, { [`statut ∈ ${attendus.join('/')}`]: (r) => attendus.includes(r.status) });
}
function uniq(prefixe) {
  return `${prefixe}-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}

function inscrire(prefixe) {
  const email = `${uniq(prefixe)}@smyleplay.example`;
  const reg = http.post(`${BASE}/auth/register`, JSON.stringify({
    email, password: MOT_DE_PASSE, accept_terms: true, age_confirmed: true,
  }), JSON_H);
  if (reg.status !== 201) fail(`inscription ${prefixe} : ${reg.status} ${reg.body}`);
  const login = http.post(`${BASE}/auth/login`, JSON.stringify({ email, password: MOT_DE_PASSE }), JSON_H);
  if (login.status !== 200) {
    fail(`connexion ${prefixe} : ${login.status} ${login.body} ` +
      '(REQUIRE_EMAIL_VERIFIED doit être à false sur le serveur testé)');
  }
  return { email, token: login.json('access_token') };
}

// ── Préparation : vendeur + recettes + acheteurs ──────────────────────────
export function setup() {
  const sante = http.get(`${BASE}/health`);
  if (sante.status !== 200) fail(`serveur injoignable ou en erreur (/health → ${sante.status})`);

  const vendeur = inscrire('k6-vendeur');
  const v = authH(vendeur.token);
  let r = http.patch(`${BASE}/users/me`, JSON.stringify({ artist_name: uniq('K6 Vendeur') }), v);
  if (r.status !== 200) fail(`profil vendeur : ${r.status} ${r.body}`);
  r = http.post(`${BASE}/artist/me/adn`, JSON.stringify({
    description:
      'Signature sonore de test de charge : nappes chaudes, basse ronde, batterie ' +
      'feutree, tempo lent, ambiance nocturne et enveloppante. Ecrite uniquement ' +
      'pour mesurer la tenue en charge du parcours d achat, sans valeur artistique.',
    price_credits: 30,
  }), v);
  if (r.status !== 201) fail(`ADN vendeur : ${r.status} ${r.body}`);

  const recettes = [];
  for (let i = 0; i < NB_RECETTES; i += 1) {
    r = http.post(`${BASE}/artist/me/prompts`, JSON.stringify({
      title: `Recette k6 ${i + 1}`,
      description: 'Produit de test de charge.',
      prompt_text:
        'deep house nocturne, 118 bpm, nappes analogiques chaudes, basse ronde, ' +
        'charleston feutree, reverb longue, ambiance de fin de nuit, arrangement minimal.',
      price_credits: PRIX,
      is_published: true,
      prompt_platform: 'suno',
      prompt_weirdness: '30%',
      prompt_style_influence: 'deep house, dub techno',
      prompt_vocal_gender: 'instrumental',
    }), v);
    if (r.status !== 201) fail(`recette ${i + 1} : ${r.status} ${r.body} (seuil d'abonnés actif ?)`);
    recettes.push(r.json('id'));
  }

  const acheteurs = [];
  for (let i = 0; i < NB_ACHETEURS; i += 1) acheteurs.push(inscrire('k6-acheteur'));
  return { recettes, acheteurs };
}

// ── Parcours 1 : accueil (visiteur anonyme) ───────────────────────────────
export function accueil() {
  group('accueil', () => {
    suivre(http.get(`${BASE}/`, { tags: { nom: 'page accueil' } }), [200]);
    const res = http.batch([
      ['GET', `${BASE}/ui/core/launch-flags.js`, null, { tags: { nom: 'launch-flags' } }],
      ['GET', `${BASE}/watt/tracks-catalog`, null, { tags: { nom: 'catalogue' } }],
      ['GET', `${BASE}/watt/artists`, null, { tags: { nom: 'artistes' } }],
      ['GET', `${BASE}/watt/tracks-recent?limit=100`, null, { tags: { nom: 'récents' } }],
    ]);
    res.forEach((r) => suivre(r, [200]));
  });
  sleep(1 + Math.random() * 3);
}

// ── Parcours 2 : connexion (compte existant) ──────────────────────────────
export function connexion(data) {
  const a = data.acheteurs[Math.floor(Math.random() * data.acheteurs.length)];
  group('connexion', () => {
    const login = http.post(`${BASE}/auth/login`,
      JSON.stringify({ email: a.email, password: MOT_DE_PASSE }),
      { ...JSON_H, tags: { nom: 'login' } });
    if (!suivre(login, [200])) return;
    suivre(http.get(`${BASE}/users/me`, { ...authH(login.json('access_token')), tags: { nom: 'users/me' } }), [200]);
  });
  sleep(2 + Math.random() * 3);
}

// ── Parcours 3 : achat d'une recette (débit réel en Smyles) ───────────────
// 201 = acheté ; 402 = solde épuisé ; 409 = déjà acheté. Les trois sont des
// réponses normales : chaque acheteur n'a que 10 Smyles (3 achats à 3).
export function achat(data) {
  const a = data.acheteurs[exec.vu.idInTest % data.acheteurs.length];
  const id = data.recettes[Math.floor(Math.random() * data.recettes.length)];
  group('achat', () => {
    suivre(http.get(`${BASE}/users/me`, { ...authH(a.token), tags: { nom: 'solde' } }), [200]);
    suivre(http.post(`${BASE}/unlocks/prompts/${id}`, null, { ...authH(a.token), tags: { nom: 'unlock' } }),
      [201, 402, 409]);
    suivre(http.get(`${BASE}/me/library/prompts`, { ...authH(a.token), tags: { nom: 'bibliothèque' } }), [200]);
  });
  sleep(2 + Math.random() * 3);
}
