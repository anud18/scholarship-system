# Phase 3 + Phase 4 Readiness Brief

**Consolidated from:** P3 (phase3-grouping), P4 (phase4-grouping), P5 (deferred-alerts-redesign),
P6 (backend-instrumentation-plan), P7 (dashboard-query-fixes)
**Date:** 2026-05-06
**Branch:** `feat/monitoring-phase2`
**Reading time:** ~5 minutes

---

## 1. Executive Summary

Phase 3 closes 29 P1 findings across 11 groups, organized into 4 sub-phases (3A → 3D).
Phase 4 closes 9 P2 findings + 1 pulled-in `noted` item across 5 groups.

| Phase | Findings | Groups | Est. Days | PRs |
|-------|----------|--------|-----------|-----|
| 3     | 29 P1    | 11     | ~6.5      | 6–7 |
| 4     | 9 P2 + 1 noted | 5 | ~3.25  | 6–7 |
| **Total** | **39** | **16** | **~9.75** | **12–14** |

**Critical-path bottleneck:** Everything gates on G1 (DB-VM metric pipeline — F-PROM-05 /
F-ALLO-06). Without `vm="db-vm"` data flowing into Prometheus, sub-phases 3B and 3C cannot
be validated, and all three PostgreSQL alerts cannot be enabled. Before starting Phase 3,
confirm `up{vm="db-vm"}` in Prometheus; if absent, the first PR of 3A is the unblock.

A secondary bottleneck is the Phase 2 runner: all Phase 3 config changes require at least one
successful self-hosted runner deploy. Verify runner registration before scheduling Phase 3 work.

---

## 2. Phase 3 Sub-Phase Ordering

