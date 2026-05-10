/**
 * Scenario 3 — admin generates a payment roster.
 *
 * Flow:
 *   admin → POST /payment-rosters/generate
 *           body: { scholarship_configuration_id, period_label, roster_cycle,
 *                   academic_year, student_verification_enabled: false }
 *           → DB payment_rosters has the new row keyed by (config_id, period)
 *
 * The endpoint sits in front of RosterService.generate_roster (covered by
 * Phase 3 contract tests). This e2e exercises the full HTTP → RosterService
 * → Postgres path under docker-compose.dev.yml.
 *
 * Cleanup: the inserted payment_rosters row is removed in afterAll so reruns
 * are idempotent.
 *
 * Phase 4 of the test-surface-hardening plan. Tagged @smoke so the new
 * CI e2e-smoke job picks it up alongside the whitelist + multi-role specs.
 */
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

// Use direct_phd (NOT phd): seed_scholarship_configs.py:258 sets
// direct_phd_114 to QuotaManagementMode.simple, while phd_114 is
// matrix_based — and matrix-mode rosters require a prior matrix
// distribution before /payment-rosters/generate will accept them
// (see roster_service.py: "找不到已執行分發的排名"). This spec only
// exercises the HTTP → RosterService → Postgres path; the matrix
// distribution flow is its own scenario.
const SCHOLARSHIP_CODE = "direct_phd";
// Use a far-future period_label so this spec never collides with seed data
// or with the multi-role-phd spec running in the same Postgres.
const PERIOD_LABEL = "2099-E2E";

test.describe.configure({ mode: "serial" });

test.describe("Admin generates a payment roster", () => {
  let runState: RunState;
  let createdRosterId: number | undefined;

  test.beforeEach(() => {
    runState = newRunState();
    createdRosterId = undefined;
  });

  test.afterEach(async ({}, testInfo) => {
    if (createdRosterId) runState.rosterId = createdRosterId;
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    if (createdRosterId !== undefined) {
      try {
        await pool.query(
          "DELETE FROM payment_roster_items WHERE roster_id = $1",
          [createdRosterId],
        );
        await pool.query("DELETE FROM payment_rosters WHERE id = $1", [
          createdRosterId,
        ]);
      } catch {
        // best-effort cleanup
      }
    }
  });

  test("@smoke admin generates a roster for the phd configuration", async ({
    browser,
  }) => {
    const config = await getActiveConfig(SCHOLARSHIP_CODE);

    const adminLogin = await loginAs(browser, "admin");
    pushTrace(runState, adminLogin.traceId);

    const res = await apiAs<{
      success: boolean;
      message?: string;
      data: { id: number; period_label: string; status?: string };
    }>(adminLogin.token, "POST", "/payment-rosters/generate", {
      scholarship_configuration_id: config.id,
      period_label: PERIOD_LABEL,
      roster_cycle: "monthly",
      academic_year: config.academic_year,
      student_verification_enabled: false,
      auto_export_excel: false,
      force_regenerate: true,
    });
    pushTrace(runState, res.traceId);

    expect(
      res.ok,
      `roster generate failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
    ).toBe(true);
    expect(res.body.success).toBe(true);
    expect(res.body.data.id).toBeGreaterThan(0);
    expect(res.body.data.period_label).toBe(PERIOD_LABEL);
    createdRosterId = res.body.data.id;

    // DB confirms.
    const { rows } = await pool.query(
      `SELECT id, scholarship_configuration_id, period_label, status
       FROM payment_rosters WHERE id = $1`,
      [createdRosterId],
    );
    expect(rows.length).toBe(1);
    expect(rows[0].scholarship_configuration_id).toBe(config.id);
    expect(rows[0].period_label).toBe(PERIOD_LABEL);
  });
});
