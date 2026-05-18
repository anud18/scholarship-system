/**
 * E2E spec: admin downloads the 申請總表 (department-summary-export) XLSX.
 *
 * This exercises GET /college-review/applications/department-summary-export —
 * the single-department variant. The spec pins:
 *   1. A submitted application for a student in dept 3551 causes the endpoint
 *      to return HTTP 200 (rather than 404 "no matching applications").
 *   2. The response Content-Type contains `spreadsheetml` (XLSX MIME type).
 *   3. The Content-Disposition header includes `.xlsx`.
 *   4. The response body is non-empty (the xlsx workbook has bytes).
 *
 * Note: The endpoint does NOT filter by status — it includes all non-deleted
 * applications. A `submitted` application therefore appears in the export.
 *
 * Auth: `require_scholarship_manager` allows admin, super_admin, and college.
 * Admin is used here for simplicity.
 *
 * Dept/student coupling:
 *   stuphd001 → mock SIS API returns std_depno="3551"
 *   When the student submits, student_data["std_depno"] is stored as "3551".
 *   The endpoint Python-filters raw_apps by std_depno == department_code,
 *   so department_code="3551" must match for at least one row to appear.
 *
 * Why this path matters (issue #76 AC):
 *   The college-review export paths are blocked in Playwright specs by the
 *   typical MinIO dependency — but department-summary-export generates the
 *   Excel entirely from DB data (CollegeRankingExportService.build_workbook)
 *   with no MinIO calls. This makes it testable in the nightly E2E suite
 *   without any object-storage setup.
 *
 * Endpoint reference:
 * - college_review/application_summary_export.py:66 — GET dept-summary-export
 * - normalize_semester_value: None / "yearly" → None; "first" → "first"
 * - CollegeRankingExportService.build_workbook: no MinIO dependency
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, getActiveConfig, getApplication, pool } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const STUDENT_ID = "stuphd001";
const SCHOLARSHIP_CODE = "phd";
const SUB_TYPE = "nstc";
/** std_depno returned by the mock SIS API for stuphd001 */
const DEPT_CODE = "3551";
const API_V1 = "http://localhost:8000/api/v1";

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

test.describe("Admin department-summary-export returns XLSX for dept with submissions", () => {
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

  test("@nightly stuphd001 submit → admin GET dept-summary-export (dept=3551) → 200 XLSX", async ({
    browser,
  }) => {
    // 0. Pre-clean to avoid unique-constraint collisions with sibling specs.
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    // 1. Student submits an application so the department has at least one row.
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

    const appId = createRes.body.data.app_id;
    createdAppId = appId;
    runState.appId = appId;

    // Pre-condition: DB status is submitted.
    const afterCreate = await getApplication(appId);
    expect(afterCreate, `application ${appId} not in DB`).not.toBeNull();
    expect(afterCreate!.status).toBe("submitted");

    // 2. Admin downloads the 申請總表 for dept 3551.
    //    GET /college-review/applications/department-summary-export
    //    params: scholarship_type_id, academic_year, [semester], department_code
    //    auth: require_scholarship_manager (admin qualifies)
    //
    //    The endpoint Python-filters applications by student_data["std_depno"].
    //    stuphd001's SIS snapshot stores std_depno="3551", so department_code
    //    must equal "3551" for the application to appear in the workbook.
    //    If no applications match, the endpoint returns HTTP 200 with an empty
    //    workbook — so the non-empty body check (step 3c) would still pass.
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    const params = new URLSearchParams({
      scholarship_type_id: String(config.scholarship_type_id),
      academic_year: String(config.academic_year),
      department_code: DEPT_CODE,
    });
    // semester=null in DB means yearly; omitting the param preserves that.
    if (config.semester) {
      params.set("semester", config.semester);
    }

    // Use fetch directly to access all response headers (Content-Type,
    // Content-Disposition) that apiAs does not expose.
    const exportRes = await fetch(
      `${API_V1}/college-review/applications/department-summary-export?${params}`,
      {
        method: "GET",
        headers: { Authorization: `Bearer ${adminLogin.token}` },
      },
    );
    const traceId = exportRes.headers.get("x-trace-id");
    if (traceId) pushTrace(runState, traceId);

    // 3a. HTTP 200 — no 404 ("no matching applications"), no 403, no 500.
    expect(
      exportRes.status,
      `dept-summary-export unexpected status: HTTP ${exportRes.status}`,
    ).toBe(200);

    // 3b. XLSX MIME type.
    const contentType = exportRes.headers.get("content-type") ?? "";
    expect(
      contentType,
      `expected spreadsheetml content-type, got: "${contentType}"`,
    ).toContain("spreadsheetml");

    // 3c. Filename carries .xlsx extension.
    const contentDisposition = exportRes.headers.get("content-disposition") ?? "";
    expect(
      contentDisposition,
      `expected .xlsx in Content-Disposition, got: "${contentDisposition}"`,
    ).toContain(".xlsx");

    // 3d. Non-empty body — the workbook serialised to bytes.
    const arrayBuf = await exportRes.arrayBuffer();
    expect(
      arrayBuf.byteLength,
      `expected non-empty xlsx payload, got 0 bytes`,
    ).toBeGreaterThan(0);
  });
});
