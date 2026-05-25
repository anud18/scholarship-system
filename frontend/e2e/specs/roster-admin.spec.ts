import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { getActiveConfig, pool } from "../helpers/db";
import {
  attachRunState,
  newRunState,
  pushTrace,
  type RunState,
} from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

// direct_phd uses QuotaManagementMode.simple so POST /payment-rosters/generate
// accepts it directly without a prior matrix distribution (see roster-generation.spec.ts).
// phd is matrix_based and requires generate-rosters-from-distribution first.
const SCHOLARSHIP_CODE = "direct_phd";

// Use a distinct period_label so this spec never collides with roster-generation.spec.ts
// which uses "2099-E2E" on the same config.
const PERIOD_LABEL = "2099-E2E-SCHEDULE";

test.describe.configure({ mode: "serial" });

// ---------------------------------------------------------------------------
// §1 — Roster admin management flows
// ---------------------------------------------------------------------------

test.describe("Admin roster management flows @nightly", () => {
  let runState: RunState;
  let adminToken: string;
  let rosterId: number | undefined;
  let excludedItemId: number | undefined;
  let auditLogCountBefore: number | undefined;

  test.beforeAll(async ({ browser }) => {
    const config = await getActiveConfig(SCHOLARSHIP_CODE);

    // Pre-clean any leftover roster for this period_label so force_regenerate
    // is not required and the test is idempotent across reruns.
    await pool.query(
      `DELETE FROM roster_audit_logs
         WHERE roster_id IN (
           SELECT id FROM payment_rosters
            WHERE scholarship_configuration_id = $1
              AND period_label = $2
         )`,
      [config.id, PERIOD_LABEL],
    );
    await pool.query(
      `DELETE FROM payment_roster_items
         WHERE roster_id IN (
           SELECT id FROM payment_rosters
            WHERE scholarship_configuration_id = $1
              AND period_label = $2
         )`,
      [config.id, PERIOD_LABEL],
    );
    await pool.query(
      `DELETE FROM payment_rosters
         WHERE scholarship_configuration_id = $1 AND period_label = $2`,
      [config.id, PERIOD_LABEL],
    );

    const adminLogin = await loginAs(browser, "admin");
    adminToken = adminLogin.token;

    const res = await apiAs<{
      success: boolean;
      message?: string;
      data: { id: number; period_label: string };
    }>(adminToken, "POST", "/payment-rosters/generate", {
      scholarship_configuration_id: config.id,
      period_label: PERIOD_LABEL,
      roster_cycle: "monthly",
      academic_year: config.academic_year,
      student_verification_enabled: false,
      auto_export_excel: false,
    });
    if (!res.ok || !res.body.success) {
      throw new Error(
        `roster-admin beforeAll: generate failed HTTP ${res.status} body=${JSON.stringify(res.body)}`,
      );
    }
    rosterId = res.body.data.id;
  });

  test.beforeEach(() => {
    runState = newRunState();
  });

  test.afterEach(async ({}, testInfo) => {
    if (rosterId !== undefined) runState.rosterId = rosterId;
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    if (rosterId !== undefined) {
      await pool
        .query("DELETE FROM roster_audit_logs WHERE roster_id = $1", [rosterId])
        .catch(() => undefined);
      await pool
        .query("DELETE FROM payment_roster_items WHERE roster_id = $1", [rosterId])
        .catch(() => undefined);
      // The roster may be locked after the lock test so we use SQL directly.
      await pool
        .query("DELETE FROM payment_rosters WHERE id = $1", [rosterId])
        .catch(() => undefined);
    }
  });

  test("@nightly roster items endpoint returns array (eligible/ineligible flag present)", async ({
    browser,
  }) => {
    const login = await loginAs(browser, "admin");
    pushTrace(runState, login.traceId);

    const res = await apiAs<{
      success: boolean;
      data: Array<{ id: number; is_qualified: boolean | null }>;
    }>(login.token, "GET", `/payment-rosters/${rosterId}/items`);
    pushTrace(runState, res.traceId);

    expect(
      res.ok,
      `GET items failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
    ).toBe(true);
    expect(res.body.success).toBe(true);
    expect(Array.isArray(res.body.data)).toBe(true);

    if (res.body.data.length > 0) {
      // Every item must expose the is_qualified flag (may be null when
      // student_verification_enabled=false and GPA rules don't apply).
      for (const item of res.body.data) {
        expect(typeof item.id).toBe("number");
        expect("is_qualified" in item).toBe(true);
      }
      // Stash for the exclude test.
      excludedItemId = res.body.data[0].id;
    }
    // A freshly generated roster with no approved applications produces zero
    // items — the schema still returns an empty array, which is the correct
    // contract. We verify the shape regardless of item count.
  });

  test("@nightly exclude one roster item → audit log grows", async ({ browser }) => {
    if (excludedItemId === undefined) {
      // No items were seeded; skip rather than false-positive.
      test.skip(
        true,
        "No roster items available — skipping exclude/audit-log test",
      );
      return;
    }

    const login = await loginAs(browser, "admin");
    pushTrace(runState, login.traceId);

    // Capture audit log count before exclusion.
    const logsBefore = await apiAs<{
      success: boolean;
      data: { total: number };
    }>(login.token, "GET", `/payment-rosters/${rosterId}/audit-logs`);
    pushTrace(runState, logsBefore.traceId);
    expect(logsBefore.ok).toBe(true);
    auditLogCountBefore = logsBefore.body.data.total;

    // Exclude the item.
    const excludeRes = await apiAs<{
      success: boolean;
      data: { id: number; is_included: boolean; exclusion_reason: string };
    }>(
      login.token,
      "POST",
      `/payment-rosters/${rosterId}/items/${excludedItemId}/exclude`,
      {
        reason_category: "declined",
        reason_note: "E2E test exclusion",
      },
    );
    pushTrace(runState, excludeRes.traceId);

    expect(
      excludeRes.ok,
      `exclude failed: HTTP ${excludeRes.status} body=${JSON.stringify(excludeRes.body)}`,
    ).toBe(true);
    expect(excludeRes.body.success).toBe(true);
    expect(excludeRes.body.data.is_included).toBe(false);

    // Audit log must have grown.
    const logsAfter = await apiAs<{
      success: boolean;
      data: { total: number };
    }>(login.token, "GET", `/payment-rosters/${rosterId}/audit-logs`);
    pushTrace(runState, logsAfter.traceId);
    expect(logsAfter.ok).toBe(true);
    expect(logsAfter.body.data.total).toBeGreaterThan(auditLogCountBefore!);
  });

  test("@nightly download endpoint returns 200 for existing roster", async ({ browser }) => {
    const login = await loginAs(browser, "admin");
    pushTrace(runState, login.traceId);

    // use_minio=false avoids MinIO dependency; falls through to local
    // on-demand generation when no excel_file_path is set.
    const res = await apiAs<unknown>(
      login.token,
      "GET",
      `/payment-rosters/${rosterId}/download?use_minio=false`,
    );
    pushTrace(runState, res.traceId);

    expect(
      res.ok,
      `download failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
    ).toBe(true);
  });

  test("@nightly lock roster succeeds and roster status becomes locked", async ({ browser }) => {
    const login = await loginAs(browser, "admin");
    pushTrace(runState, login.traceId);

    const res = await apiAs<{
      success: boolean;
      data: { roster_code: string };
    }>(login.token, "POST", `/payment-rosters/${rosterId}/lock`);
    pushTrace(runState, res.traceId);

    expect(
      res.ok,
      `lock failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
    ).toBe(true);
    expect(res.body.success).toBe(true);

    // Verify DB status directly — the lock endpoint only returns roster_code.
    const { rows } = await pool.query<{ status: string }>(
      "SELECT status FROM payment_rosters WHERE id = $1",
      [rosterId],
    );
    expect(rows[0]?.status).toBe("locked");
  });
});

// ---------------------------------------------------------------------------
// §2 — Roster schedule management flows
// ---------------------------------------------------------------------------

test.describe("Admin roster schedule management @nightly", () => {
  let runState: RunState;
  let scheduleId: number | undefined;
  let configId: number;

  test.beforeAll(async () => {
    const config = await getActiveConfig(SCHOLARSHIP_CODE);
    configId = config.id;

    // Best-effort pre-clean: remove any leftover E2E schedule rows for this config.
    await pool
      .query(
        `DELETE FROM roster_schedules
           WHERE scholarship_configuration_id = $1
             AND schedule_name LIKE '%E2E%'`,
        [configId],
      )
      .catch(() => undefined);
  });

  test.beforeEach(() => {
    runState = newRunState();
  });

  test.afterEach(async ({}, testInfo) => {
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    if (scheduleId !== undefined) {
      await pool
        .query("DELETE FROM roster_schedules WHERE id = $1", [scheduleId])
        .catch(() => undefined);
    }
    // Also clean up any rosters auto-generated by the execute test.
    await pool
      .query(
        `DELETE FROM roster_audit_logs
           WHERE roster_id IN (
             SELECT id FROM payment_rosters
              WHERE scholarship_configuration_id = $1
                AND period_label NOT IN ($2, $3)
           )`,
        [configId, PERIOD_LABEL, "2099-E2E"],
      )
      .catch(() => undefined);
    await pool
      .query(
        `DELETE FROM payment_roster_items
           WHERE roster_id IN (
             SELECT id FROM payment_rosters
              WHERE scholarship_configuration_id = $1
                AND period_label NOT IN ($2, $3)
           )`,
        [configId, PERIOD_LABEL, "2099-E2E"],
      )
      .catch(() => undefined);
    await pool
      .query(
        `DELETE FROM payment_rosters
           WHERE scholarship_configuration_id = $1
             AND period_label NOT IN ($2, $3)`,
        [configId, PERIOD_LABEL, "2099-E2E"],
      )
      .catch(() => undefined);
  });

  test("@nightly create schedule → row exists in DB with active status", async ({ browser }) => {
    const login = await loginAs(browser, "admin");
    pushTrace(runState, login.traceId);

    const res = await apiAs<{
      success: boolean;
      data: { id: number; schedule_name: string; status: string };
    }>(login.token, "POST", "/roster-schedules", {
      schedule_name: "E2E Schedule Test",
      scholarship_configuration_id: configId,
      roster_cycle: "monthly",
      student_verification_enabled: false,
      notification_enabled: false,
    });
    pushTrace(runState, res.traceId);

    expect(
      res.ok,
      `create schedule failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
    ).toBe(true);
    expect(res.body.success).toBe(true);
    expect(res.body.data.id).toBeGreaterThan(0);
    expect(res.body.data.status).toBe("active");
    scheduleId = res.body.data.id;

    const { rows } = await pool.query<{ status: string; schedule_name: string }>(
      "SELECT status, schedule_name FROM roster_schedules WHERE id = $1",
      [scheduleId],
    );
    expect(rows.length).toBe(1);
    expect(rows[0].schedule_name).toBe("E2E Schedule Test");
    expect(rows[0].status).toBe("active");
  });

  test("@nightly pause schedule → status becomes paused", async ({ browser }) => {
    const login = await loginAs(browser, "admin");
    pushTrace(runState, login.traceId);

    const res = await apiAs<{
      success: boolean;
      data: { status: string };
    }>(login.token, "PATCH", `/roster-schedules/${scheduleId}/status`, {
      status: "paused",
    });
    pushTrace(runState, res.traceId);

    expect(
      res.ok,
      `pause failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
    ).toBe(true);
    expect(res.body.success).toBe(true);
    expect(res.body.data.status).toBe("paused");

    const { rows } = await pool.query<{ status: string }>(
      "SELECT status FROM roster_schedules WHERE id = $1",
      [scheduleId],
    );
    expect(rows[0]?.status).toBe("paused");
  });

  test("@nightly execute schedule immediately → last_run_at updated", async ({ browser }) => {
    const login = await loginAs(browser, "admin");
    pushTrace(runState, login.traceId);

    // Record last_run_at before trigger.
    const { rows: before } = await pool.query<{ last_run_at: Date | null }>(
      "SELECT last_run_at FROM roster_schedules WHERE id = $1",
      [scheduleId],
    );
    const runAtBefore = before[0]?.last_run_at ?? null;

    // The endpoint awaits _execute_roster_generation, which sets last_run_at
    // before returning. The response is 200 with { success: true }.
    const res = await apiAs<{
      success: boolean;
      data: { schedule_id: number };
    }>(
      login.token,
      "POST",
      `/roster-schedules/${scheduleId}/execute?force_regenerate=true`,
    );
    pushTrace(runState, res.traceId);

    expect(
      res.ok,
      `execute failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
    ).toBe(true);
    expect(res.body.success).toBe(true);
    expect(res.body.data.schedule_id).toBe(scheduleId);

    // last_run_at must have been set (or updated) by the execution.
    const { rows: after } = await pool.query<{ last_run_at: Date | null }>(
      "SELECT last_run_at FROM roster_schedules WHERE id = $1",
      [scheduleId],
    );
    const runAtAfter = after[0]?.last_run_at ?? null;
    expect(runAtAfter).not.toBeNull();
    if (runAtBefore !== null) {
      expect(new Date(runAtAfter!).getTime()).toBeGreaterThanOrEqual(
        new Date(runAtBefore).getTime(),
      );
    }
  });

  test("@nightly delete schedule → 200 and row gone from DB", async ({ browser }) => {
    const login = await loginAs(browser, "admin");
    pushTrace(runState, login.traceId);

    const res = await apiAs<{ success: boolean; message: string }>(
      login.token,
      "DELETE",
      `/roster-schedules/${scheduleId}`,
    );
    pushTrace(runState, res.traceId);

    expect(
      res.ok,
      `delete failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
    ).toBe(true);
    expect(res.body.success).toBe(true);

    const { rows } = await pool.query(
      "SELECT id FROM roster_schedules WHERE id = $1",
      [scheduleId],
    );
    expect(rows.length).toBe(0);

    // Prevent afterAll from issuing a redundant DELETE on an already-gone row.
    scheduleId = undefined;
  });
});
