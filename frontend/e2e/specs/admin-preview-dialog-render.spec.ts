/**
 * E2E spec: the admin document-preview dialog actually RENDERS an uploaded PDF
 * — not just that the preview proxy returns 200.
 *
 * Why this exists: the #885 spec (student-draft-document-preview) pins the
 * API contract (proxy → 200 application/pdf), but three later production bugs
 * all had a GREEN proxy while the UI failed, so nightly never caught them:
 *
 *   - #942/#943 — the /api/v1/preview response carried X-Frame-Options: DENY +
 *     CSP frame-ancestors 'none' (middleware + nginx), so the browser refused
 *     to frame it ("refused to connect"). Proxy still 200.
 *   - #944 — Chrome's PDF viewer never fires the iframe onLoad, so the
 *     FilePreviewDialog skeleton covered an opacity-0 iframe forever
 *     ("載入中…" stuck). Proxy still 200.
 *   - #928/#930 — pdfjs API↔worker version mismatch made react-pdf reject
 *     getDocument BEFORE fetching; the worker asset itself served fine.
 *
 * Test 1 drives the real super_admin UI: 審核管理 → 博士生獎學金 → open the
 * application detail dialog → 上傳文件 → 預覽, and asserts the three UI-layer
 * invariants the proxy-200 check cannot see:
 *   (a) no X-Frame-Options / frame-ancestors console violation,
 *   (b) the preview response the iframe actually loads is 200 application/pdf,
 *   (c) the dialog iframe becomes visible (skeleton cleared) within the
 *       fallback window.
 *
 * Test 2 pins the pdfjs worker-version contract: /pdf.worker.min.mjs must
 * embed exactly the pdfjs-dist version from package.json (the #928 class —
 * pdf.js hard-rejects a worker whose version differs from the API).
 *
 * NOTE (dev-env scope): localhost dev serves the frontend directly (no nginx),
 * so this catches middleware/dialog regressions; the nginx header layer is
 * covered by config review + staging validation.
 */
import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, getActiveConfig, pool } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const API_V1 = "http://localhost:8000/api/v1";
const FRONTEND = "http://localhost:3000";

const STUDENT_ID = "stuphd001";
const ADMIN_ID = "super_admin";
const SCHOLARSHIP_CODE = "phd";
const SCHOLARSHIP_TAB = "博士生獎學金";
const SUB_TYPE = "nstc";
const DOC_TYPE = "transcript";
const PDF_NAME = "preview-render.pdf";

// A minimal but valid one-page PDF (same shape the #885 spec uploads).
const PDF_BYTES = Buffer.from(
  "%PDF-1.4\n" +
    "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
    "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
    "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n" +
    "trailer<</Root 1 0 R>>\n%%EOF\n",
  "latin1",
);

/** Drain leftover (student, scholarship) apps so the unique constraint
 * uq_user_scholarship_academic_term doesn't fire (stuphd001+phd is shared
 * with multi-role-phd / student-draft-save / student-withdraw specs). */
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

/** Collect framing-violation console messages (the #942 failure signal). */
function trackFramingViolations(page: Page): string[] {
  const violations: string[] = [];
  page.on("console", (msg) => {
    const text = msg.text();
    if (/refused to display|x-frame-options|frame-ancestors/i.test(text)) {
      violations.push(text.slice(0, 200));
    }
  });
  return violations;
}

test.describe.configure({ mode: "serial" });

