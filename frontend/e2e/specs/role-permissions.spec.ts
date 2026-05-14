/**
 * E2E spec: cross-role authorization pinning (issue #214).
 *
 * Closes the third missing flow listed in issue #214:
 * - student onboarding
 * - student withdrawal           (PR #236)
 * - **role-permission validation** ← this spec
 *
 * Endpoints under test:
 *
 *   POST /applications                      Depends(require_student)
 *   POST /applications/{id}/withdraw        Depends(require_student)
 *   POST /applications/{id}/review          current_user.is_professor() guard
 *
 * For each endpoint we assert the wrong-role caller is rejected with
 * HTTP 403, not silently accepted. This pins the authorization contract:
 * a future change that loosens any of these guards (e.g. removing the
 * `Depends(require_student)` from withdraw, or letting a college user
 * call /review) fails this spec.
 *
 * We seed a single submitted application through the student role and
 * reuse it for the withdraw + review checks, so the spec stays under
 * a minute and doesn't fight DB cleanup.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, getActiveConfig, pool } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

/**
 * Pre-clean any existing applications for (student, scholarship_type) —
 * `multi-role-phd.spec.ts` uses the same seed pair, and its afterAll
 * cleanup may not have propagated yet when this spec runs in the same
 * worker. Without this the create-application step would 200 with
 * body.success=false on the unique constraint
 * `uq_user_scholarship_academic_term`.
 */
async function purgeStudentApps(studentNycuId: string, scholarshipCode: string): Promise<void> {
  const { rows } = await pool.query<{ app_id: string }>(
    `SELECT a.app_id
       FROM applications a
       JOIN users u ON u.id = a.user_id
       JOIN scholarship_types st ON st.id = a.scholarship_type_id
      WHERE u.nycu_id = $1 AND st.code = $2`,
    [studentNycuId, scholarshipCode],
  );
  for (const row of rows) {
    await deleteApplicationCascade(row.app_id).catch(() => undefined);
  }
}

const STUDENT_ID = "stuphd001";
const PROFESSOR_ID = "professor";
const COLLEGE_ID = "cs_college";
const SCHOLARSHIP_CODE = "phd";
const SUB_TYPE = "nstc";

test.describe.configure({ mode: "serial" });

test.describe("Role-permission boundaries on applications endpoints", () => {
  let runState: RunState;
  let createdAppId: string | undefined;
  let appDbId: number | undefined;

  test.beforeEach(() => {
    runState = newRunState();
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

  test("wrong-role callers are 403 on student/professor endpoints", async ({ browser }) => {
    // 0a. Drain any leftover (stuphd001, phd) apps from concurrent specs
    //     whose afterAll cleanup hasn't propagated yet.
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    // 0b. Seed: student submits an application. The fixture under test is
    //    the *authorization* of the wrong-role calls below, not the
    //    submission itself.
    const studentLogin = await loginAs(browser, STUDENT_ID);
    pushTrace(runState, studentLogin.traceId);

    const config = await getActiveConfig(SCHOLARSHIP_CODE);

    const createRes = await apiAs<{
      success: boolean;
      data: { id: number; app_id: string };
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
      `seed create failed: HTTP ${createRes.status} body=${JSON.stringify(createRes.body)}`,
    ).toBe(true);

    appDbId = createRes.body.data.id;
    createdAppId = createRes.body.data.app_id;
    runState.appId = createdAppId;

    // 1. Professor tries to create an application → 403 (require_student).
    const profLogin = await loginAs(browser, PROFESSOR_ID);
    pushTrace(runState, profLogin.traceId);

    const profCreate = await apiAs(profLogin.token, "POST", "/applications?is_draft=true", {
      scholarship_type: SCHOLARSHIP_CODE,
      configuration_id: config.id,
      scholarship_subtype_list: [SUB_TYPE],
      sub_type_preferences: [SUB_TYPE],
      form_data: { fields: {}, documents: [] },
      agree_terms: true,
    });
    pushTrace(runState, profCreate.traceId);
    expect(
      profCreate.status,
      `professor create should be 403, got ${profCreate.status} body=${JSON.stringify(profCreate.body)}`,
    ).toBe(403);

    // 2. Professor tries to withdraw the student's app → 403 (require_student).
    const profWithdraw = await apiAs(
      profLogin.token,
      "POST",
      `/applications/${appDbId}/withdraw`,
      {},
    );
    pushTrace(runState, profWithdraw.traceId);
    expect(
      profWithdraw.status,
      `professor withdraw should be 403, got ${profWithdraw.status} body=${JSON.stringify(
        profWithdraw.body,
      )}`,
    ).toBe(403);

    // 3. College user tries to submit a professor-only review → 403
    //    (the endpoint checks current_user.is_professor() inline and
    //    raises 403 if the role is wrong).
    //
    // Body must satisfy `ReviewCreate` (application_id + items[]) so Pydantic
    // doesn't 422 *before* the role guard runs. The role check is what we
    // want to exercise; a 422 would mask whether the guard exists at all.
    const validReviewBody = {
      application_id: appDbId,
      items: [
        {
          sub_type_code: "nstc",
          recommendation: "approve",
          comments: "should never be persisted",
        },
      ],
    };

    const collegeLogin = await loginAs(browser, COLLEGE_ID);
    pushTrace(runState, collegeLogin.traceId);

    const collegeReview = await apiAs(
      collegeLogin.token,
      "POST",
      `/applications/${appDbId}/review`,
      validReviewBody,
    );
    pushTrace(runState, collegeReview.traceId);
    expect(
      collegeReview.status,
      `college submitting professor review should be 403, got ${collegeReview.status} body=${JSON.stringify(
        collegeReview.body,
      )}`,
    ).toBe(403);

    // 4. Student tries to submit a professor-only review → 403 as well.
    //    Different caller, same endpoint — pins that the guard rejects
    //    *any* non-professor, not just college users.
    const studentReview = await apiAs(
      studentLogin.token,
      "POST",
      `/applications/${appDbId}/review`,
      validReviewBody,
    );
    pushTrace(runState, studentReview.traceId);
    expect(
      studentReview.status,
      `student submitting professor review should be 403, got ${studentReview.status} body=${JSON.stringify(
        studentReview.body,
      )}`,
    ).toBe(403);
  });
});
