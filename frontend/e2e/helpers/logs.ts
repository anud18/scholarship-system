import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";

const execFileAsync = promisify(execFile);

const COMPOSE_FILE = path.resolve(__dirname, "..", "..", "..", "docker-compose.dev.yml");

export interface CaptureLogsOpts {
  since: number;
  traceIds?: Array<string | null | undefined>;
  maxLines?: number;
}

export async function captureBackendLogs(opts: CaptureLogsOpts): Promise<string> {
  const sinceSeconds = Math.max(1, Math.ceil((Date.now() - opts.since) / 1000));
  const maxLines = opts.maxLines ?? 200;
  let raw: string;
  try {
    const { stdout, stderr } = await execFileAsync(
      "docker",
      ["compose", "-f", COMPOSE_FILE, "logs", `--since=${sinceSeconds}s`, "--no-color", "backend"],
      { maxBuffer: 16 * 1024 * 1024 },
    );
    raw = stdout || stderr || "";
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return `<failed to capture backend logs: ${msg}>`;
  }

  const traceIds = (opts.traceIds ?? []).filter(
    (t): t is string => typeof t === "string" && t.length > 0,
  );
  if (traceIds.length === 0) {
    return tail(raw, maxLines);
  }
  const lines = raw.split(/\r?\n/);
  const matched = lines.filter((line) => traceIds.some((tid) => line.includes(tid)));
  if (matched.length === 0) {
    return `<no log lines matched trace_ids=${JSON.stringify(traceIds)}; tail follows>\n${tail(raw, maxLines)}`;
  }
  return matched.slice(-maxLines).join("\n");
}

function tail(content: string, n: number): string {
  const lines = content.split(/\r?\n/);
  return lines.slice(-n).join("\n");
}
