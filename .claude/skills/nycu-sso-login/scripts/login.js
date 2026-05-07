// NYCU Portal SSO login → save session for later headless reuse.
//
// Usage:
//   node login.js <username> [--headed]
//
// Env vars (optional):
//   NYCU_PASSWORD_FILE  Path to file containing password (default: $NYCU_DIR/.password)
//   NYCU_DIR            Directory for password + storage states (default: /tmp/pw-test)
//   NYCU_APP_URL        App entrypoint (default: https://ss.test.nycu.edu.tw/)
//
// Outputs:
//   $NYCU_DIR/auth-<username>.json       — Playwright storageState (cookies + localStorage)
//   $NYCU_DIR/dashboard-<username>.png   — post-login screenshot
//   $NYCU_DIR/login-failed-<username>.png — only on failure

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const username = process.argv[2];
const headed = process.argv.includes('--headed');
if (!username) {
  console.error('Usage: node login.js <username> [--headed]');
  process.exit(2);
}

const NYCU_DIR = process.env.NYCU_DIR || '/tmp/pw-test';
const PASSWORD_FILE = process.env.NYCU_PASSWORD_FILE || path.join(NYCU_DIR, '.password');
const APP_URL = process.env.NYCU_APP_URL || 'https://ss.test.nycu.edu.tw/';

if (!fs.existsSync(NYCU_DIR)) fs.mkdirSync(NYCU_DIR, { recursive: true });
if (!fs.existsSync(PASSWORD_FILE)) {
  console.error(`ERR: password file not found: ${PASSWORD_FILE}`);
  console.error('     Create it with: umask 077 && printf "<password>" > ' + PASSWORD_FILE);
  process.exit(2);
}
const password = fs.readFileSync(PASSWORD_FILE, 'utf8').replace(/\n$/, '');
const storagePath = path.join(NYCU_DIR, `auth-${username}.json`);

(async () => {
  const browser = await chromium.launch({ headless: !headed });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();

  console.log('[1/5] Loading scholarship system...');
  await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });

  console.log('[2/5] Clicking NYCU Portal login button...');
  await page.getByText('使用 NYCU Portal 登入').click();
  await page.waitForLoadState('domcontentloaded');

  console.log('[3/5] At portal. URL:', page.url());
  const userInput = page
    .locator('input[placeholder*="帳號"], input[placeholder*="account" i], input[type="text"]:visible')
    .first();
  await userInput.waitFor({ state: 'visible', timeout: 15000 });
  const passInput = page.locator('input[type="password"]').first();
  await passInput.waitFor({ state: 'visible', timeout: 15000 });

  console.log('[4/5] Filling credentials and submitting...');
  await userInput.fill(username);
  await passInput.fill(password);

  const submitCandidates = [
    'button:has-text("帳號登入")',
    'button:has-text("同意以及登入")',
    'button:has-text("登入")',
    'button:has-text("Login")',
    'button[type="submit"]',
  ];
  let clicked = false;
  for (const s of submitCandidates) {
    if (await page.locator(s).count()) {
      await page.locator(s).first().click();
      clicked = true;
      console.log('   Submit clicked:', s);
      break;
    }
  }
  if (!clicked) await passInput.press('Enter');

  // OAuth authorize step (if shown)
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  const authorizeCandidates = [
    'button:has-text("授權")',
    'button:has-text("Authorize")',
    'button:has-text("Allow")',
    'button:has-text("同意")',
    'input[value="授權"]',
    'input[value="Authorize"]',
  ];
  for (const s of authorizeCandidates) {
    if (await page.locator(s).count()) {
      console.log('   Authorize step detected, clicking:', s);
      await Promise.all([
        page.waitForLoadState('networkidle').catch(() => {}),
        page.locator(s).first().click(),
      ]);
      break;
    }
  }

  await page.waitForURL(/ss\.test\.nycu\.edu\.tw/, { timeout: 30000 }).catch(() => {});
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});

  console.log('[5/5] Final URL:', page.url(), 'Title:', await page.title());

  // Verify success: must be on the app host (not the portal) AND must not see the app login button.
  const finalHost = new URL(page.url()).hostname;
  const stillHasAppLoginBtn = await page.getByText('使用 NYCU Portal 登入').count();
  const onApp = finalHost === 'ss.test.nycu.edu.tw';

  if (!onApp || stillHasAppLoginBtn) {
    await page.screenshot({ path: path.join(NYCU_DIR, `login-failed-${username}.png`), fullPage: true });
    const reason = !onApp
      ? `still on ${finalHost} (likely credentials rejected or extra portal step required)`
      : 'app login button still visible (SSO redirect did not establish session)';
    throw new Error(`Login failed: ${reason}. Screenshot: ${path.join(NYCU_DIR, `login-failed-${username}.png`)}`);
  }

  await ctx.storageState({ path: storagePath });
  await page.screenshot({ path: path.join(NYCU_DIR, `dashboard-${username}.png`), fullPage: true });
  console.log('SUCCESS. Storage saved:', storagePath);

  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
