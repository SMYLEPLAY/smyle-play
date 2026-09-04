// @ts-check
const { test, expect } = require('@playwright/test');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE — ACHAT RÉEL, DE BOUT EN BOUT, SANS AUCUN MOCK (K-10, annexe B §6).
//
// `smoke-purchase.spec.js` intercepte l'appel d'unlock avec `page.route` : il
// prouve le CÂBLAGE clic → endpoint, et rien d'autre. Tout ce qui compte
// économiquement restait non couvert : le débit réel de l'acheteur, le crédit
// du vendeur, l'apparition du contenu payé dans la bibliothèque, et le fait
// qu'un même exemplaire ne se paie pas deux fois.
//
// Ce test sème donc un vrai produit par l'API publique, puis achète depuis
// l'INTERFACE (le drawer), et vérifie les conséquences EN BASE via l'API.
// Aucun `page.route`, aucune fixture SQL : uniquement des appels que
// n'importe quel utilisateur pourrait faire.
//
// Le semis (vendeur) :
//   1. inscription + connexion ;
//   2. PATCH /users/me → nom d'artiste (requis pour publier le profil) ;
//   3. POST /artist/me/adn → un ADN est le pré-requis de tout prompt ;
//   4. POST /artist/me/prompts → le produit, publié, à 5 Smyles.
// L'acheteur reçoit 10 Smyles de bienvenue à l'inscription
// (WELCOME_BONUS_CREDITS) : c'est la seule source de Smyles disponible, car
// POST /credits/grant est réservé aux comptes officiels.
//
// Répartition attendue après achat à 5 Smyles : l'acheteur passe de 10 à 5,
// exactement le prix affiché. Côté vendeur, on vérifie seulement que le solde
// AUGMENTE : le montant exact dépend de la commission de palier ET des bonus de
// trophée déclenchés par la première vente (mesuré : +9 pour une vente à 5).
// Figer ce chiffre reviendrait à verrouiller un barème qui est une décision
// produit encore ouverte — le test casserait à chaque ajustement.
// ─────────────────────────────────────────────────────────────────────────────

const TOKEN_KEY = 'smyle_api_token';
const PRICE = 5;
const WELCOME = 10;

