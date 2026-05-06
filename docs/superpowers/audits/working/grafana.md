# Grafana Subsystem Audit — Working File

**Branch:** audit/monitoring-stack-phase1
**Date:** 2026-05-06
**Auditor:** Branch A (Grafana)
**Spec:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md` (commit 07faa57)

---

## Findings

---

### F-GRAF-01  [P0]  AlertManager dangling datasource (prior-G confirmed)

**Where**: `monitoring/config/grafana/provisioning/datasources/datasources.yml:109-121` and Grafana API `/monitoring/api/datasources/uid/alertmanager-uid/health`.

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/uid/alertmanager-uid/health` via Playwright session → `{"statusCode":500,"messageId":"plugin.unavailable","message":"Plugin unavailable"}` (HTTP 500). Confirmed in captured artifact `docs/superpowers/audits/working/api-responses/grafana/datasources-health.json` line 1–8.
- Static read: `monitoring/config/grafana/provisioning/datasources/datasources.yml` lines 109–121 define datasource `AlertManager` with `uid: alertmanager-uid`, `type: alertmanager`, `url: http://alertmanager:9093`, `handleGrafanaManagedAlerts: true`. The datasource is still provisioned.
- Cross-reference: Commit `57fca5f` removed AlertManager from the compose stack. The `alertmanager` service at `http://alertmanager:9093` no longer exists, so every `/health` call returns HTTP 500. Because `handleGrafanaManagedAlerts: true` is set, Grafana attempts to route managed alert evaluations through this non-functional datasource. Any alert notification configured to use this datasource silently fails.

**Expected**: Either AlertManager is running and reachable at `http://alertmanager:9093`, or the datasource entry is removed from `datasources.yml` and Grafana unified alerting is decoupled from it.

**Root cause hypothesis**: AlertManager service was removed from compose at commit `57fca5f` but the corresponding Grafana datasource provisioning was not updated.

**Remediation owner**: Phase 2

**Suggested fix sketch**:
```yaml
# Remove the entire AlertManager block from datasources.yml (lines 107-121):
# - name: AlertManager
#   type: alertmanager
#   uid: alertmanager-uid
#   ...
```
Also remove `monitoring/config/alertmanager/alertmanager.yml` and the `alerting:` block from `prometheus.yml` per spec §6.

---

### F-GRAF-02  [P1]  DB-VM targets entirely absent — pg_stat_activity_count and MinIO metrics return zero series

