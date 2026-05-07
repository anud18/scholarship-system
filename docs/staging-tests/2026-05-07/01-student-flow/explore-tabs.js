// Click through student tabs, screenshot each
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
    storageState: path.join(NYCU_DIR, 'auth-414551001.json'),
    viewport: { width: 1440, height: 900 },
  });
  const page = await ctx.newPage();
  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  const tabs = ['獎學金列表', '學生申請', '我的申請'];
  for (const tabName of tabs) {
    console.log('--- clicking tab:', tabName);
    // Try multiple locator strategies — staging may use tab role or just buttons
    const btn = page.locator(`button:has-text("${tabName}"), [role="tab"]:has-text("${tabName}")`).first();
    await btn.click({ timeout: 15000 });
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(1500);
    const safeName = tabName.replace(/[^a-zA-Z0-9]/g, '_');
    await page.screenshot({ path: path.join(OUT, `02-tab-${safeName}.png`), fullPage: true });
    console.log('  URL:', page.url());

    // Capture body text excerpt
    const bodyText = (await page.locator('main, body').first().innerText()).slice(0, 1500);
    fs.writeFileSync(path.join(OUT, `02-tab-${safeName}.txt`), bodyText);

    // List clickable buttons in tab content
    const buttons = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('button:not([disabled])'))
        .map((b) => (b.innerText || '').trim())
        .filter((t) => t && t.length < 30);
    });
    console.log('  buttons:', JSON.stringify(buttons.slice(0, 25)));
  }

  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
