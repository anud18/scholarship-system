/**
 * E2E spec: 匯入續領生 (renewal-students import) — the full lifecycle for the
 * new RenewalImportPanel surface, proven end-to-end against the live stack:
 *
 *   upload → preview → confirm → 造冊 (roster)
 *
 * What this pins:
 *   1. A super_admin can open the 匯入續領生 tab and see the RenewalImportPanel.
 *   2. Uploading a renewal sheet keeps ONLY the 是 + 通過 rows and filters the
 *      non-passing one (the core business rule of the feature).
 *   3. Confirm creates *approved renewal* Applications shaped for 造冊
 *      (is_renewal, status=approved, sub_scholarship_type=nstc,
 *      allocation_config_id=5, app_id ends with 'R').
 *   4. The non-passing student never becomes an application.
 *   5. 造冊 (generate-rosters-from-distribution) pulls those renewals into the
 *      nstc payment roster, each item labelled `114續領`.
 *
 * Yearly-cycle note: the panel's handleUpload sends `semester=yearly` for the
 * suffix-less (yearly) period — that fix is what lets this yearly (phd) UI
 * upload succeed end-to-end. The confirm + 造冊 steps run via the API (the
 * brief's sanctioned reliable path).
 *
 * The pool (helpers/db.ts) MUST target the throwaway clone — run with
 *   E2E_DATABASE_URL=postgresql://scholarship_user:scholarship_pass@localhost:5432/scholarship_e2e
 */
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { pool } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const SUPER_ADMIN = "super_admin";
const SCHOLARSHIP_CODE = "phd";
const SCHOLARSHIP_TYPE_ID = 2;
const CONFIG_ID = 5;
const ACADEMIC_YEAR = 114;
const PERIOD_VALUE = "114"; // yearly period.value exposed by the panel's period <select>
const FILE_NAME = "e2e-renewal-import.csv";

// Two passing (是 + 通過) + one non-passing (否). All three resolve in the mock
// SIS so the ONLY reason the third is excluded is the 是/通過 filter, not a
// missing snapshot — a clean proof of the business rule.
const PASS_1 = { id: "312551007", name: "陳暐誠" };
const PASS_2 = { id: "313612215", name: "陳弘穎" };
const SKIP_1 = { id: "312551183", name: "王小明" };

const EVIDENCE_DIR = path.resolve(__dirname, "../evidence/renewal-import");
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

function buildRenewalCsv(): string {
  const header =
    "編號,學院,系所,學生姓名,學號,學生年級,學生是否申請續領,續領審核結果,獎學金類別,郵局帳號,指導教授本校人事編號";
  const rows = [
    `1,電機學院,電機工程學系,${PASS_1.name},${PASS_1.id},博二,是,通過,國科會,0012345678901,P0012345`,
    `2,電機學院,電機工程學系,${PASS_2.name},${PASS_2.id},博三,是,通過,國科會,0012345678902,P0067890`,
    `3,理學院,應用數學系,${SKIP_1.name},${SKIP_1.id},博一,否,領獎期滿，無續領,,,`,
  ];
  return [header, ...rows].join("\n") + "\n";
}

/** Reset the clone's renewal state so the spec is idempotent (disposable DB). */
async function resetRenewalState(): Promise<void> {
  await pool.query(
    `DELETE FROM roster_audit_logs WHERE roster_id IN
       (SELECT id FROM payment_rosters WHERE scholarship_configuration_id=$1)`,
    [CONFIG_ID],
  );
  await pool.query(
    `DELETE FROM payment_roster_items WHERE roster_id IN
       (SELECT id FROM payment_rosters WHERE scholarship_configuration_id=$1)`,
    [CONFIG_ID],
  );
  await pool.query(`DELETE FROM payment_rosters WHERE scholarship_configuration_id=$1`, [CONFIG_ID]);
  await pool.query(
    `DELETE FROM applications
       WHERE is_renewal=true AND academic_year=$1 AND scholarship_type_id=$2`,
    [ACADEMIC_YEAR, SCHOLARSHIP_TYPE_ID],
  );
  await pool.query(
    `UPDATE batch_imports SET import_status='cancelled'
       WHERE import_type='renewal' AND import_status IN ('pending','processing')`,
  );
}