**Where**: `monitoring/config/grafana/provisioning/dashboards/database/postgresql-monitoring.json` (all panels), `monitoring/config/grafana/provisioning/dashboards/database/minio-monitoring.json` (all panels), and Prometheus label endpoint `/api/v1/label/vm/values`.

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/label/vm/values` returns `{"status":"success","data":["ap-vm"]}` — only `ap-vm` exists; `db-vm` is absent. Subsequent targeted queries confirmed: `pg_stat_activity_count` → 0 series; all `minio_*` metrics → 0 series.
- Static read: `monitoring/config/grafana/provisioning/dashboards/database/postgresql-monitoring.json` — every panel PromQL hard-codes `vm="db-vm"` (e.g. `pg_stat_activity_count{environment="$environment", vm="db-vm", state="active"}`). `monitoring/config/grafana/provisioning/dashboards/database/minio-monitoring.json` — every panel also hard-codes `vm="db-vm"`.
- Cross-reference: DB-VM metrics are expected on `vm=db-vm` but the Prometheus instance has zero series carrying that label, meaning the DB-VM scrape pipeline (Alloy or Prometheus scrape job) is not delivering any data. All panels in both dashboards show No-data.

**Expected**: Prometheus has series with `vm="db-vm"` for `pg_stat_activity_count`, `pg_up`, `minio_bucket_usage_total_bytes`, etc., scraped from the DB-VM's postgres-exporter and minio metrics endpoints.

**Root cause hypothesis**: The DB-VM Alloy agent is either not running, not reaching the AP-VM Prometheus remote_write endpoint, or the cross-VM scrape job is misconfigured (this is the Alloy/Cross-VM branch's territory, but the symptom is confirmed here as a Grafana-observable P1).

**Remediation owner**: Phase 3

**Suggested fix sketch**: Fix the DB-VM Alloy configuration so it ships `vm="db-vm"` labeled metrics to AP-VM Prometheus. Verify firewall/network path. Once metrics arrive, the hard-coded `vm="db-vm"` filters in dashboard JSON will work correctly.

---

### F-GRAF-03  [P1]  Backend error-rate metric `http_errors_total` does not exist in Prometheus

**Where**: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` panel "Backend Error Rate (%)" (panel id 7), and Prometheus metric series endpoint.

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/query?query=http_errors_total` → `{"status":"success","data":{"result":[]}}` — zero series. Direct expression used by the panel (`rate(http_errors_total{environment="staging", vm=~"ap-vm", job="backend"}[5m])`) also returns 0 series.
- Static read: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` line 607: `"expr": "((sum(rate(http_errors_total{environment=\"$environment\", vm=~\"$vm\", job=\"backend\"}[5m])) / sum(rate(http_requests_total{environment=\"$environment\", vm=~\"$vm\", job=\"backend\"}[5m]))) * 100) or 0"`. Panel title: "Backend Error Rate (%)".
- Cross-reference: `http_requests_total` exists with 7 series (confirmed by probe); `http_errors_total` does not exist at all. The panel currently evaluates `(0/nonzero) or 0` which yields scalar `0`, masking the missing metric as a green zero rather than No-data.

**Expected**: The backend publishes an `http_errors_total` counter (or a filtered view of `http_requests_total` by status 5xx) so that the error rate panel can compute a meaningful ratio.

**Root cause hypothesis**: The backend metrics instrumentation never implemented a separate `http_errors_total` counter; the dashboard was written assuming it would exist.

**Remediation owner**: Phase 3

**Suggested fix sketch**: Either (a) add `http_errors_total` counter to `backend/app/core/metrics.py` incremented when response status >= 500, or (b) rewrite the panel PromQL to derive errors from `http_requests_total{status=~"5.."}` which already exists with a `status` label.

---

### F-GRAF-04  [P1]  Database query histogram `db_query_duration_seconds_bucket` does not exist in Prometheus

**Where**: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` panel "Database Query p95 (ms)" (panel id 9), and Prometheus metric series endpoint.

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/query?query=db_query_duration_seconds_bucket` → zero series. Panel expression `histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket{environment="staging", vm=~"ap-vm", job="backend"}[5m])) by (le)) * 1000` also returns empty.
- Static read: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` line 743: `"expr": "histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket{environment=\"$environment\", vm=~\"$vm\", job=\"backend\"}[5m])) by (le)) * 1000"`. `http_request_duration_seconds_bucket` does exist (98 series confirmed by probe), but `db_query_duration_seconds_bucket` does not.
- Cross-reference: The panel uses a metric name (`db_query_duration_seconds_bucket`) that has never been emitted by the backend. The panel shows No-data permanently. `http_request_duration_seconds_bucket` exists for HTTP latency, but there is no equivalent for database query latency.

**Expected**: The backend exports a `db_query_duration_seconds` histogram (with `le` labels) that allows p95 computation.

**Root cause hypothesis**: Database query timing instrumentation was planned but not implemented in the backend's metrics module.

**Remediation owner**: Phase 3

**Suggested fix sketch**: Add a `db_query_duration_seconds` Histogram in `backend/app/core/metrics.py`, instrument SQLAlchemy event hooks or the query execution layer to observe each query duration, and ensure the metric carries `environment` and `vm` labels via the same mechanism as `http_request_duration_seconds`.

---

### F-GRAF-05  [P1]  `$environment` variable dropdown includes `monitoring` — internal Prometheus self-monitoring environment leaks into dashboards

**Where**: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` template variable `environment` (line ~1089 in API response), and all other dashboards using `label_values(up, environment)`.

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/label/environment/values` returns `{"status":"success","data":["monitoring","staging"]}`. Prometheus internal jobs (loki, prometheus, grafana) carry `environment="monitoring"` label from Alloy's `external_labels`. When a user selects `monitoring` from the dropdown, all node/redis/backend/nginx queries return zero results (no metrics exist with that environment+vm combination), causing a confusing all-No-data state.
- Static read: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` templating section defines `$environment` variable with `query: "label_values(up, environment)"` — no regex filter to exclude the `monitoring` value.
- Cross-reference: The `monitoring` environment value appears because Alloy scrapes internal components (Prometheus, Loki, Grafana) and labels them `environment="monitoring"`. This is correct for internal monitoring but misleading in the application-facing `$environment` dropdown variable. Users see an apparently valid environment that returns no data.

