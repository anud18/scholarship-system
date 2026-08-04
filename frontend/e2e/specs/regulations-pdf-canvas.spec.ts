/**
 * E2E spec: the 獎學金要點 (regulations) PDF actually RENDERS in the consent
 * step — react-pdf canvas pages appear, no 「無法載入文件」.
 *
 * Why: #928 — a pdfjs API↔worker version mismatch made react-pdf reject
 * getDocument BEFORE fetching the PDF, so the consent step showed 「無法載入
 * 文件」 and blocked EVERY application. The worker asset itself served 200,
 * and no test drove the actual canvas render, so nightly stayed green.
 * admin-preview-dialog-render.spec.ts pins the worker-version contract; this
 * spec pins the END RESULT the user sees: real canvas pages in the dialog.
 *
 * This is the OTHER preview mechanism — react-pdf canvas (InlinePdfViewer),
 * NOT the iframe + /api/v1/preview proxy — so the iframe specs cannot cover
 * it.
 *
 * Pre-req: the dev seed ships a regulations PDF
 * (system_settings.regulations_url = system-docs/regulations_url_seed.pdf).
 * If that ever disappears the spec fails on the explicit pre-check with a
 * clear message rather than a silent skip.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { deleteApplicationCascade, pool } from "../helpers/db";
import { attachRunState, newRunState, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const STUDENT_ID = "stuphd001";
const SCHOLARSHIP_CODE = "phd";

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

test.describe("Regulations PDF renders as react-pdf canvas in the consent step", () => {
  let runState: RunState;

  test.beforeEach(() => {
    runState = newRunState();
  });

  test.afterEach(async ({}, testInfo) => {
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test("@nightly stuphd001 opens 閱讀獎學金要點 → canvas pages render, no 無法載入文件", async ({
    browser,
  }) => {
    // Pre-check: the seed regulations PDF must be configured — fail loudly,
    // never skip silently.
    const { rows } = await pool.query<{ value: string }>(
      "SELECT value FROM system_settings WHERE key = 'regulations_url'",
    );
    expect(
      rows[0]?.value,
      "dev seed must configure system_settings.regulations_url (regulations PDF) — the consent step depends on it",
    ).toBeTruthy();

    // A leftover application can make the scholarship non-selectable and
    // change the portal's new-application rendering — purge first.
    await purgeStudentApps(STUDENT_ID, SCHOLARSHIP_CODE);

    const studentLogin = await loginAs(browser, STUDENT_ID);
    const page = await studentLogin.context.newPage();

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("tab", { name: "學生申請" }).click();

    // Step 1 of the wizard = NoticeAgreementStep.
    const openButton = page.getByRole("button", { name: /閱讀獎學金要點/ });
    await openButton.waitFor({ timeout: 15_000 });

    // The #928 failure mode shows the missing/blocked copy instead of the
    // button working — assert the blocking copy is absent up front.
    await expect(page.getByText("系統管理員尚未上傳獎學金要點")).toHaveCount(0);

    await openButton.click();
    const dialog = page.getByRole("dialog").first();
    await dialog.waitFor({ timeout: 10_000 });
    await expect(dialog.getByText("獎學金要點").first()).toBeVisible();

    // The dispositive assertion: react-pdf rendered REAL canvas pages.
    // With a version-mismatched worker (#928) getDocument rejects before any
    // canvas exists and InlinePdfViewer shows 「無法載入文件」 instead.
    await expect
      .poll(async () => dialog.locator("canvas").count(), {
        timeout: 20_000,
        message: "react-pdf never rendered a canvas page (the #928 failure mode)",
      })
      .toBeGreaterThan(0);
    await expect(dialog.getByText("無法載入文件")).toHaveCount(0);

    await studentLogin.context.close();
  });
});
