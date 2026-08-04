/**
 * E2E spec: duplicate-application prevention and post-withdrawal reapplication.
 *
 * Two non-obvious invariants under test:
 *
 * 1. DUPLICATE REJECTION returns HTTP 200 (not 409):
 *    When a student submits while an active application exists, the endpoint
 *    returns HTTP 200 with `success: false` and `data.error_code = "DUPLICATE_APPLICATION"`.
 *    This is intentional — the frontend uses error_code to show a specific message
 *    rather than treating it as an HTTP error.
 *    Source: applications.py:210-220
 *
 * 2. WITHDRAWAL returns the application to `draft` (NOT `withdrawn`):
 *    POST /applications/{id}/withdraw sets status = "draft" so the student can
 *    re-edit and resubmit the same application. `withdrawn` is a separate terminal
 *    state used by other flows.
 *    Source: application_service.py:withdraw_application (pinned in student-withdraw.spec.ts)
 *
 * 3. CLEARING enables reapplication:
 *    After the withdrawn-draft is fully deleted via cascade, the duplicate check
 *    finds no blocking application and the student can submit a brand-new one.
 *
 * Spec flow:
 *   1. stuphd001 submits a phd application → status = submitted.
 *   2. stuphd001 tries to POST /applications again (same scholarship/year/semester)
 *      → HTTP 200, success=false, error_code=DUPLICATE_APPLICATION.
 *   3. stuphd001 calls POST /applications/{id}/withdraw → status = draft (not withdrawn).
 *   4. Cascade-delete the draft to clear the blocking application.
 *   5. stuphd001 submits a new phd application → HTTP 200/201, success=true (allowed).
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

const STUDENT_ID = "stuphd001";
const SCHOLARSHIP_CODE = "phd";
const SUB_TYPE = "nstc";

async function purgeStudentApps(
  studentNycuId: string,
  scholarshipCode: string,
): Promise<void> {
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

test.describe("Duplicate-application prevention + post-withdrawal reapplication", () => {
  let runState: RunState;
  // Track both apps so afterAll can clean both.
  let createdAppIds: string[] = [];

  test.beforeEach(() => {
    runState = newRunState();
    createdAppIds = [];
  });

  test.afterEach(async ({}, testInfo) => {
    if (createdAppIds[0]) runState.appId = createdAppIds[0];
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    for (const appId of createdAppIds) {
      await deleteApplicationCascade(appId).catch(() => undefined);
    }
  });

  test("@nightly stuphd001 submit → duplicate 200+false → withdraw → reapply success", async ({
    browser,
  }) => {
    // 0. Pre-clean so no stale applications block this run.
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    const studentLogin = await loginAs(browser, STUDENT_ID);
    pushTrace(runState, studentLogin.traceId);

    const config = await getActiveConfig(SCHOLARSHIP_CODE);

    const appPayload = {
      scholarship_type: SCHOLARSHIP_CODE,
      configuration_id: config.id,
      scholarship_subtype_list: [SUB_TYPE],
      sub_type_preferences: [SUB_TYPE],
      form_data: { fields: {}, documents: [] },
      agree_terms: true,
    };

    // 1. Submit the first application.
    const firstRes = await apiAs<{
      success: boolean;
      message: string;
      data: { id: number; app_id: string; status?: string };
    }>(studentLogin.token, "POST", "/applications?is_draft=false", appPayload);
    pushTrace(runState, firstRes.traceId);
    expect(
      firstRes.ok,
      `first submit failed: HTTP ${firstRes.status} body=${JSON.stringify(firstRes.body)}`,
    ).toBe(true);
    expect(firstRes.body.success).toBe(true);

    const firstAppId = firstRes.body.data.app_id;
    createdAppIds.push(firstAppId);
    runState.appId = firstAppId;

    const firstRow = await getApplication(firstAppId);
    expect(firstRow!.status).toBe("submitted");
    const firstNumericId = firstRow!.id as number;

    // 2. Attempt a second application while the first is still active.
    //    Non-obvious: the endpoint returns HTTP 200 with success=false instead of 409.
    const dupeRes = await apiAs<{
      success: boolean;
      message: string;
      data: {
        error_code?: string;
        existing_app_id?: string;
        existing_status?: string;
      };
    }>(studentLogin.token, "POST", "/applications?is_draft=false", appPayload);
    pushTrace(runState, dupeRes.traceId);

    // HTTP status must be 200 — not 409, not 422.
    expect(
      dupeRes.status,
      `duplicate rejection must be HTTP 200 (not 409), got ${dupeRes.status}`,
    ).toBe(200);
    // success must be false.
    expect(
      dupeRes.body.success,
      "duplicate response body.success must be false",
    ).toBe(false);
    // error_code must identify the specific condition.
    expect(
      dupeRes.body.data?.error_code,
      `expected DUPLICATE_APPLICATION error_code, got: ${dupeRes.body.data?.error_code}`,
    ).toBe("DUPLICATE_APPLICATION");

    // The existing application must still be there, unmodified.
    const afterDupeCheck = await getApplication(firstAppId);
    expect(afterDupeCheck!.status).toBe("submitted");

    // 3. Student withdraws the first application.
    //    PINNED: withdraw sets status to 'draft' (NOT 'withdrawn').
    //    Source: application_service.py:withdraw_application, pinned in student-withdraw.spec.ts.
    const withdrawRes = await apiAs<{ success: boolean; message: string }>(
      studentLogin.token,
      "POST",
      `/applications/${firstNumericId}/withdraw`,
    );
    pushTrace(runState, withdrawRes.traceId);
    expect(
      withdrawRes.ok,
      `withdraw failed: HTTP ${withdrawRes.status} body=${JSON.stringify(withdrawRes.body)}`,
    ).toBe(true);
    expect(withdrawRes.body.success).toBe(true);

    const afterWithdraw = await getApplication(firstAppId);
    expect(
      afterWithdraw!.status,
      "withdraw returns application to draft (not withdrawn) — pinned invariant",
    ).toBe("draft");

    // 4. Cascade-delete the draft to fully clear the blocking application.
    //    After deletion, the duplicate check finds no active application for this
    //    scholarship/year/semester, allowing a fresh submission.
    await deleteApplicationCascade(firstAppId);

    // 5. Student submits a new application — must succeed because no blocking
    //    application exists any more.
    const secondRes = await apiAs<{
      success: boolean;
      message: string;
      data: { id: number; app_id: string; status?: string };
    }>(studentLogin.token, "POST", "/applications?is_draft=false", appPayload);
    pushTrace(runState, secondRes.traceId);

    expect(
      secondRes.ok,
      `reapplication after clearing failed: HTTP ${secondRes.status} body=${JSON.stringify(secondRes.body)}`,
    ).toBe(true);
    expect(
      secondRes.body.success,
      "reapplication after clearing must succeed (success=true)",
    ).toBe(true);

    const secondAppId = secondRes.body.data.app_id;
    createdAppIds.push(secondAppId);

    const secondRow = await getApplication(secondAppId);
    expect(secondRow!.status).toBe("submitted");
    // The new application must be a distinct record from the deleted one.
    expect(secondAppId).not.toBe(firstAppId);
  });
});
