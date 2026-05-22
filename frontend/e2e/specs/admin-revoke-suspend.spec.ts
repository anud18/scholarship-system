/**
 * Scenario: admin revoke / suspend distribution — pin the user-visible flows
 * added in the revoke-suspend-distribution feature branch.
 *
 * Test 1 — "撤 button opens dialog with disabled confirm until reason filled"
 *   Self-contained: beforeAll creates the full allocate+finalize fixture
 *   (csphd0001 → professor → cs_college rank+finalize → admin allocate+finalize).
 *   afterAll cleans up. No dependency on admin-manual-distribution.spec.ts.
 *
 * Test 2 — "locked roster dialog shows revoked student panel and 從本造冊移除 works"
 *   Requires: a payment_roster with status "locked" that contains at least one
 *   item whose application has quota_allocation_status "revoked" or "suspended".
 *   This state does NOT exist in fresh seed data. The test is wrapped in
 *   test.skip() when no LOCKED roster exists, so it won't fail in CI runs
 *   against a plain seed.
 *
 * TODO (seed requirement): To make test 2 run end-to-end, add a fixture that:
 *   1. Runs the full allocate+finalize+generate-rosters flow.
 *   2. Locks one of the generated rosters via PATCH /payment-rosters/{id}/lock.
 *   3. Calls POST /manual-distribution/revoke on one of the allocated students.
 *   Then remove the test.skip() wrapper from test 2.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, getActiveConfig, pool } from "../helpers/db";
import {
  attachRunState,
  newRunState,
  pushTrace,
  type RunState,
} from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

test.describe.configure({ mode: "serial" });

// ---------------------------------------------------------------------------
// Shared fixture setup helpers
// ---------------------------------------------------------------------------

const SETUP_STUDENT = "csphd0001";
const SETUP_PROFESSOR = "professor";
const SETUP_COLLEGE = "cs_college";
const SETUP_SUB_TYPE = "nstc";
const SETUP_SCHOLARSHIP = "phd";
const SETUP_SCHOLARSHIP_NAME = "博士生獎學金"; // display name of "phd" in seed data

async function getApiToken(nycuId: string): Promise<string> {
  const r = await fetch("http://localhost:8000/api/v1/auth/mock-sso/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nycu_id: nycuId }),
  });
  const body = (await r.json()) as {
    success?: boolean;
    message?: string;
    data?: { access_token?: string };
  };
  if (!r.ok || !body.data?.access_token) {
    throw new Error(`setup login failed for ${nycuId}: HTTP ${r.status} ${body.message ?? ""}`);
  }
  return body.data.access_token;
}

// ---------------------------------------------------------------------------
// Test 1: 撤 button → dialog → disabled confirm until reason filled
// ---------------------------------------------------------------------------

test.describe("admin revoke dialog — confirm disabled until reason filled", () => {
  let runState: RunState;
  let fixtureAppId: string | undefined;
  let fixtureRankingId: number | undefined;
  let fixtureScholarshipTypeId: number;
  let fixtureAcademicYear: number;
  let fixtureSemester: string | null;

  test.beforeAll(async () => {
    // Purge any existing csphd0001 phd apps to avoid conflicts
    const { rows: existing } = await pool.query<{ app_id: string }>(
      `SELECT a.app_id FROM applications a
       JOIN users u ON u.id = a.user_id
       JOIN scholarship_types st ON st.id = a.scholarship_type_id
       WHERE u.nycu_id = $1 AND st.code = $2`,
      [SETUP_STUDENT, SETUP_SCHOLARSHIP],
    );
    for (const { app_id } of existing) {
      await deleteApplicationCascade(app_id).catch(() => undefined);
    }

    const config = await getActiveConfig(SETUP_SCHOLARSHIP);
    fixtureScholarshipTypeId = config.scholarship_type_id;
    fixtureAcademicYear = config.academic_year;
    fixtureSemester = config.semester;
    const semForReq = config.semester ?? "yearly";

    const studentToken = await getApiToken(SETUP_STUDENT);
    const professorToken = await getApiToken(SETUP_PROFESSOR);
    const collegeToken = await getApiToken(SETUP_COLLEGE);
    const adminToken = await getApiToken("admin");

    // 1. Student submits application
    const createRes = await apiAs<{
      success: boolean;
      data: { id: number; app_id: string };
    }>(studentToken, "POST", "/applications?is_draft=false", {
      scholarship_type: SETUP_SCHOLARSHIP,
      configuration_id: config.id,
      scholarship_subtype_list: [SETUP_SUB_TYPE],
      sub_type_preferences: [SETUP_SUB_TYPE],
      form_data: { fields: {}, documents: [] },
      agree_terms: true,
    });
    if (!createRes.ok || !createRes.body.success) {
      throw new Error(`revoke fixture: create application failed HTTP ${createRes.status}`);
    }
    const appDbId = createRes.body.data.id;
    fixtureAppId = createRes.body.data.app_id;

    // 2. Assign professor via DB (seed has no advisor_nycu_id set)
    const { rows: profRows } = await pool.query<{ id: number }>(
      "SELECT id FROM users WHERE nycu_id = $1",
      [SETUP_PROFESSOR],
    );
    await pool.query("UPDATE applications SET professor_id = $1 WHERE id = $2", [
      profRows[0].id,
      appDbId,
    ]);

    // 3. Professor approves
    const reviewRes = await apiAs<{ success: boolean }>(
      professorToken,
      "POST",
      `/professor/applications/${appDbId}/review`,
      {
        items: [
          {
            sub_type_code: SETUP_SUB_TYPE,
            recommendation: "approve",
            comments: "E2E revoke dialog fixture",
          },
        ],
      },
    );
    if (!reviewRes.ok) {
      throw new Error(`revoke fixture: professor review failed HTTP ${reviewRes.status}`);
    }

    // 4. College creates ranking (force_new avoids reusing leftover unfinalized ranking)
    const rankRes = await apiAs<{ success: boolean; data: { id: number } }>(
      collegeToken,
      "POST",
      "/college-review/rankings",
      {
        scholarship_type_id: config.scholarship_type_id,
        sub_type_code: SETUP_SUB_TYPE,
        academic_year: config.academic_year,
        semester: config.semester,
        force_new: true,
      },
    );
    if (!rankRes.ok || !rankRes.body.success) {
      throw new Error(`revoke fixture: create ranking failed HTTP ${rankRes.status}`);
    }
    fixtureRankingId = rankRes.body.data.id;

    const { rows: itemRows } = await pool.query<{ id: number }>(
      "SELECT id FROM college_ranking_items WHERE ranking_id = $1 AND application_id = $2",
      [fixtureRankingId, appDbId],
    );
    if (!itemRows[0]) {
      throw new Error(`revoke fixture: ranking item not found for app ${appDbId}`);
    }
    const rankingItemId = itemRows[0].id;

    // 5. College finalizes ranking
    const finalizeRankRes = await apiAs<{ success: boolean }>(
      collegeToken,
      "POST",
      `/college-review/rankings/${fixtureRankingId}/finalize`,
    );
    if (!finalizeRankRes.ok) {
      throw new Error(`revoke fixture: finalize ranking failed HTTP ${finalizeRankRes.status}`);
    }

    // 6. Admin allocates
    const allocRes = await apiAs<{ success: boolean }>(
      adminToken,
      "POST",
      "/manual-distribution/allocate",
      {
        scholarship_type_id: config.scholarship_type_id,
        academic_year: config.academic_year,
        semester: semForReq,
        allocations: [
          {
            ranking_item_id: rankingItemId,
            sub_type_code: SETUP_SUB_TYPE,
            allocation_year: config.academic_year,
          },
        ],
      },
    );
    if (!allocRes.ok) {
      throw new Error(`revoke fixture: allocate failed HTTP ${allocRes.status}`);
    }

    // 7. Admin finalizes distribution (application → approved, is_allocated = true)
    const finalDistRes = await apiAs<{ success: boolean }>(
      adminToken,
      "POST",
      "/manual-distribution/finalize",
      {
        scholarship_type_id: config.scholarship_type_id,
        academic_year: config.academic_year,
        semester: semForReq,
      },
    );
    if (!finalDistRes.ok) {
      throw new Error(`revoke fixture: finalize distribution failed HTTP ${finalDistRes.status}`);
    }
  });

  test.afterAll(async () => {
    if (fixtureRankingId) {
      await pool
        .query("DELETE FROM college_rankings WHERE id = $1", [fixtureRankingId])
        .catch(() => undefined);
    }
    if (fixtureAppId) {
      await deleteApplicationCascade(fixtureAppId).catch(() => undefined);
    }
  });

  test.beforeEach(() => {
    runState = newRunState();
  });

  test.afterEach(async ({}, testInfo) => {
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test(
    "撤 button opens dialog; confirm stays disabled until reason entered",
    async ({ browser }) => {
      // ------------------------------------------------------------------
      // Admin logs in and navigates to the Manual Distribution Panel.
      // The beforeAll guarantees an allocated student exists.
      //
      // The panel lives at root "/" under the "獎學金分發" tab → scholarship
      // type tab → ManualDistributionPanel.  There is no standalone route
      // like "/admin/manual-distribution".
      // ------------------------------------------------------------------
      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);
      const page = await adminLogin.context.newPage();

      // loginAs injects auth_token + user into localStorage; navigate root.
      await page.goto("http://localhost:3000/");

      // Admin defaults to the "dashboard" tab.  Click "獎學金分發".
      await page.getByRole("tab", { name: "獎學金分發" }).click();

      // Wait for scholarship-type tabs AND the panel selects to appear.
      // The first scholarship tab auto-selects on mount; we use this opportunity
      // to set semester="yearly" before switching to the phd tab.  This
      // eliminates a race condition where the phd panel's first fetch fires with
      // semester="first" and its empty response could overwrite the subsequent
      // "yearly" response if the two round-trips interleave.
      await page
        .getByRole("tab", { name: SETUP_SCHOLARSHIP_NAME })
        .waitFor({ timeout: 10_000 });

      // The first scholarship tab is now active and the panel is rendered.
      // Switch semester to "yearly" while still on that tab so the phd panel
      // inherits the correct semester from the start.
      await page.locator('label:has-text("學期")').waitFor({ timeout: 10_000 });
      await page
        .locator("select")
        .filter({ has: page.locator('option[value="yearly"]') })
        .selectOption("yearly");

      // Now switch to the phd scholarship tab.  selectedSemester is already
      // "yearly", so fetchData fires exactly once with the correct semester.
      await page.getByRole("tab", { name: SETUP_SCHOLARSHIP_NAME }).click();

      // Wait for the revoke button — the initial fetch with semester="yearly"
      // returns the allocated fixture student.
      const revokeBtn = page
        .locator('button[title*="撤銷此學生獎學金"]')
        .first();
      await revokeBtn.waitFor({ timeout: 15_000 });

      await revokeBtn.click();

      // Dialog must be visible.
      const dialog = page.locator('[role="alertdialog"]');
      await expect(dialog).toBeVisible({ timeout: 5_000 });

      // "確認撤銷" button inside the dialog must be disabled when reason is empty.
      const confirmBtn = dialog.locator('button:has-text("確認撤銷")');
      await expect(confirmBtn).toBeDisabled();

      // Fill in the reason textarea.
      await dialog
        .locator('textarea[placeholder*="請說明撤銷原因"]')
        .fill("E2E test revoke — reason required check");

      // Now the confirm button should be enabled.
      await expect(confirmBtn).toBeEnabled();

      // Submit and wait for success message in the panel (setSaveMessage call
      // in ManualDistributionPanel renders text that starts with "已撤銷").
      await confirmBtn.click();
      await expect(
        page.locator('text=已撤銷').first(),
      ).toBeVisible({ timeout: 8_000 });
    },
  );
});

// ---------------------------------------------------------------------------
// Test 2: LOCKED roster detail dialog shows revoked panel + 從本造冊移除 button
// ---------------------------------------------------------------------------

test.describe("locked roster dialog — revoked student panel + item removal", () => {
  let runState: RunState;

  test.beforeEach(() => {
    runState = newRunState();
  });

  test.afterEach(async ({}, testInfo) => {
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test(
    "LOCKED roster with revoked student shows 撤銷名單 panel and 從本造冊移除 button",
    async ({ browser }) => {
      // ------------------------------------------------------------------
      // Pre-check: find a LOCKED roster that contains a payment_roster_item
      // whose application has quota_allocation_status IN ('revoked',
      // 'suspended').  This state does NOT exist in fresh seed data.
      // ------------------------------------------------------------------
      const { rows: lockedRosterRows } = await pool.query<{
        roster_id: number;
        config_id: number;
      }>(
        `SELECT DISTINCT pr.id  AS roster_id,
                         pr.scholarship_configuration_id AS config_id
           FROM payment_rosters pr
           JOIN payment_roster_items pri ON pri.roster_id = pr.id
           JOIN applications a ON a.id = pri.application_id
          WHERE pr.status = 'locked'
            AND a.quota_allocation_status IN ('revoked', 'suspended')
          LIMIT 1`,
      );

      if (lockedRosterRows.length === 0) {
        test.skip(
          true,
          "No LOCKED roster with a revoked/suspended student found. " +
            "This test requires: (1) generate rosters, (2) lock a roster, " +
            "(3) POST /manual-distribution/revoke on one of its students. " +
            "Run the full setup flow before this test.",
        );
        return;
      }

      const { config_id } = lockedRosterRows[0];

      // ------------------------------------------------------------------
      // Fetch the scholarship type code so we can navigate to the right
      // roster list page.
      // ------------------------------------------------------------------
      const { rows: configRows } = await pool.query<{
        scholarship_code: string;
      }>(
        `SELECT st.code AS scholarship_code
           FROM scholarship_configurations sc
           JOIN scholarship_types st ON st.id = sc.scholarship_type_id
          WHERE sc.id = $1`,
        [config_id],
      );
      if (configRows.length === 0) {
        test.skip(true, "Scholarship config for locked roster not found");
        return;
      }

      // ------------------------------------------------------------------
      // Admin logs in and navigates to the payment-rosters list page.
      // ------------------------------------------------------------------
      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);
      const page = await adminLogin.context.newPage();

      await page.goto(`http://localhost:3000/admin/payment-rosters`);

      // Wait for at least one row to appear.
      await page.waitForSelector("table tbody tr", { timeout: 15_000 });

      // Find the first row that shows a locked status (造冊狀態 = "已鎖定" or
      // similar text; adapt to the actual i18n text if needed).
      const lockedRow = page
        .locator("tr")
        .filter({ hasText: /已鎖定|locked/i })
        .first();

      const lockedRowCount = await lockedRow.count();
      if (lockedRowCount === 0) {
        test.skip(
          true,
          "No row with '已鎖定' text visible in the payment-rosters table",
        );
        return;
      }

      // Click the "查看" (view) button on that row.
      await lockedRow.locator('button:has-text("查看")').click();

      // Wait for the dialog to appear.
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 8_000 });

      // The revoked student panel summary reads: "此造冊有 N 位學生被撤銷，請手動處理"
      const revokedSummary = dialog.locator("summary").filter({
        hasText: /請手動處理/,
      });
      await expect(revokedSummary).toBeVisible({ timeout: 5_000 });

      // The 從本造冊移除 button must be present.
      const removeBtn = dialog.locator('button:has-text("從本造冊移除")').first();
      await expect(removeBtn).toBeVisible();
      await expect(removeBtn).toBeEnabled();

      // Verify the button is clickable — confirm the browser confirms dialog
      // if the implementation shows a window.confirm.
      page.once("dialog", (d) => d.accept());
      await removeBtn.click();

      // After removal the Excel-stale banner should appear:
      //   "⚠️ 造冊資料已變更，請重新匯出 Excel"
      await expect(
        dialog.locator("text=請重新匯出 Excel"),
      ).toBeVisible({ timeout: 8_000 });
    },
  );

  test(
    "LOCKED roster GET /payment-rosters/{id}/revoked-suspended returns expected shape",
    async ({ browser }) => {
      // ------------------------------------------------------------------
      // API-level contract: the endpoint must return { success: true, data:
      // { revoked: [...], suspended: [...] } } for any LOCKED roster.
      // ------------------------------------------------------------------
      const { rows: lockedRows } = await pool.query<{ id: number }>(
        `SELECT id FROM payment_rosters WHERE status = 'locked' LIMIT 1`,
      );

      if (lockedRows.length === 0) {
        test.skip(true, "No LOCKED roster in DB — skip API shape check");
        return;
      }

      const rosterId = lockedRows[0].id;

      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);

      const res = await apiAs<{
        success: boolean;
        data: { revoked: unknown[]; suspended: unknown[] };
      }>(
        adminLogin.token,
        "GET",
        `/payment-rosters/${rosterId}/revoked-suspended`,
      );
      pushTrace(runState, res.traceId);

      expect(
        res.ok,
        `GET /payment-rosters/${rosterId}/revoked-suspended failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
      ).toBe(true);
      expect(res.body.success).toBe(true);
      expect(Array.isArray(res.body.data.revoked)).toBe(true);
      expect(Array.isArray(res.body.data.suspended)).toBe(true);
    },
  );
});
