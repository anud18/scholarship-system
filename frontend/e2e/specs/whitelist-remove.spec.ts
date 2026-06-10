/**
 * E2E spec: removing a student from the whitelist revokes eligibility.
 *
 * whitelist-grant.spec.ts pins the GRANT direction (not eligible → add →
 * eligible). This pins the inverse, which had no coverage: a student already
 * whitelisted loses access the moment the admin removes them — the eligible
 * list must NOT keep serving a stale grant.
 *
 * Flow:
 *   admin  → POST /scholarship-configurations/{id}/whitelist/batch (grant)
 *   student → GET /scholarships/eligible → contains undergraduate_freshman
 *   admin  → DELETE /scholarship-configurations/{id}/whitelist/batch (remove)
 *            → DB whitelist no longer contains the student
 *   student → GET /scholarships/eligible → undergraduate_freshman GONE
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { getActiveConfig, getWhitelist } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";
import { BACKEND_URL } from "../helpers/env";

const SCHOLARSHIP_CODE = "undergraduate_freshman";
const STUDENT = "stuunder1";
const SUB_TYPE = "general";

interface EligibleScholarship {
  code: string;
  name?: string;
}

test.describe.configure({ mode: "serial" });

test.describe("Whitelist removal revokes access to undergraduate_freshman", () => {
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
    // Best-effort: never leave the grant behind if the removal step failed.
    if (configId && whitelisted) {
      try {
        const r = await fetch(`${BACKEND_URL}/api/v1/auth/mock-sso/login`, {
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

  test("@nightly admin grant → student eligible → admin REMOVE → student no longer eligible", async ({
    browser,
  }) => {
    const config = await getActiveConfig(SCHOLARSHIP_CODE);
    configId = config.id;

    // 1. Admin grants (setup — the grant direction itself is pinned by
    //    whitelist-grant.spec.ts).
    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);
    const addRes = await apiAs<{ success: boolean; data: { added_count: number } }>(
      adminLogin.token,
      "POST",
      `/scholarship-configurations/${config.id}/whitelist/batch`,
      { students: [{ nycu_id: STUDENT, sub_type: SUB_TYPE }] },
    );
    pushTrace(runState, addRes.traceId);
    expect(addRes.ok, `grant failed: HTTP ${addRes.status} ${JSON.stringify(addRes.body)}`).toBe(true);
    whitelisted = true;

    // 2. Student is eligible while whitelisted.
    const studentLogin = await loginAs(browser, STUDENT);
    pushTrace(runState, studentLogin.traceId);
    const during = await apiAs<{ success: boolean; data: EligibleScholarship[] }>(
      studentLogin.token,
      "GET",
      "/scholarships/eligible",
    );
    pushTrace(runState, during.traceId);
    expect(during.ok).toBe(true);
    const duringCodes = (during.body.data ?? []).map((s) => s.code);
    expect(
      duringCodes,
      `${STUDENT} should see ${SCHOLARSHIP_CODE} while whitelisted; got ${JSON.stringify(duringCodes)}`,
    ).toContain(SCHOLARSHIP_CODE);

    // 3. Admin removes the student from the whitelist.
    const removeRes = await apiAs<{ success: boolean }>(
      adminLogin.token,
      "DELETE",
      `/scholarship-configurations/${config.id}/whitelist/batch`,
      { nycu_ids: [STUDENT], sub_type: SUB_TYPE },
    );
    pushTrace(runState, removeRes.traceId);
    expect(
      removeRes.ok,
      `whitelist remove failed: HTTP ${removeRes.status} body=${JSON.stringify(removeRes.body)}`,
    ).toBe(true);
    expect(removeRes.body.success).toBe(true);
    whitelisted = false;

    // 4. DB no longer lists the student.
    const wl = await getWhitelist(config.id);
    expect(wl[SUB_TYPE] ?? [], "DB whitelist must not contain the student after removal").not.toContain(
      STUDENT,
    );

    // 5. The dispositive assertion: a fresh eligibility check no longer
    //    serves the revoked grant.
    const studentLogin2 = await loginAs(browser, STUDENT);
    pushTrace(runState, studentLogin2.traceId);
    const after = await apiAs<{ success: boolean; data: EligibleScholarship[] }>(
      studentLogin2.token,
      "GET",
      "/scholarships/eligible",
    );
    pushTrace(runState, after.traceId);
    expect(after.ok).toBe(true);
    const afterCodes = (after.body.data ?? []).map((s) => s.code);
    expect(
      afterCodes,
      `${STUDENT} must NOT see ${SCHOLARSHIP_CODE} after whitelist removal; got ${JSON.stringify(afterCodes)}`,
    ).not.toContain(SCHOLARSHIP_CODE);
  });
});