**Expected**: The `$environment` variable should either regex-exclude `monitoring` (`regex: /^(?!monitoring).*$/`) or internal services should use a different label key so they don't pollute the environment dropdown.

**Root cause hypothesis**: No regex filter is applied to the `label_values(up, environment)` variable query to exclude the internal `monitoring` environment label added by Alloy for its own components.

**Remediation owner**: Phase 3

**Suggested fix sketch**:
```json
"query": "label_values(up, environment)",
"regex": "/^(?!monitoring).*$/"
```
Add this regex to the `$environment` template variable in all dashboards that use `label_values(up, environment)`.

---

### F-GRAF-06  [P2]  Backend Error Rate panel uses `or 0` masking No-data as a false zero

**Where**: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` line 607, panel "Backend Error Rate (%)" (panel id 7).

**Evidence**:
- Active probe: `http_errors_total` returns 0 series (confirmed in F-GRAF-03 probe). The expression `((... http_errors_total ...) * 100) or 0` returns scalar `0` because the entire numerator is empty, triggering the `or 0` fallback. Panel displays green "0" instead of "No data".
- Static read: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` line 607: `"expr": "((sum(rate(http_errors_total{...}[5m])) / sum(rate(http_requests_total{...}[5m]))) * 100) or 0"`. The `or 0` is appended at the end of the expression.
- Cross-reference: When `http_errors_total` is missing entirely (as confirmed by probe), `or 0` causes the panel to show "0%" (healthy-looking) rather than "No data", which violates the spec §9 principle "Dashboards must not append `or 0` to disguise No-data as zero." This is classified P2 because it is cosmetic/hygiene while the underlying metric absence is the P1 issue (F-GRAF-03).

**Expected**: Panel shows "No data" when `http_errors_total` is not scraped, allowing operators to identify missing instrumentation.

**Root cause hypothesis**: `or 0` was added as a defensive fallback to avoid division-by-zero errors, but it also masks complete metric absence.

**Remediation owner**: Phase 4

**Suggested fix sketch**: Remove the ` or 0` suffix and instead handle the division-by-zero case using `bool` operator or conditional: `(sum(rate(http_errors_total{...})) / sum(rate(http_requests_total{...})) > 0) * 100`. Once `http_errors_total` is implemented (F-GRAF-03), this `or 0` becomes unnecessary.

---

### F-GRAF-07  [P2]  Redis Hit Ratio panel uses `or 0` masking No-data

**Where**: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` line 879, panel "Redis Hit Ratio (%)" (panel id 11).

**Evidence**:
- Active probe: `redis_keyspace_hits_total` and `redis_keyspace_misses_total` do exist in staging (redis is UP). But the `or 0` fallback would mask absence if redis stops. The expression appends `or 0` after a division: `(...hits... / (...hits... + ...misses...)) * 100) or 0`.
- Static read: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` line 879: `"expr": "((sum(rate(redis_keyspace_hits_total{...}[5m])) / (sum(rate(redis_keyspace_hits_total{...}[5m])) + sum(rate(redis_keyspace_misses_total{...}[5m])))) * 100) or 0"`.
- Cross-reference: Unlike F-GRAF-06, this metric currently returns data (redis is scraping). However, the `or 0` pattern remains a hygiene issue: if Redis goes down or the scrape fails, the panel will show "0%" (appearing healthy) rather than "No data". This is a latent monitoring-lies-about-state risk once the spec §9 principle is applied.

