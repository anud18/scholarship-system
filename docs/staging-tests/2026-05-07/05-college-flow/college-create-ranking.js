// Create ranking and check #63 deadline banner + #68 nationality/identity columns
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

  // Step 1: Load and navigate to 學生排序
  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.locator('button:has-text("學生排序")').first().click();
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '20-before-create.png'), fullPage: true });

  // Step 2: Click 建立新排名 to create a ranking
  const createBtn = page.locator('button:has-text("建立新排名"), button:has-text("立即建立排名"), button:has-text("建立排名")');
  const createCount = await createBtn.count();
  console.log('[step 2] 建立新排名 button count:', createCount);

  if (createCount > 0) {
    console.log('  clicking 建立新排名...');
    await createBtn.first().click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(OUT, '21-after-create-click.png'), fullPage: true });

    // Check for dialog/modal that might appear for ranking creation
    const dialogText = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"], [class*="modal"], [class*="dialog"]');
      return dialog ? dialog.innerText || dialog.textContent : null;
    });
    console.log('  dialog content:', dialogText ? dialogText.slice(0, 200) : 'none');

    // Fill in dialog fields if needed (deadline dates etc.)
    const inputs = await page.locator('input[type="date"], input[type="datetime-local"]').count();
    console.log('  date inputs:', inputs);

    if (inputs > 0) {
      // Fill a deadline 7 days from now
      const deadline = new Date(Date.now() + 7 * 24 * 3600 * 1000);
      const deadlineStr = deadline.toISOString().split('T')[0];
      console.log('  filling deadline:', deadlineStr);
      await page.locator('input[type="date"], input[type="datetime-local"]').first().fill(deadlineStr);
      await page.waitForTimeout(500);
    }

    // Confirm the dialog
    const confirmBtn = page.locator('button:has-text("確認"), button:has-text("建立"), button:has-text("確定"), button[type="submit"]');
    const confirmCount = await confirmBtn.count();
    console.log('  confirm button count:', confirmCount);
    if (confirmCount > 0) {
      console.log('  clicking confirm...');
      await confirmBtn.first().click();
      await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(3000);
      await page.screenshot({ path: path.join(OUT, '22-after-confirm.png'), fullPage: true });
    }
  }

  // Step 3: Now look for ranking list and click into it
  const rankingItems = page.locator('[class*="ranking"], [class*="list-item"], button:has-text("排名")');
  const rankingCount = await rankingItems.count();
  console.log('[step 3] ranking items after creation:', rankingCount);

  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT, '23-post-create-body.txt'), bodyText);
  console.log('  page body (excerpt):\n', bodyText.slice(0, 500));

  // Step 4: Try to select/open the ranking if it was created
  const selectRanking = page.locator('select, [class*="select"], [role="option"], [class*="dropdown"]').first();
  if ((await selectRanking.count()) > 0) {
    console.log('[step 4] Found select element for ranking...');
  }

  // Look for the ranking table with columns
  await page.waitForTimeout(2000);

  // Check for any ranking entry to click
  const rankingEntry = page.locator('li:has-text("排名"), tr:has-text("排名"), [class*="ranking-item"]');
  if ((await rankingEntry.count()) > 0) {
    console.log('[step 4] Clicking first ranking entry...');
    await rankingEntry.first().click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(OUT, '24-ranking-detail.png'), fullPage: true });
  }

  // Step 5: Check #63 deadline banner after entering ranking
  const deadlineInfo = await page.evaluate(() => {
    const results = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const t = node.textContent.trim();
      if (t && (t.includes('截止') || t.includes('倒數') || t.includes('剩餘') || t.includes('deadline') ||
          (t.match(/\d+/) && (t.includes('天') || t.includes('day')) && t.length < 60))) {
        results.push(t);
      }
    }
    return [...new Set(results)].slice(0, 20);
  });
  console.log('[#63 deadline text]:', JSON.stringify(deadlineInfo));

  // Step 6: Check #68 columns
  const tableInfo = await page.evaluate(() => {
    const headers = Array.from(document.querySelectorAll('th, [role="columnheader"]'))
      .map((el) => el.textContent.trim());
    return { headers };
  });
  console.log('[#68 table headers]:', JSON.stringify(tableInfo.headers));

  const hasNationality = tableInfo.headers.some((h) => h.includes('國籍') || h.toLowerCase().includes('nationality'));
  const hasIdentity = tableInfo.headers.some((h) => h.includes('身分') || h.includes('身份'));
  console.log(`  #68 國籍 column: ${hasNationality ? '✅ present' : '❌ missing (no table yet?)'}`);
  console.log(`  #68 身分 column: ${hasIdentity ? '✅ present' : '❌ missing (no table yet?)'}`);

  // Final screenshot
  await page.screenshot({ path: path.join(OUT, '25-final.png'), fullPage: true });
  fs.writeFileSync(path.join(OUT, '25-api.json'), JSON.stringify(apiCalls, null, 2));

  console.log('[done]');
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
