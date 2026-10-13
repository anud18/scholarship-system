// Multi-college end-to-end verification: ranking -> distribution -> roster.
// Drives the real frontend UI as each college reviewer + admin, and uses the
// DB as ground truth at each step. Encodes the #1029 / #1034 regression check:
// finalizing one college's ranking must NOT un-finalize the others, and admin
// distribution must see ALL colleges (not just the last finalized one). It also
// checks the lock collapse: finalizing deletes the SAME college's other draft
// rankings for the period (never another college's), leaving exactly one.
//
// Run (from the skill scripts/ dir, dev stack up):
//   NODE_PATH=$(npm root -g) \
//   COLLEGES='A:hum_college,B:bio_college,C:cs_college,E:ee_college' \
//   TYPE_TAB='博士生獎學金' YEAR_LABEL='114 學年度' SEM_LABEL='全年' \
//   OUT=/tmp/mc-verify node verify-multi-college-distribution.js
//
// Notes / gotchas this script bakes in (do not "fix" them away):
//  * Auth restore needs BOTH auth_token AND a user blob in localStorage
//    (frontend/hooks/use-auth.tsx) — same contract as build-storage-state.sh.
//    Token-only => silently bounced to /dev-login.
//  * College "建立排名" (empty state) / "建立新排名" (header) creates a NEW draft
//    for the config's first sub-type, which is "default" (aggregates ALL
//    sub-types). distribution reads every finalized ranking regardless of
//    sub_type, so "default" is fine. Both are blocked (disabled / HTTP 409)
//    while the college already has a locked ranking for the period.
//  * Match "確認排名" with exact:true — the ranking cards' lock toggle is
//    labelled "確認排名（鎖定）" and may belong to a different draft.
//  * The admin distribution panel defaults to the FIRST semester, which often
//    has no data -> empty grid. You MUST select the correct semester (全年 for
//    yearly cycles) or the grid is empty and finalize finds nothing.
//  * The 所屬學院 filter <option>s are hidden; never wait on a college name to
//    be "visible" — wait on the visible 儲存目前配置 button instead.

const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

const FE = process.env.FE || 'http://localhost:3000';
const API = process.env.API || 'http://localhost:8000';
const OUT = process.env.OUT || `/tmp/mc-verify-${process.pid}`;
const ADMIN = process.env.ADMIN || 'admin';
const TYPE_TAB = process.env.TYPE_TAB || '博士生獎學金';
const YEAR_LABEL = process.env.YEAR_LABEL || '114 學年度';
const SEM_LABEL = process.env.SEM_LABEL || '全年';
// "A:hum_college,B:bio_college,..." -> [{code,user}]
const COLLEGES = (process.env.COLLEGES || 'A:hum_college,B:bio_college,C:cs_college,E:ee_college')
  .split(',').map(s => { const [code, user] = s.split(':'); return { code: code.trim(), user: user.trim() }; });

fs.mkdirSync(OUT, { recursive: true });
const DBQ = path.join(__dirname, 'db-query.sh');
const log = [];
const say = m => { const l = `[${new Date().toISOString()}] ${m}`; console.log(l); log.push(l); };

// Single-value query. psql -c prints header, value, then the row count; strip the
// decoration (header / '----' / '(1 row)') — the value row is the 2nd remaining line.
function queryValue(sql) {
  const out = execFileSync('bash', [DBQ, sql], { encoding: 'utf8' });
  const line = out.split('\n').map(s => s.trim()).filter(s => s && !s.startsWith('-') && !/^\(/.test(s));
  return line[1] || '';
}

// Ground-truth: which colleges currently hold a finalized ranking.
function finalizedColleges() {
  const val = queryValue(
    "SELECT string_agg(DISTINCT college_code, ',' ORDER BY college_code) FROM college_rankings WHERE is_finalized IS TRUE;");
  return val.split(',').map(s => s.trim()).filter(Boolean).sort();
}

// Lock collapse: rankings of this college that share a period (type, sub-type,
// year, semester) with its finalized ranking. Finalizing deletes them, so 0.
function siblingsOfFinalized(code) {
  if (!/^[A-Za-z0-9_]+$/.test(code)) throw new Error(`unexpected college code: ${code}`);
  return Number(queryValue(`SELECT count(*) FROM college_rankings f
      JOIN college_rankings r ON r.id <> f.id
       AND r.college_code = f.college_code
       AND r.scholarship_type_id = f.scholarship_type_id
       AND r.sub_type_code = f.sub_type_code
       AND r.academic_year = f.academic_year
       AND COALESCE(r.semester, 'yearly') = COALESCE(f.semester, 'yearly')
     WHERE f.is_finalized IS TRUE AND f.college_code = '${code}';`));
}

async function mockAuth(request, nycu_id) {
  const r = await request.post(`${API}/api/v1/auth/mock-sso/login`, { data: { nycu_id } });
  const j = await r.json();
  if (!j.success) throw new Error(`mock-sso login failed for ${nycu_id}: ${JSON.stringify(j)}`);
  return { token: j.data.access_token, user: j.data.user };
}

async function authedContext(browser, auth) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1300 }, locale: 'zh-TW' });
  await ctx.addInitScript(a => {
    localStorage.setItem('auth_token', a.token);
    localStorage.setItem('user', JSON.stringify(a.user));
    localStorage.setItem('dev_user', JSON.stringify(a.user));
  }, auth);
  return ctx;
}

