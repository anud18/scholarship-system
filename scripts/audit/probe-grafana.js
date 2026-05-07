// Read-only Playwright probe. Reuses /tmp/pw-test/auth-grafana-admin.json.
// Usage: node probe-grafana.js [--dashboard <uid>] [--out <dir>]
// Default behavior: enumerate datasources + dashboards, screenshot home + each
// dashboard, dump panel JSON to api-responses dir.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const NYCU_DIR = process.env.NYCU_DIR || '/tmp/pw-test';
const OUT = process.env.AUDIT_OUT_DIR ||
  path.resolve(__dirname, '../../docs/superpowers/audits/working');
const STATE = path.join(NYCU_DIR, 'auth-grafana-admin.json');
const BASE = 'https://ss.test.nycu.edu.tw/monitoring';

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    storageState: STATE,
    viewport: { width: 1600, height: 1200 },
  });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });

  const ds = await page.evaluate(async () => {
    const list = await (await fetch('/monitoring/api/datasources', { credentials: 'include' })).json();
    const out = [];
    for (const d of list) {
      const r = await fetch(`/monitoring/api/datasources/uid/${d.uid}/health`, { credentials: 'include' });
      const body = await r.json().catch(() => ({}));
      out.push({ uid: d.uid, name: d.name, type: d.type, http: r.status, status: body.status, message: body.message });
    }
    return out;
  });
  fs.writeFileSync(path.join(OUT, 'api-responses/grafana/datasources-health.json'),
    JSON.stringify(ds, null, 2));

  const dashboards = await page.evaluate(async () => {
    const r = await fetch('/monitoring/api/search?type=dash-db&limit=200', { credentials: 'include' });
    return r.json();
  });
  fs.writeFileSync(path.join(OUT, 'api-responses/grafana/dashboards-list.json'),
    JSON.stringify(dashboards, null, 2));

  for (const d of dashboards) {
    const detail = await page.evaluate(async (uid) => {
      const r = await fetch(`/monitoring/api/dashboards/uid/${uid}`, { credentials: 'include' });
      return r.json();
    }, d.uid);
    fs.writeFileSync(
      path.join(OUT, `api-responses/grafana/dashboard-${d.uid}.json`),
      JSON.stringify(detail, null, 2)
    );
    await page.goto(`${BASE}/d/${d.uid}/${d.uri ? d.uri.split('/').pop() : ''}?kiosk`, {
      waitUntil: 'networkidle', timeout: 45000
    }).catch(() => {});
    await page.waitForTimeout(4000);
    await page.screenshot({
      path: path.join(OUT, `screenshots/grafana/dashboard-${d.uid}.png`),
      fullPage: true,
    });
  }

  // Alerting view
  await page.goto(`${BASE}/alerting/list`, { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(2500);
  await page.screenshot({
    path: path.join(OUT, 'screenshots/grafana/alerting-list.png'),
    fullPage: true,
  });

  await browser.close();
  console.log('grafana probe complete; outputs under', OUT);
})().catch(e => { console.error(e); process.exit(1); });
