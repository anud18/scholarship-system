/**
 * E2E spec: admin bulk-approves a submitted application (direct shortcut path).
 *
 * This covers the faster admin approval path that bypasses the full
 * ranked-distribution flow (POST /admin/applications/bulk-approve).
 * No college ranking or manual-distribution finalize is involved — admin
 * simply bulk-approves applications that are already in submitted/under_review.
 *
 * This is distinct from admin-manual-distribution.spec.ts, which exercises
 * the ranked college review → allocate → distribution finalize path.
 *
 * Flow under test:
 *   stuphd001 (student) → POST /applications?is_draft=false
 *                          → DB applications.status = 'submitted'
 *   admin               → POST /admin/applications/bulk-approve
 *                          { application_ids: [appDbId], send_notifications: false }
 *                          → HTTP 200, data.successful_approvals.length = 1
 *                          → DB applications.status = 'approved'
 *   admin               → POST /admin/applications/bulk-approve  (second call)
 *                          { application_ids: [appDbId], send_notifications: false }
 *                          → HTTP 200 (bulk-approve never returns 4xx for individual failures)
 *                          → data.failed_approvals contains the application
 *                            (status 'approved' is not in allowed set)
 *                          → DB status remains 'approved'
 *
 * Pinned invariants:
 * - POST /admin/applications/bulk-approve is accessible by admin (require_admin).
 * - A submitted application is valid for bulk approval; transitions to 'approved'.
 * - bulk_approve_applications returns per-item success/failure, not HTTP 4xx for
 *   individual failures — the endpoint always returns HTTP 200 (BulkApprovalService
 *   collects failures in `failed_approvals` list at line 67-74).
 * - An already-approved application appears in failed_approvals when bulk-approved again.
 * - DB status does not change on a failed bulk-approve attempt.
 *
 * Endpoint reference:
 * - admin/applications.py:403 — POST /admin/applications/bulk-approve
 * - BulkApprovalService.bulk_approve_applications:30 — status check lines 63-74
 * - Allowed from-states: submitted, under_review (line 63-66)
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, getActiveConfig, getApplication, pool } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

/**
 * Pre-clean any existing applications for (student, scholarship_type) so the
 * unique constraint `uq_user_scholarship_academic_term` doesn't fire when
 * a sibling spec's afterAll cleanup hasn't propagated yet.
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

test.describe.configure({ mode: "serial" });

test.describe("Admin bulk-approves a submitted application", () => {
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

  test("@nightly stuphd001 submit → admin bulk-approve → approved; second bulk-approve in failed_approvals", async ({
    browser,
  }) => {
    // 0. Drain any leftover (stuphd001, phd) apps from concurrent specs whose
    //    afterAll cleanup hasn't propagated yet.
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    // 1. Student creates a submitted application.
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

    // Pre-condition: DB status is submitted.
    const afterCreate = await getApplication(appId);
    expect(afterCreate, `application ${appId} not in DB`).not.toBeNull();
    expect(afterCreate!.status).toBe("submitted");

    // 2. Admin bulk-approves the application.
    //    POST /admin/applications/bulk-approve requires require_admin.
    //    The service checks status ∈ {submitted, under_review} before approving.
    //    send_notifications=false avoids triggering email side-effects in test.
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    const bulkApproveRes = await apiAs<{
      success: boolean;
      data: {
        total_requested: number;
        successful_approvals: Array<{ application_id: number; app_id: string }>;
        failed_approvals: Array<{ application_id: number; reason: string }>;
        notifications_sent: number;
        notifications_failed: number;
      };
    }>(adminLogin.token, "POST", "/admin/applications/bulk-approve", {
      application_ids: [appDbId],
      send_notifications: false,
    });
    pushTrace(runState, bulkApproveRes.traceId);
    expect(
      bulkApproveRes.ok,
      `bulk-approve failed: HTTP ${bulkApproveRes.status} body=${JSON.stringify(bulkApproveRes.body)}`,
    ).toBe(true);
    expect(bulkApproveRes.body.success).toBe(true);
    expect(
      bulkApproveRes.body.data.successful_approvals.length,
      `expected 1 successful approval, got data=${JSON.stringify(bulkApproveRes.body.data)}`,
    ).toBe(1);
    expect(bulkApproveRes.body.data.failed_approvals.length).toBe(0);

    // Post-condition: DB status is approved.
    const afterApprove = await getApplication(appId);
    expect(afterApprove, `application ${appId} disappeared after bulk-approve`).not.toBeNull();
    expect(afterApprove!.status).toBe("approved");

    // 3. Second bulk-approve on the already-approved application must NOT crash
    //    (no HTTP 4xx/5xx). The service returns HTTP 200 with the application in
    //    failed_approvals (status='approved' is not in {submitted, under_review}).
    //    This pins the invariant that bulk-approve never raises on partial failures.
    const secondBulkRes = await apiAs<{
      success: boolean;
      data: {
        total_requested: number;
        successful_approvals: Array<{ application_id: number }>;
        failed_approvals: Array<{ application_id: number; reason: string; current_status: string }>;
      };
    }>(adminLogin.token, "POST", "/admin/applications/bulk-approve", {
      application_ids: [appDbId],
      send_notifications: false,
    });
    pushTrace(runState, secondBulkRes.traceId);
    expect(
      secondBulkRes.ok,
      `second bulk-approve should return HTTP 2xx (partial failures are in data.failed_approvals), got ${secondBulkRes.status} body=${JSON.stringify(secondBulkRes.body)}`,
    ).toBe(true);
    expect(secondBulkRes.body.success).toBe(true);
    expect(secondBulkRes.body.data.successful_approvals.length).toBe(0);
    expect(
      secondBulkRes.body.data.failed_approvals.length,
      `expected 1 failed_approval for already-approved app, got data=${JSON.stringify(secondBulkRes.body.data)}`,
    ).toBe(1);
    expect(secondBulkRes.body.data.failed_approvals[0].application_id).toBe(appDbId);

    // DB status is still approved — the second attempt didn't change it.
    const finalState = await getApplication(appId);
    expect(finalState!.status).toBe("approved");
  });
});
