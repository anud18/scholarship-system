# Phase 3 Dashboard Query Fix Plan

**Prepared by:** P7 (Phase 3 Prep)
**Date:** 2026-05-06
**Branch:** feat/monitoring-phase2
**Source audit:** `docs/superpowers/audits/working/grafana.md` (commit 35722b7)

Findings in scope: F-GRAF-02, F-GRAF-03, F-GRAF-04, F-GRAF-05, F-GRAF-08, F-GRAF-09, F-GRAF-10, F-GRAF-11, F-GRAF-12.
Deferred to Phase 4: F-GRAF-06, F-GRAF-07 (`or 0` cosmetic).

Total panels with actionable fixes: **16 panels** across 5 dashboards + 2 provisioning file changes.

---

## Dependency Graph

```
P5 (MinIO scrape job / ap-vm) ──────────────────────> minio-monitoring vm label fix (§3)
P6 (backend instrumentation) ──────────────────────> F-GRAF-03 full fix (§1-A)
                                                    > F-GRAF-04 (§1-B, wait)
                                                    > F-GRAF-10 (§1-C, wait)
Phase 3 infra (DB-VM Alloy fix) ───────────────────> F-GRAF-02 (§2, no JSON change needed)
Phase 3 (this plan, no external dep) ─────────────> F-GRAF-05 (§1-D, §2-env, §3-env, §4-env, §6-env)
                                                    > F-GRAF-08 deferred to Phase 5 (§4)
                                                    > F-GRAF-09 (§5)
                                                    > F-GRAF-11 (§7, dashboards.yml)
                                                    > F-GRAF-12 (§8, file move)
```

---

## §1 — scholarship-system-overview.json

**Dashboard:** Scholarship System Overview
**UID:** `scholarship-overview`
**File:** `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json`
**Folder:** General
**provisioned:** false (F-GRAF-11, see §7)

### §1-A — Backend Error Rate (%) — F-GRAF-03

| Field | Value |
|---|---|
| Panel title | Backend Error Rate (%) |
| Panel id | 7 |
| JSON path | `panels[6].targets[0].expr` |
| Current expr | `((sum(rate(http_errors_total{environment="$environment", vm=~"$vm", job="backend"}[5m])) / sum(rate(http_requests_total{environment="$environment", vm=~"$vm", job="backend"}[5m]))) * 100) or 0` |
| Problem | `http_errors_total` does not exist in Prometheus (0 series). `or 0` masks absence as a false zero. |
| Fix expr | `(sum(rate(http_requests_total{environment="$environment", vm=~"$vm", job="backend", status=~"5.."}[5m])) / sum(rate(http_requests_total{environment="$environment", vm=~"$vm", job="backend"}[5m]))) * 100` |
| Verification | `curl -sG 'http://localhost:9090/api/v1/query' --data-urlencode 'query=sum(rate(http_requests_total{status=~"5.."}[5m]))' \| jq .` — must return at least 1 result once `status` label is confirmed present |
| Phase 3 dependency | None (uses existing `http_requests_total` which has 7 series). If P6 adds `http_errors_total` counter, revert to the original numerator for semantic correctness. |

> Note: The fix eliminates the `or 0` suffix at the same time (addresses F-GRAF-06 early). Confirm `http_requests_total` carries a `status` label via: `curl -sG 'http://localhost:9090/api/v1/series' --data-urlencode 'match[]=http_requests_total' | jq '.data[0]'`.

### §1-B — Database Query p95 (ms) — F-GRAF-04

| Field | Value |
|---|---|
| Panel title | Database Query p95 (ms) |
| Panel id | 9 |
| JSON path | `panels[8].targets[0].expr` |
| Current expr | `histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket{environment="$environment", vm=~"$vm", job="backend"}[5m])) by (le)) * 1000` |
| Problem | `db_query_duration_seconds_bucket` does not exist (0 series). Panel is permanently No-data. |
| Fix | **Wait for P6 backend instrumentation** to add `db_query_duration_seconds` Histogram. No dashboard JSON change needed — the PromQL is correct once the metric exists. |
| Verification | After P6: `curl -sG 'http://localhost:9090/api/v1/query' --data-urlencode 'query=db_query_duration_seconds_bucket' \| jq '.data.result | length'` — must be > 0. |
| Phase 3 dependency | **Blocked on P6** (backend instrumentation). |

### §1-C — Applications Submitted / Approved / Emails Delivered — F-GRAF-10

