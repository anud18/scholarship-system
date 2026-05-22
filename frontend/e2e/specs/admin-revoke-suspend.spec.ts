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
 *   Self-contained: beforeAll creates the full flow up to:
 *   allocate+finalize → generate-rosters → lock roster → revoke student.
 *   afterAll cleans up (SQL-level roster delete + deleteApplicationCascade).
 *
 * Test 3 — API contract: GET /payment-rosters/{id}/revoked-suspended shape check.
 *   Uses the same locked-roster fixture as test 2.
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
// Tests 2–3: LOCKED roster detail dialog shows revoked panel + API shape
// ---------------------------------------------------------------------------

test.describe("locked roster dialog — revoked student panel + item removal", () => {
  let runState: RunState;
  let lockedFixtureAppId: string | undefined;
  let lockedFixtureAppDbId: number | undefined;
  let lockedFixtureRankingId: number | undefined;
  let lockedFixtureRosterId: number | undefined;

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

    // Purge existing csphd0001 phd apps to ensure a clean slate.
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

    const semForReq = config.semester ?? "yearly";

    const studentToken = await getApiToken(SETUP_STUDENT);
    const professorToken = await getApiToken(SETUP_PROFESSOR);
    const collegeToken = await getApiToken(SETUP_COLLEGE);
    const adminToken = await getApiToken("admin");

    // 1. Student submits application.
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
      throw new Error(`locked-roster fixture: create app failed HTTP ${createRes.status}`);
    }
    lockedFixtureAppDbId = createRes.body.data.id;
    lockedFixtureAppId = createRes.body.data.app_id;

    // 2. Assign professor via DB.
    const { rows: profRows } = await pool.query<{ id: number }>(
      "SELECT id FROM users WHERE nycu_id = $1",
      [SETUP_PROFESSOR],
    );
    await pool.query("UPDATE applications SET professor_id = $1 WHERE id = $2", [
      profRows[0].id,
      lockedFixtureAppDbId,
    ]);

    // 3. Professor approves.
    const reviewRes = await apiAs<{ success: boolean }>(
      professorToken,
      "POST",
      `/professor/applications/${lockedFixtureAppDbId}/review`,
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
      throw new Error(`locked-roster fixture: professor review failed HTTP ${reviewRes.status}`);
    }

    // 4. College creates ranking (force_new avoids reusing a stale ranking).
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

    const { rows: itemRows } = await pool.query<{ id: number }>(
      "SELECT id FROM college_ranking_items WHERE ranking_id = $1 AND application_id = $2",
      [lockedFixtureRankingId, lockedFixtureAppDbId],
    );
    if (!itemRows[0]) {
      throw new Error(`locked-roster fixture: ranking item not found for app ${lockedFixtureAppDbId}`);
    }
    const rankingItemId = itemRows[0].id;

    // 5. College finalizes ranking.
    const finalizeRankRes = await apiAs<{ success: boolean }>(
      collegeToken,
      "POST",
      `/college-review/rankings/${lockedFixtureRankingId}/finalize`,
    );
    if (!finalizeRankRes.ok) {
      throw new Error(`locked-roster fixture: finalize ranking failed HTTP ${finalizeRankRes.status}`);
    }

    // 6. Admin allocates.
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
      throw new Error(`locked-roster fixture: allocate failed HTTP ${allocRes.status}`);
    }

    // 7. Admin finalizes distribution (application → approved, quota_allocation_status → allocated).
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

    // 8. Admin generates rosters from distribution.
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

    // 9. Admin locks the roster.
    const lockRes = await apiAs<{ success: boolean }>(
      adminToken,
      "POST",
      `/payment-rosters/${lockedFixtureRosterId}/lock`,
    );
    if (!lockRes.ok) {
      throw new Error(`locked-roster fixture: lock roster failed HTTP ${lockRes.status}`);
    }

    // 10. Admin revokes the student (AFTER locking, so the item stays in the
    //     locked roster and the application's quota_allocation_status → revoked).
    const revokeRes = await apiAs<{ success: boolean }>(
      adminToken,
      "POST",
      `/manual-distribution/applications/${lockedFixtureAppDbId}/revoke`,
      { reason: "E2E locked-roster fixture — revoke after lock for UI test" },
    );
    if (!revokeRes.ok) {
      throw new Error(`locked-roster fixture: revoke failed HTTP ${revokeRes.status}`);
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
    // deleteApplicationCascade removes college_ranking_items for this app; then we
    // delete the ranking itself.
    if (lockedFixtureAppId) {
      await deleteApplicationCascade(lockedFixtureAppId).catch(() => undefined);
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
});
