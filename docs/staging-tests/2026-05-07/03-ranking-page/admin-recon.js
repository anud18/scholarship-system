// Admin recon — what does E00001 see?
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const NYCU_DIR = process.env.NYCU_DIR || '/tmp/pw-test';
const OUT = path.join(__dirname, 'shots');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    storageState: path.join(NYCU_DIR, 'auth-E00001.json'),
    viewport: { width: 1440, height: 900 },
  });
  const page = await ctx.newPage();

  const apiCalls = [];
  page.on('response', (r) => {
    const u = r.url();
    if (u.includes('/api/v1/')) apiCalls.push({ status: r.status(), url: u });
  });

  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '01-admin-dashboard.png'), fullPage: true });

  // Capture all visible buttons / nav
  const nav = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('button, [role="tab"], a'))
      .map((el) => ({ tag: el.tagName, text: (el.innerText || el.textContent || '').trim(), href: el.getAttribute('href') }))
      .filter((n) => n.text && n.text.length < 40);
  });
  fs.writeFileSync(path.join(OUT, '01-nav.json'), JSON.stringify(nav, null, 2));
  console.log('top buttons:');
  nav.slice(0, 20).forEach((n) => console.log(`  [${n.tag}] "${n.text}"`));

  fs.writeFileSync(path.join(OUT, '01-api.json'), JSON.stringify(apiCalls, null, 2));
  console.log('---');
  console.log('URL:', page.url());
  console.log('TITLE:', await page.title());
  console.log('API calls:', apiCalls.length);
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
