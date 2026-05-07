// Select existing 115 ranking, verify #68 columns and #63 deadline banner
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

  console.log('[step 1] Looking for ranking cards...');
  // Get all visible clickable elements
  const clickables = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('[class*="cursor-pointer"], [class*="cursor-default"], button, a'))
      .map((el) => {
        const t = (el.innerText || el.textContent || '').trim();
        const c = (typeof el.className === 'string') ? el.className.slice(0, 60) : '';
        return { tag: el.tagName, class: c, text: t.slice(0, 60) };
      })
      .filter((x) => x.text.length > 0 && x.text.length < 60 && x.text.includes('115'));
  });
  console.log('  115-related clickables:', JSON.stringify(clickables.slice(0, 10)));

  // Try clicking with different approaches
  // Approach 1: find the card's inner clickable part
  const cardInner = page.locator('[class*="cursor-pointer"]:has-text("博士生獎學金 - 115 全年")');
  let count = await cardInner.count();
  console.log(`  cursor-pointer cards with "115 全年": ${count}`);

  if (count > 0) {
    // Click the first one and wait longer
    await cardInner.first().click({ force: true });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(OUT, '80-clicked-card.png'), fullPage: true });
  }

  // Check if detail appeared
  let body = await page.evaluate(() => document.body.innerText);
  const hasDetail = body.includes('申請排名') || body.includes('確認排名') || body.includes('匯入排名');
  console.log('  ranking detail visible:', hasDetail);

  if (!hasDetail) {
    // Try: look for the radio button or select button on the card
    const radioOrSelect = page.locator('[type="radio"], button:has-text("選擇"), button:has-text("查看")');
    const rCount = await radioOrSelect.count();
    console.log(`  radio/select buttons: ${rCount}`);
    if (rCount > 0) {
      await radioOrSelect.first().click({ force: true });
      await page.waitForTimeout(3000);
    }

    // Try clicking the H3 title inside card
    const h3 = page.locator('h3:has-text("博士生獎學金 - 115 全年")');
    if ((await h3.count()) > 0) {
      await h3.first().click({ force: true });
      await page.waitForTimeout(3000);
    }

    body = await page.evaluate(() => document.body.innerText);
    console.log('  detail visible after h3 click:', body.includes('申請排名'));
  }

  await page.screenshot({ path: path.join(OUT, '81-after-various-clicks.png'), fullPage: true });

  // Step 2: Check for the ranking detail in the body
  fs.writeFileSync(path.join(OUT, '81-body.txt'), body);

  // Extract relevant lines
  const lines = body.split('\n').filter((l) => l.trim().length > 0);
  const rankIdx = lines.findIndex((l) => l.includes('申請排名') || l.includes('排名\t') || l.includes('國籍'));
  if (rankIdx >= 0) {
    console.log('[ranking detail excerpt]:\n', lines.slice(rankIdx, rankIdx + 15).join('\n'));
  }

  // #68 check via text
  const col68 = body.includes('國籍') && (body.includes('身分') || body.includes('身份'));
  console.log(`[#68] 國籍/身分 columns in body text: ${col68 ? '✅ YES' : '❌ NO'}`);

  // Also check specific line
  const headerLine = lines.find((l) => l.includes('排名') && l.includes('學生') && l.includes('學號'));
  if (headerLine) {
    console.log('[#68] Header line:', headerLine);
    console.log(`  國籍 in header: ${headerLine.includes('國籍') ? '✅' : '❌'}`);
    console.log(`  身分 in header: ${headerLine.includes('身分') ? '✅' : '❌'}`);
  }

  // #63 deadline banner check
  const deadlineTexts = lines.filter((l) =>
    l.includes('截止') || l.includes('倒數') || l.includes('剩餘') ||
    l.match(/20\d{2}\/\d{1,2}\/\d{1,2}/) || l.includes('排名截止')
  );
  console.log('[#63] deadline-related lines:', JSON.stringify(deadlineTexts.slice(0, 10)));

  // Step 3: Test with 114 period to trigger deadline banner
  console.log('\n[step 3] Switch to 114 to test deadline banner...');
  await page.locator('button[role="combobox"]').first().click();
  await page.waitForTimeout(600);
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(300);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(2000);

  // Create a 114 ranking
  const btn114 = page.locator('button:has-text("建立新排名"), button:has-text("立即建立排名")');
  if ((await btn114.count()) > 0) {
    await btn114.first().click();
    await page.waitForTimeout(1000);
    const confirm = page.locator('button:has-text("確認"), button:has-text("確定")');
    if ((await confirm.count()) > 0) {
      await confirm.first().click();
      await page.waitForTimeout(3000);
    }
  }

  await page.screenshot({ path: path.join(OUT, '82-114-ranking.png'), fullPage: true });
  const body114 = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT, '82-body-114.txt'), body114);

  const lines114 = body114.split('\n').filter((l) => l.trim().length > 0);
  const deadlineLines = lines114.filter((l) =>
    l.includes('截止') || l.includes('倒數') || l.includes('剩餘') ||
    l.match(/20\d{2}[\/\-]\d{1,2}[\/\-]\d{1,2}/) || l.includes('排名截止') || l.includes('排名時間')
  );
  console.log('[#63 114-year deadline-related lines]:', JSON.stringify(deadlineLines.slice(0, 10)));

  // Is the deadline from config showing?
  const hasDeadlineBanner = body114.includes('排名截止') || body114.includes('排名截止時間') || body114.includes('截止時間將至');
  console.log(`[#63] deadline banner present: ${hasDeadlineBanner ? '✅ YES' : '❌ NO (likely no config for 115 period)'}`);

  // Check columns in 114 ranking
  const headerLine114 = lines114.find((l) => l.includes('排名') && l.includes('學生') && l.includes('學號'));
  if (headerLine114) {
    console.log('[#68 on 114] Header line:', headerLine114);
    console.log(`  國籍: ${headerLine114.includes('國籍') ? '✅' : '❌'}`);
    console.log(`  身分: ${headerLine114.includes('身分') ? '✅' : '❌'}`);
  }

  await page.screenshot({ path: path.join(OUT, '83-final.png'), fullPage: true });
  fs.writeFileSync(path.join(OUT, '83-api.json'), JSON.stringify(apiCalls, null, 2));
  console.log('[done]');
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