| Sub-phase | Groups | Scope summary | Est. days | PRs | What unblocks next |
|-----------|--------|--------------|-----------|-----|--------------------|
| **3A** | G1, G2, G3 | DB-VM metric pipeline; prod-AP Alloy drift (slash-strip + label fixes for F-ALLO-01–05); Alloy fragility (F-ALLO-07, F-ALLO-08) | 2.0 | 2 (G1 isolated; G2+G3 together) | `vm="db-vm"` metrics flow into Prometheus → 3B can verify backend instrumentation end-to-end; Alloy configs stable for 3B config PRs |
| **3B** | G4, G8, G9, G10 | Backend metric instrumentation (P6: PR-A + PR-B, ~256 LOC); Prometheus rule hygiene (F-PROM-06 re-enable or delete, F-PROM-09 delete); Loki retention wiring (F-PROM-10); deploy path fixes (F-DEPL-05, F-DEPL-06) | 2.5 | 2 (G4 backend code; G8+G9+G10 config) | Backend counters live → 3C alert redesigns can reference real metrics; dashboard panels unblocked for 3C verification |
| **3C** | G5, G6, G7 | Deferred postgres alerts (A1–A3); dropped alert redesigns (B4–B6 from P5); dashboard query corrections (P7's 19 immediate JSON fixes) | 1.5 | 1–2 (alerts G5+G6; dashboards G7) | All alerts live + all panels non-empty → Phase 4 entry condition met; launch-gate gate 2 (no No-data) can be verified |
| **3D** | G11 | Prod-side blind spots (F-DEPL-11, F-DEPL-13): documentation + SCP template | 0.5 | 1 (docs-only) | No downstream gate; slip-safe but must close before prod launch-gate certification |

**PR detail:**

| PR | Sub-phase | Contents | Size |
|----|-----------|----------|------|
| PR 3A-1 | 3A | G1: `staging-db-vm.alloy` + `prod-db-vm.alloy` remote_write + postgres-exporter scrape verification | Medium (risky — cross-VM network) |
| PR 3A-2 | 3A | G2+G3: prod-AP Alloy slash-strip, label fixes, watchdog/reload hardening | Small |
| PR 3B-1 | 3B | G4 backend code: `session.py` event listeners, `db_metrics.py`, `application_service.py`, `email_management_service.py`, `auth_service.py`, `review_service.py`, `main.py`, `metrics.py` cleanup; 9 new test files | Medium |
| PR 3B-2 | 3B | G8+G9+G10: recording-rule decision (re-enable or delete), Loki retention label, deploy path fixes | Small |
| PR 3C-1 | 3C | G5+G6: `rules-database.yml` (3 postgres alerts) + `rules-application.yml` (HighHTTPErrorRate, SlowHTTPResponseTime×2, MinIODown) + staging-ap-vm.alloy + prod-ap-vm.alloy MinIO scrape block | Medium |
| PR 3C-2 | 3C | G7: 19 dashboard JSON fixes + provisioning fixes (`dashboards.yml` flags, `application-logs.json` file move) | Small |
| PR 3D-1 | 3D | G11: `monitoring/PRODUCTION_RUNBOOK.md` SCP template section; F-DEPL-11/F-DEPL-13 notes | Small |

---

## 3. Critical Decisions Before Phase 3 Starts

1. **Backend instrumentation: PR-A + PR-B split or single PR?**
   P6 recommends two PRs: PR-A (M1 db_query_duration + M2 scholarship_applications_total +
   M3 email_sent_total, ~140 LOC) first; PR-B (M4–M7 lower priority + M8 delete
   db_connections_total, ~116 LOC) after. The split is recommended — PR-A covers dashboard-
   affecting metrics and should land before 3C dashboard verification. PR-B can ship
   concurrently or slightly later. Single PR is acceptable if review velocity is high.

2. **Dashboard JSON fixes: before or after backend instrumentation?**
   The 19 "immediate" JSON fixes from P7 (F-GRAF-03 expr rewrite, F-GRAF-05 regex on 8
   dashboards, F-GRAF-09 vm variable, F-GRAF-02/minio vm label fix, F-GRAF-11 provisioning
   flags, F-GRAF-12 file move) have **no dependency on backend instrumentation** — they can
   ship in 3B-2 alongside the config PR. Panels blocked on P6 (F-GRAF-04, F-GRAF-10 ×3) need
   no JSON change; they resolve automatically once counters exist. Recommended: ship JSON-only
   fixes in 3B-2 so dashboards are clean before 3C alert validation.

3. **MinIO scrape addition: Phase 3 (3C) or deferred?**
   P5 B6 is self-contained (no DB-VM dependency) and P7 §3 requires it for the MinIO
   dashboard vm-label fix to show data. Include in Phase 3 PR 3C-1. Only risk is MinIO
   metrics auth — confirm `curl -s http://localhost:9000/minio/v2/metrics/cluster` is open
   before writing the scrape block.

4. **Nginx exporter swap (F-GRAF-08): Phase 5 or earlier?**
   P7 §4 explicitly defers to Phase 5. The 6 broken nginx dashboard targets require either
   VTS module, OpenTelemetry, or log-parser pivot — none achievable inside Phase 3 scope.
   Confirm this defer with user before Phase 3 brainstorm; if the user wants nginx status-code
   visibility sooner, a Phase 3.5 track is possible but expands scope by ~1 eng-day.

5. **PostgreSQL alert restoration: gate on PromQL probe or F-PROM-05 closure?**
   Recommended: gate on the PromQL probe (`pg_up{environment=~"staging|prod",vm="db-vm"}`
   returning ≥ 1 series via the Prometheus API) rather than on closing the issue ticket.
   The PromQL probe is the source of truth — F-PROM-05 closing without the data actually
   flowing is a paperwork win, not an observability win. Run the CLI probe in the PR checklist
   before merging 3C-1 postgres rules.

6. **Phase 4 entry condition: all P1 fixed, or dashboard-affecting P1 only?**
   P4 entry condition states "All 45 P0+P1 findings cleared (Phase 2 + Phase 3 merged and
   staging green)." However, G11 (prod-side blind spots, F-DEPL-11 / F-DEPL-13) cannot be
   fully resolved without prod repo access. Recommend: Phase 4 can start after 3A–3C are
   merged and staging is green. 3D (G11) can run in parallel with Phase 4 Group A. Decide
   whether to wait for 3D before declaring Phase 3 complete.

7. **F-DEPL-08 sleep timing: already handled by Phase 2?**
   P4 Group D explicitly flags this: "Verify Phase 2 did not already replace the `sleep 60`
   with polling." The Phase 2 spec §6 mentions strengthened health-checks but does not
   explicitly call out replacing the sleep. **Do not duplicate effort.** Before opening Phase
   4 Group D, grep `.github/workflows/deploy-monitoring-stack.yml` for `sleep` and confirm
   whether the 60 s / 30 s hardcoded waits remain. If Phase 2 already replaced them, Group D
   shrinks to F-DEPL-14 alone (15 min doc edit).

