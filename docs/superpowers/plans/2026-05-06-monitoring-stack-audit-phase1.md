# Monitoring Stack Audit — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a verified, severity-classified audit of the monitoring stack and the application metric/log interface that supports it, delivered as `docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md` with reproduction artifacts.

**Architecture:** Audit work is decomposed across five subsystem branches (Grafana, Prometheus+Loki, Alloy+CrossVM, App-Metrics, Deploy-Pipeline) which run in parallel via `superpowers:dispatching-parallel-agents`. Each branch fills its own working file with §5.4-template findings backed by Active Probe + Static Read + Cross-Reference. A final synthesis branch (PM role) merges working files into the final audit report and produces the executive summary.

**Tech Stack:** Playwright (Node, already installed globally; bundled scripts under `.claude/skills/nycu-sso-login/scripts/`), curl + jq for API probes, Bash/Python for static-read & diff, GitHub CLI (`gh`) for reading workflow run logs.

**Spec reference:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md` (commit `07faa57`).

---

## File Map

**Audit deliverables — create:**
- `docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md` — final audit report (synthesis output)
- `docs/superpowers/audits/working/grafana.md` — Branch A working findings
- `docs/superpowers/audits/working/prometheus-loki.md` — Branch B working findings
- `docs/superpowers/audits/working/alloy-crossvm.md` — Branch C working findings
- `docs/superpowers/audits/working/app-metrics.md` — Branch D working findings
- `docs/superpowers/audits/working/deploy-pipeline.md` — Branch E working findings
- `docs/superpowers/audits/working/screenshots/` — Playwright PNG artifacts (one subdir per branch)
- `docs/superpowers/audits/working/api-responses/` — captured JSON payloads (one subdir per branch)

**Tooling — create:**
- `scripts/audit/probe-grafana.js` — reusable Playwright probe for dashboards (Branch A & F)
- `scripts/audit/probe-prom.sh` — curl+jq helper for Prometheus
- `scripts/audit/probe-alloy-diff.sh` — three-way diff for `*-vm.alloy` files
- `scripts/audit/probe-deploy-honesty.sh` — deploy-vs-reality reconciliation
- `scripts/audit/README.md` — how to run probes

**Read-only — touched but not modified:**
- All files listed in spec §5.1 (monitoring config, backend metric files, deploy workflows, mirror workflow).

**Important constraints:**
- This phase modifies **no** production config. All actions are read or probe.
- The `docs/superpowers/audits/` tree is new (the existing convention has `specs/` and `plans/` only).
- Working files (`docs/superpowers/audits/working/`) are committed to git so future re-audits can diff them.

---

## Stage 0: Setup (main thread, sequential)

These tasks run in the main session before swarm dispatch. They produce the shared state every branch agent needs.

### Task 0.1: Confirm Grafana session and VPN

**Files:** none.

- [ ] **Step 1: Verify VPN tunnel up**

```bash
curl -sI --max-time 5 https://ss.test.nycu.edu.tw/ >/dev/null && echo OK || echo UNREACHABLE
```

Expected: `OK`. If `UNREACHABLE`, ask user to bring up `wg-quick up peer2` and re-run.

- [ ] **Step 2: Verify Grafana storage state exists**

```bash
ls -la /tmp/pw-test/auth-grafana-admin.json && \
  curl -sI --max-time 5 https://ss.test.nycu.edu.tw/monitoring/api/health
```

Expected: storage state file present (mtime within last few hours), and Grafana health endpoint returns 200 with `database: "ok"`.

If storage state missing or expired, run:

```bash
NODE_PATH=$(npm root -g) node /tmp/pw-test/grafana-login.js
```

(Script lives at `/tmp/pw-test/grafana-login.js`, reads creds from `/tmp/pw-test/.grafana-creds`.)

- [ ] **Step 3: Verify NYCU SSO storage state for backend access**

```bash
ls -la /tmp/pw-test/auth-414551001.json /tmp/pw-test/auth-A00001.json 2>/dev/null
```

Expected: at least one of these present. If both missing, login per `nycu-sso-login` skill.

### Task 0.2: Create audit directory structure

**Files:**
- Create: `docs/superpowers/audits/working/screenshots/{grafana,prometheus-loki,alloy-crossvm,app-metrics,deploy-pipeline}/` (placeholder `.gitkeep` in each)
- Create: `docs/superpowers/audits/working/api-responses/{grafana,prometheus-loki,alloy-crossvm,app-metrics,deploy-pipeline}/.gitkeep`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p docs/superpowers/audits/working/screenshots/{grafana,prometheus-loki,alloy-crossvm,app-metrics,deploy-pipeline}
mkdir -p docs/superpowers/audits/working/api-responses/{grafana,prometheus-loki,alloy-crossvm,app-metrics,deploy-pipeline}
for d in docs/superpowers/audits/working/screenshots/* docs/superpowers/audits/working/api-responses/*; do
  touch "$d/.gitkeep"
done
```

- [ ] **Step 2: Commit empty structure**

```bash
git add docs/superpowers/audits/
git commit -m "chore(audit): scaffold phase-1 audit directories"
```

### Task 0.3: Author the shared probe scripts

**Files:**
- Create: `scripts/audit/probe-grafana.js`
- Create: `scripts/audit/probe-prom.sh`
- Create: `scripts/audit/probe-alloy-diff.sh`
- Create: `scripts/audit/probe-deploy-honesty.sh`
- Create: `scripts/audit/README.md`

