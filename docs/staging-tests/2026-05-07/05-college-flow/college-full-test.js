// Full college ranking test: switch to 114, open ranking, check #63 deadline banner + #68 columns
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

  // Navigate to 學生排序
  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.locator('button:has-text("學生排序")').first().click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '60-ranking-115.png'), fullPage: true });
  console.log('[step 1] 學生排序 loaded (115 default)');

  // Switch year to 114 using keyboard: click combobox → ArrowDown → Enter
  console.log('[step 2] switching to 114...');
  await page.locator('button[role="combobox"]').first().click();
  await page.waitForTimeout(600);
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(300);

  // Check what's focused
  const focusedText = await page.evaluate(() => document.activeElement ? document.activeElement.textContent.trim() : '');
  console.log('  focused element:', focusedText);

  if (focusedText.includes('114')) {
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);
    console.log('  selected 114');
  } else {
    // Try clicking "114 學年度 全年" option directly via text
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    // Use Radix select approach: open and click the 114 option
    await page.locator('button[role="combobox"]').first().click();
    await page.waitForTimeout(600);
    // The listbox options — use more specific Playwright selector
    const opt = page.locator('[role="listbox"] [role="option"]:has-text("114")');
    if ((await opt.count()) > 0) {
      await opt.first().click();
      await page.waitForTimeout(2000);
      console.log('  clicked 114 option via listbox');
    } else {
      // fallback: press ArrowDown until we hit 114, then Enter
      for (let i = 0; i < 10; i++) {
        await page.keyboard.press('ArrowDown');
        await page.waitForTimeout(100);
        const t = await page.evaluate(() => document.activeElement ? document.activeElement.textContent.trim() : '');
        if (t.includes('114')) {
          await page.keyboard.press('Enter');
          await page.waitForTimeout(2000);
          console.log('  selected 114 via arrow loop at step', i);
          break;
        }
      }
    }
  }

  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  await page.screenshot({ path: path.join(OUT, '61-year-switched.png'), fullPage: true });

  // Check current year shown
  const yearShown = await page.locator('button[role="combobox"]').first().textContent();
  console.log('[year selector now shows]:', yearShown);

  // Step 3: Try to click a 114 ranking card if available
  console.log('[step 3] looking for 114 ranking cards...');
  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT, '61-body.txt'), bodyText);
  console.log('  body excerpt:\n', bodyText.slice(0, 400));

  // Click on first 114 ranking card
  const rankCards = page.locator('h3:has-text("114"), div:has-text("114 全年"):not(:has(div)), li:has-text("114")');
  const rankCount = await rankCards.count();
  console.log(`  ranking cards with 114: ${rankCount}`);

  if (rankCount > 0) {
    await rankCards.first().click({ force: true }).catch(() => {});
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(OUT, '62-ranking-detail.png'), fullPage: true });
  }

  // Step 4: #63 — Deadline banner check
  const deadlineBanner = await page.evaluate(() => {
    const results = [];
    // Check for colored alert/warning/banner elements
    document.querySelectorAll('[class*="alert"], [class*="banner"], [class*="warn"], [class*="deadline"], [role="alert"], [class*="countdown"]').forEach((el) => {
      const t = (el.innerText || el.textContent || '').trim();
      if (t) results.push(t.slice(0, 200));
    });
    // Text scan for deadline patterns
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const t = node.textContent.trim();
      if (t && (t.includes('截止') || t.includes('倒數') || t.includes('剩餘') || t.includes('排名截止') ||
          t.match(/\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}/))) {
        results.push(t);
      }
    }
    return [...new Set(results)].slice(0, 15);
  });
  console.log('\n[#63 deadline check]:', JSON.stringify(deadlineBanner));

  // Step 5: #68 — table column check
  const tableHeaders = await page.evaluate(() =>
    Array.from(document.querySelectorAll('th, [role="columnheader"]')).map((el) => el.textContent.trim())
  );
  console.log('[#68 table headers]:', JSON.stringify(tableHeaders));
  const hasNat = tableHeaders.some((h) => h.includes('國籍'));
  const hasId = tableHeaders.some((h) => h.includes('身分') || h.includes('身份'));
  console.log(`  國籍 column: ${hasNat ? '✅ present' : '❌ absent (ranking table not open?)'}`);
  console.log(`  身分 column: ${hasId ? '✅ present' : '❌ absent'}`);

  // Step 6: Try opening an existing ranking from the 115 list and clicking it
  // (The 115 ranking we created earlier should have the table)
  if (tableHeaders.length === 0) {
    console.log('[step 6] switching back to 115 to open the ranking with table...');
    await page.locator('button[role="combobox"]').first().click();
    await page.waitForTimeout(600);
    const opt115 = page.locator('[role="listbox"] [role="option"]:has-text("115")');
    if ((await opt115.count()) > 0) {
      await opt115.first().click();
      await page.waitForTimeout(2000);
    } else {
      await page.keyboard.press('Escape');
    }
    // Click the 115 ranking card
    const card115 = page.locator('h3:has-text("115 全年"), div[class*="card"]:has-text("115 全年")');
    if ((await card115.count()) > 0) {
      await card115.first().click({ force: true }).catch(() => {});
      await page.waitForTimeout(2000);
    }
    await page.screenshot({ path: path.join(OUT, '63-115-ranking-open.png'), fullPage: true });

    const headers2 = await page.evaluate(() =>
      Array.from(document.querySelectorAll('th, [role="columnheader"]')).map((el) => el.textContent.trim())
    );
    console.log('[#68 table headers (115 ranking)]:', JSON.stringify(headers2));
    console.log(`  國籍 column: ${headers2.some((h) => h.includes('國籍')) ? '✅ present' : '❌ absent'}`);
    console.log(`  身分 column: ${headers2.some((h) => h.includes('身分')) ? '✅ present' : '❌ absent'}`);
  }

  await page.screenshot({ path: path.join(OUT, '64-final.png'), fullPage: true });
  fs.writeFileSync(path.join(OUT, '64-api.json'), JSON.stringify(apiCalls, null, 2));
  console.log('[done]');
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