8. **Recording rules: re-enable or delete?** (F-PROM-06 in G8)
   P3 notes that no dashboard JSON references any recording-rule metric name — they are dead
   code even if re-enabled. CLAUDE.md §2 (no backward compatibility) favors clean delete.
   Decide before PR 3B-2: (a) delete `aggregations.yml` entirely, or (b) re-enable for
   future alerting use. Recommendation: delete, consistent with CLAUDE.md §2.

---

## 4. Cross-Phase Dependency Graph

```
Phase 2 (runner live, network fixed)
    │
    ▼
[3A-1] G1: DB-VM Alloy remote_write + postgres-exporter scrape
    │  Key output: vm="db-vm" series in Prometheus
    │
    ├──► [3A-2] G2+G3: Alloy drift + fragility (parallel, independent)
    │
    ▼
[3B-1] G4: Backend metric instrumentation (PR-A then PR-B)
    │  Key output: db_query_duration_seconds, scholarship_applications_total,
    │              email_sent_total, auth_attempts_total, etc. live
    │
    ├──► [3B-2] G8+G9+G10: Rule hygiene + Loki + deploy paths (parallel, no metric deps)
    │
    ▼
[3C-1] G5+G6: Postgres alerts (gates on vm="db-vm") +
              App alerts redesign (B4 HighHTTPErrorRate, B5 SlowHTTPResponseTime,
              B6 MinIODown — all gate on backend metrics or self-contained)
    │
    ├──► [3C-2] G7: 19 dashboard JSON fixes
    │         (immediate fixes ship with 3B-2; remaining fixes ship here post-3B-1)
    │
    ▼
[3D-1] G11: Prod blind spots docs
    │
    ▼
Phase 3 complete → staging green
    │
    ├──► [4A-1] Group A: or-0 masking removal (F-GRAF-06, F-GRAF-07, F-APP-07) — no deps
    │
    ├──► [4A-2a] Group B: Provisioning hygiene (F-GRAF-11, F-GRAF-12) — after 4A-1
    │
    ├──► [4A-2b] Group C: Cross-VM labeling (F-PROM-13) — parallel with 4A-2a
    │
    ├──► [4A-3] Group D: Workflow hygiene (F-DEPL-08 verify, F-DEPL-14) — after 4A-1/2
    │
    ├──► [4A-4] Group E: Metric inventory cleanup (F-APP-05 /metrics auth,
    │                     F-APP-06 dead metrics, optional F-ALLO-10)
    │         Gates on Phase 3 instrumentation list being finalized
    │
    └──► [4A-5] Group F: Docs + launch runbook — after all above merged
              │
              ▼
         Launch-gate certification (4 gates — see §5)
              │
              ▼
         Production cleared
```

---

## 5. Phase 4 Launch-Gate Definition

*Lifted verbatim from phase4-grouping.md §4 with cross-references added.*

**Deliverable file:** `monitoring/PRODUCTION_LAUNCH_RUNBOOK.md`
**Operator:** AP-VM maintainer or on-call engineer.
**When to run:** After all Phase 2/3/4 PRs are merged to `main`, mirrored to prod, and prod
deploy workflow has completed.

### Gate 1 — Zero broken datasources

```bash
GF_URL="https://ss.test.nycu.edu.tw/monitoring"   # or prod URL
GF_TOKEN="<service-account-token>"

for uid in $(curl -sf -H "Authorization: Bearer $GF_TOKEN" \
  "$GF_URL/api/datasources" | jq -r '.[].uid'); do
  result=$(curl -sf -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $GF_TOKEN" \
    "$GF_URL/api/datasources/uid/$uid/health")
  echo "$uid => HTTP $result"
done
# Pass: all UIDs => HTTP 200
```

**Phase 3 dependency (§2):** All datasource configs stabilize after 3A brings DB-VM online
and 3B-2 / 3C-1 add new scrape jobs. Run gate 1 after Phase 3 + 4A-1 are merged.

### Gate 2 — All 8 dashboards zero No-data for past 1 hour

```bash
curl -sf -H "Authorization: Bearer $GF_TOKEN" \
  "$GF_URL/api/search?type=dash-db" | \
  jq '[.[] | {uid, title, folderTitle}]'
# Visual or Playwright check: no panel shows "No data".
# npx playwright test monitoring/tests/launch-gate-nodata.spec.ts
```

