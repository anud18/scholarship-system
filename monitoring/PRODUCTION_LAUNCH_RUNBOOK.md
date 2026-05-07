# Production Launch Runbook — Monitoring Stack Certification

Quick reference: this is a **gate-by-gate operator checklist**, not a tutorial.
Run it once, in order, on the day production goes live. All five gates must pass
before the system is cleared for real traffic.

Companion document: `monitoring/PRODUCTION_RUNBOOK.md` (day-2 operations).
Spec references: Phase 2 design spec §7-§9; `docs/superpowers/audits/working/phase3-prep/phase4-grouping.md` §4.

---

## Table of Contents

- [1. Purpose](#1-purpose)
- [2. Pre-flight Requirements](#2-pre-flight-requirements)
- [3. Gate 1 — Datasource Health](#3-gate-1--datasource-health)
- [4. Gate 2 — All Dashboards No-Data-Free for Past 1 h](#4-gate-2--all-dashboards-no-data-free-for-past-1-h)
- [5. Gate 3 — Synthetic Alert End-to-End](#5-gate-3--synthetic-alert-end-to-end)
- [6. Gate 4 — Deploy Honesty](#6-gate-4--deploy-honesty)
- [7. Gate 5 — Production Smoke](#7-gate-5--production-smoke)
- [8. Sign-off](#8-sign-off)
- [9. Failure Paths](#9-failure-paths)
- [10. Post-launch Schedule](#10-post-launch-schedule)

---

## 1. Purpose

This runbook certifies that the monitoring stack (Grafana, Prometheus, Loki,
Grafana Alloy, and the GitHub Issues alert receiver) is production-ready and
not silently lying. It is the Phase 4 exit gate: all four prior phases of
monitoring work (P0 fixes, P1 no-data fixes, P2 hygiene fixes) must be merged
and deployed before the operator begins this runbook. When all five gates
below show `✅`, the operator signs off and production is cleared to accept
real scholarship-system traffic.

---

## 2. Pre-flight Requirements

Before starting Gate 1, verify every item in this list:

- [ ] All Phase 2, Phase 3, and Phase 4 PRs are merged to `main` in
      `anud18/scholarship-system`.
- [ ] The most recent run of `.github/workflows/deploy-monitoring-stack.yml`
      on `main` shows `success` (check:
      `gh run list --workflow=deploy-monitoring-stack.yml --repo anud18/scholarship-system --limit 3`).
- [ ] The `mirror-to-production` workflow has fired, the auto-generated PR in
      the private prod repo has been reviewed and merged, and the prod-side
      `deploy-monitoring-stack-prod.yml` workflow has completed successfully.
- [ ] GitHub Actions secrets are set on `anud18/scholarship-system`:
  - `STAGING_DB_SSH_KEY` — SSH key for the staging DB-VM.
  - `STAGING_MONITORING_SERVER_URL` — URL of the staging monitoring server
    (e.g. `https://ss.test.nycu.edu.tw/monitoring`).
- [ ] The self-hosted runner that executes `deploy-monitoring-stack.yml` is
      online (`gh run list` recent jobs show the `self-hosted` label completing,
      not queued indefinitely).
- [ ] Operator has Grafana admin credentials:
  - `GRAFANA_ADMIN_USER` — from GitHub Actions secret (or ask the maintainer).
  - `GRAFANA_ADMIN_PASSWORD` — from GitHub Actions secret.
  - These are used below as `$ADMIN_USER` / `$ADMIN_PASS`.
- [ ] Operator has `gh` CLI authenticated to `anud18/scholarship-system`:
      `gh auth status` shows the correct account.
- [ ] (Staging only) WireGuard peer `peer2` is up if the staging Grafana URL
      (`ss.test.nycu.edu.tw`) is behind the NYCU VPN.

---

## 3. Gate 1 — Datasource Health

**What this proves:** Every Grafana datasource is reachable and healthy. A
broken datasource (e.g. a leftover `alertmanager-uid` pointing at a removed
service — audit finding F-GRAF-0x) silently breaks all panels that depend on
it. Phase 2 fixed the known broken datasource; this gate confirms no regression
exists (Phase 2 spec §7.2, deploy-honesty requirement).

### Commands

```bash
# Set once; reuse across all Gate 1/2/3 commands.
GRAFANA_URL="https://ss.test.nycu.edu.tw/monitoring"   # staging
ADMIN_USER="<GRAFANA_ADMIN_USER secret value>"
ADMIN_PASS="<GRAFANA_ADMIN_PASSWORD secret value>"

# 1. List all datasources (sanity check — should show Prometheus, Loki, and
#    any additional datasources, but NOT alertmanager-uid).
curl -s -u "$ADMIN_USER:$ADMIN_PASS" "$GRAFANA_URL/api/datasources" \
  | jq '[.[] | {uid, name, type}]'

# 2. Health-check every datasource by UID.
for uid in $(curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
    "$GRAFANA_URL/api/datasources" | jq -r '.[].uid'); do
  status=$(curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
    "$GRAFANA_URL/api/datasources/uid/$uid/health" | jq -r '.status')
  echo "$uid: $status"
done
```

### Expected output

```
prometheus-uid: OK
loki-uid: OK
```

Every line must end in `OK`. The `alertmanager-uid` datasource must not appear
(it was removed in Phase 2; its presence would mean the Phase 2 PR was not
merged or the deploy did not run).

### Pass criterion

Zero datasources returning anything other than `OK`. If this passes, proceed
to Gate 2.

---

## 4. Gate 2 — All Dashboards No-Data-Free for Past 1 h

**What this proves:** Every panel in every dashboard shows real data (or a
legitimate zero series) for the most recent hour. "No data" panels mean the
scrape pipeline, label relabeling, or PromQL expressions are still broken.
Phase 3 fixed the known no-data roots (F-PROM-05 DB-VM remote_write,
F-ALLO-06 postgres-exporter target, nginx/backend label drift); this gate
confirms all 8 dashboards are clean.

### Dashboard inventory

| UID | Title | Folder |
|-----|-------|--------|
| `scholarship-overview` | Scholarship System Overview | Default |
| `node-exporter-system` | System Monitoring (Node Exporter) | System |
| `container-monitoring` | Container Monitoring (cAdvisor) | Application |
| `nginx-monitoring` | Nginx Monitoring | Application |
| `application-logs` | Application Logs | Application |
| `postgresql-monitoring` | PostgreSQL Monitoring | Database |
| `redis-monitoring` | Redis Monitoring | Database |
| `minio-monitoring` | MinIO Monitoring | Database |

### Automated probe (preferred)

Run the Playwright audit probe with a `--nodata` assertion flag:

```bash
# Requires Node and Playwright installed on the operator machine.
# Reuses the stored Grafana admin session at /tmp/pw-test/auth-grafana-admin.json.
# If the session is stale, re-authenticate first (see nycu-sso-login skill).

node scripts/audit/probe-grafana.js \
  --mode nodata-check \
  --time-range "now-1h" \
  --out /tmp/launch-gate-$(date +%Y%m%d)

# The probe screenshots each dashboard in ?kiosk mode and writes a JSON
# report to /tmp/launch-gate-<date>/nodata-report.json.
# Check the report:
cat /tmp/launch-gate-$(date +%Y%m%d)/nodata-report.json \
  | jq '[.[] | select(.noDataPanels > 0)]'
# Expected: [] (empty array)
```

### Manual verification (fallback)

For each UID in the table above, open in a browser:

```
https://ss.test.nycu.edu.tw/monitoring/d/<UID>?from=now-1h&to=now&kiosk
```

Wait 5 seconds for panels to render. Visually confirm: no panel shows
"No data" text or a grey dash placeholder. Take a full-page screenshot
and save it as evidence (attach to the launch sign-off issue).

### Pass criterion

Zero "No data" panels across all 8 dashboards for the past 1 h time range.
Screenshots of every dashboard must be attached to the sign-off record (Gate 8).

---

## 5. Gate 3 — Synthetic Alert End-to-End

**What this proves:** The full alert pipeline works: Grafana fires an alert →
webhook contact point (`github-issue`) sends a `repository_dispatch` event →
`.github/workflows/monitoring-alert-issue.yml` creates a GitHub issue with
correct labels. Phase 2 built this pipeline; this gate runs a live end-to-end
test (Phase 2 spec §7.2 smoke test).

### Steps

**Step 1 — Trigger a test alert via Grafana contact-point test**

In a browser:
1. Navigate to `https://ss.test.nycu.edu.tw/monitoring/alerting/notifications`.
2. Locate the contact point named `github-issue`.
3. Click the three-dot menu → **Test**.
4. Grafana sends a test payload with `alertname: TestAlert` to the webhook.

Alternatively, using the Grafana API:

```bash
curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
  -X POST "$GRAFANA_URL/api/alertmanager/grafana/config/api/v1/receivers/test" \
  -H "Content-Type: application/json" \
  -d '{"receivers":[{"name":"github-issue"}]}'
# Expected HTTP 200: {"alert":"<message>","receivers":[...]}
```

**Step 2 — Wait up to 60 seconds**

The `monitoring-alert-issue.yml` workflow must receive the `repository_dispatch`
event, create an issue, and label it. GitHub webhook delivery is typically
< 5 s; CI startup adds up to 30 s.

**Step 3 — Verify a GitHub issue was created**

```bash
gh issue list \
  --repo anud18/scholarship-system \
  --label "monitoring-alert" \
  --label "alert:TestAlert" \
  --limit 5
```

Expected output: at least one open issue created within the last 2 minutes.
The issue should also carry labels `env:staging` and `severity:warning` (or
whichever severity the test payload sends).

**Step 4 — Manually close the test issue**

```bash
# Replace <ISSUE_NUMBER> with the number from step 3.
gh issue close <ISSUE_NUMBER> \
  --repo anud18/scholarship-system \
  --comment "Launch gate synthetic test — closing (Gate 3 passed)."
```

### Pass criterion

A GitHub issue is created in `anud18/scholarship-system` with label
`monitoring-alert` and at least one `alert:*` label within 60 seconds of
the test fire.

---

## 6. Gate 4 — Deploy Honesty

**What this proves:** The `deploy-monitoring-stack.yml` workflow's strengthened
health-check steps (added in Phase 2 to fix audit findings prior-A and prior-B)
all pass on a fresh deploy. This means:

- Pre-flight secret check passes.
- Every Grafana datasource returns HTTP 2xx from `/health`.
- Provisioning logs contain no errors.
- Alert rules loaded without errors.
- Staging metrics count meets `MIN_EXPECTED` (≥ 7 active staging targets all `UP`).

A workflow that reports `success` while any of these internal checks fail is the
"deploy honesty" bug the Phase 2 spec §6 set out to fix. This gate confirms the
regression does not exist.

### Commands

```bash
# 1. Trigger a fresh staging deploy.
gh workflow run deploy-monitoring-stack.yml \
  --repo anud18/scholarship-system \
  --ref main

# 2. Get the run ID of the triggered run (wait ~5 s for it to appear).
RUN_ID=$(gh run list \
  --repo anud18/scholarship-system \
  --workflow=deploy-monitoring-stack.yml \
  --limit 1 \
  --json databaseId \
  -q '.[0].databaseId')
echo "Watching run $RUN_ID"

# 3. Stream the run until completion.
gh run watch "$RUN_ID" --repo anud18/scholarship-system

# 4. After completion, check every step printed a ✅ (no ❌ lines).
gh run view "$RUN_ID" \
  --repo anud18/scholarship-system \
  --log \
  | grep -E "✅|❌"
```

### Expected output

Every step line in the final `grep` output starts with `✅`. Specifically look
for these steps (names may vary slightly):

```
✅  Pre-flight secret check
✅  Verify datasource health  (all UIDs OK)
✅  Verify provisioning logs  (no errors)
✅  Verify alert rules loaded (count > 0)
✅  Verify staging targets    (≥ 7 active targets, all UP)
```

### Pass criterion

Workflow run concludes with status `success` AND every strengthened health-check
step logged a `✅`. Any `❌` line is a failure; see Gate 4 failure path in §9.

---

## 7. Gate 5 — Production Smoke

**What this proves:** The same stack, mirrored to prod and deployed by the
prod-side workflow, is healthy in production. Because `mirror-to-production.yml`
strips `*.md` files, prod-side operators must refer to this runbook before the
mirror runs, or keep a copy of the relevant commands.

Run Gates 1–3 against the production Grafana URL after confirming the prod-side
deploy workflow completed successfully.

### Setup

```bash
# Switch the URL variable to production for all commands below.
GRAFANA_URL="https://ss.nycu.edu.tw/monitoring"   # actual prod URL — confirm with maintainer
ADMIN_USER="<prod GRAFANA_ADMIN_USER>"
ADMIN_PASS="<prod GRAFANA_ADMIN_PASSWORD>"
```

### Gate 5a — Prod datasource health

Run the Gate 1 commands verbatim against `$GRAFANA_URL`.

**Pass criterion:** Identical to Gate 1 — every datasource returns `OK`.

### Gate 5b — Prod targets UP

```bash
# Confirm ≥ 7 prod targets are active and all UP.
curl -s "$GRAFANA_URL/api/datasources/proxy/uid/prometheus-uid/api/v1/targets" \
  -u "$ADMIN_USER:$ADMIN_PASS" \
  | jq '[.data.activeTargets[] | select(.labels.environment=="prod")] | length'
# Expected: ≥ 7

curl -s "$GRAFANA_URL/api/datasources/proxy/uid/prometheus-uid/api/v1/targets" \
  -u "$ADMIN_USER:$ADMIN_PASS" \
  | jq '[.data.activeTargets[] | select(.labels.environment=="prod" and .health!="up")] | length'
# Expected: 0  (zero prod targets down)
```

### Gate 5c — Prod synthetic alert end-to-end

Run the Gate 3 steps verbatim against the prod Grafana URL. The resulting
GitHub issue must carry label `env:prod` (in addition to `monitoring-alert` and
`alert:TestAlert`). Close the test issue after confirming it appears.

```bash
# After running the test, verify with env:prod label filter.
gh issue list \
  --repo anud18/scholarship-system \
  --label "monitoring-alert" \
  --label "env:prod" \
  --label "alert:TestAlert" \
  --limit 5
```

### Pass criterion

Identical to staging Gates 1–3, executed against the prod URL. Zero datasource
errors, zero prod targets down, and a test GitHub issue with `env:prod` label
created within 60 seconds.

---

## 8. Sign-off

Copy the following block into a new GitHub issue titled
`[Launch Gate] Monitoring Stack Certification — <YYYY-MM-DD>` in
`anud18/scholarship-system` (label it `monitoring-cert`), fill it in, and
close the issue when all gates pass.

```markdown
## Monitoring Stack Launch Gate Certification

**Date:** YYYY-MM-DD HH:MM UTC
**Operator:** @<github-handle>
**Branch / commit certified:** main @ <short-sha>

### Staging Gates

| Gate | Description | Result | Notes |
|------|-------------|--------|-------|
| Gate 1 | Datasource health — all UIDs `OK` | ✅ / ❌ | |
| Gate 2 | 8 dashboards no-data-free for past 1 h | ✅ / ❌ | screenshots: |
| Gate 3 | Synthetic alert → GitHub issue created | ✅ / ❌ | issue #: |
| Gate 4 | Fresh deploy — all health-check steps `✅` | ✅ / ❌ | run #: |

### Production Gates (Gate 5)

| Sub-gate | Description | Result | Notes |
|----------|-------------|--------|-------|
| Gate 5a | Prod datasource health — all UIDs `OK` | ✅ / ❌ | |
| Gate 5b | ≥ 7 prod targets UP, 0 down | ✅ / ❌ | count: |
| Gate 5c | Prod synthetic alert → GitHub issue `env:prod` | ✅ / ❌ | issue #: |

### Deviations

<!-- List any gate that required a workaround, the workaround applied,
     and a follow-up issue number (if any). -->

None.

### Final Certification

- [ ] All five gates passed.
- [ ] All staging screenshots attached to this issue.
- [ ] All test issues closed.

**Status:** `ready for traffic` / `blocked on <description>`
```

---

## 9. Failure Paths

Quick diagnostics for each gate failure. Do not skip straight to the fix —
collect the evidence first, then remediate.

### Gate 1 failure — Datasource not OK

```bash
# 1. Check Grafana provisioning errors.
docker logs monitoring_grafana 2>&1 | grep -i "level=error"

# 2. Check which datasource is failing and why.
curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
  "$GRAFANA_URL/api/datasources/uid/<failing-uid>/health" | jq .

# 3. If a datasource points at a removed service (e.g. leftover alertmanager-uid),
#    check whether monitoring/config/grafana/provisioning/datasources/datasources.yml
#    was correctly updated in Phase 2 and the deploy ran after that commit.
gh run list \
  --repo anud18/scholarship-system \
  --workflow=deploy-monitoring-stack.yml \
  --limit 5
```

Common causes: Phase 2 datasource-cleanup PR not merged; deploy did not run
after the merge; `datasources.yml` still contains the `alertmanager-uid` stanza.

### Gate 2 failure — No-data panels remain

```bash
# 1. Check whether the scrape target for the affected metric is UP.
node scripts/audit/probe-grafana.js   # full audit run, screenshots + JSON
# or:
bash scripts/audit/probe-prom.sh targets

# 2. Check which targets are DOWN.
curl -s "$GRAFANA_URL/api/datasources/proxy/uid/prometheus-uid/api/v1/targets" \
  -u "$ADMIN_USER:$ADMIN_PASS" \
  | jq '[.data.activeTargets[] | select(.health!="up") | {job:.labels.job, instance:.labels.instance, error:.lastError}]'

# 3. For DB-VM metrics specifically (pg_up, pg_stat_activity_count), confirm
#    the DB-VM Alloy remote_write pipeline is live (Phase 3 / F-PROM-05).
```

Common causes: Phase 3 DB-VM remote_write PR not merged; Alloy not reloaded
after config change; `or 0` masking removed (Phase 4 / F-GRAF-06) but a
different PromQL expression still has a typo.

### Gate 3 failure — Test issue not created

```bash
# 1. Check the monitoring-alert-issue.yml workflow run for the dispatch event.
gh run list \
  --repo anud18/scholarship-system \
  --workflow=monitoring-alert-issue.yml \
  --limit 5

# 2. View logs of the failed run.
gh run view <RUN_ID> --repo anud18/scholarship-system --log

# 3. Check whether the GH_PAT secret (used by the webhook contact point) is
#    still valid and has issues:write scope.
#    Navigate: GitHub → anud18/scholarship-system → Settings → Secrets and variables → Actions
#    Look for GH_PAT; if expired, rotate it and update the Grafana contact point config.

# 4. Verify the Grafana contact point webhook URL is correct.
curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
  "$GRAFANA_URL/api/v1/provisioning/contact-points" | jq '.[] | select(.name=="github-issue")'
```

Common causes: `GH_PAT` expired or lacks `issues:write` scope; webhook URL
in the contact point config points at the wrong repo or endpoint; the
`repository_dispatch` event type name drifted between what Grafana sends and
what the workflow's `types:` filter expects.

Note: per Phase 2 spec §8 R5 (OQ-1), the current PAT is a classic PAT. Fine-
grained PAT migration is deferred (see §10 below).

### Gate 4 failure — Deploy workflow exits non-zero

The workflow already prints the failing step name and exit reason. Read the
step output directly:

```bash
gh run view <RUN_ID> --repo anud18/scholarship-system --log | grep -A 20 "❌"
```

Each strengthened health-check step exits non-zero with a descriptive message:

- **Pre-flight secret check fail** — a required Actions secret is missing or
  empty; set it under Settings → Secrets.
- **Datasource health fail** — same as Gate 1 failure path above.
- **Provisioning log errors** — `docker logs monitoring_grafana` shows a YAML
  parse error in a provisioned file; check the dashboard or alerting YAML that
  changed in the most recent commit.
- **Alert rules not loaded** — Grafana alerting provisioning YAML is malformed;
  run `docker exec monitoring_grafana grafana-cli validate` (if supported) or
  check `docker logs monitoring_grafana`.
- **Staging targets below MIN_EXPECTED (7)** — one or more scrape targets are
  unreachable; use Gate 2 failure path diagnosis.

### Gate 5 failure — Production smoke

Apply the same diagnosis steps as Gates 1–3, but against the prod Grafana URL.
If the prod-side deploy workflow itself failed, check the prod-repo Actions tab
(requires prod-repo access). The prod-side workflow is not visible from this dev
repo (Phase 2 spec §10 blind spot / OQ-3).

---

## 10. Post-launch Schedule

### Day 1 (launch day)

- Oncall engineer monitors `monitoring-alert`-labeled GitHub issues.
- Verify no spurious alerts fire during normal traffic ramp.
- Confirm `env:prod` issues are created only for real alerts, not test fires.

### Day 7

- Review alert noise level: count issues created per alert rule.
- Adjust `for:` duration or thresholds for any rule that fires more than
  twice per day on normal traffic.
- Particularly check `HighHTTPErrorRate` (threshold 5% over 5 min) and
  `SlowHTTPResponseTimeWarning` (p95 > 2 s) — these may need tuning once
  real traffic patterns are established.

### Month 1

- Review `repeat_interval` settings in Grafana alerting policies. The
  default sends a repeat notification every hour for sustained alerts;
  adjust to match oncall tolerance.
- Review Prometheus TSDB retention (currently 15 days). If disk usage
  approaches 80%, lower retention or expand the volume.
- Review Loki retention limits (`monitoring/config/loki/limits.yml`).

### When to migrate to a fine-grained PAT (OQ-1 / Phase 2 spec §8 R5)

The current `GH_PAT` used by the Grafana `github-issue` contact point is a
classic PAT. Migrate to a fine-grained PAT scoped to `issues:write` on
`anud18/scholarship-system` only when:

1. The classic PAT comes up for rotation (recommended ≤ 90-day rotation), or
2. The team's security policy requires fine-grained PATs for all service tokens.

Update the PAT in GitHub Actions secrets (`GH_PAT`) and re-test Gate 3 after
rotation.

### When to add deferred / dropped alerts back (Phase 3 / P5)

The following alerts were deferred from Phase 2 and redesigned in Phase 3
(`docs/superpowers/audits/working/phase3-prep/deferred-alerts-redesign.md`):

| Alert | Depends on | How to re-enable |
|-------|-----------|------------------|
| `PostgreSQLDown` | DB-VM `pg_up` series reaching Prometheus (F-PROM-05 / F-ALLO-06 closed) | Append rule to `monitoring/config/grafana/provisioning/alerting/rules-database.yml` (YAML in deferred-alerts-redesign.md §A1) |
| `PostgreSQLTooManyConnections` | Same DB-VM pipeline | rules-database.yml §A2 |
| `PostgreSQLHighConnections` | Same DB-VM pipeline | rules-database.yml §A3 |
| `HighHTTPErrorRate` | `http_requests_total{job="backend"}` live (already confirmed) | Append to `rules-application.yml` (§B4) |
| `SlowHTTPResponseTimeWarning` | `http_request_duration_seconds_bucket{job="backend"}` live (already confirmed) | Append to `rules-application.yml` (§B5) |
| `SlowHTTPResponseTimeCritical` | Same histogram | Append to `rules-application.yml` (§B5) |
| `MinIODown` | MinIO scrape target added to AP-VM Alloy configs (§B6) | Add `prometheus.scrape "minio"` block + append to `rules-application.yml` (§B6) |

Enable each alert by merging its YAML into the provisioning alerting files,
then run Gate 3 to verify the pipeline still works. Run Gate 4 to confirm the
deploy health check still passes.

P2 hygiene findings resolved in Phase 4 (Group E metric cleanup — F-APP-06
dead metrics, F-APP-05 `/metrics` endpoint exposure) should also be
revisited at Month 1 if Phase 4 capacity did not cover all 13 dead metric
declarations. See `phase4-grouping.md` Group E for the decision matrix.

---

**Document version**: 1.0
**Created**: 2026-05-06
**Branch**: `feat/monitoring-phase2`
**Next review**: after Month 1 post-launch alert tuning
**Owner**: AP-VM maintainer / oncall engineer