- [ ] **Step 1: Write `scripts/audit/probe-grafana.js`**

Content:

```javascript
// Read-only Playwright probe. Reuses /tmp/pw-test/auth-grafana-admin.json.
// Usage: node probe-grafana.js [--dashboard <uid>] [--out <dir>]
// Default behavior: enumerate datasources + dashboards, screenshot home + each
// dashboard, dump panel JSON to api-responses dir.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const NYCU_DIR = process.env.NYCU_DIR || '/tmp/pw-test';
const OUT = process.env.AUDIT_OUT_DIR ||
  path.resolve(__dirname, '../../docs/superpowers/audits/working');
const STATE = path.join(NYCU_DIR, 'auth-grafana-admin.json');
const BASE = 'https://ss.test.nycu.edu.tw/monitoring';

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    storageState: STATE,
    viewport: { width: 1600, height: 1200 },
  });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });

  const ds = await page.evaluate(async () => {
    const list = await (await fetch('/monitoring/api/datasources', { credentials: 'include' })).json();
    const out = [];
    for (const d of list) {
      const r = await fetch(`/monitoring/api/datasources/uid/${d.uid}/health`, { credentials: 'include' });
      const body = await r.json().catch(() => ({}));
      out.push({ uid: d.uid, name: d.name, type: d.type, http: r.status, status: body.status, message: body.message });
    }
    return out;
  });
  fs.writeFileSync(path.join(OUT, 'api-responses/grafana/datasources-health.json'),
    JSON.stringify(ds, null, 2));

  const dashboards = await page.evaluate(async () => {
    const r = await fetch('/monitoring/api/search?type=dash-db&limit=200', { credentials: 'include' });
    return r.json();
  });
  fs.writeFileSync(path.join(OUT, 'api-responses/grafana/dashboards-list.json'),
    JSON.stringify(dashboards, null, 2));

  for (const d of dashboards) {
    const detail = await page.evaluate(async (uid) => {
      const r = await fetch(`/monitoring/api/dashboards/uid/${uid}`, { credentials: 'include' });
      return r.json();
    }, d.uid);
    fs.writeFileSync(
      path.join(OUT, `api-responses/grafana/dashboard-${d.uid}.json`),
      JSON.stringify(detail, null, 2)
    );
    await page.goto(`${BASE}/d/${d.uid}/${d.uri ? d.uri.split('/').pop() : ''}?kiosk`, {
      waitUntil: 'networkidle', timeout: 45000
    }).catch(() => {});
    await page.waitForTimeout(4000);
    await page.screenshot({
      path: path.join(OUT, `screenshots/grafana/dashboard-${d.uid}.png`),
      fullPage: true,
    });
  }

  // Alerting view
  await page.goto(`${BASE}/alerting/list`, { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(2500);
  await page.screenshot({
    path: path.join(OUT, 'screenshots/grafana/alerting-list.png'),
    fullPage: true,
  });

  await browser.close();
  console.log('grafana probe complete; outputs under', OUT);
})().catch(e => { console.error(e); process.exit(1); });
```

- [ ] **Step 2: Write `scripts/audit/probe-prom.sh`**

Content:

```bash
#!/usr/bin/env bash
# Read-only Prometheus probe via the Grafana datasource proxy (we don't have
# direct localhost:9090 access; Grafana proxies on our behalf).
# Usage: probe-prom.sh <PromQL or special>
#   special: targets | rules | runtimeinfo | metrics
set -euo pipefail
NYCU_DIR=${NYCU_DIR:-/tmp/pw-test}
OUT=${AUDIT_OUT_DIR:-docs/superpowers/audits/working}
STATE="$NYCU_DIR/auth-grafana-admin.json"
BASE='https://ss.test.nycu.edu.tw/monitoring'

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need node; need jq

# Find Prometheus datasource UID
PROM_UID=$(jq -r '.[] | select(.type=="prometheus") | .uid' \
  "$OUT/api-responses/grafana/datasources-health.json" 2>/dev/null || true)
if [ -z "$PROM_UID" ]; then
  echo "Run probe-grafana.js first to populate datasources-health.json" >&2
  exit 1
fi

case "${1:-}" in
  targets|rules|runtimeinfo|metrics)
    EP="$1"
    SCRIPT=$(cat <<EOF
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({ ignoreHTTPSErrors: true, storageState: '$STATE' });
  const p = await c.newPage();
  await p.goto('$BASE/');
  const r = await p.evaluate(async () => {
    const x = await fetch('/monitoring/api/datasources/proxy/uid/$PROM_UID/api/v1/$EP', { credentials: 'include' });
    return { http: x.status, body: await x.text() };
  });
  console.log(r.body);
  await b.close();
})();
EOF
)
    NODE_PATH=$(npm root -g) node -e "$SCRIPT"
    ;;
  query)
    Q="$2"
    SCRIPT=$(cat <<EOF
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({ ignoreHTTPSErrors: true, storageState: '$STATE' });
  const p = await c.newPage();
  await p.goto('$BASE/');
  const r = await p.evaluate(async (q) => {
    const u = '/monitoring/api/datasources/proxy/uid/$PROM_UID/api/v1/query?query=' + encodeURIComponent(q);
    const x = await fetch(u, { credentials: 'include' });
    return { http: x.status, body: await x.text() };
  }, '$Q');
  console.log(r.body);
  await b.close();
})();
EOF
)
    NODE_PATH=$(npm root -g) node -e "$SCRIPT"
    ;;
  *) echo "usage: $0 {targets|rules|runtimeinfo|metrics|query <PromQL>}"; exit 2 ;;
esac
```

