/**
 * E2E spec: student saves a draft application, updates it, then submits it.
 *
 * Closes the "暫存 (draft save)" acceptance criterion from issue #76:
 *   - student should be able to create a draft, mutate its form_data,
 *     submit when ready, and not be able to submit twice.
 *
 * Flow under test:
 *   stuphd001 (student) → POST /applications?is_draft=true
 *                          → DB applications.status = 'draft'
 *   stuphd001            → PUT  /applications/{dbId}  (mutate form_data)
 *                          → form_data persisted, status still 'draft'
 *   stuphd001            → GET  /applications/{dbId}
 *                          → returned form_data matches what we wrote
 *   stuphd001            → POST /applications/{dbId}/submit
 *                          → DB applications.status = 'submitted'
 *   stuphd001            → POST /applications/{dbId}/submit  (again)
 *                          → 422 ValidationError ("Application cannot be
 *                          submitted in current status 'submitted'", from
 *                          ApplicationService.submit_application). DB status
 *                          remains 'submitted'.
 *
 * Pinned invariants:
 * - Draft creation does NOT auto-submit; status starts as 'draft'.
 * - PUT /applications/{id} round-trips form_data while keeping status 'draft'.
 * - First submit transitions draft → submitted (not draft → under_review).
 * - A second submit on an already-submitted application is rejected with
 *   HTTP 422 — not a silent no-op, not a 500, and crucially does not flip
 *   the status to anything else.
 * - The endpoints exist at /applications, /applications/{id},
 *   /applications/{id}/submit under the /api/v1 prefix.
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
 * propagated yet. multi-role-phd.spec.ts / student-withdraw.spec.ts share
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
const SCHOLARSHIP_CODE = "phd"; // matches the seed used by multi-role-phd / student-withdraw specs
const SUB_TYPE = "nstc";

test.describe.configure({ mode: "serial" });

test.describe("Student saves draft, updates, then submits an application", () => {
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

  test("@nightly stuphd001 draft → update → submit → second submit rejected", async ({
    browser,
  }) => {
    // 0. Drain any leftover (stuphd001, phd) apps from concurrent
    //    specs whose afterAll cleanup hasn't propagated yet.
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    // 1. Student logs in and creates a DRAFT application.
    const studentLogin = await loginAs(browser, STUDENT_ID);
    pushTrace(runState, studentLogin.traceId);

    const config = await getActiveConfig(SCHOLARSHIP_CODE);

    const createRes = await apiAs<{
      success: boolean;
      message: string;
      data: { id: number; app_id: string; status?: string };
    }>(studentLogin.token, "POST", "/applications?is_draft=true", {
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
      `create draft application failed: HTTP ${createRes.status} body=${JSON.stringify(
        createRes.body,
      )}`,
    ).toBe(true);
    expect(createRes.body.success).toBe(true);

    const appDbId = createRes.body.data.id;
    const appId = createRes.body.data.app_id;
    createdAppId = appId;
    runState.appId = appId;

    // Pre-condition: DB reports draft (is_draft=true path).
    const afterCreate = await getApplication(appId);
    expect(afterCreate, `application ${appId} not in DB`).not.toBeNull();
    expect(afterCreate!.status).toBe("draft");

    // 2. Update the draft with form_data — status should stay draft.
    //    We use a tiny dynamic-form payload; the contract here is "what we
    //    PUT comes back on GET", not any particular field schema.
    const updatedFormData = {
      fields: {
        contact_phone: {
          field_id: "contact_phone",
          field_type: "text",
          value: "0912-345-678",
          required: false,
        },
      },
      documents: [],
    };
    const updateRes = await apiAs<{
      success: boolean;
      data: { id: number; status?: string };
    }>(studentLogin.token, "PUT", `/applications/${appDbId}`, {
      form_data: updatedFormData,
      agree_terms: true,
    });
    pushTrace(runState, updateRes.traceId);
    expect(
      updateRes.ok,
      `update draft failed: HTTP ${updateRes.status} body=${JSON.stringify(updateRes.body)}`,
    ).toBe(true);
    expect(updateRes.body.success).toBe(true);

    // Post-condition: status still draft after update.
    const afterUpdate = await getApplication(appId);
    expect(afterUpdate, `application ${appId} disappeared after update`).not.toBeNull();
    expect(afterUpdate!.status).toBe("draft");

    // 3. GET the application back and confirm the form_data round-tripped.
    //    The submitted_form_data column is JSONB; pg returns it parsed.
    const getRes = await apiAs<{
      success: boolean;
      data: {
        id: number;
        status?: string;
        submitted_form_data?: { fields?: Record<string, { value?: unknown }> };
        form_data?: { fields?: Record<string, { value?: unknown }> };
      };
    }>(studentLogin.token, "GET", `/applications/${appDbId}`);
    pushTrace(runState, getRes.traceId);
    expect(
      getRes.ok,
      `get draft failed: HTTP ${getRes.status} body=${JSON.stringify(getRes.body)}`,
    ).toBe(true);
    // The response may surface form_data under either `submitted_form_data`
    // (raw column) or `form_data` (serializer alias). Accept either, but
    // require at least one to carry our value.
    const persistedFields =
      getRes.body.data.submitted_form_data?.fields ?? getRes.body.data.form_data?.fields ?? {};
    expect(
      persistedFields.contact_phone?.value,
      `expected GET to return our updated contact_phone, got body=${JSON.stringify(getRes.body)}`,
    ).toBe("0912-345-678");

    // 4. Submit the draft. submit_application requires status in
    //    {draft, returned} (ApplicationService.submit_application), so this
    //    must succeed and flip the row to 'submitted'.
    const submitRes = await apiAs<{
      success: boolean;
      data: { id: number; status?: string };
    }>(studentLogin.token, "POST", `/applications/${appDbId}/submit`);
    pushTrace(runState, submitRes.traceId);
    expect(
      submitRes.ok,
      `submit failed: HTTP ${submitRes.status} body=${JSON.stringify(submitRes.body)}`,
    ).toBe(true);
    expect(submitRes.body.success).toBe(true);

    const afterSubmit = await getApplication(appId);
    expect(afterSubmit, `application ${appId} disappeared after submit`).not.toBeNull();
    expect(afterSubmit!.status).toBe("submitted");

    // 5. Second submit must be rejected. is_editable is false for
    //    'submitted', so submit_application raises ValidationError, which
    //    ScholarshipException maps to HTTP 422 (backend/app/core/exceptions.py).
    //    We pin the 4xx outcome so a future change that silently no-ops on
    //    invalid state transitions fails the test.
    const secondSubmitRes = await apiAs<{ success: boolean; detail?: string }>(
      studentLogin.token,
      "POST",
      `/applications/${appDbId}/submit`,
    );
    pushTrace(runState, secondSubmitRes.traceId);
    expect(
      secondSubmitRes.status,
      `expected 422 for second submit, got ${secondSubmitRes.status} body=${JSON.stringify(
        secondSubmitRes.body,
      )}`,
    ).toBe(422);

    // Status didn't drift after the rejected second submit — still submitted.
    const finalState = await getApplication(appId);
    expect(finalState!.status).toBe("submitted");
  });
});