**Expected**: Panel shows "No data" when Redis hit/miss counters are unavailable.

**Root cause hypothesis**: Same defensive `or 0` pattern applied as in the error rate panel, without considering the monitoring-integrity implications.

**Remediation owner**: Phase 4

**Suggested fix sketch**: Remove ` or 0`. If division-by-zero is needed: `(sum(rate(redis_keyspace_hits_total{...}[5m])) / (sum(rate(redis_keyspace_hits_total{...}[5m])) + sum(rate(redis_keyspace_misses_total{...}[5m]))) > 0) * 100`.

---

### F-GRAF-08  [P1]  Nginx Monitoring dashboard: `nginx_http_requests_total` has no `status` label — HTTP Error Rate and request-by-status panels always return No-data

**Where**: `monitoring/config/grafana/provisioning/dashboards/application/nginx-monitoring.json` lines 93, 359, 368, and Prometheus series for `nginx_http_requests_total`.

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/series?match[]=nginx_http_requests_total` returns one series with labels `{environment:"staging", instance:"nginx-exporter:9113", job:"nginx", vm:"ap-vm"}` — no `status` label. The expression `sum(rate(nginx_http_requests_total{environment="staging",status=~"5.."}[5m])) / sum(...)` returns 0 series (confirmed by probe).
- Static read: `monitoring/config/grafana/provisioning/dashboards/application/nginx-monitoring.json` line 93: `sum(rate(nginx_http_requests_total{environment="$environment"}[5m])) by (status)` — groups by `status` which doesn't exist. Line 359: filters on `status=~"5.."`. Also `nginx_http_request_duration_seconds_bucket` returns 0 series — the nginx exporter does not expose histogram latency data.
- Cross-reference: The `nginx-prometheus-exporter` (VTS or stub_status based) used in staging exposes only aggregate counters (`nginx_http_requests_total` with no per-status breakdown) and connection gauges. The dashboard assumes a VTS-style exporter that emits per-status-code counters and latency histograms, which is not what is deployed. The "HTTP Requests Rate (by status)" panel will show one merged series (no status split), "HTTP Error Rate" will show No-data, and "Request Latency (Percentiles)" will show No-data.

**Expected**: Either (a) the nginx exporter is replaced or configured to emit per-status-code breakdowns and latency histograms, or (b) the dashboard PromQL is adjusted to use the metric labels the current exporter provides.

**Root cause hypothesis**: Dashboard was written against a more capable nginx exporter (e.g., VTS module) than the one actually deployed, which only exports aggregate request counts and connection states.

**Remediation owner**: Phase 3

**Suggested fix sketch**: Confirm which nginx exporter is in use. If it is `nginx/nginx-prometheus-exporter` (stub_status only), either enable the VTS module in nginx or replace error-rate panels with Alloy-collected access-log parsing via Loki. If the VTS exporter is already planned, add it to the compose file.

---

### F-GRAF-09  [P1]  Application Logs dashboard: `$vm` variable is a hard-coded custom list (`ap-vm,db-vm`) but DB-VM has no Loki data

**Where**: `monitoring/config/grafana/provisioning/dashboards/application/application-logs.json` template variable `vm`, and Loki staging label values endpoint.

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/proxy/uid/loki-staging-uid/loki/api/v1/label/vm/values` returns `{"status":"success","data":["ap-vm"]}` — only `ap-vm` exists in Loki staging. The `db-vm` option in the custom variable dropdown will produce empty log results.
- Static read: `docs/superpowers/audits/working/api-responses/grafana/dashboard-application-logs.json` — `vm` variable is `type: custom` with `query: "ap-vm,db-vm"`. This is a hard-coded list rather than a dynamic query like `label_values({environment="$environment"}, vm)`.
- Cross-reference: When users select `db-vm` from the dropdown (which is shown as an option), all LogQL queries filtering on `vm="$vm"` return no results because DB-VM logs are not reaching Loki staging. This is a double problem: (1) DB-VM is not shipping logs (same root cause as F-GRAF-02), and (2) the variable being a static custom list will continue showing `db-vm` as an option even after DB-VM logs are fixed, drifting from the actual dynamic set of VMs shipping logs.