**Phase 3 dependency (§2):** Gate 2 can only pass after 3C (all panels have real data)
and 4A-2b (F-PROM-13 vm label, ensuring self-monitor targets are labeled). The Playwright
spec is authored in Phase 4 Group F (4A-5).

### Gate 3 — Synthetic alert end-to-end test

```bash
# Push synthetic alert to Prometheus:
curl -X POST "https://ss.test.nycu.edu.tw/monitoring/prometheus/api/v1/alerts" \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {"alertname":"SyntheticLaunchGateTest","severity":"warning","env":"staging"},
    "annotations": {"summary":"Launch gate synthetic test"},
    "startsAt": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"
  }]'

# Wait up to 2 minutes, then verify GitHub issue created:
gh issue list --label "monitoring-alert" --label "env:staging" --limit 5

# Close test issue:
gh issue close <issue-number> --comment "Launch gate synthetic test — closing."
```

**Phase 3 dependency (§2):** Gate 3 requires Phase 3 alert rules (3C-1) to be live and the
Phase 2 alert-to-GitHub-issue webhook to be operational.

### Gate 4 — Fresh deploy health checks pass

```bash
gh workflow run deploy-monitoring-stack.yml --ref main -f environment=staging
gh run watch $(gh run list --workflow=deploy-monitoring-stack.yml \
  --limit 1 --json databaseId -q '.[0].databaseId')
# Pass: all steps green, including Verify datasource health, Verify staging targets,
#       Verify dashboard provisioning, Verify alert rules loaded.
```

**Phase 3 dependency (§2):** Gate 4 validates Phase 4 Group D (readiness-poll loops replace
sleep). Must run after 4A-3 is merged.

### Launch-gate certification checklist

```
[ ] Gate 1 — Datasource health: all UIDs 200          (date/time: ___)
[ ] Gate 2 — No-data panels: 0/8 dashboards affected   (screenshot: ___)
[ ] Gate 3 — Synthetic alert: GitHub issue #___ at ___
[ ] Gate 4 — Fresh deploy: run #___ passed at ___

Operator: _______________   Date: _______________
Environment certified: [ ] staging  [ ] production
```

All four boxes checked = Phase 4 exit condition met. Production cleared.

---

## 6. Six Ready-to-Paste GitHub Issue Bodies

Paste each block into `gh issue create --title "<title>" --body "<body>"`.

---

### Issue 1 — PostgreSQLDown

**Title:** `[Phase 3] Restore PostgreSQLDown after DB-VM scrape pipeline fix (F-PROM-05 / F-ALLO-06)`

```markdown
## What it does

Alerts within 1 minute when `pg_up` drops to 0 on the DB-VM, indicating PostgreSQL is
unreachable. This alert existed in the original `basic-alerts.yml` and was deliberately
deferred in Phase 2 because the underlying `pg_up` series never reaches Prometheus (the
DB-VM Alloy agent has no `prometheus.remote_write` block — findings F-PROM-05 / F-ALLO-06).

## Phase 3 dependencies

- [ ] F-PROM-05: Add `prometheus.remote_write` to `staging-db-vm.alloy` and `prod-db-vm.alloy`
      so DB-VM metrics reach the monitoring stack.
- [ ] F-ALLO-06: Confirm `prometheus.scrape "postgres_exporter"` target
      (`postgres-exporter:9187`) is reachable from the DB-VM Alloy agent.
- [ ] Verification: `pg_up{environment=~"staging|prod",vm="db-vm"}` returns ≥ 1 series.

## YAML to append to `monitoring/config/grafana/provisioning/alerting/rules-database.yml`

```yaml
      - uid: alert-postgresql-down
        title: PostgreSQLDown
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 60
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: pg_up{environment=~"staging|prod",vm="db-vm"} == 0
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 1m
        labels:
          severity: critical
          category: database
        annotations:
          summary: "PostgreSQL is down on {{ $labels.instance }}"
          description: >-
            PostgreSQL on {{ $labels.instance }} ({{ $labels.environment }},
            {{ $labels.vm }}) is not responding. pg_up == 0.
        isPaused: false
