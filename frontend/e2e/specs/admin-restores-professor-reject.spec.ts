/**
 * E2E spec: the 回發 path — college/admin reverting a professor full-reject.
 *
 * CLAUDE.md Review-Flow Policy: "a professor full-reject is terminal for the
 * professor: it sets application.status = rejected, and the professor cannot
 * re-review (403). Only college/admin may revert it (回發) — that is a
 * separate, explicit edit path, not a professor re-submit."
 *
 * professor-reject-upsert.spec.ts pins the terminal half (reject → rejected,
 * re-review → 403). The REVERT half had no e2e coverage — this spec pins it:
 *
 *   stuphd001 → submit
 *   professor → full reject            → status=rejected
 *   professor → re-review              → 403   (precondition re-assert)
 *   admin     → PATCH status=under_review (the 回發)
 *   professor → re-review (approve)    → 200, review row UPSERTED (still 1 row)
 *
 * This is the product semantics #869 left hanging between unit and e2e: the
 * professor cannot self-reopen, but the staff edit path restores
 * reviewability.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, getActiveConfig, getApplication, getReviews, pool } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const STUDENT_ID = "stuphd001";
const SCHOLARSHIP_CODE = "phd";
const SUB_TYPE = "nstc";
const PROFESSOR_NYCU_ID = "professor";

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

test.describe.configure({ mode: "serial" });

test.describe("Admin 回發 restores professor reviewability after a full reject", () => {
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

  test("@nightly professor full-reject → 403 re-review → admin PATCH under_review → professor re-review 200 (upsert)", async ({
    browser,
  }) => {
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    // 1. Student submits.
    const studentLogin = await loginAs(browser, STUDENT_ID);
    pushTrace(runState, studentLogin.traceId);
    const config = await getActiveConfig(SCHOLARSHIP_CODE);
    const createRes = await apiAs<{ success: boolean; data: { id: number; app_id: string } }>(
      studentLogin.token,
      "POST",
      "/applications?is_draft=false",
      {
        scholarship_type: SCHOLARSHIP_CODE,
        configuration_id: config.id,
        scholarship_subtype_list: [SUB_TYPE],
        sub_type_preferences: [SUB_TYPE],
        form_data: { fields: {}, documents: [] },
        agree_terms: true,
      },
    );
    pushTrace(runState, createRes.traceId);
    expect(
      createRes.ok,
      `create failed: HTTP ${createRes.status} body=${JSON.stringify(createRes.body)}`,
    ).toBe(true);
    const appDbId = createRes.body.data.id;
    createdAppId = createRes.body.data.app_id;
    runState.appId = createdAppId;

    // 2. Assign the professor (same test-setup hack as professor-reject-upsert:
    //    advisor auto-assign needs SIS advisor data the seeded student lacks).
    const { rows: profRows } = await pool.query<{ id: number }>(
      "SELECT id FROM users WHERE nycu_id = $1",
      [PROFESSOR_NYCU_ID],
    );
    expect(profRows[0], `seeded user ${PROFESSOR_NYCU_ID} missing`).toBeDefined();
    await pool.query("UPDATE applications SET professor_id = $1 WHERE id = $2", [
      profRows[0].id,
      appDbId,
    ]);

    // 3. Professor FULL-rejects → terminal: status becomes rejected.
    const professorLogin = await loginAs(browser, PROFESSOR_NYCU_ID);
    pushTrace(runState, professorLogin.traceId);
    const rejectRes = await apiAs<{ success: boolean }>(
      professorLogin.token,
      "POST",
      `/professor/applications/${appDbId}/review`,
      {
        items: [{ sub_type_code: SUB_TYPE, recommendation: "reject", comments: "E2E 回發 spec reject" }],
      },
    );
    pushTrace(runState, rejectRes.traceId);
    expect(
      rejectRes.ok,
      `professor reject failed: HTTP ${rejectRes.status} body=${JSON.stringify(rejectRes.body)}`,
    ).toBe(true);
    const afterReject = await getApplication(createdAppId);
    expect(afterReject!.status, "professor full-reject must set status=rejected").toBe("rejected");

    // 4. Precondition re-assert: the professor cannot self-reopen (403).
    const reReviewBlocked = await apiAs<{ success: boolean }>(
      professorLogin.token,
      "POST",
      `/professor/applications/${appDbId}/review`,
      {
        items: [{ sub_type_code: SUB_TYPE, recommendation: "approve", comments: "self-reopen attempt" }],
      },
    );
    pushTrace(runState, reReviewBlocked.traceId);
    expect(
      reReviewBlocked.status,
      `professor re-review of a rejected app must be 403, got ${reReviewBlocked.status}`,
    ).toBe(403);

    // 5. THE 回發: admin explicitly moves the application back to review.
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);
    const revertRes = await apiAs<{ success: boolean }>(
      adminLogin.token,
      "PATCH",
      `/applications/${appDbId}/status`,
      { status: "under_review", comments: "E2E 回發 — revert professor full-reject" },
    );
    pushTrace(runState, revertRes.traceId);
    expect(
      revertRes.ok,
      `admin 回發 (PATCH status=under_review) failed: HTTP ${revertRes.status} body=${JSON.stringify(
        revertRes.body,
      )}`,
    ).toBe(true);
    const afterRevert = await getApplication(createdAppId);
    expect(afterRevert!.status, "回發 must clear the rejected status").toBe("under_review");

    // 6. The professor can review again — and it UPSERTS (still exactly one
    //    review row, recommendation now approve).
    const reReviewOk = await apiAs<{ success: boolean }>(
      professorLogin.token,
      "POST",
      `/professor/applications/${appDbId}/review`,
      {
        items: [{ sub_type_code: SUB_TYPE, recommendation: "approve", comments: "E2E re-review after 回發" }],
      },
    );
    pushTrace(runState, reReviewOk.traceId);
    expect(
      reReviewOk.ok,
      `professor re-review after 回發 should succeed: HTTP ${reReviewOk.status} body=${JSON.stringify(
        reReviewOk.body,
      )}`,
    ).toBe(true);

    // Scope the upsert invariant to the PROFESSOR's review row: the admin's
    // status edit may legitimately record its own review/audit row, so assert
    // on (application, reviewer) — the professor must still have exactly ONE
    // row, now carrying the post-回發 recommendation.
    const reviews = await getReviews(appDbId);
    const professorReviews = reviews.filter((r) => r.reviewer_id === profRows[0].id);
    expect(
      professorReviews.length,
      `professor review must UPSERT — expected exactly 1 row for reviewer ${profRows[0].id}, got ${
        professorReviews.length
      } (all reviews: ${JSON.stringify(reviews)})`,
    ).toBe(1);
    expect(professorReviews[0].recommendation).toBe("approve");
  });
});