function _uniq(prefix) {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

async function _register(request, prefix) {
  const email = `${_uniq(prefix)}@smyleplay.example`;
  const password = 'Test123456';
  const reg = await request.post('/auth/register', {
    data: { email, password, accept_terms: true, age_confirmed: true },
  });
  expect(reg.status(), `register ${prefix}: ${await reg.text()}`).toBe(201);
  const login = await request.post('/auth/login', { data: { email, password } });
  expect(login.status(), `login ${prefix}: ${await login.text()}`).toBe(200);
  const { access_token } = await login.json();
  expect(access_token, 'access_token présent').toBeTruthy();
  return { email, token: access_token };
}

function _auth(token) {
  return { Authorization: `Bearer ${token}` };
}

async function _me(request, token) {
  const r = await request.get('/users/me', { headers: _auth(token) });
  expect(r.status(), `users/me: ${await r.text()}`).toBe(200);
  return r.json();
}

/** Sème un prompt PUBLIÉ, vendable, par l'API publique. */
async function _seedProduit(request, token) {
  const patch = await request.patch('/users/me', {
    headers: _auth(token),
    data: { artist_name: _uniq('E2E Vendeur') },
  });
  expect(patch.status(), `patch users/me: ${await patch.text()}`).toBe(200);

  // Un prompt exige un ADN préexistant (même non publié). Description ≥ 200.
  const adn = await request.post('/artist/me/adn', {
    headers: _auth(token),
    data: {
      description:
        'Signature sonore de test bout-en-bout : nappes chaudes, basse ronde, ' +
        'batterie feutree, tempo lent, ambiance nocturne et enveloppante. ' +
        'Ecrit uniquement pour valider le parcours d achat reel en CI, sans ' +
        'aucune valeur artistique revendiquee ni resultat promis a personne.',
      price_credits: 30,
    },
  });
  expect(adn.status(), `create adn: ${await adn.text()}`).toBe(201);

  const prompt = await request.post('/artist/me/prompts', {
    headers: _auth(token),
    data: {
      title: 'Recette E2E achat reel',
      description: 'Produit seme par smoke-purchase-real.',
      prompt_text:
        'deep house nocturne, 118 bpm, nappes analogiques chaudes, basse ronde ' +
        'et ronflante, charleston feutree, reverb longue, ambiance de fin de ' +
        'nuit, arrangement minimal et hypnotique, mix aere.',
      price_credits: PRICE,
      is_published: true,
      prompt_platform: 'suno',
      prompt_weirdness: '30%',
      prompt_style_influence: 'deep house, dub techno',
      prompt_vocal_gender: 'instrumental',
    },
  });
  expect(prompt.status(), `create prompt: ${await prompt.text()}`).toBe(201);
  const body = await prompt.json();
  expect(body.id, 'id du prompt').toBeTruthy();
  return body.id;
}

test('achat réel : débit acheteur, crédit vendeur, contenu en bibliothèque', async ({ page, request }) => {
  const vendeur = await _register(request, 'e2e-seller');
  const acheteur = await _register(request, 'e2e-buyer');
  const promptId = await _seedProduit(request, vendeur.token);

  const vendeurAvant = await _me(request, vendeur.token);
  const acheteurAvant = await _me(request, acheteur.token);
  expect(acheteurAvant.credits_balance, 'bonus de bienvenue').toBe(WELCOME);

  // ── Achat depuis l'INTERFACE, sans aucune interception ───────────────────
  await page.addInitScript(([key, tok]) => {
    try { localStorage.setItem(key, tok); } catch (e) { /* */ }
    // La « recompense du jour » s'auto-ouvre une fois par session pour un
    // compte neuf (ui/modals/auth.js _maybeNudgeStreak) et se poserait par
    // dessus le drawer. On pose son verrou de session : on teste l'achat, pas
    // le streak — et surtout on ne veut aucun Smyle en plus pendant la mesure.
    try { sessionStorage.setItem('smyle_streak_autoopened', '1'); } catch (e) { /* */ }
  }, [TOKEN_KEY, acheteur.token]);

  let unlockStatus = null;
  page.on('response', (r) => {
    if (r.url().includes(`/unlocks/prompts/${promptId}`)) unlockStatus = r.status();
  });

  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !!(window.PurchaseDrawer && window.PurchaseDrawer.open), null, { timeout: 15000 });
  await page.evaluate(([id, price]) => {
    window.PurchaseDrawer.open({ type: 'son', id, price, title: 'Recette E2E achat reel' });
  }, [promptId, PRICE]);

  await expect(page.locator('#pd-overlay')).toBeVisible();
  await expect(page.locator('#pd-overlay .pd-price')).toHaveText(String(PRICE));
  // Filet : si une modale de recompense s'est quand meme ouverte, elle
  // intercepterait le clic. On la referme plutot que d'echouer sur un
  // « element intercepts pointer events » difficile a diagnostiquer.
  await page.evaluate(() => {
    ['streakModal', 'egStreakModal'].forEach((id) => {
      const m = document.getElementById(id);
      if (m) m.style.display = 'none';
    });
  });
  await page.locator('#pd-overlay .pd-confirm').click();

  await expect.poll(() => unlockStatus, { timeout: 15000 }).toBe(201);

  // ── Conséquences réelles ────────────────────────────────────────────────
  const acheteurApres = await _me(request, acheteur.token);
  expect(acheteurApres.credits_balance, 'l’acheteur est débité du prix affiché')
    .toBe(WELCOME - PRICE);

  const vendeurApres = await _me(request, vendeur.token);
  const gain = vendeurApres.credits_balance - vendeurAvant.credits_balance;
  expect(gain, 'le vendeur est crédité par la vente').toBeGreaterThan(0);
  expect(
    vendeurApres.credits_earned_total,
    'la vente entre dans le cumul gagné du vendeur'
  ).toBeGreaterThan(vendeurAvant.credits_earned_total);

  const lib = await request.get('/me/library/prompts', { headers: _auth(acheteur.token) });
  expect(lib.status(), `library: ${await lib.text()}`).toBe(200);
  const items = (await lib.json()).items || [];
  const achete = items.find((i) => String(i.prompt_id) === String(promptId));
  expect(achete, 'le produit acheté apparaît dans la bibliothèque').toBeTruthy();
  // Le contenu gaté n'est lisible qu'APRÈS paiement : c'est ce qu'on a acheté.
  expect(achete.prompt_text, 'la recette complète est livrée').toContain('deep house');
});

