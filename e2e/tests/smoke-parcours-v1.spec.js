// @ts-check
const { test, expect } = require('@playwright/test');
const { bootSessionAuthentifiee } = require('./_helpers');

// ─────────────────────────────────────────────────────────────────────────────
// SMOKE — Parcours V1 (décisions du 9/10/2026).
//   - visiteur : bandeau « Crée ton compte gratuit — 30 Smyles offerts »,
//     inscription proposée par défaut, toute action ouvre l'inscription,
//     extrait de 30 s, retour exact après inscription (return= interne
//     seulement), signalement sans compte qui invite à s'inscrire ;
//   - guide d'accueil : une seule fois, puis depuis le menu « Guide » ;
//   - email non vérifié : rappel + « Renvoyer » ;
//   - écran « Mes Œuvres » : masquer, republier, prix borné, suppression ;
//   - déconnexion : données du navigateur vidées ;
//   - anciennes pages redirigées vers l'accueil.
// ─────────────────────────────────────────────────────────────────────────────

const PWD = 'Test123456';

// Choix de mesure d'audience déjà fait : son bandeau (en bas) ne doit pas
// recouvrir les éléments testés.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    try { if (!localStorage.getItem('smyle_consent')) localStorage.setItem('smyle_consent', 'denied'); } catch (e) {}
  });
});

async function compte(request, prefix = 'e2e-pv1') {
  const email = `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@smyleplay.example`;
  const reg = await request.post('/auth/register', {
    data: { email, password: PWD, accept_terms: true, age_confirmed: true },
  });
  expect(reg.status(), `register: ${await reg.text()}`).toBe(201);
  const login = await request.post('/auth/login', { data: { email, password: PWD } });
  const { access_token: token } = await login.json();
  const me = await (await request.get('/users/me', { headers: { Authorization: `Bearer ${token}` } })).json();
  return { email, token, id: me.id, h: { Authorization: `Bearer ${token}` } };
}

// WAV PCM minimal valide (0,1 s de silence) : passe le contrôle du vrai type.
function wav() {
  const n = 800;
  const b = Buffer.alloc(44 + n);
  b.write('RIFF', 0); b.writeUInt32LE(36 + n, 4); b.write('WAVE', 8);
  b.write('fmt ', 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22);
  b.writeUInt32LE(8000, 24); b.writeUInt32LE(8000, 28); b.writeUInt16LE(1, 32); b.writeUInt16LE(8, 34);
  b.write('data', 36); b.writeUInt32LE(n, 40); b.fill(128, 44);
  return b;
}

async function sonPublie(request, c, titre) {
  await request.patch('/users/me', { headers: c.h, data: { artist_name: `Artiste ${c.id.slice(0, 6)}` } });
  const pub = await request.post('/watt/me/profile/publish', { headers: c.h });
  expect(pub.status(), await pub.text()).toBeLessThan(300);
  const up = await request.post('/watt/upload', {
    headers: c.h, multipart: { file: { name: 's.wav', mimeType: 'audio/wav', buffer: wav() }, name: titre },
  });
  expect(up.status(), await up.text()).toBe(200);
  const { key } = await up.json();
  const t = await request.post('/tracks/', {
    headers: c.h, data: { title: titre, full_prompt: 'deep house 124 bpm', r2_key: key },
  });
  expect(t.status(), await t.text()).toBe(201);
  return (await t.json()).track.id;
}

// ── Visiteur ────────────────────────────────────────────────────────────────

test('visiteur : bandeau d’inscription et inscription proposée par défaut', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const banner = page.locator('#smyle-visitor-banner');
  await expect(banner).toContainText('Crée ton compte gratuit');
  await expect(banner).toContainText('30 Smyles offerts');
  await banner.getByRole('button', { name: 'Créer mon compte' }).click();
  await expect(page.locator('#authModal')).toHaveClass(/open/);
  await expect(page.locator('#form-signup')).toBeVisible();
  await expect(page.locator('#form-login')).toBeHidden();
  await expect(page.locator('#tab-signup')).toHaveClass(/active/);
});

test('visiteur : une action refusée (401) ouvre l’inscription', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !!window.SmyleGate && !!window.apiFetch);
  await page.evaluate(() => window.apiFetch('/unlocks/prompts/00000000-0000-0000-0000-000000000000', { method: 'POST' }).catch(() => {}));
  await expect(page.locator('#authModal')).toHaveClass(/open/);
  await expect(page.locator('#form-signup')).toBeVisible();
});

