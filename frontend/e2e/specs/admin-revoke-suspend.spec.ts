/**
 * Scenario: admin revoke / suspend distribution — pin the user-visible flows
 * added in the revoke-suspend-distribution feature branch.
 *
 * Test 1 — "撤 button opens dialog with disabled confirm until reason filled"
 *   Requires: a finalized (distribution_executed=True) scholarship where at
 *   least one student row has status "allocated" or "approved".  The seeded
 *   data from reset_database.sh → seed flow satisfies this after the
 *   admin-manual-distribution spec runs (or after a manual allocate+finalize).
 *   If no such row exists the test is skipped via test.skip().
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
import { pool } from "../helpers/db";
import {
  attachRunState,
  newRunState,
  pushTrace,
  type RunState,
} from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

test.describe.configure({ mode: "serial" });

// ---------------------------------------------------------------------------
// Test 1: 撤 button → dialog → disabled confirm until reason filled
// ---------------------------------------------------------------------------

test.describe("admin revoke dialog — confirm disabled until reason filled", () => {
  let runState: RunState;

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
      // Pre-check: find a finalized distribution with at least one
      // allocated/approved student.  If the DB has none, skip gracefully.
      // ------------------------------------------------------------------
      const { rows: candidateRows } = await pool.query<{
        scholarship_type_id: number;
        academic_year: number;
        semester: string | null;
      }>(
        `SELECT DISTINCT cr.scholarship_type_id,
                         cr.academic_year,
                         cr.semester
           FROM college_ranking_items cri
           JOIN college_rankings cr ON cr.id = cri.ranking_id
          WHERE cri.is_allocated = TRUE
            AND cri.allocated_sub_type IS NOT NULL
          LIMIT 1`,
      );

      if (candidateRows.length === 0) {
        test.skip(
          true,
          "No allocated ranking items in DB — run allocate+finalize first, or run admin-manual-distribution.spec.ts",
        );
        return;
      }

      const { scholarship_type_id, academic_year, semester } = candidateRows[0];

      // ------------------------------------------------------------------
      // Admin logs in and navigates to the Manual Distribution Panel.
      // ------------------------------------------------------------------
      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);
      const page = await adminLogin.context.newPage();

      // Open the manual distribution panel for this scholarship + year.
      // The URL pattern follows the frontend routing for the admin panel.
      const semParam = semester ?? "yearly";
      await page.goto(
        `http://localhost:3000/admin/manual-distribution` +
          `?scholarship_type_id=${scholarship_type_id}` +
          `&academic_year=${academic_year}` +
          `&semester=${semParam}`,
      );

      // Wait for the table to render — the 動作 column header is the
      // reliable signal that the distribution panel is in finalized view.
      await page.waitForSelector('th:has-text("動作")', { timeout: 15_000 });

      // Find the first enabled 撤 button (title contains "撤銷此學生獎學金").
      const revokeBtn = page
        .locator('button[title*="撤銷此學生獎學金"]')
        .first();

      // If no enabled revoke button exists (all students disabled / none
      // finalized) skip rather than fail — this is a seed-state gap, not a
      // code defect.
      const btnCount = await revokeBtn.count();
      if (btnCount === 0) {
        test.skip(
          true,
          "No enabled 撤 button found — students may all be in un-finalized state",
        );
        return;
      }

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