Make executable: `chmod +x scripts/audit/probe-prom.sh`.

- [ ] **Step 3: Write `scripts/audit/probe-alloy-diff.sh`**

Content:

```bash
#!/usr/bin/env bash
# Three-way (technically four-way) diff over the *-vm.alloy files. Surfaces
# unintentional drift between staging/prod and ap/db variants.
set -euo pipefail
OUT=${AUDIT_OUT_DIR:-docs/superpowers/audits/working}
DIR=monitoring/config/alloy
mkdir -p "$OUT/api-responses/alloy-crossvm"

# pairwise diffs
for a in staging-ap-vm staging-db-vm prod-ap-vm prod-db-vm; do
  for b in staging-ap-vm staging-db-vm prod-ap-vm prod-db-vm; do
    [ "$a" \< "$b" ] || continue
    diff -u "$DIR/$a.alloy" "$DIR/$b.alloy" \
      > "$OUT/api-responses/alloy-crossvm/diff-${a}-vs-${b}.txt" || true
  done
done

# block summary: count blocks per file
for f in "$DIR"/*.alloy; do
  base=$(basename "$f" .alloy)
  echo "=== $base ==="
  grep -E '^[a-z_.]+ "[^"]*"' "$f" | sort | uniq -c
done > "$OUT/api-responses/alloy-crossvm/block-summary.txt"

echo "alloy diffs written under $OUT/api-responses/alloy-crossvm/"
```

Make executable: `chmod +x scripts/audit/probe-alloy-diff.sh`.

- [ ] **Step 4: Write `scripts/audit/probe-deploy-honesty.sh`**

Content:

```bash
#!/usr/bin/env bash
# Compare what the deploy workflow's health-check step claims (last successful
# run) against the actual stack state right now. Surfaces dishonest health checks.
set -euo pipefail
OUT=${AUDIT_OUT_DIR:-docs/superpowers/audits/working}
mkdir -p "$OUT/api-responses/deploy-pipeline"

echo "--- last successful deploy-monitoring-stack run ---"
gh run list --workflow=deploy-monitoring-stack.yml --status=success --limit=1 \
  --json databaseId,headSha,createdAt,conclusion \
  | tee "$OUT/api-responses/deploy-pipeline/last-success-meta.json"

RUN_ID=$(jq -r '.[0].databaseId' "$OUT/api-responses/deploy-pipeline/last-success-meta.json")
gh run view "$RUN_ID" --log \
  > "$OUT/api-responses/deploy-pipeline/last-success-log.txt"

echo "--- live datasource health (now) ---"
cat "$OUT/api-responses/grafana/datasources-health.json"

echo
echo "Diff this against the workflow log to find dishonest health checks."
```

Make executable: `chmod +x scripts/audit/probe-deploy-honesty.sh`.

- [ ] **Step 5: Write `scripts/audit/README.md`**

Content:

```markdown
# Audit Probe Scripts

Read-only probes for the monitoring stack audit (Phase 1 of
`docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md`).

## Prerequisites
- VPN tunnel `peer2` up (`wg-quick up peer2`)
- `/tmp/pw-test/auth-grafana-admin.json` Grafana session valid
- `gh` CLI authenticated to this repo

## Run order
1. `node scripts/audit/probe-grafana.js` — populates datasource health,
   dashboard JSON, screenshots.
2. `scripts/audit/probe-prom.sh targets|rules|query <expr>` — Prometheus probes
   via Grafana proxy.
3. `scripts/audit/probe-alloy-diff.sh` — Alloy file pairwise diffs.
4. `scripts/audit/probe-deploy-honesty.sh` — deploy-vs-reality.

## Output
All scripts write under `docs/superpowers/audits/working/`. JSON dumps under
`api-responses/`, screenshots under `screenshots/`. Working files
(`<branch>.md`) are written by the per-branch agents.
```

- [ ] **Step 6: Commit scripts**

```bash
git add scripts/audit/
git commit -m "chore(audit): add read-only probe scripts for monitoring audit"
```

### Task 0.4: Run baseline probe to populate api-responses

**Files:** writes to `docs/superpowers/audits/working/api-responses/grafana/`, `screenshots/grafana/`.

- [ ] **Step 1: Run Grafana probe**

```bash
NODE_PATH=$(npm root -g) node scripts/audit/probe-grafana.js
```

Expected: `grafana probe complete; outputs under <path>` and these files exist:
- `datasources-health.json` (5 datasources, alertmanager entry has `http: 500`)
- `dashboards-list.json` (8 dashboards)
- `dashboard-<uid>.json` × 8
- `screenshots/grafana/dashboard-<uid>.png` × 8
- `screenshots/grafana/alerting-list.png`

- [ ] **Step 2: Run Prometheus targets probe**