test.describe("Admin preview dialog renders an uploaded PDF (UI layer)", () => {
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

  test("@nightly stuphd001 upload+submit → super_admin opens 預覽 → iframe visible, no framing block", async ({
    browser,
  }) => {
    // ---- Setup via API: draft → upload PDF → submit ----
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    const studentLogin = await loginAs(browser, STUDENT_ID);
    pushTrace(runState, studentLogin.traceId);
    const config = await getActiveConfig(SCHOLARSHIP_CODE);

    const createRes = await apiAs<{ success: boolean; data: { id: number; app_id: string } }>(
      studentLogin.token,
      "POST",
      "/applications?is_draft=true",
      {
        scholarship_type: SCHOLARSHIP_CODE,
        configuration_id: config.id,
        scholarship_subtype_list: [SUB_TYPE],
        sub_type_preferences: [SUB_TYPE],
        form_data: { fields: {}, documents: [] },
        agree_terms: true,
      },
    );
    pushTrace(runState, createRes.traceId);
    expect(
      createRes.ok,
      `create draft failed: HTTP ${createRes.status} body=${JSON.stringify(createRes.body)}`,
    ).toBe(true);
    const appDbId = createRes.body.data.id;
    createdAppId = createRes.body.data.app_id;
    runState.appId = createdAppId;

    const form = new FormData();
    form.append("file", new Blob([PDF_BYTES], { type: "application/pdf" }), PDF_NAME);
    const uploadResp = await fetch(`${API_V1}/applications/${appDbId}/files/upload?file_type=${DOC_TYPE}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${studentLogin.token}` },
      body: form,
    });
    expect(uploadResp.ok, `upload failed: HTTP ${uploadResp.status}`).toBe(true);

    const submitRes = await apiAs<{ success: boolean }>(
      studentLogin.token,
      "POST",
      `/applications/${appDbId}/submit`,
    );
    pushTrace(runState, submitRes.traceId);
    expect(
      submitRes.ok,
      `submit failed: HTTP ${submitRes.status} body=${JSON.stringify(submitRes.body)}`,
    ).toBe(true);
    await studentLogin.context.close();

    // ---- Drive the real admin UI ----
    const adminLogin = await loginAs(browser, ADMIN_ID);
    pushTrace(runState, adminLogin.traceId);
    const page = await adminLogin.context.newPage();
    const framingViolations = trackFramingViolations(page);
    const previewResponses: Array<{ status: number; contentType: string }> = [];
    page.on("response", (r) => {
      if (r.url().includes("/api/v1/preview?")) {
        previewResponses.push({
          status: r.status(),
          contentType: r.headers()["content-type"] ?? "",
        });
      }
    });

    await page.goto(`${FRONTEND}/`);
    await page.getByRole("tab", { name: "審核管理" }).click();
    await page.getByRole("tab", { name: SCHOLARSHIP_TAB }).waitFor({ timeout: 10_000 });
    await page.getByRole("tab", { name: SCHOLARSHIP_TAB }).click();

    // Find the application row and open its detail dialog. The 操作 cell holds
    // [eye=detail, trash=delete] for super_admin — click the FIRST button (the
    // eye). Clicking .last() opens the 確認刪除申請 modal instead.
    const search = page.getByPlaceholder(/搜尋|申請人/).first();
    await search.waitFor({ timeout: 10_000 });
    await search.fill(STUDENT_ID);
    const row = page.locator("tr", { hasText: STUDENT_ID }).first();
    await row.waitFor({ timeout: 10_000 });
    await row.locator("td").last().locator("button, [role='button'], a").first().click();

    const dialog = page.getByRole("dialog").first();
    await dialog.waitFor({ timeout: 10_000 });
    await dialog.getByText(/上傳文件/).first().click();
    await dialog.getByText(PDF_NAME).first().waitFor({ timeout: 10_000 });
    await dialog.getByRole("button", { name: /預覽/ }).first().click();

    // (b) the iframe really fetched the PDF through the proxy.
    await expect
      .poll(() => previewResponses.length, { timeout: 10_000, message: "preview proxy never hit" })
      .toBeGreaterThan(0);
    expect(previewResponses[0].status, "preview proxy status").toBe(200);
    expect(previewResponses[0].contentType).toContain("application/pdf");

    // (c) the preview iframe becomes visible — i.e. the loading skeleton
    // cleared even though Chrome's PDF viewer may never fire onLoad (#944).
    const iframe = page.locator(`iframe[title="${PDF_NAME}"]`);
    await iframe.waitFor({ state: "attached", timeout: 10_000 });
    await expect
      .poll(
        async () => (await iframe.getAttribute("class")) ?? "",
        { timeout: 10_000, message: "preview iframe never became visible (skeleton stuck — #944 class)" },
      )
      .toContain("opacity-100");

    // (a) the browser did not refuse to frame the preview (#942 class).
    expect(framingViolations, "framing violations in console").toEqual([]);

    await adminLogin.context.close();
  });
});

test.describe("pdfjs worker version contract", () => {
  test("@nightly /pdf.worker.min.mjs version === package.json pdfjs-dist (the #928 class)", async () => {
    // pdf.js hard-rejects getDocument when the worker version differs from the
    // API version — BEFORE fetching the PDF — so a drifted public/ worker
    // breaks every react-pdf preview (regulations PDF in the consent step).
    const pkg = JSON.parse(readFileSync(join(__dirname, "..", "..", "package.json"), "utf-8")) as {
      dependencies: Record<string, string>;
    };
    const pinned = pkg.dependencies["pdfjs-dist"];
    expect(pinned, "pdfjs-dist must be EXACT-pinned (no ^/~) so the worker can't drift").toMatch(
      /^\d+\.\d+\.\d+$/,
    );

    const resp = await fetch(`${FRONTEND}/pdf.worker.min.mjs`);
    expect(resp.status, "/pdf.worker.min.mjs must be served").toBe(200);
    const workerSource = await resp.text();

    // The worker embeds its own version as a bare "x.y.z" string literal.
    expect(
      workerSource.includes(`"${pinned}"`),
      `worker does not embed version ${pinned} — API↔worker mismatch would reject all react-pdf previews (#928)`,
    ).toBe(true);
  });
});
