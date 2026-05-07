// College reviewer: navigate to 學生排序 and check #63 deadline banner + #68 nationality/identity columns
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
    storageState: path.join(NYCU_DIR, 'auth-A00002.json'),
    viewport: { width: 1440, height: 900 },
  });
  const page = await ctx.newPage();

  const apiCalls = [];
  page.on('response', (r) => {
    const u = r.url();
    if (u.includes('/api/v1/')) apiCalls.push({ status: r.status(), url: u });
  });

  // Step 1: Load dashboard
  console.log('[step 1] Loading college dashboard...');
  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '10-college-dashboard.png'), fullPage: true });
  console.log('  URL:', page.url());

  // Step 2: Click 學生排序
  console.log('[step 2] clicking 學生排序...');
  const rankBtn = page.locator('button:has-text("學生排序")');
  const c = await rankBtn.count();
  console.log('  學生排序 count:', c);

  if (c > 0) {
    await rankBtn.first().click();
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(OUT, '11-ranking-page.png'), fullPage: true });
    console.log('  URL after 學生排序:', page.url());
  } else {
    console.log('  學生排序 button not found — trying URL direct nav...');
    await page.goto('https://ss.test.nycu.edu.tw/college/ranking', { waitUntil: 'networkidle' }).catch(() => {});
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(OUT, '11-ranking-direct.png'), fullPage: true });
  }

  // Step 3: Full page content dump for analysis
  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT, '11-ranking-body.txt'), bodyText);
  console.log('[ranking body excerpt]:\n', bodyText.slice(0, 600));

  // Step 4: Check #63 — deadline banner
  // Look for: countdown timer, deadline date, warning banners, "截止", "剩餘", "天後"
  const deadlineElements = await page.evaluate(() => {
    const results = [];
    // Check for banner-like elements with deadline content
    const selectors = [
      '[class*="deadline"]',
      '[class*="banner"]',
      '[class*="alert"]',
      '[class*="warning"]',
      '[data-testid*="deadline"]',
    ];
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach((el) => {
        const t = el.innerText || el.textContent || '';
        if (t.trim()) results.push({ selector: sel, text: t.trim().slice(0, 100) });
      });
    }
    // Also text-scan
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const t = node.textContent.trim();
      if (t && (t.includes('截止') || t.includes('倒數') || t.includes('剩餘') || (t.match(/\d+\s*天/) && t.length < 50))) {
        results.push({ selector: 'text-node', text: t });
      }
    }
    return results;
  });
  console.log('[#63 deadline check]:', JSON.stringify(deadlineElements.slice(0, 10)));

  // Step 5: Check #68 — nationality + identity columns in table
  const tableInfo = await page.evaluate(() => {
    const headers = Array.from(document.querySelectorAll('th, [role="columnheader"]'))
      .map((el) => el.textContent.trim());
    const cells = Array.from(document.querySelectorAll('td'))
      .map((el) => el.textContent.trim())
      .filter((t) => t.length > 0 && t.length < 30);
    return { headers, sampleCells: cells.slice(0, 30) };
  });
  console.log('[#68 table headers]:', JSON.stringify(tableInfo.headers));
  console.log('[#68 sample cells]:', JSON.stringify(tableInfo.sampleCells.slice(0, 15)));

  const hasNationality = tableInfo.headers.some((h) => h.includes('國籍') || h.toLowerCase().includes('nationality'));
  const hasIdentity = tableInfo.headers.some((h) => h.includes('身分') || h.includes('身份'));
  console.log(`  #68 國籍 column: ${hasNationality ? '✅ present' : '❌ missing'}`);
  console.log(`  #68 身分 column: ${hasIdentity ? '✅ present' : '❌ missing'}`);

  // Step 6: Save all API calls
  fs.writeFileSync(path.join(OUT, '12-api.json'), JSON.stringify(apiCalls, null, 2));

  await page.screenshot({ path: path.join(OUT, '13-final.png'), fullPage: true });
  console.log('[done]');
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
