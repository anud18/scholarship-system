/**
 * Scenario 1 — multi-role PhD review chain.
 *
 * Flow:
 *   stuphd001 (student) → POST /applications (phd, sub_type=nstc, is_draft=false)
 *                          → DB applications.status = 'submitted'
 *   <test setup>          UPDATE applications.professor_id = <professor user id>.
 *                          The seed has professor↔stuphd001 in
 *                          professor_student_relationships, but the production
 *                          auto-assign path keys off UserProfile.advisor_nycu_id
 *                          which the seed doesn't populate. Without this step
 *                          can_professor_submit_review fails the
 *                          application.professor_id != professor_id check
 *                          (services/application_service.py:2432). Documented
 *                          here so a failure of this assignment is recognized
 *                          as a seed/data shape issue, not a backend bug.
 *   professor             → POST /professor/applications/{id}/review (approve)
 *                          → DB reviews has row with reviewer_id=professor
 *   cs_college            → POST /college-review/rankings
 *                          → DB college_rankings has the new ranking
 *   admin                 → smoke check: /applications/{id} returns 200 and
 *                          home page renders without crashing
 *
 * Diagnose-and-fix table is in helpers/diagnose.ts. On failure read the
 * attached backend-logs.txt + db-state.json, classify per the table, fix the
 * responsible layer. Never silence an assertion to make it pass.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import {
  deleteApplicationCascade,
  getActiveConfig,
  getApplication,
  getReviews,
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

test.describe.configure({ mode: "serial" });

test.describe("Multi-role PhD review chain", () => {
  let runState: RunState;
  let createdAppId: string | undefined;

  test.beforeEach(() => {
    runState = newRunState();
    createdAppId = undefined;
  });

  test.afterEach(async ({}, testInfo) => {
    if (createdAppId) runState.appId = createdAppId;
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    if (createdAppId) {
      await deleteApplicationCascade(createdAppId).catch(() => undefined);
    }
  });

  test("stuphd001 → professor → cs_college → admin", async ({ browser }) => {
    // 1. Student creates a submitted application.
    const studentLogin = await loginAs(browser, "stuphd001");
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

    // 2. DB state matches API.
    const dbApp = await getApplication(appId);
    expect(dbApp, `application ${appId} not in DB`).not.toBeNull();
    expect(dbApp!.status).toBe("submitted");

    const fetchRes = await apiAs<{ success: boolean; data: { status: string } }>(
      studentLogin.token,
      "GET",
      `/applications/${appDbId}`,
    );
    pushTrace(runState, fetchRes.traceId);
    expect(fetchRes.ok).toBe(true);
    expect(fetchRes.body.data.status).toBe("submitted");

    // Student-portal smoke check: the page renders.
    const studentPage = await studentLogin.context.newPage();
    await studentPage.goto("/", { waitUntil: "domcontentloaded" });
    await studentPage.waitForLoadState("networkidle").catch(() => undefined);
    await expect(studentPage.locator("body")).toBeVisible();

    // 3. Test-setup hack: assign the professor explicitly (see file header).
    const { rows: profRows } = await pool.query(
      "SELECT id FROM users WHERE nycu_id = $1",
      [PROFESSOR_NYCU_ID],
    );
    expect(profRows[0], `seeded user ${PROFESSOR_NYCU_ID} missing`).toBeDefined();
    const professorUserId = profRows[0].id as number;

    await pool.query(
      "UPDATE applications SET professor_id = $1 WHERE id = $2",
      [professorUserId, appDbId],
    );

    // 4. Professor approves.
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
            comments: "E2E ok",
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

    const reviewsRows = await getReviews(appDbId);
    expect(reviewsRows.length).toBeGreaterThan(0);
    const profReview = reviewsRows.find((r) => r.reviewer_id === profLogin.userId);
    expect(profReview, `no review row from professor (id=${profLogin.userId})`).toBeDefined();
    expect(profReview!.recommendation).toBe("approve");

    // 5. College creates a ranking.
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
    const rankingId = rankingRes.body.data.id;

    const { rows: rankingRows } = await pool.query(
      "SELECT id, scholarship_type_id, sub_type_code FROM college_rankings WHERE id = $1",
      [rankingId],
    );
    expect(rankingRows.length).toBe(1);
    expect(rankingRows[0].scholarship_type_id).toBe(config.scholarship_type_id);
    expect(rankingRows[0].sub_type_code).toBe(SUB_TYPE);

    // 6. Admin smoke: home renders, GET /applications/{id} returns 200.
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    const adminFetch = await apiAs<{ success: boolean; data: { status: string } }>(
      adminLogin.token,
      "GET",
      `/applications/${appDbId}`,
    );
    pushTrace(runState, adminFetch.traceId);
    expect(adminFetch.ok).toBe(true);

    const adminPage = await adminLogin.context.newPage();
    await adminPage.goto("/", { waitUntil: "domcontentloaded" });
    await adminPage.waitForLoadState("networkidle").catch(() => undefined);
    await expect(adminPage.locator("body")).toBeVisible();
  });
});