test('achat réel : un même exemplaire ne se paie pas deux fois', async ({ request }) => {
  const vendeur = await _register(request, 'e2e-seller2');
  const acheteur = await _register(request, 'e2e-buyer2');
  const promptId = await _seedProduit(request, vendeur.token);

  const premier = await request.post(`/unlocks/prompts/${promptId}`, { headers: _auth(acheteur.token) });
  expect(premier.status(), `1er unlock: ${await premier.text()}`).toBe(201);
  const apres1 = await _me(request, acheteur.token);
  expect(apres1.credits_balance).toBe(WELCOME - PRICE);

  // Second achat du MÊME exemplaire : refusé, et surtout non débité.
  const second = await request.post(`/unlocks/prompts/${promptId}`, { headers: _auth(acheteur.token) });
  expect(second.status(), 'le second achat doit être refusé (déjà possédé)').toBe(409);
  const apres2 = await _me(request, acheteur.token);
  expect(apres2.credits_balance, 'aucun débit sur un achat refusé')
    .toBe(apres1.credits_balance);
});

test('achat réel : solde insuffisant → refus sans débit', async ({ request }) => {
  const vendeur = await _register(request, 'e2e-seller3');
  const acheteur = await _register(request, 'e2e-buyer3');

  // Produit hors de portée du bonus de bienvenue (10 Smyles).
  await request.patch('/users/me', {
    headers: _auth(vendeur.token),
    data: { artist_name: _uniq('E2E Vendeur cher') },
  });
  await request.post('/artist/me/adn', {
    headers: _auth(vendeur.token),
    data: {
      description:
        'Signature sonore de test bout-en-bout, variante chere : textures ' +
        'granulaires, cordes traitees, rythmique lente et sourde, espace large. ' +
        'Ecrite uniquement pour valider le refus pour solde insuffisant en CI, ' +
        'sans aucune valeur artistique revendiquee ni promesse de resultat.',
      price_credits: 30,
    },
  });
  const cher = await request.post('/artist/me/prompts', {
    headers: _auth(vendeur.token),
    data: {
      title: 'Recette E2E hors budget',
      prompt_text:
        'ambient granulaire, 70 bpm, cordes traitees au granulateur, nappes ' +
        'sombres, percussions sourdes et lointaines, reverb tres longue, ' +
        'progression lente, aucune voix, mix large et profond.',
      price_credits: 500,
      is_published: true,
      prompt_platform: 'suno',
      prompt_weirdness: '80%',
      prompt_style_influence: 'ambient, drone',
      prompt_vocal_gender: 'instrumental',
    },
  });
  expect(cher.status(), `create prompt cher: ${await cher.text()}`).toBe(201);
  const cherId = (await cher.json()).id;

  const r = await request.post(`/unlocks/prompts/${cherId}`, { headers: _auth(acheteur.token) });
  expect(r.status(), 'solde insuffisant → 402 Payment Required').toBe(402);
  const apres = await _me(request, acheteur.token);
  expect(apres.credits_balance, 'aucun débit sur un refus').toBe(WELCOME);
});
