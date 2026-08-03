/**
 * Manual CSP verification driver for issue #1273.
 *
 * Runs against a PRODUCTION build (`next build && next start`) — the dev CSP
 * branch is deliberately relaxed, so only a production server exercises the
 * nonce-gated `style-src` + `style-src-attr 'unsafe-inline'` split.
 *
 * Captures every `securitypolicyviolation` event (the only reliable signal —
 * some blocked styles never reach console) plus console errors, across the
 * public login page and authenticated pages that render Radix
 * Dialog/Dropdown/Select portals (the primitives commit bc2019f0 broke).
 *
 * Usage: node e2e/csp-violation-check.js <frontendUrl> <backendUrl> <outDir>
 */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND = process.argv[2] || "http://localhost:3100";
const BACKEND = process.argv[3] || "http://localhost:8000";
const OUT_DIR = process.argv[4] || "test-results/screenshots";

const violations = [];
const consoleErrors = [];

async function mockSsoLogin(nycuId) {
  const r = await fetch(`${BACKEND}/api/v1/auth/mock-sso/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nycu_id: nycuId }),
  });
  const body = await r.json();
  if (!r.ok || !body.success) {
    throw new Error(`mock-sso login failed for ${nycuId}: HTTP ${r.status}`);
  }
  return { token: body.data.access_token, user: body.data.user };
}

async function visit(page, label, urlPath, interact) {
  console.log(`\n--- ${label} (${urlPath}) ---`);
  await page.goto(`${FRONTEND}${urlPath}`, { waitUntil: "networkidle" }).catch((e) => {
    console.log(`  nav warning: ${e.message.split("\n")[0]}`);
  });
  await page.waitForTimeout(1500);
  if (interact) {
    try {
      await interact(page);
    } catch (e) {
      console.log(`  interact warning: ${e.message.split("\n")[0]}`);
    }
  }
  await page.waitForTimeout(800);
  await page
    .screenshot({ path: path.join(OUT_DIR, `csp-${label}.png`), fullPage: false })
    .catch(() => {});
  console.log(`  violations so far: ${violations.length}`);
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({ locale: "zh-TW" });
  context.setDefaultTimeout(8000);

  // Record CSP violations from the page itself — console-only capture misses
  // style-src blocks in some Chromium versions.
  await context.addInitScript(() => {
    window.__cspViolations = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      window.__cspViolations.push({
        directive: e.effectiveDirective || e.violatedDirective,
        blockedURI: e.blockedURI,
        sample: (e.sample || "").slice(0, 120),
        source: `${e.sourceFile || ""}:${e.lineNumber || ""}`,
      });
    });
  });

  const page = await context.newPage();
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text().slice(0, 200));
  });

  async function drain(label) {
    const v = await page.evaluate(() => {
      const out = window.__cspViolations || [];
      window.__cspViolations = [];
      return out;
    }).catch(() => []);
    v.forEach((x) => violations.push({ page: label, ...x }));
  }

  // 1. Public login page (unauthenticated)
  await visit(page, "login", "/");
  await drain("login");

  // 2. Authenticate as admin, then exercise Radix-heavy pages
  const { token, user } = await mockSsoLogin("admin");
  console.log(`\nlogged in as: ${user.email || user.username}`);
  await context.addInitScript(
    ({ t, u }) => {
      localStorage.setItem("auth_token", t);
      localStorage.setItem("user", u);
    },
    { t: token, u: JSON.stringify(user) }
  );

  // The app is a single authenticated route ("/"), rendered by role.
  await visit(page, "admin-home", "/", async (p) => {
    const els = await p.$$eval('button,[role],a', (ns) =>
      ns
        .map((n) => ({
          role: n.getAttribute("role") || n.tagName.toLowerCase(),
          t: (n.innerText || "").trim().slice(0, 20),
        }))
        .filter((x) => x.t)
        .slice(0, 30)
    );
    console.log(`  roles: ${JSON.stringify(els)}`);
  });
  await drain("admin-home");

  // Radix Tabs — navigates the admin shell without a reload
  await visit(page, "admin-tabs", "/", async (p) => {
    const tabs = p.locator('[role="tab"]');
    const n = await tabs.count();
    console.log(`  tabs: ${n}`);
    for (let i = 1; i < Math.min(n, 5); i++) {
      await tabs.nth(i).click().catch(() => {});
      await p.waitForTimeout(900);
    }
  });
  await drain("admin-tabs");

  // Radix Select/Combobox — its floating panel is positioned with INLINE STYLE
  // ATTRIBUTES, the exact thing style-src-attr must keep allowing.
  await visit(page, "admin-dropdown", "/", async (p) => {
    const combo = p.locator('button[role="combobox"]').first();
    if (await combo.count()) {
      await combo.click();
      await p.waitForTimeout(800);
      const opened = await p.locator('[role="listbox"],[role="option"]').count();
      console.log(`  combobox opened, options visible: ${opened}`);
      await p.keyboard.press("ArrowDown");
      await p.keyboard.press("Escape");
    } else {
      console.log("  no combobox on this page");
    }
  });
  await drain("admin-dropdown");

  // Radix Dialog — the heaviest style injector (react-remove-scroll scroll-lock
  // + portal animation). Walk the admin tabs until a trigger actually opens one.
  await visit(page, "admin-dialog", "/", async (p) => {
    const tabs = p.locator('[role="tab"]');
    const tabCount = await tabs.count();
    let opened = false;
    for (let t = 0; t < tabCount && !opened; t++) {
      await tabs.nth(t).click().catch(() => {});
      await p.waitForTimeout(1200);
      const triggers = p
        .locator("button")
        .filter({ hasText: /新增|建立|設定|編輯|查看|詳情|上傳|匯入|產生|管理/ });
      const n = Math.min(await triggers.count(), 6);
      for (let i = 0; i < n && !opened; i++) {
        await triggers.nth(i).click({ timeout: 3000 }).catch(() => {});
        await p.waitForTimeout(1200);
        opened = (await p.locator('[role="dialog"]').count()) > 0;
        if (opened) {
          const tabName = (await tabs.nth(t).innerText().catch(() => "?")).trim();
          console.log(`  dialog opened from tab "${tabName}" trigger #${i}`);
          // scroll-lock proof: react-remove-scroll's stylesheet must have applied
          const locked = await p.evaluate(
            () => getComputedStyle(document.body).overflow
          );
          console.log(`  body overflow while dialog open: ${locked} (expect hidden)`);
        }
      }
    }
    if (!opened) console.log("  WARNING: no dialog could be opened");
  });
  await drain("admin-dialog");

  // Force a toast so sonner's hashed stylesheet is proven to APPLY, not merely
  // to stop violating. Rendering unstyled toasts is the silent failure mode.
  await visit(page, "toast", "/", async (p) => {
    await p.evaluate(() => {
      // sonner exposes no global; trigger via a real API failure instead —
      // an unauthenticated fetch the app surfaces as an error toast.
      window.dispatchEvent(new Event("offline"));
    });
    const anyTrigger = p.locator("button").filter({ hasText: /重新整理|重整|更新|重載/ }).first();
    if (await anyTrigger.count()) await anyTrigger.click().catch(() => {});
    await p.waitForTimeout(2000);
    const state = await p.evaluate(() => {
      const el = document.querySelector("[data-sonner-toaster]");
      if (!el) return { present: false };
      const cs = getComputedStyle(el);
      return { present: true, position: cs.position, zIndex: cs.zIndex };
    });
    console.log(`  sonner toaster: ${JSON.stringify(state)}`);
    // Independent of any toast firing: the stylesheet itself must be live.
    const sheetApplied = await p.evaluate(() => {
      for (const sheet of document.styleSheets) {
        try {
          for (const rule of sheet.cssRules) {
            if (rule.cssText && rule.cssText.includes("data-sonner-toaster")) return true;
          }
        } catch {
          /* cross-origin sheet */
        }
      }
      return false;
    });
    console.log(`  sonner CSS rules live in document.styleSheets: ${sheetApplied}`);
    if (!sheetApplied) throw new Error("sonner stylesheet was NOT applied");
  });
  await drain("toast");

  await visit(page, "admin-renewal", "/admin/renewal");
  await drain("admin-renewal");

  await browser.close();

  console.log("\n================ RESULT ================");
  console.log(`CSP violations: ${violations.length}`);
  violations.forEach((v) =>
    console.log(`  [${v.page}] ${v.directive} blocked=${v.blockedURI} sample="${v.sample}"`)
  );
  console.log(`\nconsole errors: ${consoleErrors.length}`);
  consoleErrors.slice(0, 15).forEach((e) => console.log(`  ${e}`));

  const styleViolations = violations.filter((v) => (v.directive || "").startsWith("style-src"));
  console.log(`\nstyle-src violations: ${styleViolations.length}`);
  process.exit(styleViolations.length > 0 ? 1 : 0);
})();
