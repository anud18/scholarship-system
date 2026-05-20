/**
 * E2E spec: professor rejection recommendation + upsert behaviour.
 *
 * Closes the professor-side review invariants tracked in issue #76:
 *   - A "reject" recommendation must be persisted as "reject" on the
 *     application_reviews row (no silent normalization to "approve" or
 *     "partial_approve").
 *   - A professor recommendation is *advisory*: the application's status
 *     stays at "submitted" — only review_stage advances to
 *     "professor_reviewed".
 *   - When the same professor submits a second review for the same
 *     application, ApplicationService.create_professor_review UPSERTS the
 *     existing row (services/application_service.py:1690-1716). The number
 *     of application_reviews rows for (application_id, reviewer_id) must
 *     stay at exactly one, and the row's recommendation must reflect the
 *     newer value.
 *
 * Flow under test:
 *   stuphd001 (student) → POST /applications (phd, sub_type=nstc, is_draft=false)
 *                           → DB applications.status = 'submitted'
 *   <test setup>           UPDATE applications.professor_id = <professor user id>.
 *                           Same hack used by multi-role-phd.spec.ts: the seed has
 *                           the professor↔student relationship in
 *                           professor_student_relationships but the production
 *                           auto-assign path keys off UserProfile.advisor_nycu_id
 *                           which the seed doesn't populate, so without this
 *                           assignment can_professor_submit_review fails the
 *                           application.professor_id == user.id check
 *                           (services/application_service.py:1670).
 *   professor             → POST /professor/applications/{id}/review (reject)
 *                           → DB application_reviews has exactly 1 row with
 *                             recommendation='reject'
 *                           → DB applications.status stays 'submitted'
 *                           → DB applications.review_stage = 'professor_reviewed'
 *   professor             → POST /professor/applications/{id}/review (approve)
 *                             (second call, SAME reviewer, SAME application)
 *                           → DB application_reviews still has exactly 1 row
 *                             (upsert, not insert) with recommendation='approve'
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
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

/**
 * Pre-clean any existing applications for (student, scholarship_type) so the
 * unique constraint `uq_user_scholarship_academic_term` doesn't fire when
 * another spec's cleanup (`deleteApplicationCascade` in afterAll) hasn't
 * propagated yet. multi-role-phd.spec.ts and student-withdraw.spec.ts use
 * the same seeded student `stuphd001` + `phd` triple, so without this purge
 * the second spec to run in the worker collides on the unique key.
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
const SCHOLARSHIP_CODE = "phd";
const SUB_TYPE = "nstc";
const PROFESSOR_NYCU_ID = "professor";

test.describe.configure({ mode: "serial" });

test.describe("Professor reject recommendation + upsert", () => {
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

  test("@nightly stuphd001 → professor reject → upsert to approve; status stays submitted", async ({
    browser,
  }) => {
    // 0. Drain any leftover (stuphd001, phd) apps from concurrent specs
    //    whose afterAll cleanup hasn't propagated yet.
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    // 1. Student creates a submitted application (no draft mode).
    const studentLogin = await loginAs(browser, STUDENT_ID);
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

    // Pre-condition: DB reports submitted (the create-submitted path).
    const beforeReview = await getApplication(appId);
    expect(beforeReview, `application ${appId} not in DB`).not.toBeNull();
    expect(beforeReview!.status).toBe("submitted");

    // 2. Test-setup hack: assign the professor explicitly (see file header).
    const { rows: profRows } = await pool.query("SELECT id FROM users WHERE nycu_id = $1", [
      PROFESSOR_NYCU_ID,
    ]);
    expect(profRows[0], `seeded user ${PROFESSOR_NYCU_ID} missing`).toBeDefined();
    const professorUserId = profRows[0].id as number;

    await pool.query("UPDATE applications SET professor_id = $1 WHERE id = $2", [
      professorUserId,
      appDbId,
    ]);

    // 3. Professor submits a REJECT review.
    const profLogin = await loginAs(browser, PROFESSOR_NYCU_ID);
    pushTrace(runState, profLogin.traceId);

    const rejectRes = await apiAs<{ success: boolean; data: { id: number } }>(
      profLogin.token,
      "POST",
      `/professor/applications/${appDbId}/review`,
      {
        items: [
          {
            sub_type_code: SUB_TYPE,
            recommendation: "reject",
            comments: "E2E reject path",
          },
        ],
      },
    );
    pushTrace(runState, rejectRes.traceId);
    expect(
      rejectRes.ok,
      `professor reject review failed: HTTP ${rejectRes.status} body=${JSON.stringify(
        rejectRes.body,
      )}`,
    ).toBe(true);
    expect(rejectRes.body.success).toBe(true);

    // 4. Invariants after the reject:
    //    a) Exactly one application_reviews row exists for this application,
    //       and its recommendation is 'reject'.
    const reviewsAfterReject = await getReviews(appDbId);
    expect(
      reviewsAfterReject.length,
      `expected exactly 1 review row after reject, got ${reviewsAfterReject.length}: ${JSON.stringify(
        reviewsAfterReject,
      )}`,
    ).toBe(1);
    expect(reviewsAfterReject[0].reviewer_id).toBe(professorUserId);
    expect(reviewsAfterReject[0].recommendation).toBe("reject");

    //    b) application.status is unchanged — professor recommendation is
    //       advisory only and must not flip status away from 'submitted'.
    const appAfterReject = await getApplication(appId);
    expect(appAfterReject, `application ${appId} disappeared after reject`).not.toBeNull();
    expect(
      appAfterReject!.status,
      `professor reject should NOT change application.status, got ${appAfterReject!.status}`,
    ).toBe("submitted");

    //    c) review_stage advanced to 'professor_reviewed' (per
    //       create_professor_review at services/application_service.py:1729).
    const stageAfterReject = await pool.query<{ review_stage: string }>(
      "SELECT review_stage FROM applications WHERE id = $1",
      [appDbId],
    );
    expect(stageAfterReject.rows[0]?.review_stage).toBe("professor_reviewed");

    // 5. Second professor review for the SAME application with a DIFFERENT
    //    recommendation. The service upserts on (application_id, reviewer_id)
    //    so the row count must stay at 1 and the value must update.
    const approveRes = await apiAs<{ success: boolean; data: { id: number } }>(
      profLogin.token,
      "POST",
      `/professor/applications/${appDbId}/review`,
      {
        items: [
          {
            sub_type_code: SUB_TYPE,
            recommendation: "approve",
            comments: "E2E upsert path",
          },
        ],
      },
    );
    pushTrace(runState, approveRes.traceId);
    expect(
      approveRes.ok,
      `professor approve review (upsert) failed: HTTP ${approveRes.status} body=${JSON.stringify(
        approveRes.body,
      )}`,
    ).toBe(true);
    expect(approveRes.body.success).toBe(true);

    // 6. Upsert invariants:
    //    a) Still exactly one application_reviews row — no duplicate created.
    const reviewsAfterUpsert = await getReviews(appDbId);
    expect(
      reviewsAfterUpsert.length,
      `expected exactly 1 review row after upsert (no duplicate), got ${reviewsAfterUpsert.length}: ${JSON.stringify(
        reviewsAfterUpsert,
      )}`,
    ).toBe(1);

    //    b) Same row id as before (truly an update, not a delete+insert).
    expect(
      reviewsAfterUpsert[0].id,
      "upsert should reuse the existing review row, not allocate a new id",
    ).toBe(reviewsAfterReject[0].id);

    //    c) Recommendation reflects the newer value.
    expect(reviewsAfterUpsert[0].recommendation).toBe("approve");

    //    d) Status still 'submitted' — second call also advisory.
    const appAfterUpsert = await getApplication(appId);
    expect(appAfterUpsert!.status).toBe("submitted");
  });
});