| Panel title | Panel id | JSON path | Current metric | Problem |
|---|---|---|---|---|
| Applications Submitted ($__range) | 12 | `panels[11].targets[0].expr` | `scholarship_applications_total{status="submitted"}` | 0 series — never emitted by backend |
| Applications Approved ($__range) | 13 | `panels[12].targets[0].expr` | `scholarship_applications_total{status="approved"}` | 0 series — never emitted by backend |
| Emails Delivered ($__range) | 14 | `panels[13].targets[0].expr` | `email_sent_total{status="success"}` | 0 series — never emitted by backend |

**Fix:** Wait for P6 backend instrumentation. No dashboard JSON changes needed — PromQL is correct once counters exist.

**Verification after P6:**
```bash
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=scholarship_applications_total' | jq '.data.result | length'
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=email_sent_total' | jq '.data.result | length'
```
Both must return > 0.

**Phase 3 dependency:** Blocked on P6.

### §1-D — $environment template variable — F-GRAF-05

| Field | Value |
|---|---|
| Variable name | `environment` |
| JSON path | `templating.list[0].regex` |
| Current value | `""` (empty — no filter) |
| Problem | `label_values(up, environment)` returns `["monitoring","staging"]`. Selecting `monitoring` from the dropdown makes all panels return No-data, misleading operators. |
| Fix | Set `regex` field to `/^(?!monitoring).*$/` |
| Verification | In Grafana UI: confirm the `$environment` dropdown no longer shows `monitoring`. Or via PromQL: `curl -sG 'http://localhost:9090/api/v1/label/environment/values' \| jq '.data'` — `monitoring` will still be in Prometheus, but the Grafana variable should filter it out. |
| Phase 3 dependency | None. Can be applied immediately. |

---

## §2 — postgresql-monitoring.json

**Dashboard:** PostgreSQL Monitoring
**UID:** `postgresql-monitoring`
**File:** `monitoring/config/grafana/provisioning/dashboards/database/postgresql-monitoring.json`
**Folder:** Database
**provisioned:** false (F-GRAF-11, see §7)

### F-GRAF-02 — All panels hardcode `vm="db-vm"`

| Panel title | JSON path | Current filter | Problem |
|---|---|---|---|
| Active Connections | `panels[0].targets[0].expr` | `vm="db-vm"` | DB-VM absent from Prometheus — 0 series |
| Total Connections | `panels[1].targets[0].expr` | `vm="db-vm"` | Same |
| PostgreSQL Status | `panels[2].targets[0].expr` | `vm="db-vm"` | Same |
| Database Size | `panels[3].targets[0].expr` | `vm="db-vm"` | Same |
| Connections by State | `panels[4].targets[0].expr` | `vm="db-vm"` | Same |
| Longest Transaction Duration | `panels[5].targets[0].expr` | `vm="db-vm"` | Same |
| Transaction Rate (commit) | `panels[6].targets[0].expr` | `vm="db-vm"` | Same |
| Transaction Rate (rollback) | `panels[6].targets[1].expr` | `vm="db-vm"` | Same |
| Tuple Activity (fetched) | `panels[7].targets[0].expr` | `vm="db-vm"` | Same |
| Tuple Activity (returned) | `panels[7].targets[1].expr` | `vm="db-vm"` | Same |
| Cache Hit Ratio | `panels[8].targets[0].expr` | `vm="db-vm"` | Same |
| Deadlocks | `panels[9].targets[0].expr` | `vm="db-vm"` | Same |

Also: `$database` variable query at `templating.list[1]` uses `vm="db-vm"` — no data until DB-VM is in Prometheus.

**Fix:** **No dashboard JSON change needed.** The `vm="db-vm"` label is correct. Fix requires Phase 3 infrastructure work to bring DB-VM Alloy agent online and deliver `vm="db-vm"` labeled series to AP-VM Prometheus.

**Verification after DB-VM Alloy fix:**
```bash
curl -sG 'http://localhost:9090/api/v1/label/vm/values' | jq '.data'
# Must include "db-vm"
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=pg_stat_activity_count{vm="db-vm"}' | jq '.data.result | length'
# Must be > 0
```

**Phase 3 dependency:** Blocked on Phase 3 infra (DB-VM Alloy cross-VM pipeline).

**F-GRAF-05 also applies here:** `$environment` variable at `templating.list[0]` has empty `regex`. Apply `/^(?!monitoring).*$/` — same fix as §1-D.

---

## §3 — minio-monitoring.json