```

## Verification

```bash
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=pg_up{environment=~"staging|prod",vm="db-vm"}' \
  | jq '.data.result | length'
# Must return ≥ 1 before enabling the rule.
```
```

---

### Issue 2 — PostgreSQLTooManyConnections

**Title:** `[Phase 3] Restore PostgreSQLTooManyConnections after DB-VM scrape pipeline fix (F-PROM-05 / F-ALLO-06)`

```markdown
## What it does

Fires a **warning** when `pg_stat_activity_count` exceeds 80% of
`pg_settings_max_connections` for 5 minutes, allowing operators to intervene before
connection exhaustion. Deferred from Phase 2 due to missing DB-VM remote_write pipeline.

## Phase 3 dependencies

- [ ] F-PROM-05 + F-ALLO-06 closed (same as PostgreSQLDown issue).
- [ ] Verification: both `pg_stat_activity_count` and `pg_settings_max_connections` return
      ≥ 1 series with `{environment=~"staging|prod",vm="db-vm"}`.

## YAML to append to `rules-database.yml`

```yaml
      - uid: alert-postgresql-too-many-connections
        title: PostgreSQLTooManyConnections
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: >-
                sum(pg_stat_activity_count{environment=~"staging|prod",vm="db-vm"})
                  by (instance, environment)
                >
                sum(pg_settings_max_connections{environment=~"staging|prod",vm="db-vm"})
                  by (instance, environment) * 0.8
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: database
        annotations:
          summary: "PostgreSQL has too many connections on {{ $labels.instance }}"
          description: >-
            PostgreSQL on {{ $labels.instance }} ({{ $labels.environment }})
            is using more than 80% of max_connections.
            Current: {{ $value | humanize }}
        isPaused: false
```

## Verification

```bash
for metric in pg_stat_activity_count pg_settings_max_connections; do
  echo -n "$metric: "
  curl -sG 'http://localhost:9090/api/v1/query' \
    --data-urlencode "query=${metric}{environment=~\"staging|prod\",vm=\"db-vm\"}" \
    | jq '.data.result | length'
done
# Each must return ≥ 1
```
```

---

### Issue 3 — PostgreSQLHighConnections

**Title:** `[Phase 3] Restore PostgreSQLHighConnections after DB-VM scrape pipeline fix (F-PROM-05 / F-ALLO-06)`

```markdown
## What it does

Fires **critical** when connections exceed 90% of `max_connections` for 2 minutes — the
escalated tier above the 80% warning. Deferred from Phase 2.

## Phase 3 dependencies

Same as issue 2 (PostgreSQLTooManyConnections). Both alerts can be merged into a single PR
once the DB-VM pipeline is live.

## YAML to append to `rules-database.yml`

```yaml
      - uid: alert-postgresql-high-connections
        title: PostgreSQLHighConnections
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 120
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: >-
                sum(pg_stat_activity_count{environment=~"staging|prod",vm="db-vm"})
                  by (instance, environment)
                >
                sum(pg_settings_max_connections{environment=~"staging|prod",vm="db-vm"})
                  by (instance, environment) * 0.9
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 2m
        labels:
          severity: critical
          category: database
        annotations:
          summary: "PostgreSQL connection limit critical on {{ $labels.instance }}"
          description: >-
            PostgreSQL on {{ $labels.instance }} ({{ $labels.environment }})
            is using more than 90% of max_connections. Immediate action required!
            Current: {{ $value | humanize }}
        isPaused: false
```

## Verification

Same bash snippet as issue 2. If both metrics return ≥ 1, A2 and A3 can be enabled
simultaneously in the same PR.
```

---

### Issue 4 — HighHTTPErrorRate

**Title:** `[Phase 3] Restore HighHTTPErrorRate using backend metrics (replaces dropped nginx-based alert)`

