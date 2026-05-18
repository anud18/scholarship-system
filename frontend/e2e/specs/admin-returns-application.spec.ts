/**
 * E2E spec: admin/staff returns a submitted application; student edits and re-submits.
 *
 * Closes the `returned` acceptance criterion from issue #76:
 *   - staff can return a submitted application (PATCH /applications/{id}/status)
 *   - student can edit and re-submit a returned application
 *   - the `returned → submitted` transition is the only way out of `returned`
 *     via student action; a subsequent PUT edit attempt on the re-submitted
 *     application is rejected (is_editable = False for `submitted`).
 *
 * Flow under test:
 *   stuphd001 (student) → POST /applications?is_draft=false
 *                          → DB applications.status = 'submitted'
 *   admin               → PATCH /applications/{id}/status
 *                          { status: "returned", comments: "E2E test return" }
 *                          → DB applications.status = 'returned'
 *   stuphd001            → PUT  /applications/{id}  (update form_data)
 *                          → succeeds (is_editable = True for 'returned')
 *   stuphd001            → POST /applications/{id}/submit
 *                          → DB applications.status = 'submitted'
 *   stuphd001            → PUT  /applications/{id}  (attempt edit after re-submit)
 *                          → 422 ValidationError ("Application cannot be edited
 *                          in current status", from ApplicationService.update_application).
 *                          DB status remains 'submitted'.
 *
 * Pinned invariants:
 * - PATCH /applications/{id}/status is reachable under /api/v1 by staff (admin role).
 * - Setting status='returned' on a submitted application succeeds (HTTP 200).
 * - PUT /applications/{id} is allowed when status='returned' (is_editable=True).
 * - PUT /applications/{id} is rejected (HTTP 422) when status='submitted' (is_editable=False).
 * - POST /applications/{id}/submit succeeds from 'returned', flips to 'submitted'.
 * - DB status does not drift after the rejected PUT attempt.
 *
 * Service references:
 * - ApplicationService.update_application (line 1085): checks is_editable → 422 if False
 * - Application.is_editable (model): True for draft|returned, False for submitted|...
 * - ApplicationService.submit_application (line 1241): allowed_statuses = [draft, returned]
 * - PATCH endpoint (applications.py line 664): require_staff dependency
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
 * another spec's cleanup (`deleteApplicationCascade` in afterAll) hasn't
 * propagated yet. student-withdraw.spec.ts / student-draft-save.spec.ts share
 * the same seeded student `stuphd001` + `phd` triple, so without this the
 * second spec to run in the worker collides on the unique key.
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

test.describe("Admin returns application; student edits and re-submits", () => {
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

  test("@nightly stuphd001 submit → admin return → student edit+resubmit → edit rejected", async ({
    browser,
  }) => {
    // 0. Drain any leftover (stuphd001, phd) apps from concurrent specs whose
    //    afterAll cleanup hasn't propagated yet.
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

    // Pre-condition: DB reports submitted (not draft).
    const afterCreate = await getApplication(appId);
    expect(afterCreate, `application ${appId} not in DB`).not.toBeNull();
    expect(afterCreate!.status).toBe("submitted");

    // 2. Admin returns the application.
    //    PATCH /applications/{id}/status requires require_staff (admin qualifies).
    //    The service sets application.status = status_update.status without
    //    validating the FROM state — any status can be set by staff.
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    const returnRes = await apiAs<{
      success: boolean;
      data: { id: number; status?: string };
    }>(adminLogin.token, "PATCH", `/applications/${appDbId}/status`, {
      status: "returned",
      comments: "E2E test: please revise your contact information",
    });
    pushTrace(runState, returnRes.traceId);
    expect(
      returnRes.ok,
      `admin return failed: HTTP ${returnRes.status} body=${JSON.stringify(returnRes.body)}`,
    ).toBe(true);
    expect(returnRes.body.success).toBe(true);

    // Post-condition: DB reports returned.
    const afterReturn = await getApplication(appId);
    expect(afterReturn, `application ${appId} disappeared after return`).not.toBeNull();
    expect(afterReturn!.status).toBe("returned");

    // 3. Student edits form_data — allowed because is_editable = True for 'returned'
    //    (Application.is_editable: draft | returned → True, else → False).
    const updatedFormData = {
      fields: {
        contact_phone: {
          field_id: "contact_phone",
          field_type: "text",
          value: "0987-654-321",
          required: false,
        },
      },
      documents: [],
    };
    const editRes = await apiAs<{
      success: boolean;
      data: { id: number; status?: string };
    }>(studentLogin.token, "PUT", `/applications/${appDbId}`, {
      form_data: updatedFormData,
      agree_terms: true,
    });
    pushTrace(runState, editRes.traceId);
    expect(
      editRes.ok,
      `edit returned application failed: HTTP ${editRes.status} body=${JSON.stringify(editRes.body)}`,
    ).toBe(true);
    expect(editRes.body.success).toBe(true);

    // Status stays returned after edit.
    const afterEdit = await getApplication(appId);
    expect(afterEdit, `application ${appId} disappeared after edit`).not.toBeNull();
    expect(afterEdit!.status).toBe("returned");

    // 4. Student re-submits.
    //    submit_application allows status ∈ {draft, returned} — see application_service.py:1241.
    const resubmitRes = await apiAs<{
      success: boolean;
      data: { id: number; status?: string };
    }>(studentLogin.token, "POST", `/applications/${appDbId}/submit`);
    pushTrace(runState, resubmitRes.traceId);
    expect(
      resubmitRes.ok,
      `re-submit failed: HTTP ${resubmitRes.status} body=${JSON.stringify(resubmitRes.body)}`,
    ).toBe(true);
    expect(resubmitRes.body.success).toBe(true);

    // Post-condition: DB status is back to submitted.
    const afterResubmit = await getApplication(appId);
    expect(afterResubmit, `application ${appId} disappeared after re-submit`).not.toBeNull();
    expect(afterResubmit!.status).toBe("submitted");

    // 5. Student tries to edit again — must be rejected because is_editable = False
    //    for 'submitted'. ApplicationService.update_application raises ValidationError
    //    ("Application cannot be edited in current status"), which ScholarshipException
    //    maps to HTTP 422 (backend/app/core/exceptions.py).
    const editAfterSubmitRes = await apiAs<{ success: boolean; detail?: string }>(
      studentLogin.token,
      "PUT",
      `/applications/${appDbId}`,
      {
        form_data: {
          fields: {
            contact_phone: {
              field_id: "contact_phone",
              field_type: "text",
              value: "should-not-save",
              required: false,
            },
          },
          documents: [],
        },
        agree_terms: true,
      },
    );
    pushTrace(runState, editAfterSubmitRes.traceId);
    expect(
      editAfterSubmitRes.status,
      `expected 422 for edit on submitted application, got ${editAfterSubmitRes.status} body=${JSON.stringify(editAfterSubmitRes.body)}`,
    ).toBe(422);

    // Status didn't drift after the rejected edit — still submitted.
    const finalState = await getApplication(appId);
    expect(finalState!.status).toBe("submitted");
  });
});
