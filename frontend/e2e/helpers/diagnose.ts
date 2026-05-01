/**
 * Diagnose-and-fix decision rule.
 *
 * Use this table when an E2E spec fails. Read the attached `backend-logs.txt`
 * and `db-state.json` from the failed test's HTML report (or the
 * `=== DIAGNOSTIC: <name> ===` block printed to stdout).
 *
 *   | Symptom                                               | Class    | Where to fix                                                              |
 *   |-------------------------------------------------------|----------|---------------------------------------------------------------------------|
 *   | Backend log shows 5xx, exception, missing column,     | codebase | backend/app/services/{application,review,college_review,eligibility}_     |
 *   | enum mismatch                                         |          | service.py first; then the API endpoint                                    |
 *   | Seeded user / scholarship / config missing or in      | seed     | backend/app/seed.py + backend/app/db/seed_scholarship_configs.py           |
 *   | wrong state at test start                             |          |                                                                            |
 *   | API response correct (verified by `apiAs` inside the  | frontend | the relevant component under frontend/components/                          |
 *   | test) but UI does not reflect it                      |          |                                                                            |
 *   | Backend behavior is documented + intentional, test    | test     | the spec                                                                   |
 *   | asserted otherwise                                    |          |                                                                            |
 *
 * The dev's loop:
 *   npm run e2e
 *   → on failure read attached backend-logs.txt + db-state.json
 *   → classify per the table
 *   → patch the right layer
 *   → npm run e2e -- specs/<file>.spec.ts until green
 *
 * Never silence an assertion to make it pass.
 */

import type { TestInfo } from "@playwright/test";
import { captureBackendLogs } from "./logs";
import { dumpRelated } from "./db";
import type { RunState } from "./runState";

export const BACKEND_LOGS_ATTACHMENT = "backend-logs.txt";
export const DB_STATE_ATTACHMENT = "db-state.json";

export interface DiagnosticDump {
  testName: string;
  traceIds: string[];
  backendLogsPreview: string;
  dbState: Record<string, unknown>;
  classificationHint?: string;
}

export function formatDiagnostic(d: DiagnosticDump): string {
  const lines: string[] = [];
  lines.push(`=== DIAGNOSTIC: ${d.testName} ===`);
  lines.push(`trace_ids: ${JSON.stringify(d.traceIds)}`);
  lines.push("backend logs (top 20 matching lines):");
  const logLines = d.backendLogsPreview.split(/\r?\n/).slice(0, 20);
  for (const l of logLines) lines.push(`  ${l}`);
  lines.push("db state:");
  for (const [k, v] of Object.entries(d.dbState)) {
    lines.push(`  ${k}: ${truncate(JSON.stringify(v), 500)}`);
  }
  lines.push(
    `classification hint: ${d.classificationHint ?? "(unset — read logs+db and classify per table in helpers/diagnose.ts)"}`,
  );
  lines.push("=== END DIAGNOSTIC ===");
  return lines.join("\n");
}

/**
 * Call from `test.afterEach` (or equivalent) — attaches backend-logs.txt and
 * db-state.json to the failed test so the reporter (and the HTML report) can
 * surface them.
 */
export async function captureDiagnostics(
  testInfo: TestInfo,
  state: RunState,
): Promise<void> {
  if (testInfo.status === testInfo.expectedStatus) return;

  const logs = await captureBackendLogs({
    since: state.startedAt,
    traceIds: state.traceIds,
  }).catch((err) => `<captureBackendLogs threw: ${err instanceof Error ? err.message : String(err)}>`);

  await testInfo.attach(BACKEND_LOGS_ATTACHMENT, {
    body: logs,
    contentType: "text/plain",
  });

  const dump = await dumpRelated({ appId: state.appId, configId: state.configId }).catch((err) => ({
    error: `dumpRelated failed: ${err instanceof Error ? err.message : String(err)}`,
  }));

  await testInfo.attach(DB_STATE_ATTACHMENT, {
    body: JSON.stringify(dump, null, 2),
    contentType: "application/json",
  });
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return `${s.slice(0, n)}…(${s.length - n} more chars)`;
}