```markdown
## What it does

Fires **warning** when more than 5% of backend HTTP requests return 5xx responses over a
5-minute window. The original alert used `nginx_http_requests_total{status=~"5.."}`, but
nginx-prometheus-exporter does not expose a `status` label (finding F-GRAF-08), so that alert
was dropped in Phase 2.

This redesign uses `http_requests_total{job="backend"}` which is confirmed live (7 series,
Phase 1 audit). Coverage is equivalent — every request reaching nginx ultimately hits the
backend.

## Phase 3 dependencies

- [x] `http_requests_total{job="backend"}` already live — no prerequisite infrastructure.
- [ ] Create `monitoring/config/grafana/provisioning/alerting/rules-application.yml`.

## Config diff

**New file:** `monitoring/config/grafana/provisioning/alerting/rules-application.yml`

```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: application_health
    folder: Alerts
    interval: 30s
    rules:
      - uid: alert-high-http-error-rate
        title: HighHTTPErrorRate
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: >-
                sum(rate(http_requests_total{job="backend",status=~"5.."}[5m]))
                  by (instance, environment)
                /
                sum(rate(http_requests_total{job="backend"}[5m]))
                  by (instance, environment)
                > 0.05
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: application
        annotations:
          summary: "High HTTP 5xx error rate on {{ $labels.instance }}"
          description: >-
            More than 5% of backend requests are returning 5xx errors on
            {{ $labels.instance }} ({{ $labels.environment }}).
            Current rate: {{ $value | humanizePercentage }}
        isPaused: false
```

## Verification

```bash
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=http_requests_total{job="backend"}' \
  | jq '.data.result | length'
# Expected: ≥ 7
```
```

---

### Issue 5 — SlowHTTPResponseTime

**Title:** `[Phase 3] Restore SlowHTTPResponseTime using backend histogram (replaces dropped nginx-based alert)`

```markdown
## What it does

Alerts on high p95 backend response latency. Original alert used
`nginx_http_request_duration_seconds_bucket` which does not exist in the nginx-prometheus-
exporter (finding F-PROM-08). Redesigned to use `http_request_duration_seconds_bucket{job="backend"}`
(98 series confirmed live in Phase 1 audit). Two severity tiers:
- **Warning**: p95 > 2s for 5 minutes
- **Critical**: p95 > 5s for 2 minutes

## Phase 3 dependencies

- [x] `http_request_duration_seconds_bucket{job="backend"}` already live.
- [ ] Append two rules to `rules-application.yml` (same file as issue 4).

## Config diff — append inside `rules-application.yml` `rules:` list

```yaml
      - uid: alert-slow-http-response-warning
        title: SlowHTTPResponseTimeWarning
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: >-
                histogram_quantile(
                  0.95,
                  sum(rate(http_request_duration_seconds_bucket{job="backend"}[5m]))
                    by (le, instance, environment)
                ) > 2
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: application
        annotations:
          summary: "Slow backend response time (p95 > 2s) on {{ $labels.instance }}"
          description: >-
            95th percentile backend response time exceeds 2 seconds on
            {{ $labels.instance }} ({{ $labels.environment }}).
            Current p95: {{ $value | humanizeDuration }}
        isPaused: false

      - uid: alert-slow-http-response-critical
        title: SlowHTTPResponseTimeCritical
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: >-
                histogram_quantile(
                  0.95,
                  sum(rate(http_request_duration_seconds_bucket{job="backend"}[5m]))
                    by (le, instance, environment)
                ) > 5
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 2m
        labels:
          severity: critical
          category: application
        annotations:
          summary: "Critical backend response time (p95 > 5s) on {{ $labels.instance }}"
          description: >-
            95th percentile backend response time exceeds 5 seconds on
            {{ $labels.instance }} ({{ $labels.environment }}).
            Current p95: {{ $value | humanizeDuration }}. Immediate investigation required.
        isPaused: false
```

## Verification

```bash
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=http_request_duration_seconds_bucket{job="backend"}' \
  | jq '.data.result | length'
# Expected: ~98
```
```

---

### Issue 6 — MinIODown

**Title:** `[Phase 3] Restore MinIODown by adding MinIO scrape target to AP-VM Alloy configs`

