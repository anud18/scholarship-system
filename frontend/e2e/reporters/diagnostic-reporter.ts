import type {
  Reporter,
  TestCase,
  TestResult,
  FullConfig,
  Suite,
  FullResult,
} from "@playwright/test/reporter";
import { RUN_STATE_ATTACHMENT, type RunState } from "../helpers/runState";
import {
  BACKEND_LOGS_ATTACHMENT,
  DB_STATE_ATTACHMENT,
  formatDiagnostic,
} from "../helpers/diagnose";

/**
 * Prints a `=== DIAGNOSTIC: <test name> ===` block to stdout for every failing
 * test, sourced from the attachments written by helpers/diagnose#captureDiagnostics
 * (in spec afterEach hooks). The HTML report shows the full attachments; this
 * reporter just makes the same info visible without opening it.
 */
export default class DiagnosticReporter implements Reporter {
  onBegin(_config: FullConfig, _suite: Suite): void {
    /* noop */
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    if (result.status === "passed" || result.status === "skipped") return;

    const runState = readJsonAttachment<RunState>(result, RUN_STATE_ATTACHMENT);
    const dbState = readJsonAttachment<Record<string, unknown>>(result, DB_STATE_ATTACHMENT) ?? {};
    const logsBody = readTextAttachment(result, BACKEND_LOGS_ATTACHMENT) ?? "<no backend-logs.txt attachment found>";

    const block = formatDiagnostic({
      testName: test.titlePath().slice(1).join(" › ") || test.title,
      traceIds: runState?.traceIds ?? [],
      backendLogsPreview: logsBody,
      dbState,
      classificationHint: runState?.classificationHint,
    });

    process.stdout.write(`\n${block}\n\n`);
  }

  async onEnd(_result: FullResult): Promise<void> {
    /* noop */
  }
}

function readJsonAttachment<T>(result: TestResult, name: string): T | undefined {
  const a = result.attachments.find((x) => x.name === name);
  if (!a?.body) return undefined;
  try {
    const text = a.body instanceof Buffer ? a.body.toString("utf8") : String(a.body);
    return JSON.parse(text) as T;
  } catch {
    return undefined;
  }
}

function readTextAttachment(result: TestResult, name: string): string | undefined {
  const a = result.attachments.find((x) => x.name === name);
  if (!a?.body) return undefined;
  return a.body instanceof Buffer ? a.body.toString("utf8") : String(a.body);
}
