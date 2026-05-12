/**
 * E2E spec: student withdraws a submitted application.
 *
 * Closes one of the three missing flows listed in issue #214:
 * - student onboarding
 * - **student withdrawal**  ← this spec
 * - role-permission validation
 *
 * Flow under test:
 *   stuphd001 (student) → POST /applications (phd, sub_type=nstc, is_draft=false)
 *                          → DB applications.status = 'submitted'
 *   stuphd001            → POST /applications/{id}/withdraw
 *                          → DB applications.status = 'draft' (per
 *                          ApplicationService.withdraw_application:
 *                          submitted/under_review → draft)
 *   stuphd001            → POST /applications/{id}/withdraw  (again)
 *                          → 400 ValidationError ("Only submitted or
 *                          under-review applications can be withdrawn")
 *
 * Pinned invariants:
 * - Withdrawal happy path returns the application to `draft`, not to
 *   `withdrawn` (the latter is a separate terminal state used elsewhere).
 * - A second withdrawal call on the now-draft application is rejected
 *   with HTTP 400 — not a silent no-op, not a 500.
 * - The endpoint exists at POST /applications/{id}/withdraw under the
 *   /api/v1 prefix.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, getActiveConfig, getApplication } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const STUDENT_ID = "stuphd001";
const SCHOLARSHIP_CODE = "phd"; // matches the seed used by multi-role-phd spec
const SUB_TYPE = "nstc";

test.describe.configure({ mode: "serial" });

test.describe("Student withdraws a submitted application", () => {
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

  test("@smoke submit → withdraw → state=draft; second withdraw rejected", async ({ browser }) => {
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
    const beforeWithdraw = await getApplication(appId);
    expect(beforeWithdraw, `application ${appId} not in DB`).not.toBeNull();
    expect(beforeWithdraw!.status).toBe("submitted");

    // 2. Withdraw — should succeed and return the row to draft.
    const withdrawRes = await apiAs<{
      success: boolean;
      data: { id: number; status?: string };
    }>(studentLogin.token, "POST", `/applications/${appDbId}/withdraw`, {});
    pushTrace(runState, withdrawRes.traceId);
    expect(
      withdrawRes.ok,
      `withdraw failed: HTTP ${withdrawRes.status} body=${JSON.stringify(withdrawRes.body)}`,
    ).toBe(true);
    expect(withdrawRes.body.success).toBe(true);

    // Post-condition: DB reports draft (per ApplicationService.withdraw_application).
    const afterWithdraw = await getApplication(appId);
    expect(afterWithdraw, `application ${appId} disappeared after withdraw`).not.toBeNull();
    expect(afterWithdraw!.status).toBe("draft");

    // 3. Second withdraw must be rejected — application is no longer in
    //    submitted/under_review, so the service raises ValidationError →
    //    HTTP 400. We pin this so a future change that silently no-ops on
    //    invalid state transitions fails the test.
    const secondWithdrawRes = await apiAs<{ success: boolean; detail?: string }>(
      studentLogin.token,
      "POST",
      `/applications/${appDbId}/withdraw`,
      {},
    );
    pushTrace(runState, secondWithdrawRes.traceId);
    expect(
      secondWithdrawRes.status,
      `expected 400 for second withdraw, got ${secondWithdrawRes.status} body=${JSON.stringify(
        secondWithdrawRes.body,
      )}`,
    ).toBe(400);

    // Status didn't drift further — still draft.
    const finalState = await getApplication(appId);
    expect(finalState!.status).toBe("draft");
  });
});
