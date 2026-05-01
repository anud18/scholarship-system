/**
 * Scenario 2 — whitelist-driven access grant.
 *
 * Flow:
 *   stuunder1 (student)  → GET /scholarships/eligible
 *                           → undergraduate_freshman NOT in list
 *                              (whitelist_enabled=true and student not in list)
 *   admin                → POST /scholarship-configurations/{id}/whitelist/batch
 *                           students=[{nycu_id:'stuunder1', sub_type:'general'}]
 *                           → DB whitelist_student_ids.general contains stuunder1
 *   stuunder1 (re-login) → GET /scholarships/eligible
 *                           → undergraduate_freshman NOW present
 *
 * Cleanup: DELETE the whitelist entry so reruns are idempotent. Note shapes:
 *   POST body: { students:[{nycu_id, sub_type}] }
 *   DELETE body: { nycu_ids:[...], sub_type? }
 * (verified at backend/app/api/v1/endpoints/scholarship_configurations.py:1357,1416)
 *
 * Diagnose-and-fix table is in helpers/diagnose.ts.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { getActiveConfig, getWhitelist } from "../helpers/db";
import {
  attachRunState,
  newRunState,
  pushTrace,
  type RunState,
} from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const SCHOLARSHIP_CODE = "undergraduate_freshman";
const STUDENT = "stuunder1";
const SUB_TYPE = "general";

interface EligibleScholarship {
  code: string;
  name?: string;
}

test.describe.configure({ mode: "serial" });

test.describe("Whitelist grants access to undergraduate_freshman", () => {
  let runState: RunState;
  let configId: number | undefined;
  let whitelisted = false;

  test.beforeEach(() => {
    runState = newRunState();
  });

  test.afterEach(async ({}, testInfo) => {
    if (configId) runState.configId = configId;
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    if (configId && whitelisted) {
      try {
        const r = await fetch("http://localhost:8000/api/v1/auth/mock-sso/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nycu_id: "admin" }),
        });
        const body = (await r.json()) as { data?: { access_token?: string } };
        const token = body?.data?.access_token;
        if (token) {
          await apiAs(token, "DELETE", `/scholarship-configurations/${configId}/whitelist/batch`, {
            nycu_ids: [STUDENT],
            sub_type: SUB_TYPE,
          });
        }
      } catch {
        // best-effort cleanup
      }
    }
  });

  test("admin grants stuunder1 access via whitelist", async ({ browser }) => {
    // 1. Pre: student does NOT see undergraduate_freshman.
    const studentLogin = await loginAs(browser, STUDENT);
    pushTrace(runState, studentLogin.traceId);

    const before = await apiAs<{
      success: boolean;
      data: EligibleScholarship[];
    }>(studentLogin.token, "GET", "/scholarships/eligible");
    pushTrace(runState, before.traceId);
    expect(before.ok).toBe(true);
    expect(before.body.success).toBe(true);
    const beforeCodes = (before.body.data ?? []).map((s) => s.code);
    expect(
      beforeCodes,
      `${STUDENT} should NOT see ${SCHOLARSHIP_CODE} before being whitelisted; got ${JSON.stringify(beforeCodes)}`,
    ).not.toContain(SCHOLARSHIP_CODE);

    // 2. Admin adds stuunder1 to the whitelist for the active config.
    const config = await getActiveConfig(SCHOLARSHIP_CODE);
    configId = config.id;
    runState.configId = config.id;

    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    const addRes = await apiAs<{
      success: boolean;
      data: { added_count: number; errors: string[] };
    }>(
      adminLogin.token,
      "POST",
      `/scholarship-configurations/${config.id}/whitelist/batch`,
      {
        students: [{ nycu_id: STUDENT, sub_type: SUB_TYPE }],
      },
    );
    pushTrace(runState, addRes.traceId);
    expect(
      addRes.ok,
      `whitelist add failed: HTTP ${addRes.status} body=${JSON.stringify(addRes.body)}`,
    ).toBe(true);
    expect(addRes.body.success).toBe(true);
    expect(addRes.body.data.added_count).toBeGreaterThan(0);
    whitelisted = true;

    // 3. DB confirms.
    const wl = await getWhitelist(config.id);
    expect(wl[SUB_TYPE] ?? []).toContain(STUDENT);

    // 4. Re-login student → eligible list now contains undergraduate_freshman.
    const studentLogin2 = await loginAs(browser, STUDENT);
    pushTrace(runState, studentLogin2.traceId);

    const after = await apiAs<{
      success: boolean;
      data: EligibleScholarship[];
    }>(studentLogin2.token, "GET", "/scholarships/eligible");
    pushTrace(runState, after.traceId);
    expect(after.ok).toBe(true);
    expect(after.body.success).toBe(true);
    const afterCodes = (after.body.data ?? []).map((s) => s.code);
    expect(
      afterCodes,
      `${STUDENT} should NOW see ${SCHOLARSHIP_CODE} after whitelist; got ${JSON.stringify(afterCodes)}`,
    ).toContain(SCHOLARSHIP_CODE);

    // 5. UI smoke: student portal renders. The exact "可申請" chip rendering
    //    depends on portal copy and timing; we assert the student page loads
    //    without crashing. The dispositive assertion is the DB+API state above.
    const page = await studentLogin2.context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await expect(page.locator("body")).toBeVisible();
  });
});
