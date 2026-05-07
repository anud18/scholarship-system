// Switch to 114学年 PhD ranking to trigger deadline banner (#63) and check columns (#68)
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

  // Step 1: Load dashboard and go to 學生排序
  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.locator('button:has-text("學生排序")').first().click();
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '30-ranking-default.png'), fullPage: true });

  // Step 2: Find the year/period selector and switch to 114
  console.log('[step 2] Looking for period selector...');
  const allButtons = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('button, select, [role="option"], [role="combobox"]'))
      .map((el) => ({ tag: el.tagName, text: (el.innerText || el.textContent || '').trim(), role: el.getAttribute('role') }))
      .filter((n) => n.text && n.text.length < 30);
  });
  console.log('  period-like buttons:', JSON.stringify(allButtons.filter((b) => b.text.match(/11[0-9]|全年|第/))));

  // Try to click something that switches to 114
  const periodCandidates = [
    'button:has-text("114")',
    '[role="option"]:has-text("114")',
    'select',
  ];

  for (const sel of periodCandidates) {
    const c = await page.locator(sel).count();
    if (c > 0) {
      console.log(`  found period control "${sel}" count ${c}`);
      const el = page.locator(sel).first();
      if (sel === 'select') {
        // Try to select 114 option
        const options = await page.evaluate(() => {
          return Array.from(document.querySelectorAll('select option')).map((o) => ({ value: o.value, text: o.textContent }));
        });
        console.log('  select options:', JSON.stringify(options));
        const opt114 = options.find((o) => o.text.includes('114'));
        if (opt114) {
          await el.selectOption({ value: opt114.value });
        }
      } else {
        await el.click();
      }
      await page.waitForTimeout(2000);
      break;
    }
  }

  await page.screenshot({ path: path.join(OUT, '31-period-switched.png'), fullPage: true });

  // Step 3: Check if there are existing rankings for 114
  const bodyText = await page.evaluate(() => document.body.innerText);
  console.log('[body excerpt]:\n', bodyText.slice(0, 400));
  fs.writeFileSync(path.join(OUT, '31-body.txt'), bodyText);

  // Step 4: Click existing 114 ranking or create new one
  const rankingItems = page.locator('li:has-text("114"), div:has-text("114学年"):not(:has(div)), [class*="ranking-item"]:has-text("114")');
  const rankingCount = await rankingItems.count();
  console.log('[step 4] 114 ranking items:', rankingCount);

  // Look for ranking list entries
  const listItems = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('[class*="card"], [class*="list-item"], li'))
      .map((el) => el.textContent.trim().slice(0, 80))
      .filter((t) => t.includes('114') || t.includes('博士'));
  });
  console.log('  114-related list items:', JSON.stringify(listItems.slice(0, 5)));

  // Step 5: Check #63 deadline banner — look for colored banners
  const banners = await page.evaluate(() => {
    const results = [];
    // Look for alert/banner elements
    document.querySelectorAll('[class*="alert"], [class*="banner"], [class*="deadline"], [class*="warning"], [role="alert"]').forEach((el) => {
      const t = (el.innerText || el.textContent || '').trim();
      if (t) results.push({ tag: el.tagName, class: el.className.slice(0, 60), text: t.slice(0, 150) });
    });
    // Text scan for deadline-related content
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const t = node.textContent.trim();
      if (t && (t.includes('截止') || t.includes('倒數') || t.includes('07月') || t.includes('7月') || t.includes('剩餘'))) {
        results.push({ tag: 'TEXT', text: t });
      }
    }
    return results;
  });
  console.log('[#63 deadline banners]:', JSON.stringify(banners.slice(0, 10)));

  // Step 6: #68 column check
  const headers = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('th, [role="columnheader"]')).map((el) => el.textContent.trim());
  });
  console.log('[#68 table headers]:', JSON.stringify(headers));

  const hasNationality = headers.some((h) => h.includes('國籍') || h.toLowerCase().includes('nationality'));
  const hasIdentity = headers.some((h) => h.includes('身分') || h.includes('身份'));
  console.log(`  #68 國籍 column: ${hasNationality ? '✅ present' : '❌ missing'}`);
  console.log(`  #68 身分 column: ${hasIdentity ? '✅ present' : '❌ missing'}`);

  await page.screenshot({ path: path.join(OUT, '32-final.png'), fullPage: true });
  fs.writeFileSync(path.join(OUT, '32-api.json'), JSON.stringify(apiCalls, null, 2));
  console.log('[done]');
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
