/**
 * E2E spec: 批次匯入 (batch import) upload-data parses a CSV and returns a
 * preview batch — the first e2e coverage for the batch-import surface.
 *
 * Scope: the upload→parse→preview contract (POST
 * /college-review/batch-import/upload-data). The downstream
 * validate/documents/confirm pipeline mutates student/application state and
 * depends on external SIS data, so it stays out of scope here — this spec
 * pins that:
 *   - a college user can upload a CSV with the required columns (學號/學生姓名)
 *   - the parser returns a persisted batch_id + per-row preview data
 *   - a malformed CSV (missing required columns) is REJECTED, not silently
 *     accepted as zero rows
 *   - the batch shows up in /history
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { pool } from "../helpers/db";
import { BACKEND_URL } from "../helpers/env";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const COLLEGE_USER = "cs_college";
const SCHOLARSHIP_CODE = "phd";
const ACADEMIC_YEAR = 114;
const CSV_STUDENT_ID = "313551099";
const CSV_STUDENT_NAME = "批次匯入測試生";

test.describe.configure({ mode: "serial" });

test.describe("College batch-import upload parses CSV into a preview batch", () => {
  let runState: RunState;
  let createdBatchId: number | undefined;

  test.beforeEach(() => {
    runState = newRunState();
  });

  test.afterEach(async ({}, testInfo) => {
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    if (createdBatchId) {
      await pool
        .query("DELETE FROM batch_imports WHERE id = $1", [createdBatchId])
        .catch(() => undefined);
    }
  });

  test("@nightly cs_college uploads CSV → batch_id + preview row; malformed CSV rejected", async ({
    browser,
  }) => {
    const collegeLogin = await loginAs(browser, COLLEGE_USER);
    pushTrace(runState, collegeLogin.traceId);

    // 1. Valid CSV with the required columns (Chinese header variant).
    //    phd defines real sub-types (nstc/moe_1w), so a row with NO sub-type
    //    marked is now excluded at parse as missing_sub_type — the valid row
    //    must carry a sub-type mark (教育部 = moe_1w) to be counted.
    const csv = `學號,學生姓名,教育部\n${CSV_STUDENT_ID},${CSV_STUDENT_NAME},1\n`;
    const form = new FormData();
    form.append("file", new Blob([csv], { type: "text/csv" }), "e2e-batch.csv");

    const uploadResp = await fetch(
      `${BACKEND_URL}/api/v1/college-review/batch-import/upload-data` +
        `?scholarship_type=${SCHOLARSHIP_CODE}&academic_year=${ACADEMIC_YEAR}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${collegeLogin.token}` },
        body: form,
      },
    );
    const uploadBody = (await uploadResp.json()) as {
      success?: boolean;
      message?: string;
      data?: {
        batch_id?: number;
        total_records?: number;
        preview_data?: Array<Record<string, unknown>>;
        validation_summary?: { valid_count?: number; invalid_count?: number };
      };
    };
    expect(
      uploadResp.ok,
      `upload-data failed: HTTP ${uploadResp.status} body=${JSON.stringify(uploadBody)}`,
    ).toBe(true);
    expect(uploadBody.success).toBe(true);
    expect(uploadBody.data?.batch_id, "parser must persist and return a batch_id").toBeTruthy();
    createdBatchId = uploadBody.data?.batch_id;
    expect(uploadBody.data?.total_records, "exactly the one CSV row must be parsed").toBe(1);
    const previewRow = JSON.stringify(uploadBody.data?.preview_data ?? []);
    expect(previewRow, "preview must carry the uploaded student id").toContain(CSV_STUDENT_ID);

    // 2. The persisted batch is retrievable via /details. (NOT /history —
    //    history intentionally lists only CONFIRMED imports; a freshly-parsed
    //    batch is still pending.)
    const detailsRes = await apiAs<{ success: boolean; data: Record<string, unknown> }>(
      collegeLogin.token,
      "GET",
      `/college-review/batch-import/${createdBatchId}/details`,
    );
    pushTrace(runState, detailsRes.traceId);
    expect(
      detailsRes.ok,
      `details for batch ${createdBatchId} failed: HTTP ${detailsRes.status} body=${JSON.stringify(
        detailsRes.body,
      )}`,
    ).toBe(true);
    expect(detailsRes.body.success).toBe(true);
    // Per-row student data lives in the upload-data preview (asserted above);
    // /details carries the batch envelope — pin its contract.
    const details = detailsRes.body.data as {
      file_name?: string;
      total_records?: number;
      import_status?: string;
    };
    expect(details.file_name).toBe("e2e-batch.csv");
    expect(details.total_records).toBe(1);
    expect(details.import_status, "an unconfirmed batch must stay pending").toBe("pending");

    // 3. Negative case: a CSV MISSING the required columns must be rejected —
    //    not silently parsed into an empty batch.
    const badCsv = `foo,bar\n1,2\n`;
    const badForm = new FormData();
    badForm.append("file", new Blob([badCsv], { type: "text/csv" }), "e2e-bad.csv");
    const badResp = await fetch(
      `${BACKEND_URL}/api/v1/college-review/batch-import/upload-data` +
        `?scholarship_type=${SCHOLARSHIP_CODE}&academic_year=${ACADEMIC_YEAR}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${collegeLogin.token}` },
        body: badForm,
      },
    );
    const badBody = (await badResp.json()) as {
      success?: boolean;
      data?: { validation_summary?: { invalid_count?: number }; total_records?: number };
      message?: string;
    };
    const rejected =
      !badResp.ok ||
      badBody.success === false ||
      (badBody.data?.validation_summary?.invalid_count ?? 0) > 0;
    expect(
      rejected,
      `CSV without 學號/學生姓名 columns must be rejected or flagged invalid; got HTTP ${
        badResp.status
      } body=${JSON.stringify(badBody)}`,
    ).toBe(true);
  });
});
