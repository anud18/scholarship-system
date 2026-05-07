// Headless reuse of a saved NYCU SSO session.
//
// Usage:
//   node with-session.js <username> [url] [--headed]
//
// Loads $NYCU_DIR/auth-<username>.json (created by login.js), navigates,
// prints status/title and a 400-char body excerpt, and saves a screenshot.
//
// Use this as a starting template — copy and adapt for specific test flows.

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const username = process.argv[2];
const url = process.argv[3] && !process.argv[3].startsWith('--')
  ? process.argv[3]
  : (process.env.NYCU_APP_URL || 'https://ss.test.nycu.edu.tw/');
const headed = process.argv.includes('--headed');

if (!username) {
  console.error('Usage: node with-session.js <username> [url] [--headed]');
  process.exit(2);
}

const NYCU_DIR = process.env.NYCU_DIR || '/tmp/pw-test';
const storagePath = path.join(NYCU_DIR, `auth-${username}.json`);
if (!fs.existsSync(storagePath)) {
  console.error(`ERR: no saved session for ${username}: ${storagePath}`);
  console.error('     Run: node login.js ' + username);
  process.exit(2);
}

(async () => {
  const browser = await chromium.launch({ headless: !headed });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, storageState: storagePath });
  const page = await ctx.newPage();

  const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  console.log('STATUS:', resp && resp.status());
  console.log('URL   :', page.url());
  console.log('TITLE :', await page.title());

  const stillHasLogin = await page.getByText('使用 NYCU Portal 登入').count();
  console.log('SESSION:', stillHasLogin ? 'EXPIRED — re-run login.js' : 'OK');

  const shot = path.join(NYCU_DIR, `session-${username}-${Date.now()}.png`);
  await page.screenshot({ path: shot, fullPage: true });
  console.log('SHOT  :', shot);

  const body = (await page.locator('body').innerText()).slice(0, 400);
  console.log('--- BODY (first 400 chars) ---\n' + body);

  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
