const FRONTEND_URL = "http://localhost:3000";
const BACKEND_HEALTH_URL = "http://localhost:8000/health";

const BRING_UP_HINT = `
E2E pre-flight failed.

Bring up the dev stack first:
  docker compose -f docker-compose.dev.yml up -d
  until curl -fsS http://localhost:8000/health >/dev/null; do sleep 2; done
  until curl -fsS http://localhost:3000          >/dev/null; do sleep 2; done
`;

async function ping(url: string, label: string): Promise<void> {
  try {
    const r = await fetch(url, { method: "GET" });
    if (!r.ok) {
      throw new Error(`${label} returned HTTP ${r.status}`);
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`${label} not reachable at ${url}: ${msg}\n${BRING_UP_HINT}`);
  }
}

export default async function globalSetup(): Promise<void> {
  await ping(BACKEND_HEALTH_URL, "Backend /health");
  await ping(FRONTEND_URL, "Frontend root");
}
