/**
 * E2E spec: a student uploads a document to a DRAFT, saves the draft with an
 * EMPTY documents[] (the exact frontend payload shape that caused the bug),
 * reopens it, and confirms the uploaded file is NOT lost and IS previewable.
 *
 * Regression guard for:
 *   - PR #885 — get_application_by_id rebuilds submitted_form_data.documents[]
 *     from application_files (a draft saved with documents:[] used to lose every
 *     uploaded file on reopen).
 *   - PR #890 — the same create-or-update enrichment applied to the other read
 *     paths (get_applications / get_applications_for_review /
 *     get_student_dashboard_stats / submit_application).
 *   - PR #885 frontend preview — the same-origin /api/v1/preview proxy serves the
 *     file inline so the wizard's preview iframe renders it.
 *
 * Flow under test (stuphd001):
 *   POST /applications?is_draft=true
 *   POST /applications/{id}/files/upload?file_type=transcript   (multipart)
 *   PUT  /applications/{id}   with form_data.documents = []      (the bug shape)
 *   GET  /applications/{id}   → documents[] REBUILT, contains the upload
 *   GET  {file_path}          → backend serves the file inline (200, %PDF)
 *   GET  /api/v1/preview?...   → Next.js proxy serves it (200, application/pdf)
 *
 * Pinned invariants:
 * - A file uploaded to a draft survives a save that sends documents:[] —
 *   reopening rebuilds documents[] from application_files (the #885/#890 bug).
 * - The rebuilt doc carries a real file_id and a same-origin /files/... file_path.
 * - Form field values still round-trip through that documents:[] save.
 * - The file is retrievable BOTH via the backend inline endpoint AND via the
 *   Next.js /api/v1/preview proxy the wizard uses for preview.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, getActiveConfig, getApplication, pool } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const API_V1 = "http://localhost:8000/api/v1";
const FRONTEND = "http://localhost:3000";

const STUDENT_ID = "stuphd001";
const SCHOLARSHIP_CODE = "phd";
const SUB_TYPE = "nstc";
const DOC_TYPE = "transcript";

// A minimal but valid one-page PDF — clearly not a 19-byte placeholder.
const PDF_BYTES = Buffer.from(
  "%PDF-1.4\n" +
    "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
    "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
    "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n" +
    "trailer<</Root 1 0 R>>\n%%EOF\n",
  "latin1",
);

/**
 * Pre-clean any existing applications for (student, scholarship_type) so the
 * unique constraint uq_user_scholarship_academic_term doesn't fire when another
 * spec's afterAll cleanup hasn't propagated yet. stuphd001 + phd is shared with
 * multi-role-phd / student-withdraw / student-draft-save specs.
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

interface DocEntry {
  document_type?: string;
  document_id?: string;
  file_id?: number;
  file_path?: string;
}

test.describe.configure({ mode: "serial" });

test.describe("Student uploads a document to a draft, reopens it, and previews it", () => {
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

  test("@nightly stuphd001 upload → save draft (documents:[]) → reopen keeps file → preview works", async ({
    browser,
  }) => {
    // 0. Drain leftover (stuphd001, phd) apps from concurrent specs.
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    // 1. Student logs in and creates a DRAFT application.
    const studentLogin = await loginAs(browser, STUDENT_ID);
    pushTrace(runState, studentLogin.traceId);

    const config = await getActiveConfig(SCHOLARSHIP_CODE);

    const createRes = await apiAs<{
      success: boolean;
      data: { id: number; app_id: string };
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
      `create draft failed: HTTP ${createRes.status} body=${JSON.stringify(createRes.body)}`,
    ).toBe(true);

    const appDbId = createRes.body.data.id;
    const appId = createRes.body.data.app_id;
    createdAppId = appId;
    runState.appId = appId;

    // 2. Upload a document to the draft (multipart). apiAs is JSON-only, so use
    //    a raw fetch with FormData. This creates an application_files row but
    //    does NOT touch submitted_form_data.documents.
    const form = new FormData();
    form.append("file", new Blob([PDF_BYTES], { type: "application/pdf" }), "transcript.pdf");
    const uploadResp = await fetch(
      `${API_V1}/applications/${appDbId}/files/upload?file_type=${DOC_TYPE}`,
      { method: "POST", headers: { Authorization: `Bearer ${studentLogin.token}` }, body: form },
    );
    expect(
      uploadResp.ok,
      `file upload failed: HTTP ${uploadResp.status} body=${await uploadResp.text().catch(() => "")}`,
    ).toBe(true);

    // 3. Save the draft with form fields AND an EMPTY documents[] — this is the
    //    exact payload shape the frontend used to send, which is what made the
    //    uploaded file "disappear" on reopen before #885.
    const updateRes = await apiAs<{ success: boolean }>(
      studentLogin.token,
      "PUT",
      `/applications/${appDbId}`,
      {
        form_data: {
          fields: {
            contact_phone: {
              field_id: "contact_phone",
              field_type: "text",
              value: "0912-345-678",
              required: false,
            },
          },
          documents: [],
        },
        agree_terms: true,
      },
    );
    pushTrace(runState, updateRes.traceId);
    expect(
      updateRes.ok,
      `save draft failed: HTTP ${updateRes.status} body=${JSON.stringify(updateRes.body)}`,
    ).toBe(true);

    // Status must still be draft (saving documents:[] is not a submit).
    const afterUpdate = await getApplication(appId);
    expect(afterUpdate!.status).toBe("draft");

    // 4. Reopen. Despite saving documents:[], the read path must REBUILD
    //    documents[] from application_files (the #885/#890 fix), and the form
    //    field must round-trip.
    const getRes = await apiAs<{
      data: {
        submitted_form_data?: {
          fields?: Record<string, { value?: unknown }>;
          documents?: DocEntry[];
        };
      };
    }>(studentLogin.token, "GET", `/applications/${appDbId}`);
    pushTrace(runState, getRes.traceId);
    expect(
      getRes.ok,
      `reopen failed: HTTP ${getRes.status} body=${JSON.stringify(getRes.body)}`,
    ).toBe(true);

    const formData = getRes.body.data.submitted_form_data ?? {};
    expect(
      formData.fields?.contact_phone?.value,
      `form field must round-trip through the documents:[] save, got ${JSON.stringify(formData.fields)}`,
    ).toBe("0912-345-678");

    const docs = formData.documents ?? [];
    const uploaded = docs.find((d) => d.document_type === DOC_TYPE || d.document_id === DOC_TYPE);
    expect(
      uploaded,
      `uploaded ${DOC_TYPE} must survive the documents:[] save (rebuilt from application_files), got docs=${JSON.stringify(docs)}`,
    ).toBeTruthy();
    expect(uploaded!.file_id, "rebuilt doc must carry a real file_id").toBeTruthy();
    expect(
      String(uploaded!.file_path),
      "rebuilt doc must carry a same-origin /files/applications/{id}/files/ path",
    ).toContain(`/files/applications/${appDbId}/files/`);

    // 5a. The file is retrievable inline via the backend endpoint (the content
    //     source the preview proxy forwards to). file_path carries its own token.
    const inlineResp = await fetch(String(uploaded!.file_path));
    expect(
      inlineResp.ok,
      `backend inline file fetch failed: HTTP ${inlineResp.status}`,
    ).toBe(true);
    const inlineBytes = Buffer.from(await inlineResp.arrayBuffer());
    expect(
      inlineBytes.subarray(0, 5).toString("latin1"),
      "backend must serve a real PDF, not a placeholder",
    ).toBe("%PDF-");

    // 5b. The Next.js /api/v1/preview proxy (what the wizard's preview iframe
    //     uses) serves it from the same origin as the SPA.
    const previewUrl =
      `${FRONTEND}/api/v1/preview?fileId=${uploaded!.file_id}` +
      `&filename=transcript.pdf&type=pdf&applicationId=${appDbId}` +
      `&token=${encodeURIComponent(studentLogin.token)}`;
    const previewResp = await fetch(previewUrl);
    expect(
      previewResp.ok,
      `preview proxy failed: HTTP ${previewResp.status} body=${await previewResp.text().catch(() => "")}`,
    ).toBe(true);
    expect(
      (previewResp.headers.get("content-type") ?? "").toLowerCase(),
      "preview proxy must serve the document as a PDF for inline rendering",
    ).toContain("application/pdf");
  });
});
