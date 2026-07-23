/**
 * Scenario: admin revoke / suspend distribution — pin the user-visible flows
 * added in the revoke-suspend-distribution feature branch.
 *
 * Describe #1 — "admin revoke dialog — confirm disabled until reason filled"
 *   Self-contained: beforeAll creates the full allocate+finalize fixture
 *   (csphd0001 → professor → cs_college rank+finalize → admin allocate+finalize).
 *   afterAll cleans up. No dependency on admin-manual-distribution.spec.ts.
 *
 *   Also covers (Task 5 additions):
 *   - Old ✕ ("取消此學生的分配") column is gone
 *   - "停發此學生獎學金" button is visible
 *   - 停 button opens 停發獎學金分發 dialog; default 休學; 確認停發 enabled
 *
 * Describe #2 — "locked roster dialog — revoked student panel + item removal"
 *   Self-contained: beforeAll creates the full flow up to:
 *   allocate+finalize → generate-rosters → lock roster → revoke student.
 *   afterAll cleans up (SQL-level roster delete + deleteApplicationCascade).
 *
 *   Also covers (Task 5 additions):
 *   - A suspended student (post-lock) shows in the revoked-suspended API list
 *   - The suspended entry has a non-null item_id (→ "從本造冊移除" would render)
 *
 * Test 3 — API contract: GET /payment-rosters/{id}/revoked-suspended shape check.
 *   Uses the same locked-roster fixture as describe #2.
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
import { BACKEND_URL, FRONTEND_URL } from "../helpers/env";

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
  const r = await fetch(`${BACKEND_URL}/api/v1/auth/mock-sso/login`, {
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

  // ---------------------------------------------------------------------------
  // Task 5 additions — new feature guards: ✕ gone, 停 visible, suspend dialog
  //
  // These non-destructive tests run FIRST (serial mode, declaration order).
  // The final "撤" test is destructive — it actually revokes the allocation.
  // ---------------------------------------------------------------------------

  test(
    "old ✕ allocation-removal button is absent; 停發此學生獎學金 button is visible",
    async ({ browser }) => {
      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);
      const page = await adminLogin.context.newPage();
      await page.goto(`${FRONTEND_URL}/`);

      await page.getByRole("tab", { name: "獎學金分發" }).click();
      await page.getByRole("tab", { name: SETUP_SCHOLARSHIP_NAME }).waitFor({ timeout: 10_000 });
      await page.locator('label:has-text("學期")').waitFor({ timeout: 10_000 });
      await page
        .locator("select")
        .filter({ has: page.locator('option[value="yearly"]') })
        .selectOption("yearly");
      await page.getByRole("tab", { name: SETUP_SCHOLARSHIP_NAME }).click();

      // Wait for the panel to load by waiting for the revoke button.
      await page
        .locator('button[title*="撤銷此學生獎學金"]')
        .first()
        .waitFor({ timeout: 15_000 });

      // Old ✕ column ("取消此學生的分配") must be completely removed.
      await expect(page.getByTitle("取消此學生的分配")).toHaveCount(0);

      // New 停 button must be visible for the allocated student.
      await expect(
        page.locator('button[title*="停發此學生獎學金"]').first(),
      ).toBeVisible();
    },
  );

  test(
    "停 button opens 停發獎學金分發 dialog; default 休學; 確認停發 enabled without note",
    async ({ browser }) => {
      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);
      const page = await adminLogin.context.newPage();
      await page.goto(`${FRONTEND_URL}/`);

      await page.getByRole("tab", { name: "獎學金分發" }).click();
      await page.getByRole("tab", { name: SETUP_SCHOLARSHIP_NAME }).waitFor({ timeout: 10_000 });
      await page.locator('label:has-text("學期")').waitFor({ timeout: 10_000 });
      await page
        .locator("select")
        .filter({ has: page.locator('option[value="yearly"]') })
        .selectOption("yearly");
      await page.getByRole("tab", { name: SETUP_SCHOLARSHIP_NAME }).click();

      // Wait for the 停 button.
      const suspendBtn = page
        .locator('button[title*="停發此學生獎學金"]')
        .first();
      await suspendBtn.waitFor({ timeout: 15_000 });

      await suspendBtn.click();

      // AllocationActionDialog renders as role="dialog" (not alertdialog).
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 5_000 });

      // Dialog title must be "停發獎學金分發".
      await expect(dialog.getByText("停發獎學金分發")).toBeVisible();

      // Default suspend option must display 休學 in the select trigger.
      await expect(dialog.locator('[id="suspend-option"]')).toContainText("休學");

      // With default option 休學 (not "其他"), note is optional → confirm enabled.
      const confirmBtn = dialog.locator('button:has-text("確認停發")');
      await expect(confirmBtn).toBeEnabled();

      // Cancel without submitting (preserve the allocation for the revoke test).
      await dialog.locator('button:has-text("取消")').click();
      await expect(dialog).not.toBeVisible({ timeout: 3_000 });
    },
  );

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
      await page.goto(`${FRONTEND_URL}/`);

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

      // Dialog must be visible (AllocationActionDialog uses role="dialog").
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 5_000 });

      // "確認撤銷" button inside the dialog must be disabled when reason is empty.
      const confirmBtn = dialog.locator('button:has-text("確認撤銷")');
      await expect(confirmBtn).toBeDisabled();

      // Fill in the reason textarea (placeholder changed to 違反獎學金要點 in
      // AllocationActionDialog — the old inline AlertDialog used 請說明撤銷原因).
      await dialog
        .locator('textarea[placeholder*="違反獎學金要點"]')
        .fill("E2E test revoke — reason required check");

      // Now the confirm button should be enabled.
      await expect(confirmBtn).toBeEnabled();

      // Submit and wait for success message in the panel (setSaveMessage call
      // in ManualDistributionPanel renders "已撤銷 {name} 的獎學金分發").
      await confirmBtn.click();
      await expect(
        page.getByText(/已撤銷 .+ 的獎學金分發/).first(),
      ).toBeVisible({ timeout: 8_000 });
    },
  );
});

// ---------------------------------------------------------------------------
// Tests 2–3: LOCKED roster detail dialog shows revoked panel + API shape
// ---------------------------------------------------------------------------

// Second student for describe #2 suspend sub-fixture (csphd0002).
const SETUP_STUDENT2 = "csphd0002";

// A missing bank account no longer excludes an item from the roster (it is
// only a 補件 warning now), but the fixture applications still carry one so
// the generated items are fully payable and the revoked entry surfaces via
// get_revoked_suspended_for_roster (PR #916 soft-delete gate on is_included).
const SETUP_FORM_DATA = {
  fields: {
    bank_account: {
      field_id: "bank_account",
      field_type: "text",
      value: "0001234567890123",
      required: false,
    },
  },
  documents: [],
};

test.describe("locked roster dialog — revoked student panel + item removal", () => {
  let runState: RunState;
  let lockedFixtureAppId: string | undefined;
  let lockedFixtureAppDbId: number | undefined;
  let lockedFixtureRankingId: number | undefined;
  let lockedFixtureRosterId: number | undefined;
  // Second student (csphd0002) — allocated and then suspended post-lock.
  let lockedFixtureSuspendAppId: string | undefined;
  let lockedFixtureSuspendAppDbId: number | undefined;

  test.beforeAll(async () => {
    const config = await getActiveConfig(SETUP_SCHOLARSHIP);

    // Clean up any leftover rosters for this scholarship config (including locked ones
    // from prior test runs that force_regenerate=true cannot override).
    // Must delete roster_audit_logs first due to FK constraint.
    await pool.query(
      `DELETE FROM roster_audit_logs WHERE roster_id IN (SELECT id FROM payment_rosters WHERE scholarship_configuration_id = $1)`,
      [config.id],
    );
    await pool.query(
      `DELETE FROM payment_roster_items WHERE roster_id IN (SELECT id FROM payment_rosters WHERE scholarship_configuration_id = $1)`,
      [config.id],
    );
    await pool.query(
      `DELETE FROM payment_rosters WHERE scholarship_configuration_id = $1`,
      [config.id],
    );

    // Purge existing csphd0001 and csphd0002 phd apps to ensure a clean slate.
    for (const studentId of [SETUP_STUDENT, SETUP_STUDENT2]) {
      const { rows: existing } = await pool.query<{ app_id: string }>(
        `SELECT a.app_id FROM applications a
         JOIN users u ON u.id = a.user_id
         JOIN scholarship_types st ON st.id = a.scholarship_type_id
         WHERE u.nycu_id = $1 AND st.code = $2`,
        [studentId, SETUP_SCHOLARSHIP],
      );
      for (const { app_id } of existing) {
        await deleteApplicationCascade(app_id).catch(() => undefined);
      }
    }

    const semForReq = config.semester ?? "yearly";

    const studentToken = await getApiToken(SETUP_STUDENT);
    const student2Token = await getApiToken(SETUP_STUDENT2);
    const professorToken = await getApiToken(SETUP_PROFESSOR);
    const collegeToken = await getApiToken(SETUP_COLLEGE);
    const adminToken = await getApiToken("admin");

    const { rows: profRows } = await pool.query<{ id: number }>(
      "SELECT id FROM users WHERE nycu_id = $1",
      [SETUP_PROFESSOR],
    );
    const profDbId = profRows[0].id;

    // 1a. Student 1 (csphd0001) submits application.
    const createRes = await apiAs<{
      success: boolean;
      data: { id: number; app_id: string };
    }>(studentToken, "POST", "/applications?is_draft=false", {
      scholarship_type: SETUP_SCHOLARSHIP,
      configuration_id: config.id,
      scholarship_subtype_list: [SETUP_SUB_TYPE],
      sub_type_preferences: [SETUP_SUB_TYPE],
      form_data: SETUP_FORM_DATA,
      agree_terms: true,
    });
    if (!createRes.ok || !createRes.body.success) {
      throw new Error(`locked-roster fixture: create app (student1) failed HTTP ${createRes.status}`);
    }
    lockedFixtureAppDbId = createRes.body.data.id;
    lockedFixtureAppId = createRes.body.data.app_id;
    await pool.query("UPDATE applications SET professor_id = $1 WHERE id = $2", [
      profDbId,
      lockedFixtureAppDbId,
    ]);

    // 1b. Student 2 (csphd0002) submits application.
    const createRes2 = await apiAs<{
      success: boolean;
      data: { id: number; app_id: string };
    }>(student2Token, "POST", "/applications?is_draft=false", {
      scholarship_type: SETUP_SCHOLARSHIP,
      configuration_id: config.id,
      scholarship_subtype_list: [SETUP_SUB_TYPE],
      sub_type_preferences: [SETUP_SUB_TYPE],
      form_data: SETUP_FORM_DATA,
      agree_terms: true,
    });
    if (!createRes2.ok || !createRes2.body.success) {
      throw new Error(`locked-roster fixture: create app (student2) failed HTTP ${createRes2.status}`);
    }
    lockedFixtureSuspendAppDbId = createRes2.body.data.id;
    lockedFixtureSuspendAppId = createRes2.body.data.app_id;
    await pool.query("UPDATE applications SET professor_id = $1 WHERE id = $2", [
      profDbId,
      lockedFixtureSuspendAppDbId,
    ]);

    // 2. Professor approves both applications.
    for (const appDbId of [lockedFixtureAppDbId, lockedFixtureSuspendAppDbId]) {
      const reviewRes = await apiAs<{ success: boolean }>(
        professorToken,
        "POST",
        `/professor/applications/${appDbId}/review`,
        {
          items: [
            {
              sub_type_code: SETUP_SUB_TYPE,
              recommendation: "approve",
              comments: "E2E locked-roster fixture",
            },
          ],
        },
      );
      if (!reviewRes.ok) {
        throw new Error(`locked-roster fixture: professor review failed for app ${appDbId} HTTP ${reviewRes.status}`);
      }
    }

    // 3. College creates ranking — both students are now eligible and auto-included.
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
      throw new Error(`locked-roster fixture: create ranking failed HTTP ${rankRes.status}`);
    }
    lockedFixtureRankingId = rankRes.body.data.id;

    const { rows: itemRows } = await pool.query<{ id: number; application_id: number }>(
      "SELECT id, application_id FROM college_ranking_items WHERE ranking_id = $1 AND application_id = ANY($2::int[])",
      [lockedFixtureRankingId, [lockedFixtureAppDbId, lockedFixtureSuspendAppDbId]],
    );
    const rankingItemId = itemRows.find(r => r.application_id === lockedFixtureAppDbId)?.id;
    const rankingItemId2 = itemRows.find(r => r.application_id === lockedFixtureSuspendAppDbId)?.id;
    if (!rankingItemId) {
      throw new Error(`locked-roster fixture: ranking item not found for student1 app ${lockedFixtureAppDbId}`);
    }
    if (!rankingItemId2) {
      throw new Error(`locked-roster fixture: ranking item not found for student2 app ${lockedFixtureSuspendAppDbId}`);
    }

    // 4. College finalizes ranking.
    const finalizeRankRes = await apiAs<{ success: boolean }>(
      collegeToken,
      "POST",
      `/college-review/rankings/${lockedFixtureRankingId}/finalize`,
    );
    if (!finalizeRankRes.ok) {
      throw new Error(`locked-roster fixture: finalize ranking failed HTTP ${finalizeRankRes.status}`);
    }

    // 5. Admin allocates both students.
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
          {
            ranking_item_id: rankingItemId2,
            sub_type_code: SETUP_SUB_TYPE,
            allocation_year: config.academic_year,
          },
        ],
      },
    );
    if (!allocRes.ok) {
      throw new Error(`locked-roster fixture: allocate failed HTTP ${allocRes.status}`);
    }

    // 6. Admin finalizes distribution (both applications → approved, quota_allocation_status → allocated).
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
      throw new Error(`locked-roster fixture: finalize distribution failed HTTP ${finalDistRes.status}`);
    }

    // 7. Admin generates rosters from distribution.
    //    force_regenerate=true prevents collisions from prior test runs.
    const genRes = await apiAs<{
      success: boolean;
      data: { rosters_created: number; rosters: Array<{ id: number }> };
    }>(adminToken, "POST", "/manual-distribution/generate-rosters-from-distribution", {
      scholarship_type_id: config.scholarship_type_id,
      academic_year: config.academic_year,
      semester: semForReq,
      student_verification_enabled: false,
      force_regenerate: true,
    });
    if (!genRes.ok || !genRes.body.success || !genRes.body.data.rosters.length) {
      throw new Error(
        `locked-roster fixture: generate-rosters failed HTTP ${genRes.status} body=${JSON.stringify(genRes.body)}`,
      );
    }
    lockedFixtureRosterId = genRes.body.data.rosters[0].id;

    // 8. Admin locks the roster.
    const lockRes = await apiAs<{ success: boolean }>(
      adminToken,
      "POST",
      `/payment-rosters/${lockedFixtureRosterId}/lock`,
    );
    if (!lockRes.ok) {
      throw new Error(`locked-roster fixture: lock roster failed HTTP ${lockRes.status}`);
    }

    // 9. Admin revokes student 1 (AFTER locking) — roster item stays, status → revoked.
    const revokeRes = await apiAs<{ success: boolean }>(
      adminToken,
      "POST",
      `/manual-distribution/applications/${lockedFixtureAppDbId}/revoke`,
      { reason: "E2E locked-roster fixture — revoke after lock for UI test" },
    );
    if (!revokeRes.ok) {
      throw new Error(`locked-roster fixture: revoke failed HTTP ${revokeRes.status}`);
    }

    // 10. Admin suspends student 2 (AFTER locking) — roster item stays, status → suspended.
    const suspendRes = await apiAs<{ success: boolean }>(
      adminToken,
      "POST",
      `/manual-distribution/applications/${lockedFixtureSuspendAppDbId}/suspend`,
      { reason: "E2E locked-roster fixture — suspend after lock for UI test" },
    );
    if (!suspendRes.ok) {
      throw new Error(`locked-roster fixture: suspend failed HTTP ${suspendRes.status}`);
    }
  });

  test.afterAll(async () => {
    // Clean up roster (locked — must use direct SQL, not the API delete endpoint).
    // roster_audit_logs must be deleted first due to FK constraint.
    if (lockedFixtureRosterId) {
      await pool
        .query("DELETE FROM roster_audit_logs WHERE roster_id = $1", [lockedFixtureRosterId])
        .catch(() => undefined);
      await pool
        .query("DELETE FROM payment_roster_items WHERE roster_id = $1", [lockedFixtureRosterId])
        .catch(() => undefined);
      await pool
        .query("DELETE FROM payment_rosters WHERE id = $1", [lockedFixtureRosterId])
        .catch(() => undefined);
    }
    // deleteApplicationCascade removes college_ranking_items for each app; then we
    // delete the ranking itself.
    if (lockedFixtureAppId) {
      await deleteApplicationCascade(lockedFixtureAppId).catch(() => undefined);
    }
    if (lockedFixtureSuspendAppId) {
      await deleteApplicationCascade(lockedFixtureSuspendAppId).catch(() => undefined);
    }
    if (lockedFixtureRankingId) {
      await pool
        .query("DELETE FROM college_rankings WHERE id = $1", [lockedFixtureRankingId])
        .catch(() => undefined);
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
    "@nightly LOCKED roster: GET revoked-suspended returns item, DELETE removes it",
    async ({ browser }) => {
      // API workflow: verify the revoked student appears in revoked-suspended list,
      // then remove them via DELETE /{roster_id}/items/{item_id}, then confirm gone.
      // (The UI for this lives under "造冊管理" tab at root "/" which requires
      // RosterSchedule rows — not in seed data. API test covers the same contract.)
      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);

      // Step 1: GET revoked-suspended list for our locked roster.
      const listRes = await apiAs<{
        success: boolean;
        data: {
          revoked: Array<{
            application_id: number;
            item_id: number | null;
            student_name: string;
          }>;
          suspended: unknown[];
        };
      }>(
        adminLogin.token,
        "GET",
        `/payment-rosters/${lockedFixtureRosterId}/revoked-suspended`,
      );
      pushTrace(runState, listRes.traceId);

      expect(
        listRes.ok,
        `GET revoked-suspended failed: HTTP ${listRes.status} body=${JSON.stringify(listRes.body)}`,
      ).toBe(true);
      expect(listRes.body.success).toBe(true);
      expect(listRes.body.data.revoked.length).toBeGreaterThan(0);

      // Step 2: Find our fixture application in the revoked list.
      const revokedEntry = listRes.body.data.revoked.find(
        (e) => e.application_id === lockedFixtureAppDbId,
      );
      expect(
        revokedEntry,
        `Fixture application ${lockedFixtureAppDbId} not found in revoked list`,
      ).toBeDefined();
      expect(revokedEntry!.item_id, "item_id must be non-null for a locked-roster item").not.toBeNull();
      const itemId = revokedEntry!.item_id as number;

      // Step 3: DELETE the item from the locked roster.
      const deleteRes = await apiAs<{ success: boolean; message: string }>(
        adminLogin.token,
        "DELETE",
        `/payment-rosters/${lockedFixtureRosterId}/items/${itemId}`,
        { reason: "E2E test: remove revoked student from locked roster" },
      );
      pushTrace(runState, deleteRes.traceId);

      expect(
        deleteRes.ok,
        `DELETE item failed: HTTP ${deleteRes.status} body=${JSON.stringify(deleteRes.body)}`,
      ).toBe(true);
      expect(deleteRes.body.success).toBe(true);

      // Step 4: Re-query revoked-suspended — our fixture item must be gone.
      const listRes2 = await apiAs<{
        success: boolean;
        data: { revoked: Array<{ application_id: number }>; suspended: unknown[] };
      }>(
        adminLogin.token,
        "GET",
        `/payment-rosters/${lockedFixtureRosterId}/revoked-suspended`,
      );
      expect(listRes2.ok).toBe(true);
      const stillRevoked = listRes2.body.data.revoked.find(
        (e) => e.application_id === lockedFixtureAppDbId,
      );
      expect(
        stillRevoked,
        "Application must not appear in revoked list after item deletion",
      ).toBeUndefined();
    },
  );

  test(
    "@nightly LOCKED roster GET /payment-rosters/{id}/revoked-suspended returns expected shape",
    async ({ browser }) => {
      // API-level contract: endpoint must return { success: true, data:
      // { revoked: [...], suspended: [...] } } for any LOCKED roster.
      // Uses the roster created in beforeAll.
      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);

      const res = await apiAs<{
        success: boolean;
        data: { revoked: unknown[]; suspended: unknown[] };
      }>(
        adminLogin.token,
        "GET",
        `/payment-rosters/${lockedFixtureRosterId}/revoked-suspended`,
      );
      pushTrace(runState, res.traceId);

      expect(
        res.ok,
        `GET /payment-rosters/${lockedFixtureRosterId}/revoked-suspended failed: ` +
          `HTTP ${res.status} body=${JSON.stringify(res.body)}`,
      ).toBe(true);
      expect(res.body.success).toBe(true);
      expect(Array.isArray(res.body.data.revoked)).toBe(true);
      expect(Array.isArray(res.body.data.suspended)).toBe(true);
    },
  );

  // ---------------------------------------------------------------------------
  // Task 5 addition — suspended student appears in revoked-suspended API list
  // with a non-null item_id (→ RevokedSuspendedSection renders "從本造冊移除").
  // ---------------------------------------------------------------------------

  test(
    "@nightly LOCKED roster: suspended student appears in revoked-suspended list with item_id",
    async ({ browser }) => {
      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);

      const listRes = await apiAs<{
        success: boolean;
        data: {
          revoked: Array<{ application_id: number; item_id: number | null }>;
          suspended: Array<{
            application_id: number;
            item_id: number | null;
            student_name: string;
          }>;
        };
      }>(
        adminLogin.token,
        "GET",
        `/payment-rosters/${lockedFixtureRosterId}/revoked-suspended`,
      );
      pushTrace(runState, listRes.traceId);

      expect(
        listRes.ok,
        `GET revoked-suspended failed: HTTP ${listRes.status} body=${JSON.stringify(listRes.body)}`,
      ).toBe(true);
      expect(listRes.body.success).toBe(true);

      // The suspended section must contain our student2 fixture entry.
      expect(
        listRes.body.data.suspended.length,
        "Expected at least one suspended student in locked roster",
      ).toBeGreaterThan(0);

      const suspendedEntry = listRes.body.data.suspended.find(
        (e) => e.application_id === lockedFixtureSuspendAppDbId,
      );
      expect(
        suspendedEntry,
        `Student2 application ${lockedFixtureSuspendAppDbId} not found in suspended list`,
      ).toBeDefined();

      // item_id must be non-null: the student was in the roster when it was locked,
      // so RevokedSuspendedSection renders "從本造冊移除" for this entry.
      expect(
        suspendedEntry!.item_id,
        "item_id must be non-null for suspended student in locked roster (enables 從本造冊移除 button)",
      ).not.toBeNull();
    },
  );

  test(
    "@nightly revoke/suspend queues the admin notification email (email_history row, #938)",
    async () => {
      // #938 wired _notify_admin_of_cancellation into the revoke/suspend
      // endpoints; #946 moved SMTP delivery to a background task. The durable,
      // SMTP-independent signal is the email_history audit row that
      // EmailService.send_email always writes (status sent OR failed). The
      // fixture above already revoked lockedFixtureAppDbId and suspended
      // lockedFixtureSuspendAppDbId — assert both notifications were queued.
      // Poll: the send runs AFTER the API response, and a dev SMTP timeout can
      // delay the history write.
      for (const [appDbId, label] of [
        [lockedFixtureAppDbId, "撤銷"],
        [lockedFixtureSuspendAppDbId, "停發"],
      ] as Array<[number | undefined, string]>) {
        expect(appDbId, `fixture app for ${label} missing`).toBeTruthy();
        await expect
          .poll(
            async () => {
              const { rows } = await pool.query<{ subject: string; recipient_email: string }>(
                `SELECT subject, recipient_email
                   FROM email_history
                  WHERE application_id = $1
                    AND subject LIKE $2
                  ORDER BY id DESC
                  LIMIT 1`,
                [appDbId, `%${label}操作通知%`],
              );
              return rows[0] ?? null;
            },
            {
              timeout: 60_000,
              message: `no email_history row for ${label} notification of application ${appDbId} — the #938 admin-notification wiring regressed`,
            },
          )
          .not.toBeNull();

        const { rows } = await pool.query<{ recipient_email: string }>(
          `SELECT recipient_email FROM email_history
            WHERE application_id = $1 AND subject LIKE $2
            ORDER BY id DESC LIMIT 1`,
          [appDbId, `%${label}操作通知%`],
        );
        // The notification goes to the ACTING admin (the fixture acted as 'admin').
        expect(rows[0].recipient_email).toBe("admin@nycu.edu.tw");
      }
    },
  );
  test(
    "@nightly suspend is queryable via /admin/audit-logs and visible in 學生領獎紀錄查詢 (G29 #991)",
    async ({ browser }) => {
      // The fixture suspended csphd0002 AFTER the roster locked (its item is
      // untouched by earlier tests — the revoked student's item gets removed
      // by the DELETE test above, so the suspend twin is the stable probe).
      // Two compliance read paths must surface it:
      //   1. the system-wide audit-log endpoint (#1007) carries the typed
      //      suspend event with the reason;
      //   2. 學生領獎紀錄查詢 (#1005) shows the paid row WITH the suspension
      //      context instead of an unqualified 已領取.
      const adminLogin = await loginAs(browser, "admin");
      pushTrace(runState, adminLogin.traceId);

      // 1. Audit-log queryability.
      const auditRes = await apiAs<{
        success: boolean;
        data: {
          items: Array<{
            action: string;
            resource_id: string;
            new_values: { reason?: string } | null;
            actor_nycu_id: string | null;
          }>;
        };
      }>(
        adminLogin.token,
        "GET",
        `/admin/audit-logs?resource_type=application&resource_id=${lockedFixtureSuspendAppDbId}&action=suspend`,
      );
      pushTrace(runState, auditRes.traceId);
      expect(
        auditRes.ok,
        `GET /admin/audit-logs failed: HTTP ${auditRes.status} body=${JSON.stringify(auditRes.body)}`,
      ).toBe(true);
      const suspendEvents = auditRes.body.data.items;
      expect(
        suspendEvents.length,
        `no suspend audit event for application ${lockedFixtureSuspendAppDbId}`,
      ).toBeGreaterThan(0);
      expect(suspendEvents[0].new_values?.reason).toContain("E2E locked-roster fixture");
      expect(suspendEvents[0].actor_nycu_id).toBe("admin");

      // 2. 學生領獎紀錄查詢 suspension context.
      const historyRes = await apiAs<{
        success: boolean;
        data: {
          payment_records: Array<{
            quota_allocation_status: string | null;
            suspend_reason: string | null;
            suspended_at: string | null;
          }>;
        };
      }>(adminLogin.token, "GET", `/admin/student-history/${SETUP_STUDENT2}`);
      pushTrace(runState, historyRes.traceId);
      expect(
        historyRes.ok,
        `GET student-history failed: HTTP ${historyRes.status} body=${JSON.stringify(historyRes.body)}`,
      ).toBe(true);
      const suspendedRecords = historyRes.body.data.payment_records.filter(
        (r) => r.quota_allocation_status === "suspended",
      );
      expect(
        suspendedRecords.length,
        "suspended-after-lock payment must carry suspension context in 學生領獎紀錄查詢 (G25)",
      ).toBeGreaterThan(0);
      expect(suspendedRecords[0].suspend_reason).toContain("E2E locked-roster fixture");
      expect(suspendedRecords[0].suspended_at).toBeTruthy();
    },
  );
});