```bash
scripts/audit/probe-prom.sh targets > docs/superpowers/audits/working/api-responses/prometheus-loki/targets.json
scripts/audit/probe-prom.sh rules > docs/superpowers/audits/working/api-responses/prometheus-loki/rules.json
scripts/audit/probe-prom.sh runtimeinfo > docs/superpowers/audits/working/api-responses/prometheus-loki/runtimeinfo.json
```

Expected: each file is valid JSON with non-empty `data`. `targets.json` lists every active scrape target; `rules.json` lists Prometheus alert rules.

- [ ] **Step 3: Run Alloy diff**

```bash
scripts/audit/probe-alloy-diff.sh
```

Expected: 6 pairwise diffs and `block-summary.txt` under `api-responses/alloy-crossvm/`.

- [ ] **Step 4: Run deploy honesty probe**

```bash
scripts/audit/probe-deploy-honesty.sh
```

Expected: `last-success-meta.json` and `last-success-log.txt` under `api-responses/deploy-pipeline/`. (If `gh` is not authenticated, prompt user.)

- [ ] **Step 5: Commit baseline artifacts**

```bash
git add docs/superpowers/audits/working/
git commit -m "chore(audit): capture baseline probe artifacts (grafana/prom/alloy/deploy)"
```

---

## Stage 1: Parallel branch dispatch (PM, single tool message)

**REQUIRED SUB-SKILL:** Use `superpowers:dispatching-parallel-agents` to launch Branches A–E in one message with five `Agent` tool calls. Branches are independent: each reads its own subset of artifacts (already captured in Stage 0) and writes to its own working file. No two branches edit the same path.

Each branch agent receives the full prompt template below, with the `BRANCH_*` placeholders filled in.

### Branch prompt template

```
You are auditing the {BRANCH_NAME} subsystem of the scholarship-system
monitoring stack as part of Phase 1 of the design at
docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md (commit 07faa57).

Working file: docs/superpowers/audits/working/{BRANCH_FILE}.md
Artifact dir: docs/superpowers/audits/working/{api-responses,screenshots}/{BRANCH_DIR}/

Your scope (do not exceed it):
{BRANCH_SCOPE}

Mandatory finding template (use exactly this Markdown for every finding):

### F-{BRANCH_PREFIX}-NN  [P0|P1|P2|noted]  Short title

**Where**: `path/to/file:start-end` and any related API endpoint or workflow step.

**Evidence**:
- Active probe: <command and actual response excerpt>
- Static read: <file path and line numbers, with the relevant excerpt>
- Cross-reference: <the contradiction in one or two sentences>

**Expected**: <what the system should be doing>

**Root cause hypothesis**: <one sentence>

**Remediation owner**: Phase 2 / 3 / 4

**Suggested fix sketch**: <a few lines, not a final design>

Process:
1. Read the spec sections relevant to your scope (§5.1, §5.3, §11) before
   starting.
2. For each prior in §11 that lies in your scope, run the three gates
   (Active Probe + Static Read + Cross-Reference). Either confirm it
   becomes a numbered finding or explicitly debunk it with evidence.
3. Hunt for additional findings in your scope. Look for: dangling
   references, missing labels, queries that don't match metric names,
   typos, drift between similar files, dead code, silent failures.
4. Write everything to the working file as you go. Each finding gets the
   template above.
5. Append a "Coverage" section listing every file/endpoint you actually
   inspected and every prior you addressed.
6. Commit your working file at the end with message
   "audit({BRANCH_DIR}): findings for {BRANCH_NAME} subsystem".
7. Do NOT modify any production config or any other branch's working
   file. Read-only on everything outside your working file and artifact
   subdir.

Constraints:
- No fallback data. If a probe fails, record the failure as evidence,
  don't fabricate.
- Use the existing Grafana session at /tmp/pw-test/auth-grafana-admin.json.
- Stay within your scope; if you find a bug clearly outside it, note it
  in a "Cross-branch observations" section at the bottom of your working
  file (do NOT log a finding for another branch's territory).
- Severity: use the spec's §5.3 rubric strictly. P0 = monitoring lying;
  P1 = monitoring missing data; P2 = cosmetic; noted = out of scope.

Deliverable check before you return:
- Working file exists at the stated path and has at least one finding
  per addressed prior, plus the Coverage section.
- Every finding has all three evidence gates.
- Working file committed to git.
- Final reply <= 300 words: count of findings by severity, list of priors
  confirmed/debunked, and any cross-branch observations.
```

### Task 1.A: Branch A — Grafana

**Branch placeholders:**
- `BRANCH_NAME` = `Grafana`
- `BRANCH_FILE` = `grafana`
- `BRANCH_DIR` = `grafana`
- `BRANCH_PREFIX` = `GRAF`
- `BRANCH_SCOPE` = (paste verbatim into the prompt)

```
- monitoring/config/grafana/provisioning/datasources/datasources.yml
- monitoring/config/grafana/provisioning/dashboards/dashboards.yml
- monitoring/config/grafana/provisioning/dashboards/**/*.json (8 files)
- monitoring/config/grafana/grafana.ini.example
- Grafana API responses already captured under
  docs/superpowers/audits/working/api-responses/grafana/
- Grafana UI screenshots already captured under
  docs/superpowers/audits/working/screenshots/grafana/

Address these spec priors: prior-G (alertmanager dangling datasource).
Hunt for: panels using `or 0` to mask No-data; query/label drift;
dashboards filtering on $environment / $vm template variables that the
underlying metrics don't carry; dashboard folder naming inconsistencies;
dead datasources; broken dashboard JSON (loader errors visible in Grafana
admin or in datasource health responses).

When the answer requires a live PromQL probe, use:
  scripts/audit/probe-prom.sh query '<PromQL>'
```