async function finalizeCollege(browser, c, idx) {
  say(`=== College ${c.code} (${c.user}): create + finalize ranking ===`);
  const ctx = await authedContext(browser, await mockAuth(browser.__req, c.user));
  const page = await ctx.newPage();
  try {
    await page.goto(`${FE}/`, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: '學生排序' }).first().click({ timeout: 30000 });
    await page.getByRole('heading', { name: /學生排序管理/ }).first().waitFor({ timeout: 30000 });
    // The college page defaults to the CURRENT academic year (115 since the AY115
    // seed); switch the period selector to the year/semester under test.
    await page.getByRole('combobox').first().click({ timeout: 15000 });
    await page.getByRole('option', { name: `${YEAR_LABEL} ${SEM_LABEL}` }).first().click({ timeout: 15000 });
    await page.waitForTimeout(1000);
    // The empty-state "建立排名" only renders while the college has no ranking
    // for the period; otherwise an existing ranking (locked first, else the
    // newest draft) is auto-opened and gets finalized instead.
    const create = page.getByRole('button', { name: '建立排名', exact: true }).first();
    const needsCreate = await create.waitFor({ state: 'visible', timeout: 5000 }).then(() => true, () => false);
    if (needsCreate) await create.click({ timeout: 30000 });
    const finalize = page.getByRole('button', { name: '確認排名', exact: true }).first();
    await finalize.waitFor({ timeout: 30000 });
    await page.waitForTimeout(1500);
    await finalize.click();
    // With other drafts in the period, finalizing first asks to delete them;
    // without any it locks straight away (toast 「排名已鎖定…」).
    const collapse = page.getByRole('button', { name: '確認並刪除其他排名' }).first();
    const locked = page.getByText(/排名已鎖定|此排名已確認/).first();
    await collapse.or(locked).first().waitFor({ timeout: 30000 });
    if (await collapse.isVisible()) {
      say(`  College ${c.code}: confirming deletion of its other draft rankings`);
      await collapse.click({ timeout: 15000 });
      await locked.waitFor({ timeout: 30000 });
    }
    await page.screenshot({ path: `${OUT}/college-${c.code}-finalized.png`, fullPage: true });
    say(`  College ${c.code} finalized OK`);
  } catch (e) {
    await page.screenshot({ path: `${OUT}/college-${c.code}-ERROR.png`, fullPage: true });
    throw new Error(`College ${c.code} finalize failed: ${e.message}`);
  } finally { await ctx.close(); }

  // #1034 regression: every college finalized so far must STILL be finalized.
  const got = finalizedColleges();
  const want = COLLEGES.slice(0, idx + 1).map(x => x.code).sort();
  const missing = want.filter(x => !got.includes(x));
  say(`  finalized colleges now=[${got}] expected superset of [${want}]`);
  if (missing.length) throw new Error(`REGRESSION (#1034): finalizing ${c.code} dropped colleges ${missing}`);
  const siblings = siblingsOfFinalized(c.code);
  if (siblings !== 0) throw new Error(`lock collapse: college ${c.code} still has ${siblings} other ranking(s) next to its finalized one`);
}

