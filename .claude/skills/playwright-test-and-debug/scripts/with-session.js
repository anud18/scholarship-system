// Load a Playwright storageState JSON, navigate to URL, dump title + body excerpt + screenshot.
// Usage:
//   NODE_PATH=$(npm root -g) node with-session.js <storageState.json> <url> [out.png]

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const [, , storagePath, url, outArg] = process.argv;
if (!storagePath || !url) {
  console.error('Usage: node with-session.js <storageState.json> <url> [out.png]');
  process.exit(2);
}
if (!fs.existsSync(storagePath)) {
  console.error('ERR: storage file not found:', storagePath);
  process.exit(2);
}
const out = outArg || `/tmp/session-${Date.now()}.png`;

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    storageState: storagePath,
    viewport: { width: 1440, height: 900 },
  });
  const page = await ctx.newPage();
  const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  console.log('STATUS:', resp && resp.status());
  console.log('URL   :', page.url());
  console.log('TITLE :', await page.title());
  await page.screenshot({ path: out, fullPage: true });
  console.log('SHOT  :', out);
  const body = (await page.locator('body').innerText()).slice(0, 400);
  console.log('--- BODY (first 400 chars) ---');
  console.log(body);
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