- [ ] **Step 1: Dispatch Branch A**

`Agent(subagent_type=general-purpose, description="Audit Grafana subsystem", prompt=<filled template>)`

- [ ] **Step 2: Verify deliverable**

After agent returns, run:

```bash
ls -la docs/superpowers/audits/working/grafana.md && \
  grep -c '^### F-GRAF-' docs/superpowers/audits/working/grafana.md && \
  grep -c '^**Active probe**\|^**Static read**\|^**Cross-reference**' docs/superpowers/audits/working/grafana.md
```

Expected: file exists, finding count >= 1, evidence-line count is a multiple of 3 × finding count.

If file missing or evidence incomplete, re-dispatch Branch A with corrective notes.

### Task 1.B: Branch B — Prometheus + Loki

**Branch placeholders:**
- `BRANCH_NAME` = `Prometheus + Loki`
- `BRANCH_FILE` = `prometheus-loki`
- `BRANCH_DIR` = `prometheus-loki`
- `BRANCH_PREFIX` = `PROM`
- `BRANCH_SCOPE`:

```
- monitoring/config/prometheus/prometheus.yml
- monitoring/config/prometheus/alerts/basic-alerts.yml
- monitoring/config/prometheus/recording-rules/aggregations.yml
- monitoring/config/loki/loki-config.yml
- monitoring/config/loki/limits.yml
- API responses captured under docs/superpowers/audits/working/api-responses/prometheus-loki/

Address these spec priors: prior-G (Prometheus alert rules without
receiver). Hunt for: scrape jobs that exist in prometheus.yml but have no
matching exporter in compose; alert rules referencing metrics that don't
appear in current scrape targets; recording rules that compute metrics
not used anywhere; Loki tenant scoping mismatches; Loki retention not set
or set inconsistently with limits.yml.

For Loki probes, use the same Playwright session pattern as probe-prom.sh
but proxy through the Loki datasources (Dev/Staging/Production).
```

- [ ] **Step 1: Dispatch Branch B**

`Agent(subagent_type=general-purpose, description="Audit Prometheus + Loki", prompt=<filled template>)`

- [ ] **Step 2: Verify deliverable**

```bash
ls -la docs/superpowers/audits/working/prometheus-loki.md && \
  grep -c '^### F-PROM-' docs/superpowers/audits/working/prometheus-loki.md
```

Expected: file exists, finding count >= 1.

### Task 1.C: Branch C — Alloy + Cross-VM

**Branch placeholders:**
- `BRANCH_NAME` = `Alloy + Cross-VM`
- `BRANCH_FILE` = `alloy-crossvm`
- `BRANCH_DIR` = `alloy-crossvm`
- `BRANCH_PREFIX` = `ALLO`
- `BRANCH_SCOPE`:

```
- monitoring/config/alloy/staging-ap-vm.alloy
- monitoring/config/alloy/staging-db-vm.alloy
- monitoring/config/alloy/prod-ap-vm.alloy
- monitoring/config/alloy/prod-db-vm.alloy
- Pairwise diffs already captured under
  docs/superpowers/audits/working/api-responses/alloy-crossvm/
- Cross-reference Alloy targets vs Prometheus targets list

Address: cross-VM topology (vm=ap vs vm=db labels), environment label
consistency, intentional vs unintentional drift between staging and prod
Alloy configs, missing relabel_rules causing $environment / $vm filters
to break dashboards, remote_write target health.

The four .alloy files SHOULD be near-identical structurally with the only
intentional differences being:
  (a) target endpoints (staging-ap vs staging-db vs prod-ap vs prod-db)
  (b) the `environment` external label value
  (c) the `vm` external label value
Anything else that differs is a finding.
```

- [ ] **Step 1: Dispatch Branch C**

`Agent(subagent_type=general-purpose, description="Audit Alloy + cross-VM topology", prompt=<filled template>)`

- [ ] **Step 2: Verify deliverable**

```bash
ls -la docs/superpowers/audits/working/alloy-crossvm.md && \
  grep -c '^### F-ALLO-' docs/superpowers/audits/working/alloy-crossvm.md
```

Expected: file exists, finding count >= 1.

### Task 1.D: Branch D — Application Metrics & Logs

**Branch placeholders:**
- `BRANCH_NAME` = `Application Metrics & Logs`
- `BRANCH_FILE` = `app-metrics`
- `BRANCH_DIR` = `app-metrics`
- `BRANCH_PREFIX` = `APP`
- `BRANCH_SCOPE`:

```
- backend/app/main.py (lines around the /metrics endpoint definition,
  currently around line 354)
- backend/app/core/metrics.py (full file)
- backend/app/middleware/metrics_middleware.py
- Dashboard PromQL expressions captured under
  docs/superpowers/audits/working/api-responses/grafana/dashboard-*.json
  (extract `targets[].expr` from every panel)
- Backend logging configuration: search backend/app for logging.* and
  structlog/logger.* usage

Address: the three "No data" panels on the scholarship overview dashboard
(Backend Error Rate %, PostgreSQL Active Connections, Database Query p95
ms). For each, determine via Static Read + Active Probe whether the
metric exists in code, whether it's exported on /metrics, whether it's
scraped, and whether it carries the labels the dashboard expects.

Verify: /metrics endpoint is reachable without auth (anonymous scrape
must work). The middleware EXCLUDED_PATHS list does not strip metrics
the dashboards depend on. Log output is structured (JSON) so Loki can
parse fields like level and request_id.

For the live /metrics check, use:
  curl -s http://localhost:8000/metrics  # if backend is running locally
  OR proxy via Grafana's Prometheus datasource — the metric will appear
  in scripts/audit/probe-prom.sh metrics output if scraped.
```

- [ ] **Step 1: Dispatch Branch D**

`Agent(subagent_type=backend-engineer-postgres-minio, description="Audit backend metrics interface", prompt=<filled template>)`

(Use backend specialist here; this branch reads backend Python code in depth.)

- [ ] **Step 2: Verify deliverable**

```bash
ls -la docs/superpowers/audits/working/app-metrics.md && \
  grep -c '^### F-APP-' docs/superpowers/audits/working/app-metrics.md
```

Expected: file exists, finding count >= 1, includes per-panel verdict for the three No-data panels.

### Task 1.E: Branch E — Deploy Pipeline

**Branch placeholders:**
- `BRANCH_NAME` = `Deploy & Mirror Pipeline`
- `BRANCH_FILE` = `deploy-pipeline`
- `BRANCH_DIR` = `deploy-pipeline`
- `BRANCH_PREFIX` = `DEPL`
- `BRANCH_SCOPE`:

```
- .github/workflows/deploy-monitoring-stack.yml
- .github/workflows/mirror-to-production.yml
- .github/PRODUCTION_SYNC_GUIDE.md
- monitoring/GITHUB_DEPLOYMENT.md
- .github/production-workflows-examples/ (note: stripped at mirror time)
- Captured deploy-honesty artifacts under
  docs/superpowers/audits/working/api-responses/deploy-pipeline/

Address these spec priors: prior-A (health check thinness), prior-B
(false-positive trap), prior-C (paths filter), prior-D (grafana.ini.example
one-shot copy), prior-E (dead ALERT_* env vars), prior-F (sleep timing),
prior-H (mirror strip rules vs monitoring config), prior-I (prod-side
workflow blind spot — mark as blind spot if no access).

Hunt for additional findings: secrets that are read but never used; SSH
key handling weaknesses; race conditions in the DB-VM tar shipping;
docker compose file path mismatches; assumptions that break if the
prod-side workflow doesn't exist yet.
```

- [ ] **Step 1: Dispatch Branch E**

`Agent(subagent_type=general-purpose, description="Audit deploy and mirror pipelines", prompt=<filled template>)`

- [ ] **Step 2: Verify deliverable**

```bash
ls -la docs/superpowers/audits/working/deploy-pipeline.md && \
  grep -c '^### F-DEPL-' docs/superpowers/audits/working/deploy-pipeline.md
```

Expected: file exists, finding count >= 7 (priors A-F at minimum, plus H; I marked as blind spot).

### Task 1.F: Verify all branches converged

After all five Agents have returned, the PM (main thread) checks completion before moving to synthesis.

- [ ] **Step 1: List working files**

```bash
ls -la docs/superpowers/audits/working/*.md
```

Expected: 5 files (`grafana.md`, `prometheus-loki.md`, `alloy-crossvm.md`, `app-metrics.md`, `deploy-pipeline.md`), each with non-zero size.

- [ ] **Step 2: Aggregate finding counts**

```bash
for f in docs/superpowers/audits/working/*.md; do
  echo "=== $f ==="
  grep -E '^### F-[A-Z]+-[0-9]+' "$f" | wc -l
done
```

Expected: each file > 0 findings; total across files >= 12 (priors A-I = 9, plus discovered findings).

- [ ] **Step 3: Verify priors coverage**

```bash
for prior in A B C D E F G H I; do
  echo -n "prior-$prior addressed by: "
  grep -l "prior-$prior" docs/superpowers/audits/working/*.md || echo "MISSING"
done
```

Expected: every prior has at least one branch addressing it. If `MISSING`, dispatch a follow-up Agent for that branch with explicit instruction to address the missing prior.

- [ ] **Step 4: Commit branch outputs (if any branch agent forgot to commit)**

```bash
git status -- docs/superpowers/audits/working/
git add docs/superpowers/audits/working/
if ! git diff --cached --quiet; then
  git commit -m "audit(branches): collect findings from parallel branch agents"
fi
```

---

## Stage 2: Synthesis (PM, sequential — single agent or main thread)

The synthesis pass merges the five working files into a single audit report with executive summary, severity-grouped findings, cross-cutting matrix, and noted-but-not-fixing appendix. This stage is intentionally NOT parallel — the synthesis judgment must see all branches at once.

### Task 2.1: Generate the executive summary

**Files:**
- Create: `docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md` (final report)

- [ ] **Step 1: Compute counts**

