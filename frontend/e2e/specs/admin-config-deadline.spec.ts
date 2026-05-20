/**
 * E2E spec: admin scholarship-configuration CRUD pins deadline enforcement.
 *
 * Flow under test:
 *   admin    → POST /scholarship-configurations/configurations
 *              (phd, academic_year=115, semester=null, application window
 *               in the past — i.e. window already CLOSED)
 *              → 201/200, config row persisted with the supplied
 *                application_start_date / application_end_date.
 *   admin    → GET  /scholarship-configurations/configurations/{id}
 *              → response round-trips application_start_date /
 *                application_end_date as ISO strings.
 *   stuphd001 → POST /applications?is_draft=false   (configuration_id=<new>)
 *              → 422  (EligibilityService.check_student_eligibility rejects
 *                because now > application_end_date — DEV_SCHOLARSHIP_SETTINGS
 *                ["ALWAYS_OPEN_APPLICATION"] is False, so the deadline IS
 *                enforced in the test env.)
 *   admin    → PUT  /scholarship-configurations/configurations/{id}
 *              (application_start_date 1 day ago, application_end_date 1y
 *               in the future — window now OPEN)
 *              → 200, DB row reflects the new end_date.
 *   stuphd001 → POST /applications?is_draft=false   (same configuration_id)
 *              → 200, applications.status='submitted'.
 *
 * Pinned invariants:
 *   - The POST endpoint persists application_start_date / application_end_date
 *     to scholarship_configurations.
 *   - GET /configurations/{id} round-trips both date fields.
 *   - With application_end_date in the past, the student application POST
 *     returns HTTP 422 (not 500, not a silent 200) — this is the test-env
 *     contract that ALWAYS_OPEN_APPLICATION=False keeps in place.
 *   - After PUT extends application_end_date into the future, the same
 *     student succeeds (HTTP 200, applications.status='submitted').
 *   - application_end_date in the past is the ONLY barrier to step 8:
 *     academic_year=115 has no seeded scholarship_rules and no other active
 *     phd configuration, so eligibility passes once the window is open.
 *     (SIS API term data for year 115 doesn't exist either, but that only
 *      sets _term_data_status='error' in the snapshot — it does not block
 *      application creation when no rule needs term data.)
 *
 * Why year 115:
 *   - Seeded configurations cover 112/113/114 only — year 115 has no
 *     conflicting active config, so the 409 unique-period check (type,
 *     year, semester, is_active=True) does not fire.
 *   - No scholarship_rules for year 115, so the rule loop is a no-op.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, pool } from "../helpers/db";
import {
  attachRunState,
  newRunState,
  pushTrace,
  type RunState,
} from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const STUDENT_NYCU_ID = "stuphd001";
const SCHOLARSHIP_CODE = "phd";
const ACADEMIC_YEAR = 115;
const CONFIG_CODE = "phd_115_e2e_deadline";
const CONFIG_NAME = "E2E Deadline Test 115";
const AMOUNT = 10000;

test.describe.configure({ mode: "serial" });

/**
 * Pre-clean any lingering config row keyed by config_code, and any
 * applications that point at it (FK in applications.configuration_id).
 * Required because the POST 409s on (type, year, semester, is_active=True)
 * uniqueness, and any leftover from a crashed earlier run would block step 2.
 */
async function purgeE2EConfig(): Promise<void> {
  const { rows: configRows } = await pool.query<{ id: number }>(
    "SELECT id FROM scholarship_configurations WHERE config_code = $1",
    [CONFIG_CODE],
  );
  for (const { id: configId } of configRows) {
    const { rows: appRows } = await pool.query<{ app_id: string }>(
      "SELECT app_id FROM applications WHERE configuration_id = $1",
      [configId],
    );
    for (const { app_id } of appRows) {
      await deleteApplicationCascade(app_id).catch(() => undefined);
    }
    await pool
      .query("DELETE FROM scholarship_configurations WHERE id = $1", [configId])
      .catch(() => undefined);
  }
}