**Dashboard:** MinIO Monitoring
**UID:** `minio-monitoring`
**File:** `monitoring/config/grafana/provisioning/dashboards/database/minio-monitoring.json`
**Folder:** Database
**provisioned:** false (F-GRAF-11, see §7)

### F-GRAF-02 — All panels hardcode `vm="db-vm"` but MinIO runs on AP-VM

All 8 MinIO panels incorrectly use `vm="db-vm"`. MinIO is deployed on AP-VM (confirmed: only `ap-vm` exists in Prometheus label values). This is a **JSON fix required** (unlike PostgreSQL).

| Panel title | Panel id | JSON path | Current expr (excerpt) | Fix expr (excerpt) |
|---|---|---|---|---|
| Total Storage Used | 1 | `panels[1].targets[0].expr` | `...vm="db-vm"` | `...vm="ap-vm"` |
| Total Objects | 2 | `panels[2].targets[0].expr` | `...vm="db-vm"` | `...vm="ap-vm"` |
| Total Buckets | 3 | `panels[3].targets[0].expr` | `...vm="db-vm"` | `...vm="ap-vm"` |
| MinIO Status | 4 | `panels[4].targets[0].expr` | `...vm="db-vm"` | `...vm="ap-vm"` |
| S3 API Requests | 5 | `panels[6].targets[0].expr` | `...vm="db-vm"` | `...vm="ap-vm"` |
| S3 API Errors | 6 | `panels[7].targets[0].expr` | `...vm="db-vm"` | `...vm="ap-vm"` |
| Network Traffic (rx) | 7 | `panels[9].targets[0].expr` | `...vm="db-vm"` | `...vm="ap-vm"` |
| Network Traffic (tx) | 7 | `panels[9].targets[1].expr` | `...vm="db-vm"` | `...vm="ap-vm"` |
| Bucket Usage Over Time | 8 | `panels[10].targets[0].expr` | `...vm="db-vm"` | `...vm="ap-vm"` |

**Full replacement:** In the dashboard JSON, replace all occurrences of `vm="db-vm"` with `vm="ap-vm"` (9 target expressions).

**Verification after P5 adds MinIO scrape job on AP-VM:**
```bash
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=minio_bucket_usage_total_bytes{vm="ap-vm"}' | jq '.data.result | length'
# Must be > 0
```

**Phase 3 dependency:** Blocked on P5 (MinIO scrape job addition). The `vm` label fix can be applied immediately to the JSON; the metric will only appear once P5 deploys the scrape config.

**F-GRAF-05 also applies here:** `$environment` variable at `templating.list[0]` has empty `regex`. Apply `/^(?!monitoring).*$/`.

---

## §4 — nginx-monitoring.json

**Dashboard:** Nginx Monitoring
**UID:** `nginx-monitoring`
**File:** `monitoring/config/grafana/provisioning/dashboards/application/nginx-monitoring.json`
**Folder:** Application
**provisioned:** false (F-GRAF-11, see §7)

### F-GRAF-08 — HTTP Requests Rate (by status) / HTTP Error Rate / Request Latency — No status label, no histogram

| Panel title | Panel id | JSON path | Current expr | Problem |
|---|---|---|---|---|
| HTTP Requests Rate (by status) | 1 | `panels[0].targets[0].expr` | `sum(rate(nginx_http_requests_total{environment="$environment"}[5m])) by (status)` | `nginx_http_requests_total` has no `status` label — `by (status)` returns one merged series, status split never shows |
| Request Latency (Percentiles) p50 | 2 | `panels[1].targets[0].expr` | `histogram_quantile(0.50, sum(rate(nginx_http_request_duration_seconds_bucket{...}[5m])) by (le))` | `nginx_http_request_duration_seconds_bucket` — 0 series, stub_status exporter does not expose histograms |
| Request Latency (Percentiles) p95 | 2 | `panels[1].targets[1].expr` | same metric, 0.95 | Same |
| Request Latency (Percentiles) p99 | 2 | `panels[1].targets[2].expr` | same metric, 0.99 | Same |
| HTTP Error Rate (5xx) | 4 | `panels[3].targets[0].expr` | `100 * sum(rate(nginx_http_requests_total{...,status=~"5.."}[5m])) / sum(...)` | No `status` label — numerator always 0 |
| HTTP Error Rate (4xx) | 4 | `panels[3].targets[1].expr` | `100 * sum(rate(nginx_http_requests_total{...,status=~"4.."}[5m])) / sum(...)` | Same |

**Decision: Defer to Phase 5 (nginx exporter swap).**