```bash
P0=$(grep -hE '^### F-[A-Z]+-[0-9]+ +\[P0\]' docs/superpowers/audits/working/*.md | wc -l)
P1=$(grep -hE '^### F-[A-Z]+-[0-9]+ +\[P1\]' docs/superpowers/audits/working/*.md | wc -l)
P2=$(grep -hE '^### F-[A-Z]+-[0-9]+ +\[P2\]' docs/superpowers/audits/working/*.md | wc -l)
NOTED=$(grep -hE '^### F-[A-Z]+-[0-9]+ +\[noted\]' docs/superpowers/audits/working/*.md | wc -l)
TOTAL=$((P0+P1+P2+NOTED))
echo "P0=$P0 P1=$P1 P2=$P2 noted=$NOTED total=$TOTAL"
```

Record the result.

- [ ] **Step 2: Write the executive-summary section**

Open `docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md` and write the header:

```markdown
# Monitoring Stack Audit — 2026-05-06

**Scope:** monitoring stack + application metric/log interface + deploy pipeline.
**Method:** see spec §5.2 (Active Probe + Static Read + Cross-Reference).
**Spec:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md` (commit 07faa57).

## Executive Summary

| Severity | Count | Allocated to |
|---|---|---|
| P0 | <P0> | Phase 2 |
| P1 | <P1> | Phase 3 |
| P2 | <P2> | Phase 4 |
| noted | <NOTED> | Phase 5+ (out of scope) |
| **Total** | **<TOTAL>** | — |

**Top 3 risks (read this first):**

1. <pick the most-impactful P0 finding by hand>
2. <second>
3. <third>

**Production-launch verdict:** <Not ready | Ready with caveats | Ready>.
Caveats and required Phase 2/3/4 fixes listed below.
```

Replace `<P0>` etc. with the counts from Step 1. Pick the top-3 risks by reading P0 findings and selecting the three with widest blast radius.

- [ ] **Step 3: Commit the skeleton**

```bash
git add docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md
git commit -m "audit(synthesis): scaffold final report with executive summary"
```

### Task 2.2: Merge findings grouped by severity then subsystem

- [ ] **Step 1: Append findings sections**

For each severity in P0, P1, P2 order, write a section. Within each severity, group by subsystem (`grafana/`, `prometheus-loki/`, `alloy-crossvm/`, `app-metrics/`, `deploy-pipeline/`). Copy each finding block from the working files verbatim (preserving the §5.4 template). Do NOT renumber findings — keep the `F-GRAF-NN` etc. IDs assigned by branch agents so cross-references between report and working files stay stable.

Suggested section structure:

```markdown
## P0 — Monitoring is silently lying

### From Grafana (`grafana.md`)
<copy F-GRAF-* P0 findings here>

### From Prometheus + Loki (`prometheus-loki.md`)
<copy F-PROM-* P0 findings here>

### From Alloy + Cross-VM (`alloy-crossvm.md`)
<copy F-ALLO-* P0 findings here>

### From Application Metrics & Logs (`app-metrics.md`)
<copy F-APP-* P0 findings here>

### From Deploy Pipeline (`deploy-pipeline.md`)
<copy F-DEPL-* P0 findings here>

## P1 — Monitoring missing data
<same subsystem grouping>

## P2 — Cosmetic / hygiene
<same subsystem grouping>
```

- [ ] **Step 2: Commit findings merge**

```bash
git add docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md
git commit -m "audit(synthesis): merge findings by severity and subsystem"
```

### Task 2.3: Build the cross-VM / cross-environment matrix

- [ ] **Step 1: Append matrix section**

For every finding, infer which combination of (staging, prod) × (AP-VM, DB-VM) it affects. Build a table:

```markdown
## Cross-VM / Cross-Environment Matrix

