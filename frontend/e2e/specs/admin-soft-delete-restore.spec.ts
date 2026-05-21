/**
 * E2E spec: admin soft-deletes a submitted application then restores it.
 *
 * Non-obvious invariant under test:
 *   A soft-deleted application that was previously submitted restores to
 *   `under_review` — NOT `draft` — because the service checks whether
 *   `submitted_at` is set (application_service.py:2120-2128).
 *
 * Spec flow:
 *   1. stuphd001 submits a phd application → status = submitted.
 *   2. Student attempts DELETE /applications/{id} on their own submitted app
 *      → HTTP 422 (students can only delete DRAFT applications).
 *   3. Admin calls DELETE /applications/{id}?reason=… (soft delete)
 *      → HTTP 200, DB status = deleted.
 *   4. Admin calls POST /applications/{id}/restore
 *      → HTTP 200, DB status = under_review (not draft — submitted_at is set).
 *
 * Why `under_review` and not `draft`:
 *   application_service.py restore_application():
 *     if application.submitted_at:
 *         application.status = ApplicationStatus.under_review
 *     else:
 *         application.status = ApplicationStatus.draft
 *   Soft delete preserves submitted_at, so restore always goes to under_review
 *   for any application that was ever formally submitted.
 *
 * Auth notes:
 *   - DELETE /applications/{id}: any authenticated user; students restricted to DRAFT
 *   - POST /applications/{id}/restore: any authenticated user; staff can restore any app
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

test.describe("Admin soft-delete + restore: submitted app → deleted → under_review", () => {
  let runState: RunState;
  let createdAppId: string | undefined;
  let createdNumericId: number | undefined;

  test.beforeEach(() => {
    runState = newRunState();
    createdAppId = undefined;
    createdNumericId = undefined;
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

  test("@nightly stuphd001 submit → student DELETE 422 → admin soft-delete → admin restore → under_review", async ({
    browser,
  }) => {
    // 0. Pre-clean.
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    // 1. Student submits a phd application.
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
      `create failed: HTTP ${createRes.status} body=${JSON.stringify(createRes.body)}`,
    ).toBe(true);
    expect(createRes.body.success).toBe(true);

    const appId = createRes.body.data.app_id;
    createdAppId = appId;
    runState.appId = appId;

    // Fetch the numeric DB id — needed by DELETE and restore endpoints.
    const appRow = await getApplication(appId);
    expect(appRow, `application ${appId} not in DB`).not.toBeNull();
    expect(appRow!.status).toBe("submitted");
    const numericId = appRow!.id as number;
    createdNumericId = numericId;
    expect(typeof numericId).toBe("number");

    // 2. Student attempts to delete their own submitted application.
    //    Expectation: HTTP 422 — students may only delete DRAFT applications.
    const studentDeleteRes = await apiAs<{ success: boolean; message: string }>(
      studentLogin.token,
      "DELETE",
      `/applications/${numericId}`,
    );
    pushTrace(runState, studentDeleteRes.traceId);
    expect(
      studentDeleteRes.status,
      `student DELETE submitted app should return 422, got ${studentDeleteRes.status}`,
    ).toBe(422);

    // Verify the application was NOT deleted by the student attempt.
    const afterStudentDelete = await getApplication(appId);
    expect(
      afterStudentDelete!.status,
      "status must still be submitted after failed student DELETE",
    ).toBe("submitted");

    // 3. Admin soft-deletes the submitted application (requires reason= query param).
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    const adminDeleteRes = await apiAs<{
      success: boolean;
      message: string;
      data: unknown;
    }>(
      adminLogin.token,
      "DELETE",
      `/applications/${numericId}?reason=e2e-soft-delete-test`,
    );
    pushTrace(runState, adminDeleteRes.traceId);
    expect(
      adminDeleteRes.ok,
      `admin soft-delete failed: HTTP ${adminDeleteRes.status} body=${JSON.stringify(adminDeleteRes.body)}`,
    ).toBe(true);
    expect(adminDeleteRes.body.success).toBe(true);

    // DB must now show status = deleted.
    const afterAdminDelete = await getApplication(appId);
    expect(
      afterAdminDelete,
      "application row must still exist after soft-delete",
    ).not.toBeNull();
    expect(
      afterAdminDelete!.status,
      "status must be deleted after admin soft-delete",
    ).toBe("deleted");

    // 4. Admin restores the soft-deleted application.
    //    Key invariant: restore lands at `under_review` (not `draft`) because
    //    submitted_at was set before the soft-delete and is preserved.
    const restoreRes = await apiAs<{
      success: boolean;
      message: string;
      data: { status?: string };
    }>(adminLogin.token, "POST", `/applications/${numericId}/restore`);
    pushTrace(runState, restoreRes.traceId);
    expect(
      restoreRes.ok,
      `restore failed: HTTP ${restoreRes.status} body=${JSON.stringify(restoreRes.body)}`,
    ).toBe(true);
    expect(restoreRes.body.success).toBe(true);

    // DB must show under_review — not draft — because submitted_at is preserved.
    const afterRestore = await getApplication(appId);
    expect(
      afterRestore,
      "application row must exist after restore",
    ).not.toBeNull();
    expect(
      afterRestore!.status,
      "restored submitted app must be under_review (submitted_at preserved through soft-delete)",
    ).toBe("under_review");
  });
});