async function adminDistributeAndRoster(browser) {
  say('=== Admin: distribution + roster ===');
  const ctx = await authedContext(browser, await mockAuth(browser.__req, ADMIN));
  const page = await ctx.newPage();
  const res = { collegesSeen: [], distribution: null, roster: null };
  try {
    await page.goto(`${FE}/`, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: '獎學金分發' }).first().click({ timeout: 30000 });
    try { await page.getByRole('tab', { name: new RegExp(TYPE_TAB) }).first().click({ timeout: 8000 }); } catch (_) {}
    await page.getByRole('heading', { name: /手動分發/ }).first().waitFor({ timeout: 30000 });
    // Native <select>s — pick year + semester so the grid actually loads.
    const yearSel = page.locator('select').filter({ has: page.locator('option', { hasText: '選擇學年度' }) }).first();
    const semSel = page.locator('select').filter({ has: page.locator('option', { hasText: '選擇學期' }) }).first();
    await yearSel.selectOption({ label: YEAR_LABEL });
    await semSel.selectOption({ label: SEM_LABEL });
    // Grid populated <=> the visible 儲存目前配置 button renders (NOT the hidden college <option>s).
    await page.getByRole('button', { name: '儲存目前配置' }).first().waitFor({ timeout: 30000 });
    await page.waitForTimeout(1500);
    const filterSel = page.locator('select').filter({ has: page.locator('option', { hasText: '全部學院' }) }).first();
    res.collegesSeen = await filterSel.locator('option').evaluateAll(os => os.map(o => o.value).filter(Boolean));
    say(`  distribution grid colleges=[${res.collegesSeen}]`);
    await page.screenshot({ path: `${OUT}/distribution-allcolleges.png`, fullPage: true });

    await page.getByRole('button', { name: '儲存目前配置' }).first().click({ timeout: 15000 });
    await page.waitForTimeout(2500);
    await page.getByRole('button', { name: /確認分發/ }).first().click({ timeout: 20000 });
    await page.getByText('確認執行分發？').first().waitFor({ timeout: 15000 });
    await page.getByRole('button', { name: '確認執行' }).first().click({ timeout: 15000 });
    const dm = page.getByText(/分發完成：核准/).first();
    await dm.waitFor({ timeout: 40000 });
    res.distribution = (await dm.textContent())?.trim();
    say(`  ${res.distribution}`);
    await page.screenshot({ path: `${OUT}/distribution-done.png`, fullPage: true });

    await page.getByRole('button', { name: '生成造冊' }).first().click({ timeout: 15000 });
    await page.getByText('確認產生造冊？').first().waitFor({ timeout: 15000 });
    await page.getByRole('button', { name: '確認產生' }).first().click({ timeout: 15000 });
    await page.waitForTimeout(3000);
    // Strip psql decoration (header / '----' / '(1 row)') the same way finalizedColleges does —
    // a naive /\d+/g .pop() would grab the "1" from "(1 row)", not the real count.
    res.roster = queryValue('SELECT count(*) FROM payment_rosters;');
    say(`  payment_rosters=${res.roster}`);
    await page.screenshot({ path: `${OUT}/roster.png`, fullPage: true });
  } catch (e) {
    await page.screenshot({ path: `${OUT}/admin-ERROR.png`, fullPage: true });
    res.error = e.message;
  } finally { await ctx.close(); }
  return res;
}

(async () => {
  say(`pre-run finalized=[${finalizedColleges()}]  (expect empty for a clean run)`);
  const browser = await chromium.launch({ headless: true });
  browser.__req = (await browser.newContext()).request;
  const summary = { ok: false };
  try {
    for (let i = 0; i < COLLEGES.length; i++) await finalizeCollege(browser, COLLEGES[i], i);
    summary.admin = await adminDistributeAndRoster(browser);
    const finalized = finalizedColleges();
    const codes = COLLEGES.map(c => c.code).sort();
    summary.allFinalized = codes.every(c => finalized.includes(c));
    summary.distributionSeesAll = summary.admin && codes.every(c => summary.admin.collegesSeen.includes(c));
    summary.ok = summary.allFinalized && summary.distributionSeesAll && !!summary.admin.distribution && !summary.admin.error;
    say(`FINAL finalized=[${finalized}] allFinalized=${summary.allFinalized} distributionSeesAll=${summary.distributionSeesAll}`);
  } catch (e) { summary.error = e.message; say(`FATAL ${e.message}`); }
  finally { await browser.close(); }
  fs.writeFileSync(`${OUT}/result.json`, JSON.stringify(summary, null, 2));
  fs.writeFileSync(`${OUT}/log.txt`, log.join('\n'));
  say(`RESULT ok=${summary.ok}  (artifacts in ${OUT})`);
  process.exit(summary.ok ? 0 : 1);
})().catch(e => { console.error('FATAL (pre-run/launch):', e); process.exit(1); });