**Expected**: The `$vm` variable should use a dynamic Loki label query (`label_values({environment="$environment"}, vm)`) rather than a hard-coded custom list, so it auto-adapts as VMs are added or removed.

**Root cause hypothesis**: The `vm` variable was written as a static list during initial dashboard development, not updated to be dynamic when Loki label discovery was available.

**Remediation owner**: Phase 3

**Suggested fix sketch**: Change the `vm` variable from `type: custom` to `type: query` with `datasource: loki-staging-uid` and `query: label_values({environment="$environment"}, vm)`.

---

### F-GRAF-10  [P1]  Scholarship overview: `scholarship_applications_total` and `email_sent_total` metrics do not exist — application business-metric panels always No-data

**Where**: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` panels "Applications Submitted", "Applications Approved" (panel ids 12, 13), and "Emails Delivered" (panel id 14).

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/query?query=scholarship_applications_total` → 0 series. `GET /monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/query?query=email_sent_total` → 0 series. Both confirm via the Prometheus proxy that these metrics are never emitted.
- Static read: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` lines for panels 12–14 use `increase(scholarship_applications_total{...,status="submitted"}[$__range])`, `increase(scholarship_applications_total{...,status="approved"}[$__range])`, `increase(email_sent_total{...,status="success"}[$__range])`.
- Cross-reference: The backend scrape target (`backend:8000`) is UP and `http_requests_total` is being collected, but neither `scholarship_applications_total` nor `email_sent_total` appear in any Prometheus series. These application-domain counters were designed into the dashboard but not implemented in the backend's metrics module.

**Expected**: The backend increments `scholarship_applications_total{status="submitted"}` and `scholarship_applications_total{status="approved"}` counters when applications change state, and `email_sent_total{status="success"|"failure"}` when emails are sent.

**Root cause hypothesis**: Application-domain business metrics were planned in the dashboard design but not yet implemented in `backend/app/core/metrics.py` or the relevant service layers.

**Remediation owner**: Phase 3

**Suggested fix sketch**: Add `scholarship_applications_total` (Counter with `status` label) and `email_sent_total` (Counter with `status` label) to the backend metrics module. Increment them in the application/review service layer and the email notification service.

---

### F-GRAF-11  [P2]  All 8 dashboards show `provisioned: false` in API — `allowUiUpdates: true` causes dashboards to lose provisioning link after UI edits

**Where**: `monitoring/config/grafana/provisioning/dashboards/dashboards.yml` lines 14, 26, 38, 50, 62 (`allowUiUpdates: true`), and Grafana API `meta.provisioned` field.

**Evidence**:
- Active probe: All 8 dashboard API responses (`dashboard-*.json` in api-responses/grafana/) show `"provisioned": false` while still carrying `"provisionedExternalId": "<filename>.json"`. This is the Grafana state where a previously provisioned dashboard was edited in the UI, breaking the provisioning link.
- Static read: `monitoring/config/grafana/provisioning/dashboards/dashboards.yml` — every provider sets `allowUiUpdates: true` and `disableDeletion: false`. With `allowUiUpdates: true`, any UI save of a provisioned dashboard converts it from provisioned to user-owned, causing `provisioned: false`.
- Cross-reference: With `provisioned: false`, the dashboards are no longer managed by the IaC config files. Changes to the on-disk JSON files will not propagate to the running Grafana instance until a restart. The "provisionedExternalId" field being set while `provisioned=false` indicates the dashboard was originally provisioned but subsequently edited in the UI, breaking the file→Grafana sync. This violates the spec §9 "IaC-first" principle.

**Expected**: All dashboards remain `provisioned: true`, ensuring on-disk JSON files are the source of truth. Any authorized change goes through the file + git workflow, not the UI.

**Root cause hypothesis**: `allowUiUpdates: true` was set to allow iterative dashboard development, but now dashboards have been UI-edited and their provisioning link is permanently broken without a Grafana restart or dashboard delete+reload.

**Remediation owner**: Phase 4

**Suggested fix sketch**: Set `allowUiUpdates: false` and `disableDeletion: true` in all providers in `dashboards.yml` once dashboards reach a stable state. To re-sync current state: delete each dashboard in the UI and let Grafana re-provision from the on-disk JSON at next `updateIntervalSeconds` (30s) cycle.

---

### F-GRAF-12  [P2]  Dashboard folder naming inconsistency — "Logs" folder defined in provisioner but not used; all log dashboards land in "Application"

**Where**: `monitoring/config/grafana/provisioning/dashboards/dashboards.yml` lines 56–65 (Logs Monitoring provider), and `docs/superpowers/audits/working/api-responses/grafana/dashboards-list.json`.

**Evidence**:
- Active probe: `dashboards-list.json` shows `application-logs` dashboard in `folderTitle: "Application"` (folderUid: bf0qa6pv62cxsd), not in any "Logs" folder. No dashboard exists in a "Logs" folder.
- Static read: `monitoring/config/grafana/provisioning/dashboards/dashboards.yml` lines 56–65 define a provider named `Logs Monitoring` with `folder: 'Logs'` and `path: /etc/grafana/provisioning/dashboards/logs`. No JSON files exist at the corresponding on-disk path `monitoring/config/grafana/provisioning/dashboards/logs/` — the `application/application-logs.json` is stored under `application/` not `logs/`.
- Cross-reference: The `logs` directory provider in `dashboards.yml` is configured but maps to an empty (or non-existent) directory. The Application Logs dashboard is stored under `application/` and therefore lands in the "Application" folder. This creates a dead provider configuration and folder naming that doesn't match user expectations (log dashboards should logically be in "Logs").

**Expected**: Either (a) move `application-logs.json` to `monitoring/config/grafana/provisioning/dashboards/logs/` and keep the Logs provider, or (b) remove the Logs provider from `dashboards.yml` if consolidating into Application.

**Root cause hypothesis**: The "Logs" folder provisioner was planned but the file was placed in the `application/` directory during initial setup, creating an orphaned provider config.

**Remediation owner**: Phase 4

**Suggested fix sketch**: Create `monitoring/config/grafana/provisioning/dashboards/logs/` and move `application-logs.json` into it. The Logs Monitoring provider in `dashboards.yml` will then correctly serve it under the "Logs" folder.

---

## Coverage

### Files Inspected

| File | Lines Read | Method |
|---|---|---|
| `monitoring/config/grafana/provisioning/datasources/datasources.yml` | Full (121 lines) | Static read |
| `monitoring/config/grafana/provisioning/dashboards/dashboards.yml` | Full (65 lines) | Static read |
| `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` | Full (~1146 lines) | Static read |
| `monitoring/config/grafana/provisioning/dashboards/application/application-logs.json` | Full | Static read (via API response) |
| `monitoring/config/grafana/provisioning/dashboards/application/container-monitoring.json` | Full | Static read (via API response) |
| `monitoring/config/grafana/provisioning/dashboards/application/nginx-monitoring.json` | Full | Static read |
| `monitoring/config/grafana/provisioning/dashboards/database/minio-monitoring.json` | Full | Static read (via API response) |
| `monitoring/config/grafana/provisioning/dashboards/database/postgresql-monitoring.json` | Full | Static read (via API response) |
| `monitoring/config/grafana/provisioning/dashboards/database/redis-monitoring.json` | Full | Static read (via API response) |
| `monitoring/config/grafana/provisioning/dashboards/system/node-exporter-system.json` | Full | Static read (via API response) |
| `monitoring/config/grafana/grafana.ini.example` | Full (264 lines) | Static read |
| `docs/superpowers/audits/working/api-responses/grafana/datasources-health.json` | Full | Artifact read |
| `docs/superpowers/audits/working/api-responses/grafana/dashboards-list.json` | Full | Artifact read |
| `docs/superpowers/audits/working/api-responses/grafana/dashboard-scholarship-overview.json` | Full | Artifact read |
| All other `dashboard-*.json` API responses (7 files) | Full | Artifact read |

### API Endpoints Probed (Active Probes)

| Endpoint | Result |
|---|---|
| `GET /monitoring/api/health` | HTTP 200, database OK, version 12.2.1 |
| `GET /monitoring/api/datasources` | HTTP 200, 5 datasources |
| `GET /monitoring/api/datasources/uid/alertmanager-uid/health` | HTTP 500, "Plugin unavailable" |
| `GET /monitoring/api/datasources/uid/prometheus-uid/health` | HTTP 200, OK |
| `GET /monitoring/api/search?type=dash-db&limit=200` | HTTP 200, 8 dashboards |
| Prometheus proxy: `query?query=up` | HTTP 200, 9 series |
| Prometheus proxy: `query?query=up{environment="staging"}` | HTTP 200, 6 series |
| Prometheus proxy: `label/environment/values` | HTTP 200, `["monitoring","staging"]` |
| Prometheus proxy: `label/vm/values` | HTTP 200, `["ap-vm"]` only |
| Prometheus proxy: `query?query=pg_stat_activity_count` | HTTP 200, 0 series |
| Prometheus proxy: `query?query=http_errors_total` | HTTP 200, 0 series |
| Prometheus proxy: `query?query=http_requests_total` | HTTP 200, 7 series |
| Prometheus proxy: `query?query=db_query_duration_seconds_bucket` | HTTP 200, 0 series |
| Prometheus proxy: `query?query=node_cpu_seconds_total` | HTTP 200, 16 series |
| Prometheus proxy: `query?query=nginx_http_requests_total` | HTTP 200, 1 series (no `status` label) |
| Prometheus proxy: `query?query=scholarship_applications_total` | HTTP 200, 0 series |
| Prometheus proxy: `query?query=email_sent_total` | HTTP 200, 0 series |
| Prometheus proxy: `query?query=http_request_duration_seconds_bucket` | HTTP 200, 98 series |
| Prometheus proxy: `query?query=nginx_http_request_duration_seconds_bucket` | HTTP 200, 0 series |
| Prometheus proxy: `query?query=nginx_connections_active` | HTTP 200, 1 series |
| Prometheus proxy: `series?match[]=nginx_http_requests_total` | HTTP 200, 1 series, no status label |
| Loki staging proxy: `/loki/api/v1/label/vm/values` | HTTP 200, `["ap-vm"]` only |
| Loki staging proxy: `/loki/api/v1/label/environment/values` | HTTP 200, `["staging"]` |

### Priors Addressed

| Prior | Result | Finding |
|---|---|---|
| **prior-G** | **CONFIRMED** | F-GRAF-01 (P0) — AlertManager datasource returns HTTP 500, `datasources.yml:109-121` still defines it |

### Screenshot Artifacts

All screenshots captured at Stage 0.4 are in `docs/superpowers/audits/working/screenshots/grafana/`:
- `dashboard-scholarship-overview.png`
- `dashboard-application-logs.png`
- `dashboard-container-monitoring.png`
- `dashboard-minio-monitoring.png`
- `dashboard-nginx-monitoring.png`
- `dashboard-node-exporter-system.png`
- `dashboard-postgresql-monitoring.png`
- `dashboard-redis-monitoring.png`
- `alerting-list.png`

---

## Finding Summary

| ID | Severity | Title |
|---|---|---|
| F-GRAF-01 | P0 | AlertManager dangling datasource |
| F-GRAF-02 | P1 | DB-VM targets entirely absent — pg/minio No-data |
| F-GRAF-03 | P1 | `http_errors_total` metric does not exist |
| F-GRAF-04 | P1 | `db_query_duration_seconds_bucket` does not exist |
| F-GRAF-05 | P1 | `$environment` variable includes internal `monitoring` value |
| F-GRAF-06 | P2 | Backend Error Rate panel uses `or 0` masking No-data |
| F-GRAF-07 | P2 | Redis Hit Ratio panel uses `or 0` |
| F-GRAF-08 | P1 | Nginx Monitoring: `nginx_http_requests_total` has no `status` label |
| F-GRAF-09 | P1 | Application Logs: `$vm` variable is a hard-coded static list |
| F-GRAF-10 | P1 | `scholarship_applications_total` / `email_sent_total` do not exist |
| F-GRAF-11 | P2 | All dashboards show `provisioned: false` due to `allowUiUpdates: true` |
| F-GRAF-12 | P2 | "Logs" folder provider configured but dashboard stored under "Application" |

**Totals: P0=1, P1=6, P2=4, noted=0**

---

## Stage 0.4 Supplemental Context: Screenshot vs Probe Discrepancy

The task brief noted that some screenshots show data (CPU, Memory, p95, Nginx) while Stage 0.4 PromQL probes returned 0 series for `up`, `node_cpu_seconds_total`, etc.

**Resolution**: The Stage 0.4 probes likely failed because the Grafana session had expired (it returned HTTP 401 on API calls while still responding HTTP 200 on `/api/health` due to different auth requirements). After refreshing the session via `grafana-login.js`, all probes succeeded. The screenshots were taken with a valid browser session (which maintains cookies differently), explaining why they showed data.

The current confirmed state with a fresh session:
- `node_cpu_seconds_total{environment="staging"}` → 16 series (CPU data IS available)
- `nginx_http_requests_total{environment="staging"}` → 1 series (Nginx data IS available)
- `redis_memory_used_bytes{environment="staging"}` → 1 series (Redis data IS available)
- `http_request_duration_seconds_bucket{environment="staging"}` → 98 series (p95 latency IS available for backend)

The three **confirmed No-data panels** on the overview dashboard are:
1. **Backend Error Rate (%)** — `http_errors_total` does not exist (F-GRAF-03)
2. **PostgreSQL Active Connections** — `pg_stat_activity_count` returns 0 series; DB-VM not in Prometheus (F-GRAF-02)
3. **Database Query p95 (ms)** — `db_query_duration_seconds_bucket` does not exist (F-GRAF-04)

---

## Cross-branch Observations

(Not logged as F-GRAF findings; for synthesis pass only)

1. **Alloy/Cross-VM (Branch C territory)**: DB-VM is completely absent from Prometheus — no `vm="db-vm"` series exist. This is the root cause of F-GRAF-02. The Alloy cross-VM pipeline or DB-VM remote_write is not functional.

2. **App-Metrics (Branch D territory)**: Three backend metrics are missing: `http_errors_total`, `db_query_duration_seconds_bucket`, `scholarship_applications_total`, `email_sent_total`. These need to be added to `backend/app/core/metrics.py`.

3. **Nginx exporter configuration**: The deployed nginx exporter (`nginx-exporter:9113`) only exports stub_status metrics (`nginx_http_requests_total` as an aggregate counter, no status label; `nginx_connections_active`). It does NOT export per-status-code counters or latency histograms. This is a fundamental mismatch with the Nginx Monitoring dashboard design. Branch D or an infrastructure-side fix is needed.

4. **Prometheus internal self-monitoring environment**: Prometheus, Loki, and Grafana targets carry `environment="monitoring"` label. This appears to be set by Alloy's `external_labels` when scraping the monitoring stack itself. The `monitoring` environment pollutes the `$environment` dropdown in all dashboards using `label_values(up, environment)`.
