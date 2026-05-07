// Debug: open combobox and dump full DOM including portals
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const NYCU_DIR = process.env.NYCU_DIR || '/tmp/pw-test';
const OUT = path.join(__dirname, 'shots');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: false });  // visible for debugging
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    storageState: path.join(NYCU_DIR, 'auth-A00002.json'),
    viewport: { width: 1440, height: 900 },
  });
  const page = await ctx.newPage();

  await page.goto('https://ss.test.nycu.edu.tw/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.locator('button:has-text("學生排序")').first().click();
  await page.waitForTimeout(2000);

  // Click combobox
  await page.locator('button[role="combobox"]:has-text("全年"), button[role="combobox"]:has-text("115")').first().click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(OUT, '50-combobox-open.png'), fullPage: true });

  // Dump ALL text visible on page after combobox click (including portal elements)
  const allText = await page.evaluate(() => {
    const allEl = Array.from(document.querySelectorAll('*'));
    return allEl
      .filter((el) => {
        const t = (el.textContent || '').trim();
        return t.length > 0 && t.length < 50 && el.children.length === 0;
      })
      .map((el) => ({
        tag: el.tagName,
        role: el.getAttribute('role'),
        class: (el.className || '').slice(0, 40),
        text: el.textContent.trim(),
      }))
      .filter((x) => x.text.match(/11[0-9]/) || x.role === 'option' || x.role === 'listbox');
  });
  console.log('dropdown items after combobox click:', JSON.stringify(allText));

  // Try pressing down arrow and reading
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(500);
  const focusedText = await page.evaluate(() => document.activeElement ? document.activeElement.textContent : 'none');
  console.log('focused after ArrowDown:', focusedText);

  // Check for popover/listbox in body
  const listbox = await page.evaluate(() => {
    const lb = document.querySelector('[role="listbox"]');
    return lb ? lb.innerHTML.slice(0, 500) : 'no listbox';
  });
  console.log('listbox HTML:', listbox);

  await page.screenshot({ path: path.join(OUT, '51-after-arrow.png'), fullPage: true });
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