```markdown
## What it does

Alerts when MinIO object storage is unreachable. The original alert used
`up{job="staging-db-minio"}` which referenced a scrape job that never existed (finding
F-PROM-07). Additionally, MinIO runs on AP-VM, not DB-VM, so the target VM was also wrong.

This redesign:
1. Adds a `prometheus.scrape "minio"` block to both AP-VM Alloy configs targeting MinIO's
   `/minio/v2/metrics/cluster` endpoint on port 9000.
2. Alerts on the resulting `up{job="minio",vm="ap-vm"}` series.

## Phase 3 dependencies

- [ ] No upstream fix required — self-contained addition.
- [ ] Confirm MinIO container name/DNS is `minio` on both AP-VMs (check `docker-compose.yml`
      service names).
- [ ] If MinIO requires auth for metrics, add `bearer_token` or `basic_auth` to scrape block.

## Config diff

**`monitoring/config/alloy/staging-ap-vm.alloy`** — add after `prometheus.scrape "backend"`:

```hcl
// Scrape MinIO cluster metrics
prometheus.scrape "minio" {
  targets = [{
    __address__ = "minio:9000",
  }]

  forward_to = [prometheus.relabel.add_labels.receiver]

  job_name        = "minio"
  scrape_interval = "15s"
  metrics_path    = "/minio/v2/metrics/cluster"
}
```

**`monitoring/config/alloy/prod-ap-vm.alloy`** — identical block.

**`monitoring/config/grafana/provisioning/alerting/rules-application.yml`** — append:

```yaml
      - uid: alert-minio-down
        title: MinIODown
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 120
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: up{job="minio",vm="ap-vm"} == 0
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 2m
        labels:
          severity: critical
          category: application
        annotations:
          summary: "MinIO object storage is down on {{ $labels.instance }}"
          description: >-
            MinIO on {{ $labels.instance }} ({{ $labels.environment }},
            {{ $labels.vm }}) is not responding. File upload/download will fail.
        isPaused: false
```

## Verification

```bash
# After Alloy reload on AP-VM:
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=up{job="minio",vm="ap-vm"}' \
  | jq '.data.result'
# Expected: value "1"

# Direct MinIO probe from AP-VM host:
curl -s http://localhost:9000/minio/v2/metrics/cluster | grep '^minio_' | head -5
```
```

---

## 7. Open Questions for Phase 3 Brainstorm

These are the items from §3 (critical decisions) plus synthesis additions. Bring to the user
brainstorm session before opening any PRs:

1. **Is the Phase 2 runner registered and has it completed at least one successful deploy?**
   This is the hard prerequisite for all of Phase 3. Check: `gh workflow view deploy-monitoring-stack.yml`.

2. **Is `up{vm="db-vm"}` already in Prometheus?** If yes, G1 (3A-1) shrinks from a cross-VM
   network fix to a label-verification task. Saves ~0.75 days.

3. **Backend instrumentation: two PRs (recommended) or one combined PR?**

4. **Do the 19 immediate dashboard JSON fixes ship in 3B-2 (before backend instrumentation
   lands) or wait for 3C-2 after?** (No technical blocker on shipping early.)

5. **MinIO metrics auth:** Does production MinIO require bearer token for `/minio/v2/metrics/cluster`?
   Check before writing the scrape block.

6. **Nginx exporter swap (F-GRAF-08):** Confirmed Phase 5 defer, or does the user want to
   pull it into Phase 3 scope? Affects scope by ~1 eng-day and requires VTS/OTel decision.

7. **Recording rules (F-PROM-06):** Delete `aggregations.yml` or re-enable? Recommend delete
   per CLAUDE.md §2 (no backward compat).

8. **F-DEPL-05 ownership:** Phase 2 spec §3 Non-Goals lists it as Phase 3; audit assigns to
   Phase 4. G10 currently includes it in Phase 3. Confirm which phase owns it to avoid
   duplicating effort.

9. **Phase 4 entry: wait for 3D (prod docs) or start 4A-1 after 3C merges?**
   Group A and B of Phase 4 are independent of 3D. Parallel tracks are safe.

10. **F-DEPL-13 prod repo access:** Is the maintainer able to provide prod repo read access
    before Phase 3.D? If not, G11 produces a written SCP template only.

11. **`db_query_duration_seconds` async coverage:** The sync-engine event listener covers
    Alembic/background tasks; the async path needs manual `observe_query()` wrapper calls at
    key hot-paths. How many call sites require wrapping? (P6 proposes `application_service.py`
    line ~1210 as the primary example.) Agree on scope before writing PR-A.

12. **`honor_labels = true` (F-ALLO-10):** Pull into Phase 4 Group E or defer to Phase 5?
    Decision depends on whether Phase 3 Alloy label work reveals actual label bleed.

---

## 8. Scope-Correction Notes

These are contradictions between P3/P4/P5/P6/P7 and the audit, resolved with reasoning:

### S1. F-DEPL-05 phase ownership conflict
**Conflict:** Phase 2 spec §3 Non-Goals assigns F-DEPL-05 to Phase 3; the audit text
assigns remediation to Phase 4.
**Resolution:** G10 keeps F-DEPL-05 in Phase 3 (alongside F-DEPL-06), matching the spec
Non-Goals list. The audit assigns it to Phase 4 only as a rough sketch. Spec takes precedence.
If Phase 3 capacity is constrained, F-DEPL-05 can slip to Phase 4 without blocking anything.

### S2. http_errors_total declared dead in P7, contradicted by P6
**Conflict:** P7 §1-A notes `http_errors_total` has 0 series in Prometheus and treats it as
absent. P6's key finding explicitly states `http_errors_total` is NOT dead — middleware
already calls it at lines 84-87 and 115-118 of `metrics_middleware.py`.
**Resolution:** P6 is correct. P7's "Fix expr" (rewriting the panel to use
`http_requests_total{status=~"5.."}`) is still a valid panel improvement since it eliminates
the `or 0` mask and aligns with the same data used by B4 (HighHTTPErrorRate). However, the
F-GRAF-03 panel fix should note that `http_errors_total` is alive — the panel query rewrite
is a simplification choice, not a dead-metric workaround. The new expression in §1-A is still
preferred because it matches the alert expression exactly (single source of truth for 5xx
rate). No further conflict; apply P7 §1-A fix as written.

### S3. F-GRAF-06 and F-GRAF-11 phase assignment
**Conflict:** F-GRAF-06 (`or 0` masking on overview dashboard) appears in both P3 G7 scope
(P7 §1-A applies the fix as part of the F-GRAF-03 expr rewrite) and P4 Group A. P4 states
"F-GRAF-06, F-GRAF-07, F-APP-07 — or-0 masking removal" as a Phase 4 item.
**Resolution:** P7 §1-A resolves F-GRAF-06 as a side effect of the F-GRAF-03 expression
rewrite (replacing the entire expression including the `or 0` suffix). This means F-GRAF-06
closes in Phase 3 as part of dashboard PR 3C-2, and Phase 4 Group A only needs to handle
F-GRAF-07 (Redis Hit Ratio) and F-APP-07 (second dashboard copy). Phase 4 Group A shrinks to
0.5 day or less but remains a valid group for F-GRAF-07 + F-APP-07. Update Phase 4 Group A
scope accordingly when opening those PRs.

### S4. F-GRAF-11 phase assignment
**Conflict:** P7 §7 (F-GRAF-11 provisioning fix) is included in Phase 3 scope as part of
dashboard PR 3C-2. P4 Group B (provisioning hygiene) also lists F-GRAF-11 as a Phase 4 item.
**Resolution:** If P7 ships F-GRAF-11 in Phase 3 (3C-2), it closes before Phase 4 starts.
Phase 4 Group B then owns only F-GRAF-12 (Logs folder). P4 Group B should be updated to
reflect this when Phase 3 closes. This reduces Phase 4 Group B to a single file move
(already described in P7 §8) — 0.25 day, not 0.5 day.

### S5. MinIO scrape — Phase 3 (P5 B6) vs. Phase 4 implicit
**Conflict:** P5 B6 includes the MinIO scrape block as part of Phase 3. P4 Group E
(F-APP-06 dead metrics) notes that MinIO metrics will be live after "Phase 3 instruments
them." This is consistent — no conflict. MinIO scrape is Phase 3 (3C-1).

### S6. P6 LOC estimate variance
**Conflict:** P6 summary states "Grand total: ~250 LOC across 2 PRs, 9 new test cases."
The per-metric breakdown sums to ~140 LOC (PR-A) + ~116 LOC (PR-B) = 256 LOC.
**Resolution:** 256 LOC is more accurate; brief uses 256. Trivial rounding discrepancy,
no action needed.

### S7. Phase 3 finding count
**Conflict:** P3 header states "34 P1 findings" with "31 remaining P1 findings" (after
F-PROM-11 debunked + F-PROM-12 to Phase 4). The grouping table covers 29 active findings
(the note explains G5/G6 track alert dispositions, not finding IDs).
**Resolution:** 29 is the actionable finding count for code/config changes. 31 is the formal
audit count before the G5/G6 alert-disposition items are recognized as non-finding-ID items.
Brief uses 29 (actionable) throughout.