Root cause: The deployed `nginx-prometheus-exporter` (stub_status only) does not emit per-status-code counters or latency histograms. Fixing this requires either:
- (a) Enabling the nginx-vts-exporter, which requires the nginx VTS module compiled in
- (b) Replacing panels with Loki-based log-parsing queries (depends on Loki having nginx access logs)
- (c) Switching to a log-parser-based approach via Alloy

None of these are achievable within Phase 3 scope without broader infrastructure changes. **These 6 panel targets are documented as "won't fix in Phase 3" and deferred to a Phase 5 nginx exporter swap track.**

Panel id=3 ("Active Connections") is unaffected — `nginx_connections_active` has 1 series and works correctly.

**F-GRAF-05 also applies here:** `$environment` variable at `templating.list[0]` has empty `regex`. Apply `/^(?!monitoring).*$/`.

---

## §5 — application-logs.json

**Dashboard:** Application Logs
**UID:** `application-logs`
**File:** `monitoring/config/grafana/provisioning/dashboards/application/application-logs.json`
**Folder:** Application (should be Logs — see §8)
**provisioned:** false (F-GRAF-11, see §7)

### F-GRAF-09 — $vm variable is hard-coded custom list

| Field | Value |
|---|---|
| Variable name | `vm` |
| JSON path | `templating.list[1]` |
| Current `type` | `custom` |
| Current `query` | `ap-vm,db-vm` |
| Current `regex` | `""` |
| Problem | Hard-coded list shows `db-vm` as an option even though DB-VM has no Loki data (`loki/api/v1/label/vm/values` returns only `ap-vm`). Selecting `db-vm` yields empty logs. Does not auto-adapt as VMs are added. |
| Fix `type` | `query` |
| Fix datasource | `loki-staging-uid` |
| Fix `query` | `label_values({environment="$environment"}, vm)` |
| Fix `regex` | `""` (no filter needed — Loki only has real VMs) |
| Verification | After fix: Grafana `$vm` dropdown should only show `ap-vm`. After DB-VM Loki is fixed, `db-vm` appears automatically. `curl -sG 'http://localhost:3100/loki/api/v1/label/vm/values' \| jq '.data'` — confirms source of truth. |
| Phase 3 dependency | None. Can be applied immediately. |

**F-GRAF-05 also applies here:** `$environment` variable at `templating.list[0]` has empty `regex`. Apply `/^(?!monitoring).*$/`.

---

## §6 — Dashboards with F-GRAF-05 Only ($environment regex)

The following 3 dashboards have no other Phase 3 panel fixes, but all use `label_values(up, environment)` without a regex filter and must receive the F-GRAF-05 fix:

| Dashboard | UID | File | Template var JSON path |
|---|---|---|---|
| Container Monitoring (cAdvisor) | `container-monitoring` | `application/container-monitoring.json` | `templating.list[0].regex` |
| System Monitoring (Node Exporter) | `node-exporter-system` | `system/node-exporter-system.json` | `templating.list[0].regex` |
| Redis Monitoring | `redis-monitoring` | `database/redis-monitoring.json` | `templating.list[0].regex` |

**Fix for each:** Set `templating.list[0].regex` to `/^(?!monitoring).*$/`.

**Verification:**
```bash
# Confirm monitoring env is excluded from variable in Grafana UI after applying fix and reloading provision.
# Source of truth: still 2 values in Prometheus
curl -sG 'http://localhost:9090/api/v1/label/environment/values' | jq '.data'
# ["monitoring","staging"] — regex filters "monitoring" out in Grafana only
```

---

## §7 — F-GRAF-11: Provisioned Status Remediation (dashboards.yml)

**File:** `monitoring/config/grafana/provisioning/dashboards/dashboards.yml`
**Problem:** All 5 providers set `allowUiUpdates: true` and `disableDeletion: false`. This caused all 8 dashboards to show `provisioned: false` after UI edits, breaking IaC file→Grafana sync.

**Fix:** Change both flags in every provider block:

```yaml
# Before (each provider):
disableDeletion: false
allowUiUpdates: true

# After (each provider):
disableDeletion: true
allowUiUpdates: false
```

Affected provider names (lines in `dashboards.yml`):
- `Default` (line 14)
- `System Monitoring` (line 26)
- `Application Monitoring` (line 38)
- `Database Monitoring` (line 50)
- `Logs Monitoring` (line 62)

