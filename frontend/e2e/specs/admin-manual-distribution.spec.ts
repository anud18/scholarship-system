/**
 * Scenario: admin manual distribution flow — application reaches `approved`.
 *
 * This is the longest path in issue #76's acceptance criteria that no existing
 * spec covers. It exercises allocate+finalize and pins the invariant that a
 * ranked application transitions to `approved` after distribution finalize.
 *
 * Flow:
 *   csphd0001 (student, college C) → POST /applications (phd, sub_type=nstc, is_draft=false)
 *                                    → DB applications.status = 'submitted'
 *   <test setup>                     UPDATE applications.professor_id = <professor user id>
 *                                    Same workaround as multi-role-phd.spec.ts (see header there).
 *   professor                       → POST /professor/applications/{id}/review (approve)
 *   cs_college (college C)          → POST /college-review/rankings (force_new=true)
 *                                    → auto-includes csphd0001's application:
 *                                      create_ranking filters by creator college_code ('C');
 *                                      csphd0001 has std_academyno='C' in the mock SIS API.
 *                                      stuphd001 has 'EE' and would be excluded.
 *   cs_college                      → POST /college-review/rankings/{id}/finalize
 *                                    ManualDistributionService.finalize() requires
 *                                    CollegeRanking.is_finalized=True (line 701). Allocate does
 *                                    NOT require finalized rankings — finalize does.
 *   admin                           → POST /manual-distribution/allocate
 *                                    _validate_allocations only checks duplicate item IDs;
 *                                    quota enforcement is frontend-side only (line 886).
 *   admin                           → POST /manual-distribution/finalize
 *                                    → DB applications.status = 'approved'
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import {
  deleteApplicationCascade,
  getActiveConfig,
  getApplication,
  pool,
} from "../helpers/db";
import {
  attachRunState,
  newRunState,
  pushTrace,
  type RunState,
} from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const SUB_TYPE = "nstc";
const SCHOLARSHIP_CODE = "phd";
const PROFESSOR_NYCU_ID = "professor";
const STUDENT_NYCU_ID = "csphd0001";

test.describe.configure({ mode: "serial" });

async function purgeStudentApps(): Promise<void> {
  const { rows } = await pool.query<{ app_id: string }>(
    `SELECT a.app_id
       FROM applications a
       JOIN users u ON u.id = a.user_id
       JOIN scholarship_types st ON st.id = a.scholarship_type_id
      WHERE u.nycu_id = $1 AND st.code = $2`,
    [STUDENT_NYCU_ID, SCHOLARSHIP_CODE],
  );
  for (const { app_id } of rows) {
    await deleteApplicationCascade(app_id).catch(() => undefined);
  }
}

test.describe("Admin manual distribution → application approved", () => {
  let runState: RunState;
  let createdAppId: string | undefined;
  let createdRankingId: number | undefined;

  test.beforeEach(async () => {
    runState = newRunState();
    createdAppId = undefined;
    createdRankingId = undefined;
    await purgeStudentApps();
  });

  test.afterEach(async ({}, testInfo) => {
    if (createdAppId) runState.appId = createdAppId;
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    if (createdRankingId) {
      await pool
        .query("DELETE FROM college_rankings WHERE id = $1", [createdRankingId])
        .catch(() => undefined);
    }
    if (createdAppId) {
      await deleteApplicationCascade(createdAppId).catch(() => undefined);
    }
  });

  test("@nightly csphd0001 → professor → cs_college rank+finalize → admin allocate+finalize → approved", async ({
    browser,
  }) => {
    // 1. Student creates a submitted application.
    const studentLogin = await loginAs(browser, STUDENT_NYCU_ID);
    pushTrace(runState, studentLogin.traceId);

    const config = await getActiveConfig(SCHOLARSHIP_CODE);

    const createRes = await apiAs<{
      success: boolean;
      message: string;
      data: { id: number; app_id: string; status?: string };
    }>(studentLogin.token, "POST", "/applications?is_draft=false", {
      scholarship_type: SCHOLARSHIP_CODE,
      configuration_id: config.id,
      scholarship_subtype_list: [SUB_TYPE],
      sub_type_preferences: [SUB_TYPE],
      form_data: { fields: {}, documents: [] },
      agree_terms: true,
    });
    pushTrace(runState, createRes.traceId);
    expect(
      createRes.ok,
      `create application failed: HTTP ${createRes.status} body=${JSON.stringify(createRes.body)}`,
    ).toBe(true);
    expect(createRes.body.success).toBe(true);

    const appDbId = createRes.body.data.id;
    const appId = createRes.body.data.app_id;
    createdAppId = appId;
    runState.appId = appId;

    const dbApp = await getApplication(appId);
    expect(dbApp, `application ${appId} not in DB`).not.toBeNull();
    expect(dbApp!.status).toBe("submitted");

    // 2. Test-setup hack: assign professor explicitly (same workaround as
    //    multi-role-phd.spec.ts — seed has the relationship but auto-assign
    //    path needs UserProfile.advisor_nycu_id which the seed doesn't set).
    const { rows: profRows } = await pool.query(
      "SELECT id FROM users WHERE nycu_id = $1",
      [PROFESSOR_NYCU_ID],
    );
    expect(profRows[0], `seeded user ${PROFESSOR_NYCU_ID} missing`).toBeDefined();
    const professorUserId = profRows[0].id as number;

    await pool.query("UPDATE applications SET professor_id = $1 WHERE id = $2", [
      professorUserId,
      appDbId,
    ]);

    // 3. Professor approves.
    const profLogin = await loginAs(browser, PROFESSOR_NYCU_ID);
    pushTrace(runState, profLogin.traceId);

    const reviewRes = await apiAs<{ success: boolean; data: { id: number } }>(
      profLogin.token,
      "POST",
      `/professor/applications/${appDbId}/review`,
      {
        items: [
          {
            sub_type_code: SUB_TYPE,
            recommendation: "approve",
            comments: "E2E distribution test",
          },
        ],
      },
    );
    pushTrace(runState, reviewRes.traceId);
    expect(
      reviewRes.ok,
      `professor review failed: HTTP ${reviewRes.status} body=${JSON.stringify(reviewRes.body)}`,
    ).toBe(true);
    expect(reviewRes.body.success).toBe(true);

    // 4. College creates a ranking (force_new=true avoids reusing a leftover
    //    unfinalized ranking from a previous run — which might not contain
    //    our application if it was created before the application existed).
    const collegeLogin = await loginAs(browser, "cs_college");
    pushTrace(runState, collegeLogin.traceId);

    const rankingRes = await apiAs<{
      success: boolean;
      data: { id: number; sub_type_code: string };
    }>(collegeLogin.token, "POST", "/college-review/rankings", {
      scholarship_type_id: config.scholarship_type_id,
      sub_type_code: SUB_TYPE,
      academic_year: config.academic_year,
      semester: config.semester,
      force_new: true,
    });
    pushTrace(runState, rankingRes.traceId);
    expect(
      rankingRes.ok,
      `create ranking failed: HTTP ${rankingRes.status} body=${JSON.stringify(rankingRes.body)}`,
    ).toBe(true);
    expect(rankingRes.body.success).toBe(true);

    const rankingId = rankingRes.body.data.id;
    createdRankingId = rankingId;

    // Confirm our application landed in the ranking as a ranking item.
    const { rows: itemRows } = await pool.query<{ id: number }>(
      "SELECT id FROM college_ranking_items WHERE ranking_id = $1 AND application_id = $2",
      [rankingId, appDbId],
    );
    expect(
      itemRows[0],
      `application ${appDbId} not found in ranking ${rankingId} — ` +
        `check that csphd0001's std_academyno ('C') matches cs_college.college_code ('C')`,
    ).toBeDefined();
    const rankingItemId = itemRows[0].id;

    // 5. College finalizes the ranking — required before distribution finalize
    //    (ManualDistributionService.finalize queries is_finalized=True at line 701).
    const finalizeRankingRes = await apiAs<{
      success: boolean;
      data: { id: number; is_finalized: boolean };
    }>(
      collegeLogin.token,
      "POST",
      `/college-review/rankings/${rankingId}/finalize`,
    );
    pushTrace(runState, finalizeRankingRes.traceId);
    expect(
      finalizeRankingRes.ok,
      `finalize ranking failed: HTTP ${finalizeRankingRes.status} body=${JSON.stringify(finalizeRankingRes.body)}`,
    ).toBe(true);
    expect(finalizeRankingRes.body.data.is_finalized).toBe(true);

    // 6. Admin allocates the ranking item.
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    // semester null (yearly) → send "yearly" so _ranking_semester_condition
    // maps it back to the IS NULL || == 'annual' || == 'yearly' condition.
    const semesterForRequest: string = config.semester ?? "yearly";

    const allocateRes = await apiAs<{
      success: boolean;
      data: { updated_count: number };
    }>(adminLogin.token, "POST", "/manual-distribution/allocate", {
      scholarship_type_id: config.scholarship_type_id,
      academic_year: config.academic_year,
      semester: semesterForRequest,
      allocations: [
        {
          ranking_item_id: rankingItemId,
          sub_type_code: SUB_TYPE,
          allocation_year: config.academic_year,
        },
      ],
    });
    pushTrace(runState, allocateRes.traceId);
    expect(
      allocateRes.ok,
      `allocate failed: HTTP ${allocateRes.status} body=${JSON.stringify(allocateRes.body)}`,
    ).toBe(true);
    expect(allocateRes.body.success).toBe(true);
    expect(allocateRes.body.data.updated_count).toBe(1);

    // Confirm the ranking item is marked allocated in DB.
    const { rows: allocatedRows } = await pool.query<{ is_allocated: boolean }>(
      "SELECT is_allocated FROM college_ranking_items WHERE id = $1",
      [rankingItemId],
    );
    expect(allocatedRows[0]?.is_allocated).toBe(true);

    // 7. Admin finalizes distribution — updates application.status → 'approved'.
    const finalizeDistRes = await apiAs<{
      success: boolean;
      data: { approved_count: number; rejected_count: number };
    }>(adminLogin.token, "POST", "/manual-distribution/finalize", {
      scholarship_type_id: config.scholarship_type_id,
      academic_year: config.academic_year,
      semester: semesterForRequest,
    });
    pushTrace(runState, finalizeDistRes.traceId);
    expect(
      finalizeDistRes.ok,
      `finalize distribution failed: HTTP ${finalizeDistRes.status} body=${JSON.stringify(finalizeDistRes.body)}`,
    ).toBe(true);
    expect(finalizeDistRes.body.success).toBe(true);
    expect(
      finalizeDistRes.body.data.approved_count,
      "expected at least 1 approved application",
    ).toBeGreaterThanOrEqual(1);

    // 8. Assert the application status is now 'approved' — the critical
    //    end-to-end invariant this spec is here to protect.
    const finalApp = await getApplication(appId);
    expect(
      finalApp?.status,
      `application ${appId} status should be 'approved' after distribution finalize`,
    ).toBe("approved");
  });
});
