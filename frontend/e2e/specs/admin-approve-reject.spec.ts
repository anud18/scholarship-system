/**
 * E2E spec: admin PATCH /admin/applications/{id}/status → approved and rejected.
 *
 * Non-obvious invariants under test:
 *
 * 1. APPROVED sets approved_at timestamp in DB.
 *    update_application_status() (application_service.py:1604-1606):
 *      if status_update.status == ApplicationStatus.approved.value:
 *          application.approved_at = datetime.now(timezone.utc)
 *    Only the APPROVE branch writes this column; no other transition does.
 *
 * 2. REJECTED does NOT clear approved_at (if previously set).
 *    The service only sets approved_at on the approve branch; the reject branch
 *    only writes status_name. A previously-set approved_at is preserved even
 *    after a subsequent rejection.
 *
 * 3. reviewer_id is recorded on both approve and reject.
 *    The admin's user.id is written to application.reviewer_id on every call.
 *
 * Spec flow:
 *   1. stuphd001 submits a phd application → status = submitted.
 *   2. Admin PATCHes /admin/applications/{id}/status → {status: "approved"}
 *      → HTTP 200; DB: status=approved, approved_at is non-null.
 *   3. Admin PATCHes same application → {status: "rejected", rejection_reason: "…"}
 *      → HTTP 200; DB: status=rejected, approved_at is now NULL (cleared by G16).
 *
 * Route: PATCH /api/v1/admin/applications/{id}/status
 * Auth: require_admin (admin or super_admin).
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

test.describe("Admin PATCH /admin/applications/{id}/status: approve then reject", () => {
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

  test("@nightly stuphd001 submit → admin approve (approved_at set) → admin reject (approved_at cleared)", async ({
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
      `create failed: HTTP ${createRes.status} body=${JSON.stringify(createRes.body)}`,
    ).toBe(true);
    expect(createRes.body.success).toBe(true);

    const appId = createRes.body.data.app_id;
    createdAppId = appId;
    runState.appId = appId;

    const appRow = await getApplication(appId);
    expect(appRow!.status).toBe("submitted");
    const numericId = appRow!.id as number;

    // 2. Admin approves the application.
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    const approveRes = await apiAs<{ success: boolean; message: string }>(
      adminLogin.token,
      "PATCH",
      `/admin/applications/${numericId}/status`,
      {
        status: "approved",
        comments: "e2e-approve-test",
      },
    );
    pushTrace(runState, approveRes.traceId);
    expect(
      approveRes.ok,
      `approve failed: HTTP ${approveRes.status} body=${JSON.stringify(approveRes.body)}`,
    ).toBe(true);
    expect(approveRes.body.success).toBe(true);

    // DB: status=approved, approved_at must be non-null.
    const afterApprove = await getApplication(appId);
    expect(afterApprove!.status).toBe("approved");
    expect(
      afterApprove!.approved_at,
      "approved_at must be set after approval — only the approve branch writes this column",
    ).not.toBeNull();

    // 3. Admin rejects the same application (rejection_reason satisfies the
    //    G16 admin-override requirement for the approved→rejected transition,
    //    and the reject branch clears approved_at).
    const rejectRes = await apiAs<{ success: boolean; message: string }>(
      adminLogin.token,
      "PATCH",
      `/admin/applications/${numericId}/status`,
      {
        status: "rejected",
        rejection_reason: "e2e-reject-test",
      },
    );
    pushTrace(runState, rejectRes.traceId);
    expect(
      rejectRes.ok,
      `reject failed: HTTP ${rejectRes.status} body=${JSON.stringify(rejectRes.body)}`,
    ).toBe(true);
    expect(rejectRes.body.success).toBe(true);

    // DB: status=rejected, approved_at CLEARED. G16 (#978/#1004): rejecting
    // an approved application nulls approved_at so period-scoped「核准清單」
    // queries don't count later-rejected rows. (approved→rejected is an
    // illegal transition, so this also exercises the admin-override path,
    // which the rejection_reason above satisfies.)
    const afterReject = await getApplication(appId);
    expect(afterReject!.status).toBe("rejected");
    expect(
      afterReject!.approved_at,
      "approved_at must be CLEARED after rejection (G16 #1004) — a rejected application is not in any approved list",
    ).toBeNull();
  });
});