**Post-fix procedure:**
1. Apply changes to `dashboards.yml`
2. For each of the 8 dashboards: delete the dashboard in the Grafana UI
3. Wait up to 30 seconds for the provisioner to re-load from disk (controlled by `updateIntervalSeconds: 30`)
4. Verify each dashboard shows `"provisioned": true` via `GET /monitoring/api/dashboards/uid/<uid>` → `meta.provisioned`

**Verification command:**
```bash
for uid in scholarship-overview postgresql-monitoring minio-monitoring nginx-monitoring \
           application-logs container-monitoring node-exporter-system redis-monitoring; do
  result=$(curl -s -u admin:admin "http://localhost:3000/monitoring/api/dashboards/uid/$uid" | jq -r '.meta.provisioned')
  echo "$uid: provisioned=$result"
done
```

**Phase 3 dependency:** None. Apply after all JSON dashboard fixes are committed and Grafana is restarted.

---

## §8 — F-GRAF-12: Folder Remediation (application-logs.json file move)

**Problem:** `dashboards.yml` defines a `Logs Monitoring` provider pointing to `path: /etc/grafana/provisioning/dashboards/logs`, but `application-logs.json` lives under `application/`. The `logs/` directory is empty/nonexistent, so the `Logs Monitoring` provider is a dead no-op. The Application Logs dashboard lands in the "Application" folder instead of "Logs".

**Fix:**
```bash
# On-disk path (in the repo):
mkdir -p monitoring/config/grafana/provisioning/dashboards/logs
git mv monitoring/config/grafana/provisioning/dashboards/application/application-logs.json \
       monitoring/config/grafana/provisioning/dashboards/logs/application-logs.json
```

After the move:
- The `Application Monitoring` provider (folder: `Application`, path: `application/`) no longer serves this file
- The `Logs Monitoring` provider (folder: `Logs`, path: `logs/`) picks it up → dashboard appears in "Logs" folder

**Verification:**
```bash
curl -s -u admin:admin 'http://localhost:3000/monitoring/api/search?type=dash-db' | \
  jq '.[] | select(.uid=="application-logs") | {uid, folderTitle}'
# Expected: {"uid": "application-logs", "folderTitle": "Logs"}
```

**Phase 3 dependency:** None. Must be done alongside §7 provisioning fix so the move takes effect on restart.

---

## Summary Table

| Finding | Dashboard | Panels affected | Action | Phase 3 dep | Status |
|---|---|---|---|---|---|
| F-GRAF-03 | scholarship-overview | 1 (panel 7) | Rewrite expr to use `status=~"5.."` filter on `http_requests_total` | None | Fix now |
| F-GRAF-04 | scholarship-overview | 1 (panel 9) | No JSON change — wait for P6 to add histogram | P6 | Wait |
| F-GRAF-05 | All 8 dashboards | 8 `$environment` vars | Add `regex: /^(?!monitoring).*$/` | None | Fix now |
| F-GRAF-08 | nginx-monitoring | 6 targets (panels 1, 2, 4) | Deferred — document as won't fix Phase 3 | Phase 5 | Defer |
| F-GRAF-09 | application-logs | 1 `$vm` var | Change type→query, datasource=loki-staging-uid | None | Fix now |
| F-GRAF-10 | scholarship-overview | 3 (panels 12, 13, 14) | No JSON change — wait for P6 counters | P6 | Wait |
| F-GRAF-02 (pg) | postgresql-monitoring | 12 targets + 1 var | No JSON change — fix DB-VM Alloy | Phase 3 infra | Wait |
| F-GRAF-02 (minio vm) | minio-monitoring | 9 targets | Change `vm="db-vm"` → `vm="ap-vm"` everywhere | P5 scrape job | Fix now |
| F-GRAF-11 | dashboards.yml (all) | 5 providers | Set `allowUiUpdates: false`, `disableDeletion: true` | None | Fix now |
| F-GRAF-12 | application-logs file | File location | `git mv application/application-logs.json logs/` | None (with §7) | Fix now |

**Panel-fix count:**
- Immediate JSON fixes: 1 (F-GRAF-03) + 8 (F-GRAF-05) + 1 (F-GRAF-09) + 9 (F-GRAF-02/minio vm) = **19 expression/variable changes**
- Waiting on P6: 4 panels (F-GRAF-04, F-GRAF-10 ×3) — no JSON change, backend instrumentation needed
- Deferred Phase 5: 6 targets (F-GRAF-08) — nginx exporter swap required
- Provisioning file changes: 1 dashboards.yml (10 flag changes across 5 providers)
- File system change: 1 (git mv application-logs.json to logs/)
