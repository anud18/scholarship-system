// Recon student dashboard — what's there for 414551001?
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const NYCU_DIR = process.env.NYCU_DIR || '/tmp/pw-test';
const OUT_DIR = path.join(__dirname, 'shots');
fs.mkdirSync(OUT_DIR, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    storageState: path.join(NYCU_DIR, 'auth-414551001.json'),
    viewport: { width: 1440, height: 900 },
  });
  const page = await ctx.newPage();
  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });

  // Screenshot dashboard
  await page.screenshot({ path: path.join(OUT_DIR, '01-dashboard.png'), fullPage: true });
  console.log('STATUS:', 'dashboard captured');
  console.log('URL   :', page.url());
  console.log('TITLE :', await page.title());

  // Get all visible text-like nav items + buttons
  const nav = await page.evaluate(() => {
    const items = [];
    document.querySelectorAll('a, button, [role="menuitem"], [role="link"], [role="button"]').forEach((el) => {
      const text = (el.innerText || el.textContent || '').trim();
      if (text && text.length < 50) items.push({ tag: el.tagName, text, href: el.getAttribute('href') });
    });
    return items.slice(0, 60);
  });
  console.log('--- nav/clickables ---');
  nav.forEach((n) => console.log(`  [${n.tag}] "${n.text}"${n.href ? ' → ' + n.href : ''}`));

  // Save the link list to JSON
  fs.writeFileSync(path.join(OUT_DIR, '01-nav.json'), JSON.stringify(nav, null, 2));

  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