| Finding | staging-ap | staging-db | prod-ap | prod-db | notes |
|---|---|---|---|---|---|
| F-GRAF-01 | ✓ | — | ✓ | — | Grafana lives on AP-VM only |
| F-DEPL-09 | ✓ | ✓ | blind spot | blind spot | prod workflow not visible |
| ... |
```

Use `✓` for "affected", `—` for "not affected", `blind spot` where prod-side info is unavailable (per spec §10).

- [ ] **Step 2: Commit matrix**

```bash
git add docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md
git commit -m "audit(synthesis): add cross-VM cross-environment matrix"
```

### Task 2.4: Build the noted-but-not-fixing appendix

- [ ] **Step 1: Append `noted` findings**

```bash
grep -hA20 '^### F-[A-Z]+-[0-9]+ +\[noted\]' docs/superpowers/audits/working/*.md
```

Copy each `[noted]` finding into a new section:

```markdown
## Noted but not fixing (future Phase 5+)

<copy each [noted] finding block verbatim, ordered by subsystem>
```

If no noted items exist, write: `_No noted items in this audit. The team noted this and may add SLO / retention / rotation discovery as Phase 5 if needed._`

- [ ] **Step 2: Commit appendix**

```bash
git add docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md
git commit -m "audit(synthesis): add noted-but-not-fixing appendix"
```

### Task 2.5: Build reproduction-artifact appendix

- [ ] **Step 1: Append artifact index**

```markdown
## Reproduction Artifacts

All probe outputs and screenshots are under
`docs/superpowers/audits/working/`.

### Screenshots
- Grafana dashboards (8): `working/screenshots/grafana/dashboard-*.png`
- Grafana alerting list: `working/screenshots/grafana/alerting-list.png`
- (any branch-specific screenshots)

### API responses
- Grafana datasource health: `working/api-responses/grafana/datasources-health.json`
- Grafana dashboard JSON × 8: `working/api-responses/grafana/dashboard-*.json`
- Prometheus targets: `working/api-responses/prometheus-loki/targets.json`
- Prometheus rules: `working/api-responses/prometheus-loki/rules.json`
- Alloy diffs: `working/api-responses/alloy-crossvm/diff-*.txt`
- Deploy run logs: `working/api-responses/deploy-pipeline/last-success-log.txt`

### Per-branch working files (raw)
- `working/grafana.md`
- `working/prometheus-loki.md`
- `working/alloy-crossvm.md`
- `working/app-metrics.md`
- `working/deploy-pipeline.md`
```

- [ ] **Step 2: Commit artifact index**

```bash
git add docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md
git commit -m "audit(synthesis): add reproduction artifact index"
```

### Task 2.6: Final self-review against acceptance criteria

- [ ] **Step 1: Verify spec §14 acceptance criteria**

Run this checklist:

```bash
echo "1. File exists:"; test -f docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md && echo OK || echo FAIL
echo "2. Has executive summary:"; grep -c '^## Executive Summary' docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md
echo "3. P0/P1/P2/noted sections:"; for s in P0 P1 P2 noted; do grep -c "^## $s\\| (future\\|Cosmetic\\|missing\\|silently)" docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md || true; done
echo "4. Matrix present:"; grep -c '^## Cross-VM' docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md
echo "5. Artifact index present:"; grep -c '^## Reproduction Artifacts' docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md
echo "6. All priors A-I addressed:"
for prior in A B C D E F G H I; do
  if grep -q "prior-$prior" docs/superpowers/audits/working/*.md; then
    echo "  prior-$prior: covered"
  else
    echo "  prior-$prior: MISSING"
  fi
done
echo "7. Every finding has all three evidence gates:"
python3 - <<'PY'
import re, pathlib
p = pathlib.Path('docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md')
text = p.read_text()
findings = re.findall(r'^### F-[A-Z]+-\d+.*?(?=^### F-|^## |\Z)', text, re.M | re.S)
bad = []
for f in findings:
    if 'Active probe' not in f or 'Static read' not in f or 'Cross-reference' not in f:
        bad.append(f.split('\n', 1)[0])
print(f"findings checked: {len(findings)}; missing-gate findings: {len(bad)}")
for b in bad: print(f"  - {b}")
PY
```

Expected: every line returns OK / non-zero count / `covered`. Zero missing-gate findings.

- [ ] **Step 2: If any item fails**

Fix inline (re-dispatch the offending branch with explicit corrective notes, or directly edit the synthesis file to copy the missing evidence from the working file).

- [ ] **Step 3: Final commit**

```bash
git add docs/superpowers/audits/
git commit -m "audit(synthesis): complete phase-1 monitoring stack audit"
```

### Task 2.7: Hand back to user

- [ ] **Step 1: Print summary**

Reply to user with:
- Path to the final audit report
- P0 / P1 / P2 / noted counts
- Top 3 P0 findings (titles only)
- Whether any prior was debunked
- Cross-branch observations summary
- Whether the prod-side workflow blind spot remains

- [ ] **Step 2: Propose Phase 2 brainstorm**

Suggest the user review the audit report, then we transition to Phase 2 brainstorming using `superpowers:brainstorming` to design the P0 fixes.

---

## Self-Review (post-write check)

Performed inline before this plan was committed:

- [x] **Spec coverage**: every spec §5.1 scope item is referenced in at least one branch's `BRANCH_SCOPE`.
  - Grafana files → Branch A
  - Prometheus + Loki → Branch B
  - Alloy + cross-VM → Branch C
  - Backend metrics, middleware, /metrics, log structure → Branch D
  - Deploy + mirror workflows + production-workflows-examples → Branch E
  - Acceptance criteria §14 → Stage 2 Task 2.6
- [x] **Priors A–I**: every prior is named in the relevant `BRANCH_SCOPE` block. Stage 1 Task 1.F Step 3 enforces coverage.
- [x] **Placeholder scan**: no `TBD`, `TODO`, "fill in details", or "similar to Task N" wording. Code blocks are complete.
- [x] **Type consistency**: finding ID prefixes (`F-GRAF`, `F-PROM`, `F-ALLO`, `F-APP`, `F-DEPL`) are stable across all references.
- [x] **Granularity**: each step is 2–15 minutes. Branch dispatch tasks bundle "dispatch + verify" because dispatch is one tool call.
- [x] **No production config modified**: every step is read or probe; no `Edit` / `Write` against `monitoring/**` or workflow files.
- [x] **Frequent commits**: 1 commit per branch + 1 commit per synthesis section + final.

---

## Notes for the executor

- This plan is read-heavy and write-light. The agent dispatcher (PM) does most of the work; engineering branches do focused reads + one Markdown write each.
- Branch agents must NOT modify production config. If a branch finds something that is fixable in 30 seconds, it still records it as a finding and leaves the fix for Phase 2/3/4. Audit-then-fix discipline.
- If the Grafana session expires mid-run, the executor re-runs the login script under `/tmp/pw-test/grafana-login.js` (kept on the user's local box, not in repo).
- The prod-side `deploy-monitoring-stack-prod.yml` blind spot is intentional. Branch E records it as a finding (`prior-I`) and the synthesis matrix shows `blind spot` cells. This is not a plan failure.
