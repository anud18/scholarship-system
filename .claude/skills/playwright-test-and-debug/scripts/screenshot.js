// Quick fullPage screenshot of any URL.
// Usage:
//   NODE_PATH=$(npm root -g) node screenshot.js <url> [out.png] [width] [height]
// Defaults: out=shot.png, viewport=1440x900.

const { chromium } = require('playwright');

const [, , url, out = 'shot.png', wRaw = '1440', hRaw = '900'] = process.argv;
if (!url) {
  console.error('Usage: node screenshot.js <url> [out.png] [width] [height]');
  process.exit(2);
}
const width = Number(wRaw);
const height = Number(hRaw);

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width, height }, ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  await page.screenshot({ path: out, fullPage: true });
  console.log('saved:', out, '(' + width + 'x' + height + ')');
  await browser.close();
})().catch((e) => {
  console.error('ERR:', e.message);
  process.exit(1);
});
