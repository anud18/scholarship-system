// Open year combobox, switch to 114, open ranking, check #63 + #68
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const NYCU_DIR = process.env.NYCU_DIR || '/tmp/pw-test';
const OUT = path.join(__dirname, 'shots');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
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

  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.locator('button:has-text("學生排序")').first().click();
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(2000);

  // Step 1: Click the year combobox ("115 全年")
  console.log('[step 1] clicking year combobox...');
  await page.locator('button[role="combobox"]:has-text("115")').first().click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(OUT, '40-combobox-open.png'), fullPage: true });

  // Step 2: Inspect all visible options
  const options = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('[role="option"], [role="listbox"] li, [role="listbox"] [role="option"]'))
      .map((el) => ({ text: el.textContent.trim(), value: el.getAttribute('data-value') || el.getAttribute('value') }));
  });
  console.log('  combobox options:', JSON.stringify(options));

  // Step 3: Click 114 option
  const opt114 = page.locator('[role="option"]:has-text("114"), [role="listbox"] li:has-text("114")');
  const optCount = await opt114.count();
  console.log(`  114 option count: ${optCount}`);

  if (optCount > 0) {
    await opt114.first().click();
    await page.waitForTimeout(2000);
    console.log('  switched to 114');
  } else {
    // Try any visible text containing 114
    const anyOpt = page.locator(':visible:has-text("114 全年"), :visible:has-text("114学年")');
    if ((await anyOpt.count()) > 0) {
      await anyOpt.first().click();
      await page.waitForTimeout(2000);
    } else {
      console.log('  114 option not found — staying on 115');
    }
  }

  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  await page.screenshot({ path: path.join(OUT, '41-year-114.png'), fullPage: true });

  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT, '41-body.txt'), bodyText);
  console.log('[body excerpt]:\n', bodyText.slice(0, 500));

  // Step 4: Try to open a 114 ranking
  const rankingCard = page.locator('[class*="card"]:has-text("114"), li:has-text("114 全年"), div:has-text("114 全年"):not(:has(div))');
  if ((await rankingCard.count()) > 0) {
    console.log('[step 4] clicking 114 ranking card...');
    await rankingCard.first().click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(OUT, '42-ranking-detail.png'), fullPage: true });
  } else {
    // Look for clickable items with 114
    const allText = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('*')).filter((el) => {
        const t = (el.textContent || '').trim();
        return t.includes('114') && t.length < 50 && el.children.length === 0;
      }).map((el) => ({ tag: el.tagName, text: el.textContent.trim() }));
    });
    console.log('  114 leaf elements:', JSON.stringify(allText.slice(0, 10)));
  }

  // Step 5: #63 deadline banner check
  const deadlineBanner = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll('[class*="alert"], [class*="banner"], [role="alert"], [class*="deadline"], [class*="countdown"]').forEach((el) => {
      const t = (el.innerText || '').trim();
      if (t) results.push({ class: el.className.slice(0, 80), text: t.slice(0, 200) });
    });
    // Text scan
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const t = node.textContent.trim();
      if (t && (t.includes('截止') || t.includes('剩餘') || t.includes('倒數') || t.match(/\d+\s*天/))) {
        results.push({ class: 'TEXT', text: t });
      }
    }
    return [...new Set(results.map((r) => r.text))].slice(0, 20);
  });
  console.log('[#63 deadline]:', JSON.stringify(deadlineBanner));

  // Step 6: #68 columns
  const headers = await page.evaluate(() =>
    Array.from(document.querySelectorAll('th, [role="columnheader"]')).map((el) => el.textContent.trim())
  );
  console.log('[#68 headers]:', JSON.stringify(headers));
  console.log(`  國籍/身分 column: ${headers.some((h) => h.includes('國籍') || h.includes('身分')) ? '✅ present' : '❌ absent'}`);

  await page.screenshot({ path: path.join(OUT, '43-final.png'), fullPage: true });
  fs.writeFileSync(path.join(OUT, '43-api.json'), JSON.stringify(apiCalls, null, 2));
  console.log('[done]');
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
