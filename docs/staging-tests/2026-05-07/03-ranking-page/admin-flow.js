// Admin: navigate 審核管理 → ranking page; capture deadline + nationality columns
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
  await page.screenshot({ path: path.join(OUT, '02-admin-dashboard-fresh.png'), fullPage: true });

  // Step 1: click 審核管理
  console.log('[step 1] clicking 審核管理...');
  await page.locator('button:has-text("審核管理")').first().click({ timeout: 10000 });
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '03-review-mgmt.png'), fullPage: true });
  console.log('  URL:', page.url());

  // Capture all clickables in the review mgmt view to find ranking entry
  const buttons = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('button, a, [role="tab"]'))
      .map((b) => (b.innerText || '').trim())
      .filter((t) => t && t.length < 30);
  });
  console.log('  buttons after 審核管理:', JSON.stringify(buttons.slice(0, 30)));

  // Try to find ranking-related entry — could be 排名 / 學院審核 / 評選
  const rankingCandidates = ['button:has-text("排名")', 'button:has-text("學院審核")', 'button:has-text("評選")', 'button:has-text("初審排序")', 'a:has-text("排名")'];
  let foundRanking = false;
  for (const sel of rankingCandidates) {
    const c = await page.locator(sel).count();
    if (c > 0) {
      console.log('[step 2] clicking', sel, '→ count', c);
      await page.locator(sel).first().click().catch(() => {});
      await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(OUT, '04-ranking-page.png'), fullPage: true });
      console.log('  URL after ranking click:', page.url());
      foundRanking = true;
      break;
    }
  }
  if (!foundRanking) {
    console.log('No ranking entry found via direct selectors');
  }

  // Try 學院審核 if not found
  const collegeReviewBtn = page.locator('button:has-text("學院"), a:has-text("學院")').first();
  if ((await collegeReviewBtn.count()) > 0) {
    console.log('[step 2b] clicking 學院 entry...');
    await collegeReviewBtn.click().catch(() => {});
    await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(OUT, '05-college-view.png'), fullPage: true });
  }

  fs.writeFileSync(path.join(OUT, '03-api.json'), JSON.stringify(apiCalls, null, 2));
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
