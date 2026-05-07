// College reviewer: navigate dashboard → ranking page; check #63 deadline banner, #68 columns
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

  // Step 1: Dashboard
  console.log('[step 1] Loading college dashboard...');
  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '01-college-dashboard.png'), fullPage: true });
  console.log('  URL:', page.url());
  console.log('  Title:', await page.title());

  const nav = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('button, [role="tab"], a, [role="menuitem"]'))
      .map((el) => ({ tag: el.tagName, text: (el.innerText || el.textContent || '').trim() }))
      .filter((n) => n.text && n.text.length < 40 && n.text.length > 0);
  });
  fs.writeFileSync(path.join(OUT, '01-nav.json'), JSON.stringify(nav, null, 2));
  console.log('  nav items:', nav.slice(0, 20).map((n) => `[${n.tag}] "${n.text}"`).join(', '));

  // Step 2: Find and click 院區審核 / 排名 / 學院 type nav
  const rankingCandidates = [
    'button:has-text("院區審核")',
    'button:has-text("排名")',
    'button:has-text("審核")',
    'a:has-text("院區審核")',
    'a:has-text("排名")',
    '[role="menuitem"]:has-text("院區")',
  ];

  let clickedRanking = false;
  for (const sel of rankingCandidates) {
    const c = await page.locator(sel).count();
    if (c > 0) {
      console.log(`[step 2] clicking "${sel}" (count ${c})...`);
      await page.locator(sel).first().click().catch(() => {});
      await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(OUT, '02-ranking-click.png'), fullPage: true });
      console.log('  URL after click:', page.url());
      clickedRanking = true;
      break;
    }
  }

  if (!clickedRanking) {
    console.log('[step 2] No ranking nav found; dumping all clickables...');
    console.log('  ALL nav:', JSON.stringify(nav));
  }

  // Step 3: Look for scholarship tabs (博士生 / 學士班)
  const scholarshipTabs = [
    'button:has-text("博士生")',
    'button:has-text("學士班")',
    '[role="tab"]:has-text("博士")',
    '[role="tab"]:has-text("學士")',
  ];
  for (const sel of scholarshipTabs) {
    const c = await page.locator(sel).count();
    if (c > 0) {
      console.log(`[step 3] clicking scholarship tab "${sel}"...`);
      await page.locator(sel).first().click().catch(() => {});
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(OUT, '03-scholarship-tab.png'), fullPage: true });
      break;
    }
  }

  // Step 4: Check for deadline banner (#63) — look for deadline-related text
  const deadlineText = await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const texts = [];
    let node;
    while ((node = walker.nextNode())) {
      const t = node.textContent.trim();
      if (t && (t.includes('截止') || t.includes('deadline') || t.includes('倒數') || t.includes('剩餘') || t.includes('天') && t.length < 30)) {
        texts.push(t);
      }
    }
    return [...new Set(texts)].slice(0, 20);
  });
  console.log('[check #63] deadline-related text nodes:', JSON.stringify(deadlineText));

  // Step 5: Check for nationality/identity columns (#68) — look for 國籍 / 身分 in table headers
  const tableHeaders = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('th, [role="columnheader"], thead td'))
      .map((el) => el.textContent.trim())
      .filter((t) => t.length > 0);
  });
  console.log('[check #68] table headers:', JSON.stringify(tableHeaders));

  const hasNationality = tableHeaders.some((h) => h.includes('國籍') || h.includes('nationality'));
  const hasIdentity = tableHeaders.some((h) => h.includes('身分') || h.includes('身份') || h.includes('identity'));
  console.log(`  国籍 column present: ${hasNationality}`);
  console.log(`  身分 column present: ${hasIdentity}`);

  // Step 6: Full page text capture for debugging
  const bodyText = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT, '06-body-text.txt'), bodyText.slice(0, 5000));

  // Save API calls
  fs.writeFileSync(path.join(OUT, '05-api.json'), JSON.stringify(apiCalls, null, 2));

  await page.screenshot({ path: path.join(OUT, '07-final-state.png'), fullPage: true });
  console.log('[done] screenshots saved to', OUT);
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