test.describe.configure({ mode: "serial" });

test.describe("Renewal import: upload → preview → confirm → 造冊", () => {
  let runState: RunState;
  let batchId: number | undefined;

  test.beforeAll(async () => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    await resetRenewalState();
  });

  test.beforeEach(() => {
    runState = newRunState();
    runState.configId = CONFIG_ID;
  });

  test.afterEach(async ({}, testInfo) => {
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test("super_admin imports 是+通過 renewals and they reach the nstc 造冊", async ({ browser }) => {
    test.setTimeout(180_000);

    // ── 1. Login (browser) ────────────────────────────────────────────────
    const login = await loginAs(browser, SUPER_ADMIN);
    const page = await login.context.newPage();
    page.setDefaultTimeout(30_000);
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 60_000 });
    const renewalTab = page.getByRole("tab", { name: /匯入續領生/ });
    await expect(renewalTab, "super_admin sees the 匯入續領生 tab").toBeVisible({ timeout: 60_000 });
    await page.screenshot({ path: shot("01-login.png"), fullPage: true });

    // ── 2. Open the RenewalImportPanel ────────────────────────────────────
    await renewalTab.click();
    await expect(page.getByText("匯入續領生名單")).toBeVisible({ timeout: 60_000 });
    await page.screenshot({ path: shot("02-renewal-tab.png"), fullPage: true });

    // ── 3+4. Upload via the real UI → preview ─────────────────────────────
    const selects = page.locator("select");
    await selects.nth(0).selectOption(SCHOLARSHIP_CODE); // 獎學金類型 → phd
    await expect(
      selects.nth(1).locator(`option[value="${PERIOD_VALUE}"]`),
      "period options load after picking the scholarship",
    ).toHaveCount(1, { timeout: 30_000 });
    await selects.nth(1).selectOption(PERIOD_VALUE); // 學年度 → 114
    await page.setInputFiles("#renewal-file-upload", {
      name: FILE_NAME,
      mimeType: "text/csv",
      buffer: Buffer.from(buildRenewalCsv(), "utf-8"),
    });

    const uploadRespP = page.waitForResponse(
      (r) => r.url().includes("renewal-import/upload") && r.request().method() === "POST",
      { timeout: 60_000 },
    );
    await page.getByRole("button", { name: /上傳並驗證/ }).click();
    const uploadResp = await uploadRespP;
    pushTrace(runState, uploadResp.headers()["x-trace-id"]);
    expect(uploadResp.ok(), `upload failed: HTTP ${uploadResp.status()}`).toBe(true);

    const uploadBody = (await uploadResp.json()) as {
      data?: {
        batch_id?: number;
        total_records?: number;
        skipped_records?: number;
        validation_summary?: { invalid_count?: number };
      };
    };
    batchId = uploadBody.data?.batch_id;
    expect(batchId, "parser persists a batch_id").toBeTruthy();
    expect(uploadBody.data?.total_records, "only the two 是+通過 rows are parsed").toBe(2);
    expect(uploadBody.data?.skipped_records, "the 否 row is filtered, not imported").toBe(1);
    expect(uploadBody.data?.validation_summary?.invalid_count, "no validation errors").toBe(0);

    // The genuine preview UI reflects the same filtering.
    await expect(page.getByText("資料預覽與驗證")).toBeVisible({ timeout: 30_000 });
    const summaryText =
      (await page.getByText(/通過.*筆.*跳過.*筆/).first().textContent()) ?? "";
    expect(summaryText, "UI summary shows 2 passed").toContain("通過 2");
    expect(summaryText, "UI summary shows 1 skipped").toContain("跳過 1");
    await expect(page.getByText(PASS_1.id), "passing student 1 in preview").toBeVisible();
    await expect(page.getByText(PASS_2.id), "passing student 2 in preview").toBeVisible();
    await expect(page.getByText(SKIP_1.id), "skipped student absent from preview").toHaveCount(0);
    await page.screenshot({ path: shot("03-preview.png"), fullPage: true });

    // ── 5. Confirm (API) → approved renewal applications ──────────────────
    const confirmRes = await apiAs<{
      data: { success_count: number; failed_count: number; created_application_ids: number[] };
    }>(login.token, "POST", `/college-review/renewal-import/${batchId}/confirm`, {
      batch_id: batchId,
      confirm: true,
    });
    pushTrace(runState, confirmRes.traceId);
    expect(
      confirmRes.ok,
      `confirm failed: HTTP ${confirmRes.status} ${JSON.stringify(confirmRes.body)}`,
    ).toBe(true);
    const createdAppIds = confirmRes.body.data.created_application_ids;
    expect(createdAppIds, "two approved renewals created").toHaveLength(2);

    const { rows: appRows } = await pool.query(
      `SELECT app_id, status, is_renewal, sub_scholarship_type, allocation_config_id
         FROM applications WHERE id = ANY($1::int[]) ORDER BY id`,
      [createdAppIds],
    );
    expect(appRows.length).toBe(2);
    for (const r of appRows) {
      expect(r.status).toBe("approved");
      expect(r.is_renewal).toBe(true);
      expect(r.sub_scholarship_type).toBe("nstc");
      expect(Number(r.allocation_config_id)).toBe(CONFIG_ID);
      expect(String(r.app_id).endsWith("R"), `app_id ${r.app_id} must end with R`).toBe(true);
    }
    runState.appId = appRows[0].app_id as string;

    // Core filter proof: the 否 student produced NO renewal application.
    const skipCheck = await pool.query(
      `SELECT count(*)::int AS c FROM applications a JOIN users u ON u.id = a.user_id
         WHERE u.nycu_id = $1 AND a.is_renewal = true AND a.academic_year = $2`,
      [SKIP_1.id, ACADEMIC_YEAR],
    );
    expect(skipCheck.rows[0].c, "非通過列不得建立續領申請").toBe(0);

    // ── 04 evidence: the confirmed batch appears in 歷史紀錄 ──────────────
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByRole("tab", { name: /匯入續領生/ }).click();
    await expect(page.getByText("匯入續領生名單")).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: /歷史紀錄/ }).click();
    await expect(page.getByText(FILE_NAME).first()).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: shot("04-after-confirm.png"), fullPage: true });

    // ── 6. 造冊 (API) ─────────────────────────────────────────────────────
    const rosterRes = await apiAs<{
      data: { rosters: Array<{ id: number; roster_code: string; sub_type: string }> };
    }>(login.token, "POST", "/manual-distribution/generate-rosters-from-distribution", {
      scholarship_type_id: SCHOLARSHIP_TYPE_ID,
      academic_year: ACADEMIC_YEAR,
      semester: "yearly",
      student_verification_enabled: false,
      force_regenerate: true,
    });
    pushTrace(runState, rosterRes.traceId);
    expect(
      rosterRes.ok,
      `roster generation failed: HTTP ${rosterRes.status} ${JSON.stringify(rosterRes.body)}`,
    ).toBe(true);
    const nstcRoster = rosterRes.body.data.rosters.find((r) => r.sub_type === "nstc");
    expect(nstcRoster, "an nstc roster was generated").toBeTruthy();
    runState.rosterId = nstcRoster!.id;

    // ── 7. The renewals are in the nstc roster, labelled 114續領 ──────────
    const rosterDb = await pool.query(
      `SELECT id, roster_code FROM payment_rosters
         WHERE scholarship_configuration_id = $1 AND sub_type = 'nstc'
         ORDER BY id DESC LIMIT 1`,
      [CONFIG_ID],
    );
    expect(rosterDb.rows.length, "nstc roster persisted").toBe(1);
    const items = await pool.query(
      `SELECT student_number, application_identity FROM payment_roster_items
         WHERE roster_id = $1 AND application_identity = $2 ORDER BY student_number`,
      [rosterDb.rows[0].id, `${ACADEMIC_YEAR}續領`],
    );
    const rosterStudentIds = items.rows.map((r) => r.student_number as string).sort();
    expect(rosterStudentIds, "both renewals appear in the nstc roster as 114續領").toEqual(
      [PASS_1.id, PASS_2.id].sort(),
    );

    // ── 05 evidence: the 造冊管理 dashboard ───────────────────────────────
    await page
      .getByRole("tab", { name: "造冊管理" })
      .click()
      .catch(() => undefined);
    await page.waitForTimeout(4000);
    await page.screenshot({ path: shot("05-roster.png"), fullPage: true });
  });
});