test('visiteur : l’écoute s’arrête après 30 s et propose l’inscription', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !!window.SmyleGate);
  const paused = await page.evaluate(() => {
    const a = document.createElement('audio');
    document.body.appendChild(a);
    let t = 0;
    Object.defineProperty(a, 'currentTime', { get: () => t, set: (v) => { t = v; }, configurable: true });
    let pause = false;
    a.pause = () => { pause = true; };
    a.play().catch(() => {});
    t = 31;   // la lecture atteint 31 s
    a.dispatchEvent(new Event('timeupdate'));
    return pause && t === 0;
  });
  expect(paused, 'lecteur arrêté et remis au début').toBe(true);
  await expect(page.locator('#authModal')).toHaveClass(/open/);
  await expect(page.locator('#authReason')).toContainText('30 secondes');
});

test('retour exact après inscription (return= interne)', async ({ page }) => {
  await page.goto('/?auth=signup&return=%2Flibrary%3Fx%3D1', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#form-signup')).toBeVisible();
  const email = `e2e-pv1-ret-${Date.now()}@smyleplay.example`;
  await page.fill('#signup-email', email);
  await page.fill('#signup-password', PWD);
  await page.check('#signup-terms');
  await page.check('#signup-age');
  await page.locator('#form-signup button[type="submit"]').click();
  await page.waitForURL(/\/library\?x=1$/);
});

test('pas de redirection ouverte : return= externe ignoré', async ({ page, request }) => {
  const c = await compte(request);
  for (const bad of ['//evil.example/x', '/\\evil.example', 'https://evil.example/']) {
    await page.goto('/?auth=login&return=' + encodeURIComponent(bad), { waitUntil: 'domcontentloaded' });
    const safe = await page.evaluate((v) => window.SmyleGate.safeReturn(v), bad);
    expect(safe, bad).toBeNull();
  }
  await page.fill('#login-email', c.email);
  await page.fill('#login-password', PWD);
  await page.locator('#form-login button[type="submit"]').click();
  await expect(page.locator('#authArea .user-badge')).toBeVisible({ timeout: 15000 });
  expect(page.url()).not.toContain('evil');
});

test('signalement sans compte : message juste + invitation à s’inscrire', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !!window.ReportModal);
  await page.evaluate(() => window.ReportModal.open({ targetType: 'track', targetId: '00000000-0000-0000-0000-000000000000' }));
  await expect(page.locator('.rm-join')).toContainText('compte gratuit');
  // Lot D : la déclaration de bonne foi est obligatoire.
  await expect(page.locator('#rm-submit')).toBeDisabled();
  await page.locator('#rm-faith').check();
  await page.locator('#rm-submit').click();
  await expect(page.locator('#rm-err')).toContainText('ajoute une précision ou ton email');
  await expect(page.locator('#rm-err')).not.toContainText('Réessaie dans un instant');
});

// ── Compte ──────────────────────────────────────────────────────────────────

test('guide d’accueil : une seule fois, puis depuis le menu « Guide »', async ({ page, request }) => {
  test.setTimeout(90_000);
  const c = await compte(request);
  await bootSessionAuthentifiee(page, c.token, { guide: true });
  await page.addInitScript(() => { try { sessionStorage.setItem('smyle_verify_ferme', '1'); } catch (e) {} });
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const guide = page.locator('#obWelcome');
  await expect(guide).toBeVisible({ timeout: 15000 });
  await expect(guide).toContainText('Étape 1 sur');
  await expect(guide).toContainText('30');
  const n = Number((await guide.locator('.ob-count').textContent()).match(/sur (\d+)/)[1]);
  expect(n).toBeGreaterThanOrEqual(4);
  expect(n).toBeLessThanOrEqual(6);
  for (let i = 1; i < n; i++) await guide.getByRole('button', { name: 'Suivant' }).click();
  await guide.getByRole('button', { name: "C'est parti !" }).click();
  await expect(guide).toBeHidden();
  await expect.poll(async () => (await (await request.get('/users/me', { headers: c.h })).json()).onboarding_done_at)
    .not.toBeNull();
  // Nouvelle visite (nouvel onglet) : il ne revient pas tout seul.
  const p2 = await page.context().newPage();
  await p2.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(p2.locator('#authArea .user-badge')).toBeVisible({ timeout: 15000 });
  await p2.waitForTimeout(1500);
  await expect(p2.locator('#obWelcome')).toHaveCount(0);
  // … mais se rouvre depuis le menu.
  await p2.locator('#authArea .user-badge').click();
  await p2.getByRole('menuitem', { name: 'Guide' }).click();
  await expect(p2.locator('#obWelcome')).toBeVisible();
});