test.describe("Admin config CRUD pins application_end_date deadline enforcement", () => {
  let runState: RunState;
  let createdConfigId: number | undefined;
  let createdAppId: string | undefined;

  test.beforeEach(async () => {
    runState = newRunState();
    createdConfigId = undefined;
    createdAppId = undefined;
    await purgeE2EConfig();
  });

  test.afterEach(async ({}, testInfo) => {
    if (createdAppId) runState.appId = createdAppId;
    if (createdConfigId) runState.configId = createdConfigId;
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    if (createdAppId) {
      await deleteApplicationCascade(createdAppId).catch(() => undefined);
    }
    if (createdConfigId) {
      await pool
        .query("DELETE FROM scholarship_configurations WHERE id = $1", [
          createdConfigId,
        ])
        .catch(() => undefined);
    }
  });

  test("@nightly admin POST/PUT phd 115 config — closed window 422, opened window 200", async ({
    browser,
  }) => {
    // Build dates relative to "now" so the spec is stable regardless of
    // wall-clock when CI runs.
    const now = new Date();
    const past2y = new Date(
      now.getTime() - 2 * 365 * 24 * 60 * 60 * 1000,
    ).toISOString();
    const past1y = new Date(
      now.getTime() - 1 * 365 * 24 * 60 * 60 * 1000,
    ).toISOString();
    const pastDay = new Date(
      now.getTime() - 24 * 60 * 60 * 1000,
    ).toISOString();
    const future1y = new Date(
      now.getTime() + 365 * 24 * 60 * 60 * 1000,
    ).toISOString();

    // Resolve scholarship_type_id for "phd" — the POST body wants the FK id,
    // not the code, and the seeded id may differ across environments.
    const { rows: typeRows } = await pool.query<{ id: number }>(
      "SELECT id FROM scholarship_types WHERE code = $1",
      [SCHOLARSHIP_CODE],
    );
    expect(
      typeRows[0],
      `seeded scholarship_type with code='${SCHOLARSHIP_CODE}' missing`,
    ).toBeDefined();
    const scholarshipTypeId = typeRows[0].id;

    // 1. Admin creates the config with a CLOSED window (end_date 1y ago).
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    const createConfigRes = await apiAs<{
      success: boolean;
      message: string;
      data: { id: number; config_code: string };
    }>(adminLogin.token, "POST", "/scholarship-configurations/configurations", {
      scholarship_type_id: scholarshipTypeId,
      academic_year: ACADEMIC_YEAR,
      config_name: CONFIG_NAME,
      config_code: CONFIG_CODE,
      amount: AMOUNT,
      is_active: true,
      // semester omitted → endpoint reads config_data.get("semester") → null
      // (yearly). Omitting (rather than sending null) keeps the request shape
      // identical to admin-UI behaviour for yearly scholarships.
      application_start_date: past2y,
      application_end_date: past1y,
      requires_professor_recommendation: false,
      requires_college_review: false,
    });
    pushTrace(runState, createConfigRes.traceId);
    expect(
      createConfigRes.ok,
      `create config failed: HTTP ${createConfigRes.status} body=${JSON.stringify(createConfigRes.body)}`,
    ).toBe(true);
    expect(createConfigRes.body.success).toBe(true);
    expect(createConfigRes.body.data.config_code).toBe(CONFIG_CODE);

    createdConfigId = createConfigRes.body.data.id;
    runState.configId = createdConfigId;

    // 2. DB-level: config row exists, is_active=true, end_date ≈ 1y in past.
    const { rows: dbConfigRows } = await pool.query<{
      is_active: boolean;
      application_end_date: Date | null;
      semester: string | null;
    }>(
      "SELECT is_active, application_end_date, semester FROM scholarship_configurations WHERE id = $1",
      [createdConfigId],
    );
    expect(
      dbConfigRows[0],
      `config ${createdConfigId} not in DB after POST`,
    ).toBeDefined();
    expect(dbConfigRows[0].is_active).toBe(true);
    expect(dbConfigRows[0].semester).toBeNull();
    expect(
      dbConfigRows[0].application_end_date,
      "application_end_date should be persisted by POST",
    ).not.toBeNull();
    const persistedEndMs = new Date(
      dbConfigRows[0].application_end_date as Date,
    ).getTime();
    expect(
      persistedEndMs,
      "persisted application_end_date should be in the past after POST",
    ).toBeLessThan(now.getTime());

    // 3. Admin GET round-trips the date fields as ISO strings.
    const getRes = await apiAs<{
      success: boolean;
      data: {
        id: number;
        config_code: string;
        application_start_date: string | null;
        application_end_date: string | null;
      };
    }>(
      adminLogin.token,
      "GET",
      `/scholarship-configurations/configurations/${createdConfigId}`,
    );
    pushTrace(runState, getRes.traceId);
    expect(
      getRes.ok,
      `GET config failed: HTTP ${getRes.status} body=${JSON.stringify(getRes.body)}`,
    ).toBe(true);
    expect(getRes.body.data.config_code).toBe(CONFIG_CODE);
    expect(
      getRes.body.data.application_start_date,
      "GET must round-trip application_start_date",
    ).not.toBeNull();
    expect(
      getRes.body.data.application_end_date,
      "GET must round-trip application_end_date",
    ).not.toBeNull();
    // Parse-able as a real date.
    expect(
      Number.isFinite(
        new Date(getRes.body.data.application_start_date as string).getTime(),
      ),
    ).toBe(true);
    expect(
      Number.isFinite(
        new Date(getRes.body.data.application_end_date as string).getTime(),
      ),
    ).toBe(true);

    // 4. Student attempts to apply with the window CLOSED. The eligibility
    //    service must reject with HTTP 422 — pin the exact status so a
    //    regression that silently allows late applications (e.g. someone
    //    flips ALWAYS_OPEN_APPLICATION=True or skips the date check) fails
    //    here instead of polluting production data.
    const studentLogin = await loginAs(browser, STUDENT_NYCU_ID);
    pushTrace(runState, studentLogin.traceId);

    const closedApplyRes = await apiAs<{
      success?: boolean;
      detail?: unknown;
      message?: string;
    }>(studentLogin.token, "POST", "/applications?is_draft=false", {
      scholarship_type: SCHOLARSHIP_CODE,
      configuration_id: createdConfigId,
      scholarship_subtype_list: [],
      sub_type_preferences: null,
      form_data: { fields: {}, documents: [] },
      agree_terms: true,
    });
    pushTrace(runState, closedApplyRes.traceId);
    expect(
      closedApplyRes.status,
      `expected 422 when application_end_date is in the past, got ${closedApplyRes.status} body=${JSON.stringify(closedApplyRes.body)}`,
    ).toBe(422);

    // 5. Admin PUTs new dates to OPEN the window (start = yesterday,
    //    end = +1 year). Partial body — only the two date fields, matching
    //    the documented contract.
    const updateRes = await apiAs<{
      success: boolean;
      message: string;
      data: { id: number };
    }>(
      adminLogin.token,
      "PUT",
      `/scholarship-configurations/configurations/${createdConfigId}`,
      {
        application_start_date: pastDay,
        application_end_date: future1y,
      },
    );
    pushTrace(runState, updateRes.traceId);
    expect(
      updateRes.ok,
      `PUT config failed: HTTP ${updateRes.status} body=${JSON.stringify(updateRes.body)}`,
    ).toBe(true);
    expect(updateRes.body.success).toBe(true);

    // 6. DB-level: application_end_date now lies in the future.
    const { rows: dbAfterPutRows } = await pool.query<{
      application_end_date: Date | null;
    }>(
      "SELECT application_end_date FROM scholarship_configurations WHERE id = $1",
      [createdConfigId],
    );
    expect(dbAfterPutRows[0]?.application_end_date).not.toBeNull();
    expect(
      new Date(dbAfterPutRows[0].application_end_date as Date).getTime(),
      "application_end_date should be in the future after PUT",
    ).toBeGreaterThan(now.getTime());

    // 7. Student tries again — same config, window now open. Must succeed.
    const openApplyRes = await apiAs<{
      success: boolean;
      message: string;
      data: { id: number; app_id: string; status?: string };
    }>(studentLogin.token, "POST", "/applications?is_draft=false", {
      scholarship_type: SCHOLARSHIP_CODE,
      configuration_id: createdConfigId,
      scholarship_subtype_list: [],
      sub_type_preferences: null,
      form_data: { fields: {}, documents: [] },
      agree_terms: true,
    });
    pushTrace(runState, openApplyRes.traceId);
    expect(
      openApplyRes.ok,
      `apply after PUT failed: HTTP ${openApplyRes.status} body=${JSON.stringify(openApplyRes.body)}`,
    ).toBe(true);
    expect(openApplyRes.body.success).toBe(true);

    createdAppId = openApplyRes.body.data.app_id;
    runState.appId = createdAppId;

    // 8. DB confirms the application landed as submitted.
    const { rows: appRows } = await pool.query<{ status: string }>(
      "SELECT status FROM applications WHERE app_id = $1",
      [createdAppId],
    );
    expect(
      appRows[0],
      `application ${createdAppId} not in DB after open-window POST`,
    ).toBeDefined();
    expect(appRows[0].status).toBe("submitted");
  });
});
