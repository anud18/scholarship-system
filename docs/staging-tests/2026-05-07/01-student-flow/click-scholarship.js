// Click into 博士生獎學金 card to reach application form
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const NYCU_DIR = process.env.NYCU_DIR || '/tmp/pw-test';
const OUT = path.join(__dirname, 'shots');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    storageState: path.join(NYCU_DIR, 'auth-414551001.json'),
    viewport: { width: 1440, height: 900 },
  });
  const page = await ctx.newPage();

  // Capture network for clues
  const apiCalls = [];
  page.on('response', (r) => {
    const url = r.url();
    if (url.includes('/api/v1/')) apiCalls.push({ status: r.status(), url });
  });

  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // Look for any clickable card mentioning 博士生獎學金 or 申請
  const cardCandidates = [
    'text=博士生獎學金',
    'button:has-text("申請")',
    'text=查看詳情',
    'text=立即申請',
    'a:has-text("詳情")',
  ];
  for (const sel of cardCandidates) {
    const loc = page.locator(sel).first();
    if (await loc.count()) {
      console.log('FOUND:', sel, '→ count', await page.locator(sel).count());
    }
  }

  // Click "博士生獎學金" tile (try the heading link / button)
  const cardTitle = page.locator('text=博士生獎學金').first();
  if (await cardTitle.count()) {
    console.log('Clicking "博士生獎學金"...');
    await cardTitle.click();
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(2000);
    console.log('URL after click:', page.url());
    await page.screenshot({ path: path.join(OUT, '03-scholarship-detail.png'), fullPage: true });
  }

  // Look for any "開始申請" / "申請" button now
  const applyBtn = page.locator('button:has-text("申請"), button:has-text("開始申請"), button:has-text("立即申請")').first();
  if (await applyBtn.count()) {
    const txt = (await applyBtn.innerText()).trim();
    console.log('Apply button found:', txt);
    await applyBtn.click().catch((e) => console.log('apply click failed:', e.message));
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(2000);
    console.log('URL after apply click:', page.url());
    await page.screenshot({ path: path.join(OUT, '04-apply-step1.png'), fullPage: true });
    const body = await page.locator('main, body').first().innerText();
    fs.writeFileSync(path.join(OUT, '04-apply-step1.txt'), body.slice(0, 3000));
  } else {
    console.log('No apply button visible after card click');
  }

  // Save api call log
  fs.writeFileSync(path.join(OUT, '03-api-calls.json'), JSON.stringify(apiCalls, null, 2));
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