test('email non vérifié : « Compte créé, vérifie ta boîte mail » + Renvoyer', async ({ page, request }) => {
  const c = await compte(request);
  await request.post('/users/me/onboarding', { headers: c.h });
  await bootSessionAuthentifiee(page, c.token, { guide: true });
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const b = page.locator('#smyle-verify-banner');
  await expect(b).toContainText('Compte créé, vérifie ta boîte mail', { timeout: 15000 });
  await b.getByRole('button', { name: 'Renvoyer' }).click();
  await expect(b).toContainText(/Email renvoyé|plus tard/);
  await expect(b.getByRole('button', { name: /Renvoyer/ })).toBeDisabled();
});

test('Mes Œuvres : masquer, republier, prix borné, suppression', async ({ page, request }) => {
  const c = await compte(request);
  const titre = `Œuvre e2e ${Date.now()}`;
  const tid = await sonPublie(request, c, titre);
  await bootSessionAuthentifiee(page, c.token);
  await page.goto('/mes-oeuvres', { waitUntil: 'domcontentloaded' });
  const row = page.locator(`.mo-row[data-id="${tid}"]`);
  await expect(row).toContainText(titre, { timeout: 15000 });
  await expect(row).toContainText('Publiée');

  await row.locator('.mo-check').check();
  await page.locator('[data-bulk="masquer"]').click();
  await expect(row).toContainText('Masquée');
  const recents = await (await request.get('/watt/tracks-recent?limit=100')).json();
  expect(recents.tracks.map((t) => t.trackUuid)).not.toContain(tid);

  await page.locator(`.mo-row[data-id="${tid}"] .mo-check`).check();
  await page.locator('[data-bulk="republier"]').click();
  await expect(page.locator(`.mo-row[data-id="${tid}"]`)).toContainText('Publiée');

  await page.locator(`.mo-row[data-id="${tid}"] .mo-check`).check();
  await page.locator('[data-bulk="prix"]').click();
  await expect(page.locator('#mo-modal-box')).toContainText('Les prix montent avec la rareté et le travail de création.');
  await page.fill('#mo-price', '9');
  await page.locator('#mo-modal-box [data-ok]').click();
  await expect(page.locator('#mo-modal-box .mo-err')).toContainText('entre 10 et 150');
  await page.locator('#mo-modal-box [data-close]').first().click();

  await page.locator('[data-bulk="supprimer"]').click();
  await expect(page.locator('#mo-modal-box')).toContainText('Ton œuvre disparaît de la plateforme. Ceux qui l\'ont déjà achetée la gardent.');
  await page.locator('#mo-modal-box [data-ok]').click();
  await expect(page.locator(`.mo-row[data-id="${tid}"]`)).toHaveCount(0);
});

test('Mes Œuvres : un visiteur passe par l’inscription et revient', async ({ page }) => {
  await page.goto('/mes-oeuvres', { waitUntil: 'domcontentloaded' });
  await page.waitForURL(/\/\?auth=signup&return=%2Fmes-oeuvres/);
  await expect(page.locator('#form-signup')).toBeVisible();
});

test('déconnexion : les données personnelles du navigateur sont vidées', async ({ page, request }) => {
  const c = await compte(request);
  await request.post('/users/me/onboarding', { headers: c.h });
  // Vraie connexion par le formulaire (un jeton injecté à chaque chargement
  // reviendrait après la déconnexion).
  await page.goto('/?auth=login', { waitUntil: 'domcontentloaded' });
  await page.fill('#login-email', c.email);
  await page.fill('#login-password', PWD);
  await page.locator('#form-login button[type="submit"]').click();
  await expect(page.locator('#authArea .user-badge')).toBeVisible({ timeout: 15000 });
  await page.evaluate(() => { try { sessionStorage.setItem('smyle_verify_ferme', '1'); } catch (e) {} });
  await page.evaluate(() => {
    localStorage.setItem('smyle_plays_x', '3');
    localStorage.setItem('smyle_consent', 'granted');
  });
  await page.locator('#authArea .user-badge').click();
  await page.getByRole('menuitem', { name: 'Déconnexion' }).click();
  const etat = await page.evaluate(() => ({
    token: localStorage.getItem('smyle_api_token'),
    plays: localStorage.getItem('smyle_plays_x'),
    consent: localStorage.getItem('smyle_consent'),
    session: sessionStorage.length,
  }));
  expect(etat).toEqual({ token: null, plays: null, consent: 'granted', session: 0 });
});

test('anciennes adresses : /oeuvre.html redirige vers l’accueil', async ({ request }) => {
  const r = await request.get('/oeuvre.html', { maxRedirects: 0 });
  expect(r.status()).toBe(302);
  expect(r.headers()['location']).toBe('/');
});
