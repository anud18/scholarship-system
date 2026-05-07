// Inspect ranking table DOM structure + check deadline banner on 114
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

  // Step 1: Go to 學生排序 → open the 115 ranking (we know it exists with a table)
  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.locator('button:has-text("學生排序")').first().click();
  await page.waitForTimeout(2000);

  console.log('[step 1] Click the 進行中 ranking card...');
  // Click the ranking card — it's a div/card with "進行中" badge and "博士生獎學金 - 115 全年"
  const cardSel = page.locator('div:has-text("進行中"):has-text("博士生獎學金 - 115 全年")').first();
  if ((await cardSel.count()) > 0) {
    await cardSel.click({ force: true }).catch(() => {});
    await page.waitForTimeout(2000);
    console.log('  clicked card');
  } else {
    // Try clicking button with the text
    const btn = page.locator('button:has-text("博士生獎學金 - 115 全年"), [class*="cursor"]:has-text("115 全年")');
    if ((await btn.count()) > 0) {
      await btn.first().click({ force: true }).catch(() => {});
      await page.waitForTimeout(2000);
      console.log('  clicked button');
    }
  }
  await page.screenshot({ path: path.join(OUT, '70-ranking-opened.png'), fullPage: true });

  // Step 2: Dump body text to confirm table is showing
  const body = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT, '70-body.txt'), body);
  const hasRankingTable = body.includes('排名') && body.includes('學號');
  console.log('  ranking table visible in text:', hasRankingTable);
  if (hasRankingTable) {
    // Extract the table section
    const tableIdx = body.indexOf('排名\t');
    console.log('  table section:', body.slice(tableIdx, tableIdx + 200));
  }

  // Step 3: Find what tags the header cells use
  const headerElements = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('th, [role="columnheader"], thead *, [class*="header"] *, [class*="thead"] *'))
      .map((el) => ({
        tag: el.tagName,
        role: el.getAttribute('role'),
        class: (el.className || '').slice(0, 60),
        text: (el.textContent || '').trim().slice(0, 30),
      }))
      .filter((x) => x.text.length > 0);
  });
  console.log('[table header elements]:', JSON.stringify(headerElements.slice(0, 15)));

  // Step 4: Check the actual columns in the table via body text parsing
  const columns = [];
  const lines = body.split('\n');
  for (const line of lines) {
    if (line.includes('排名') && line.includes('學生') && line.includes('學號')) {
      // This looks like the header row
      console.log('[#68] header row found:', line.trim());
      if (line.includes('國籍') || line.includes('身分')) {
        console.log('  ✅ 國籍/身分 column present in header row');
      }
      break;
    }
  }

  // Also scan tab-separated column headers
  const tableSection = body.slice(body.indexOf('排名'));
  const firstLine = tableSection.split('\n')[0];
  console.log('[#68] first table line:', firstLine);

  // Step 5: Test deadline banner on 114 — create a 114 ranking
  console.log('\n[step 5] Switch to 114 and create ranking to test #63 deadline...');
  await page.locator('button[role="combobox"]').first().click();
  await page.waitForTimeout(600);
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(300);
  const focused = await page.evaluate(() => document.activeElement ? document.activeElement.textContent.trim() : '');
  if (focused.includes('114')) {
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);
  }

  const yearNow = await page.locator('button[role="combobox"]').first().textContent();
  console.log('  year now:', yearNow);

  // Create a 114 ranking
  const createBtn = page.locator('button:has-text("建立新排名"), button:has-text("立即建立排名")');
  if ((await createBtn.count()) > 0) {
    await createBtn.first().click();
    await page.waitForTimeout(2000);
    // Confirm if needed
    const confirmBtn = page.locator('button:has-text("確認"), button:has-text("確定")');
    if ((await confirmBtn.count()) > 0) {
      await confirmBtn.first().click();
      await page.waitForTimeout(2000);
    }
  }

  // Click the 114 ranking card
  const card114 = page.locator('div:has-text("博士生獎學金 - 114 全年")').first();
  if ((await card114.count()) > 0) {
    await card114.click({ force: true }).catch(() => {});
    await page.waitForTimeout(2000);
  }

  await page.screenshot({ path: path.join(OUT, '71-114-ranking-open.png'), fullPage: true });

  // Step 6: Check deadline banner
  const deadlineBanners = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll('[class*="alert"], [class*="banner"], [class*="warn"], [class*="deadline"], [class*="countdown"], [role="alert"], [class*="border-"]').forEach((el) => {
      const t = (el.innerText || '').trim();
      if (t && t.length < 300 && (t.includes('截止') || t.includes('剩餘') || t.includes('排名') || t.match(/\d{4}/) )) {
        results.push({ class: (el.className || '').slice(0, 80), text: t });
      }
    });
    return results;
  });
  console.log('\n[#63 deadline banners]:', JSON.stringify(deadlineBanners.slice(0, 5)));

  const body114 = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT, '71-body-114.txt'), body114);

  // Look for date in body text
  const datePattern = /20\d{2}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}/g;
  const dates = [...body114.matchAll(datePattern)].map((m) => m[0]);
  console.log('  dates found in body:', [...new Set(dates)]);

  // Step 7: Check 114 ranking table columns
  const headers114 = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('th, [role="columnheader"]')).map((el) => el.textContent.trim());
  });
  console.log('[#68 114 ranking headers]:', JSON.stringify(headers114));

  await page.screenshot({ path: path.join(OUT, '72-final.png'), fullPage: true });
  fs.writeFileSync(path.join(OUT, '72-api.json'), JSON.stringify(apiCalls, null, 2));
  console.log('[done]');
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
