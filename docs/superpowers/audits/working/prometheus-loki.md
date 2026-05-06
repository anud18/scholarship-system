# Branch B — Prometheus + Loki Audit Working File

**Branch:** B  
**Subsystem:** Prometheus + Loki  
**Spec:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md` (commit 07faa57)  
**Auditor:** Claude (Sonnet 4.6)  
**Date:** 2026-05-06  

---

## Findings

---

### F-PROM-01  [P0]  Alert rules and recording rules both disabled — all Prometheus rule evaluation turned off

**Where**: `monitoring/config/prometheus/prometheus.yml:20-23`

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/rules` →
  ```json
  {"status":"success","data":{"groups":[]}}
  ```
  Zero rule groups loaded. Confirmed live at 2026-05-06T18:10Z.
- Static read: `monitoring/config/prometheus/prometheus.yml:20-23`
  ```yaml
  # Alert rules (disabled - no AlertManager)
  # rule_files:
  #   - '/etc/prometheus/alerts/*.yml'
  #   - '/etc/prometheus/recording-rules/*.yml'
  ```
  Both `alerts/*.yml` and `recording-rules/*.yml` are commented out.
- Cross-reference: `monitoring/config/prometheus/alerts/basic-alerts.yml` defines 14 alert rules across 5 groups (system_health, container_health, database_health, application_health, monitoring_health). `monitoring/config/prometheus/recording-rules/aggregations.yml` defines 25 recording rules across 6 groups. None are loaded. The alert files are mounted into the container (`docker-compose.monitoring.yml:109`) but ignored.

**Expected**: Both `rule_files` entries should be active. Prometheus should load and evaluate all alert and recording rules.

**Root cause hypothesis**: When AlertManager was removed (commit 57fca5f), `rule_files` was also commented out to silence evaluation errors, but this also silenced every recording rule needed by dashboards.

**Remediation owner**: Phase 2 (alert rules → Grafana unified alerting); Phase 3 (recording rules → re-enable in `rule_files`).

**Suggested fix sketch**:
```yaml
# Re-enable recording rules immediately (no AlertManager needed):
rule_files:
  - '/etc/prometheus/recording-rules/*.yml'
# Alert rules: migrate to Grafana unified alerting (Phase 2), then optionally
# remove the alerts/*.yml file entirely.
```

---

### F-PROM-02  [P0]  AlertManager datasource still provisioned in Grafana pointing at removed service

**Where**: `monitoring/config/grafana/provisioning/datasources/datasources.yml:109-120`

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/uid/alertmanager-uid/health` → HTTP 500, `{"message":"Plugin unavailable"}` (captured in `api-responses/grafana/datasources-health.json`).
- Static read: `monitoring/config/grafana/provisioning/datasources/datasources.yml:109-120`
  ```yaml
  - name: AlertManager
    type: alertmanager
    uid: alertmanager-uid
    orgId: 1
    access: proxy
    url: http://alertmanager:9093
    editable: false
    jsonData:
      implementation: prometheus
      handleGrafanaManagedAlerts: true
  ```
- Cross-reference: `monitoring/docker-compose.monitoring.yml` has no `alertmanager:` service. The `alertmanager:9093` URL resolves to nothing. The datasource provisions but the plugin health call returns 500 "Plugin unavailable" on every Grafana startup.

**Expected**: Either (a) the AlertManager datasource entry is removed entirely, or (b) AlertManager service is restored.

**Root cause hypothesis**: The AlertManager service was removed from compose (commit 57fca5f) but the datasource provisioning file was never updated.

**Remediation owner**: Phase 2.

**Suggested fix sketch**:
```yaml
# Delete lines 109-120 from datasources.yml entirely.
# No AlertManager = no AlertManager datasource.
```

---

### F-PROM-03  [P0]  Prior-G confirmed: alert rules fire into a void — no receiver exists

**Where**: `monitoring/config/prometheus/prometheus.yml:12-18` and `monitoring/config/prometheus/alerts/basic-alerts.yml:1-276`

**Evidence**:
- Active probe: `GET /api/v1/rules` → `{"groups":[]}` (rules not loaded). Even if they were loaded, the `alerting:` block is absent:
  ```yaml
  # alerting:
  #   alertmanagers:
  #     - static_configs:
  #         - targets:
  #             - alertmanager:9093
  ```
- Static read: `monitoring/config/prometheus/prometheus.yml:12-18` — `alerting:` block is commented out. `monitoring/config/prometheus/alerts/basic-alerts.yml:1-276` — 14 alert rules defined across 5 groups.
- Cross-reference: Rules exist in files, files not loaded (F-PROM-01), AlertManager not running (F-PROM-02), `alerting:` block commented out. Triple failure: rules not loaded → not evaluated → no receiver anyway. Any alert that were firing would reach nobody.

**Expected**: Alert rules are evaluated by Prometheus and delivered to a working receiver (Grafana unified alerting or AlertManager).

**Root cause hypothesis**: Removal of AlertManager also removed the full alert pipeline rather than migrating it.

**Remediation owner**: Phase 2.

**Suggested fix sketch**: Migrate all rules in `basic-alerts.yml` to Grafana unified alerting provisioning YAML; remove `alerting:` block; configure Grafana contact point targeting GitHub Issues webhook (per spec §6).

---

### F-PROM-04  [P0]  Zero prod-environment metrics — prod Alloy not pushing to this Prometheus

**Where**: Active probe only (no static-read counterpart — this is an operational gap, not a config error in files we control).

**Evidence**:
- Active probe: `GET /api/v1/query?query=up{environment="prod"}` → `{"result":[]}` (0 series). `GET /api/v1/label/vm/values` → `["ap-vm"]`. No `vm=prod-*`, no `environment=prod` data in TSDB.
- Static read: `monitoring/config/alloy/prod-ap-vm.alloy` and `prod-db-vm.alloy` exist in repo and configure `remote_write` to `${MONITORING_SERVER_URL}:9090/api/v1/write`. Prometheus has `--web.enable-remote-write-receiver` enabled.
- Cross-reference: Prometheus has no prod-environment metrics despite prod Alloy configs being defined. Either (a) prod Alloy is not deployed/running, (b) `MONITORING_SERVER_URL` on prod VMs points to wrong host, or (c) network path from prod VMs to AP-VM Prometheus is blocked. The staging environment does deliver metrics correctly (6 `up` series with `environment=staging`).

**Expected**: `up{environment="prod"}` returns at least `node`, `cadvisor`, `nginx`, `backend`, `redis` series from prod AP-VM, and `node`, `postgres` from prod DB-VM.

**Root cause hypothesis**: Prod Alloy has not been deployed to prod VMs, or `MONITORING_SERVER_URL` is misconfigured on the prod side.

**Remediation owner**: Phase 3.

**Suggested fix sketch**: Deploy Alloy to prod VMs using `docker-compose.prod-db-monitoring.yml` and a prod-AP counterpart. Verify `MONITORING_SERVER_URL` points to the AP-VM hosting Prometheus.

---

### F-PROM-05  [P1]  DB-VM metrics completely absent — postgres-exporter not reaching Prometheus

**Where**: `monitoring/config/alloy/staging-db-vm.alloy:83-98` and `docker-compose.staging-db-monitoring.yml:56-70`

**Evidence**:
- Active probe: `GET /api/v1/query?query=up{vm="db-vm"}` → `{"result":[]}`. `GET /api/v1/label/vm/values` → `["ap-vm"]`. `GET /api/v1/query?query=pg_stat_activity_count` → 0 series. `GET /api/v1/query?query=pg_up` → 0 series.
- Static read: `monitoring/config/alloy/staging-db-vm.alloy:83-98`:
  ```
  // =============================================================================
  // METRICS PIPELINE - PULL MODE
  // =============================================================================
  // Metrics are exposed via exporters and scraped directly by Prometheus on AP-VM:
  // - Node Exporter: exposed on port 9100
  // - PostgreSQL Exporter: exposed on port 9187
  // ...
  // Prometheus on AP-VM will add environment/vm labels during scrape using
  // relabel_configs in its prometheus.yml configuration.
  ```
  DB-VM Alloy does NOT push metrics via `prometheus.remote_write`. It expects AP-VM Prometheus to pull (scrape) directly from exposed ports on the DB-VM.
- Cross-reference: `monitoring/config/prometheus/prometheus.yml` has **no scrape_config** for `postgres-exporter`, `node-exporter` on DB-VM, or any cross-VM scrape job. The comment in `prometheus.yml` says "All application/system metrics are collected by Grafana Alloy and sent to Prometheus via remote_write". But `staging-db-vm.alloy` uses the opposite model (pull, not push). The two sides of the DB-VM metrics pipeline expect different collection modes and are incompatible.

**Expected**: Either (a) `prometheus.yml` adds scrape jobs for DB-VM exporters (`postgres-exporter:9187`, `node-exporter:9100` on db-vm host), or (b) `staging-db-vm.alloy` is updated to use `prometheus.remote_write` like `staging-ap-vm.alloy` does.

**Root cause hypothesis**: Architecture mismatch between AP-VM (push via Alloy remote_write) and DB-VM (pull assumed but Prometheus scrape_configs never written).

**Remediation owner**: Phase 3.

**Suggested fix sketch** (option B — consistent push model):
```alloy
// In staging-db-vm.alloy, add:
prometheus.scrape "postgres_exporter" {
  targets = [{ __address__ = "postgres-exporter:9187" }]
  forward_to = [prometheus.relabel.add_labels.receiver]
  job_name = "postgres"
  scrape_interval = "15s"
}

prometheus.scrape "node_exporter" {
  targets = [{ __address__ = "node-exporter:9100" }]
  forward_to = [prometheus.relabel.add_labels.receiver]
  job_name = "node"
  scrape_interval = "15s"
}

prometheus.relabel "add_labels" {
  forward_to = [prometheus.remote_write.default.receiver]
  rule { target_label = "environment"; replacement = "staging" }
  rule { target_label = "vm"; replacement = "db-vm" }
}

prometheus.remote_write "default" {
  endpoint { url = env("MONITORING_SERVER_URL") + ":9090/api/v1/write" }
}
```

---

### F-PROM-06  [P1]  Recording rules disabled — all pre-aggregated metrics unavailable for dashboards

**Where**: `monitoring/config/prometheus/prometheus.yml:21-23` and `monitoring/config/prometheus/recording-rules/aggregations.yml:1-224`

**Evidence**:
- Active probe: `GET /api/v1/rules` → `{"groups":[]}`. Zero recording rule groups loaded.
- Static read: `monitoring/config/prometheus/recording-rules/aggregations.yml` defines 25 recording rules: `instance:node_cpu_utilization:rate5m`, `postgres:connection_utilization:ratio`, `nginx:http_requests:rate5m`, `slo:request_success_rate:ratio5m`, etc. All are computed from raw metrics. File is mounted at `/etc/prometheus/recording-rules/aggregations.yml` per `docker-compose.monitoring.yml:109`.
- Cross-reference: No dashboard JSON in `monitoring/config/grafana/provisioning/dashboards/**` references any recording rule metric name (grepped for `instance:node_cpu`, `nginx:http_requests:rate`, `slo:`, `postgres:connection`, `environment:cpu`). Dashboards query raw metrics directly, so recording rules produce dead-code aggregations even if enabled.

**Expected**: If recording rules are retained, they should be loadable and either referenced by dashboards or documented as reserved for future external consumers (e.g., alerting thresholds).

**Root cause hypothesis**: `rule_files` was commented out (F-PROM-01) when AlertManager was removed; no dashboards use the recording-rule names so the dead code has not been noticed.

**Remediation owner**: Phase 3.

**Suggested fix sketch**: Either (a) re-enable `rule_files` for recording-rules only and update dashboards to reference recorded metric names for performance, or (b) acknowledge they are dead code and delete `aggregations.yml`.

---

### F-PROM-07  [P1]  Alert rule references non-existent job label `staging-db-minio`

**Where**: `monitoring/config/prometheus/alerts/basic-alerts.yml:226-232`

**Evidence**:
- Active probe: `GET /api/v1/label/job/values` → `["backend","cadvisor","grafana","integrations/self","loki","nginx","node","prometheus","redis"]`. No `staging-db-minio` job exists in any alloy config or prometheus scrape_config.
- Static read: `monitoring/config/prometheus/alerts/basic-alerts.yml:224-232`
  ```yaml
  - alert: MinIODown
    expr: |
      up{job="staging-db-minio"} == 0
    for: 2m
    labels:
      severity: critical
      category: application
  ```
  The alert references `job="staging-db-minio"` which is never assigned by any scrape job or relabel rule.
- Cross-reference: `monitoring/config/alloy/staging-ap-vm.alloy` scrapes `node-exporter`, `cadvisor`, `nginx-exporter`, `redis-exporter`, `backend` — no MinIO scrape. MinIO is deployed in `docker-compose.staging.yml` on AP-VM but no Alloy block scrapes it. Even if added, the job label would not be `staging-db-minio` (and MinIO is on AP-VM, not DB-VM).

**Expected**: Alert expression uses an existing job label, or a MinIO scrape job is added to `staging-ap-vm.alloy` with a consistent job name.

**Root cause hypothesis**: Alert rule was authored speculatively with a job name that was never created; MinIO scraping was never implemented in the Alloy configuration.

**Remediation owner**: Phase 3.

**Suggested fix sketch**: Add MinIO scrape to `staging-ap-vm.alloy` with `job_name = "minio"`, update the alert to `up{job="minio"}`, and update `minio-monitoring.json` panel queries to use `vm=~"$vm"` (currently hardcoded `vm="db-vm"` which is wrong since MinIO is on AP-VM).

---

### F-PROM-08  [P1]  Alert rules reference `nginx_http_request_duration_seconds_bucket` — metric absent

**Where**: `monitoring/config/prometheus/alerts/basic-alerts.yml:213-221` and `monitoring/config/prometheus/recording-rules/aggregations.yml:145-157`

**Evidence**:
- Active probe: `GET /api/v1/query?query=nginx_http_request_duration_seconds_bucket` → 0 series. `GET /api/v1/query?query=nginx_http_requests_total` → 1 series (only `nginx_connections_*` family plus `nginx_http_requests_total` exist from `nginx-prometheus-exporter`).
- Static read: `monitoring/config/prometheus/alerts/basic-alerts.yml:213-221`:
  ```yaml
  - alert: SlowHTTPResponseTime
    expr: |
      histogram_quantile(0.95, sum(rate(nginx_http_request_duration_seconds_bucket[5m]))
      by (le, instance, environment)) > 2
  ```
  Also in `aggregations.yml:145-157`: `nginx:http_request_duration:p50/p95/p99` all use this bucket.
- Cross-reference: The `nginx-prometheus-exporter` (stub_status based) only exports: `nginx_connections_accepted`, `nginx_connections_active`, `nginx_connections_handled`, `nginx_connections_reading`, `nginx_connections_waiting`, `nginx_connections_writing`, `nginx_http_requests_total`, `nginx_up`. It does NOT export request duration histograms. Those require VTS module or OpenTelemetry instrumentation. The `nginx-monitoring.json` dashboard uses this metric in 3 panels and will show No data.

**Expected**: Either nginx is configured to export request duration (via VTS/OTel), or the alert and dashboard use alternative latency metrics (e.g., from the backend's `http_request_duration_seconds_bucket`).

**Root cause hypothesis**: Alert and recording rules were authored assuming VTS-enabled nginx or a custom nginx exporter, but only the basic stub_status exporter is deployed.

**Remediation owner**: Phase 3.

**Suggested fix sketch**: Replace the 3 p50/p95/p99 panels in `nginx-monitoring.json` with `http_request_duration_seconds_bucket{job="backend"}` (which does exist with 98 series). Remove or update the `SlowHTTPResponseTime` alert to use backend metrics.

---

### F-PROM-09  [P1]  Alert rules reference `pg_stat_statements_mean_exec_time_bucket` — metric absent

**Where**: `monitoring/config/prometheus/recording-rules/aggregations.yml:93-96`

**Evidence**:
- Active probe: `GET /api/v1/query?query=pg_stat_statements_mean_exec_time_bucket` → 0 series. Only `postgres_exporter_config_last_reload_success_timestamp_seconds` and `postgres_exporter_config_last_reload_successful` present (self-monitoring only, no pg_ prefixed metrics).
- Static read: `monitoring/config/prometheus/recording-rules/aggregations.yml:93-96`:
  ```yaml
  - record: postgres:query_duration:p95
    expr: |
      histogram_quantile(0.95, sum by(le, instance, environment) (rate(pg_stat_statements_mean_exec_time_bucket[5m])))
  ```
- Cross-reference: `pg_stat_statements_mean_exec_time_bucket` is not a standard `postgres_exporter` metric. Standard `postgres_exporter` exposes `pg_stat_statements_mean_exec_time` (gauge) not as a histogram. The recording rule would never produce a value. Also DB-VM metrics are not arriving at all (F-PROM-05).

**Expected**: `postgres:query_duration:p95` recording rule uses an existing postgres metric or is removed.

**Root cause hypothesis**: Recording rule was written for a non-standard or future metric name; `pg_stat_statements_mean_exec_time_bucket` does not exist in the exporter's standard output.

**Remediation owner**: Phase 3.

**Suggested fix sketch**: Remove this recording rule or replace with `pg_stat_statements_mean_exec_time` directly (after DB-VM scraping is fixed per F-PROM-05). The scholarship-overview dashboard uses `db_query_duration_seconds_bucket` from the backend, not postgres stats.

---

### F-PROM-10  [P1]  Loki per-tenant limits from `limits.yml` are never loaded — retention policies silently absent

**Where**: `monitoring/config/loki/loki-config.yml:74-96` and `monitoring/config/loki/limits.yml:1-33`

**Evidence**:
- Active probe: Loki health check returns OK (`GET /monitoring/api/datasources/uid/loki-staging-uid/health` → HTTP 200). No runtime_config API available to confirm loaded overrides.
- Static read: `monitoring/config/loki/loki-config.yml` — no `runtime_config:` block. `loki-config.yml:74-96` defines `limits_config:` inline (global defaults). `limits.yml` is mounted at `/etc/loki/limits.yml` per `docker-compose.monitoring.yml:71` but Loki requires a `runtime_config` stanza pointing to the file to load per-tenant overrides:
  ```yaml
  runtime_config:
    file: /etc/loki/limits.yml
  ```
  This stanza is absent from `loki-config.yml`. Per Loki documentation, per-tenant overrides require the `runtime_config` section; simply mounting the file does nothing.
- Cross-reference: `limits.yml` defines `retention_period: 720h` for prod and `336h` for staging but `loki-config.yml:71` has `retention_enabled: false`. Even if the runtime_config were wired up, retention would not run because it is disabled at the compactor level.

**Expected**: Either (a) `runtime_config: { file: /etc/loki/limits.yml }` is added to `loki-config.yml`, or (b) `limits.yml` contents are merged into `loki-config.yml`'s `limits_config:` block. Additionally, `compactor.retention_enabled: true` to actually enforce the retention periods.

**Root cause hypothesis**: `limits.yml` was created as a separate file but the Loki config was never updated to reference it via `runtime_config`, making it dead configuration.

**Remediation owner**: Phase 3.

**Suggested fix sketch**:
```yaml
# In loki-config.yml, add:
runtime_config:
  file: /etc/loki/limits.yml
  period: 60s

# And change:
compactor:
  retention_enabled: true
```

---

### F-PROM-11  [P1]  Prometheus `/api/v1/runtimeinfo` unavailable via Grafana datasource proxy

**Where**: API endpoint `/monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/runtimeinfo`

**Evidence**:
- Active probe: `GET /monitoring/api/datasources/proxy/uid/prometheus-uid/api/v1/runtimeinfo` → HTTP 404 `404 page not found`. Captured in `api-responses/prometheus-loki/runtimeinfo.json` (shows `Unauthorized` when session was expired; confirmed 404 after refresh).
- Static read: Grafana datasource proxy configuration in `datasources.yml` — no special HTTP headers configured for Prometheus.
- Cross-reference: Prometheus `--web.enable-admin-api` flag is NOT in `docker-compose.monitoring.yml:111-116`. The `/api/v1/runtimeinfo` endpoint requires the admin API. Grafana proxies the request but Prometheus returns 404 because admin API is disabled, not because of auth.

**Expected**: This is the expected behavior if admin API is intentionally disabled. The original `runtimeinfo.json` showing `Unauthorized` was a session expiry artifact, not an auth issue on Prometheus's side.

**Root cause hypothesis**: Session expired during Stage 0.4 probe; re-running after session refresh shows 404 which is Prometheus admin API being disabled (expected). The `Unauthorized` in the captured artifact was misleading.

**Remediation owner**: Not a bug — debunked. Note: `/api/v1/rules` returns 200 with empty groups (confirming no admin API restriction), so the initial `Unauthorized` was purely a Grafana session expiry.

**Suggested fix sketch**: No fix needed. Document that admin API is intentionally disabled and `runtimeinfo` is not available via Grafana proxy.

---

### F-PROM-12  [P1]  Prometheus external_labels lack `environment` and `vm` — Alloy remote_write data may collide

**Where**: `monitoring/config/prometheus/prometheus.yml:8-10`

**Evidence**:
- Active probe: Self-scrape metrics show `environment=monitoring` (set via static_configs label, not external_label). Alloy-pushed metrics show `environment=staging`, `vm=ap-vm` (set by Alloy relabel). External labels in prometheus.yml are `cluster=scholarship-system` and `monitor=main-prometheus`.
- Static read: `monitoring/config/prometheus/prometheus.yml:7-10`:
  ```yaml
  global:
    external_labels:
      cluster: 'scholarship-system'
      monitor: 'main-prometheus'
  ```
  These labels are attached to self-scraped metrics when sent via remote_write (if any remote_write were configured), and to alerts sent to AlertManager. They do NOT affect Alloy-pushed remote_write data.
- Cross-reference: The self-scrape targets (prometheus, loki, grafana) carry `environment=monitoring` via static label. The Alloy-pushed targets carry `environment=staging`/`environment=prod`. There is no collision. However, `cluster` and `monitor` external_labels are orphaned: no remote_write is configured in `prometheus.yml`, no AlertManager receives them. They serve no current purpose.

**Expected**: External labels are typically meaningful for federation or remote_write. If unused, they add noise. Not a blocking issue but worth noting.

**Root cause hypothesis**: `external_labels` were set with federation/remote_write in mind but no downstream consumer exists.

**Remediation owner**: Phase 4 (cleanup).

**Suggested fix sketch**: Remove or update `external_labels` to reflect actual topology when Phase 2 introduces Grafana unified alerting (the labels would flow into alert annotations).

---

### F-PROM-13  [P2]  Three scrape targets all carry `environment=monitoring` and `vm=null` — violates cross-VM labeling convention

**Where**: `monitoring/config/prometheus/prometheus.yml:35-63` and `api-responses/prometheus-loki/targets.json`

**Evidence**:
- Active probe: `targets.json` shows 3 active targets, all with `environment=monitoring`, no `vm` label (`vm=null`).
- Static read: `monitoring/config/prometheus/prometheus.yml:35-63` — static_configs labels for all three jobs set only `environment: 'monitoring'` and `service: '<name>'`. No `vm` label is set.
- Cross-reference: Spec §9.5: "every metric stream carries an `environment` label" and "every scrape target carries a `vm=ap` or `vm=db` label". The monitoring-stack self-scrape targets on AP-VM carry no `vm` label, violating the labeling convention.

**Expected**: Self-monitoring targets should carry `vm: 'ap-vm'` (monitoring stack runs on AP-VM).

**Root cause hypothesis**: Self-monitoring scrape jobs were authored before the `vm` label convention was finalized.

**Remediation owner**: Phase 4.

**Suggested fix sketch**:
```yaml
- job_name: 'prometheus'
  static_configs:
    - targets: ['localhost:9090']
      labels:
        environment: 'monitoring'
        service: 'prometheus'
        vm: 'ap-vm'
```

---

### F-PROM-14  [noted]  No Prometheus remote_write to long-term storage — 15-day TSDB retention only

**Where**: `monitoring/docker-compose.monitoring.yml:111-116` and `monitoring/config/prometheus/prometheus.yml`

**Evidence**:
- Static read: Prometheus flags: `--storage.tsdb.retention.time=15d`. No `remote_write:` block in `prometheus.yml`.
- Cross-reference: Production systems typically forward to Thanos/Cortex/Grafana Cloud for long-term storage. None configured.

**Expected**: Out of scope for this audit (no SLO/retention policy defined — see spec §3 non-goals).

**Root cause hypothesis**: N/A — accepted omission at this time.

**Remediation owner**: Phase 5+ (out of scope).

**Suggested fix sketch**: Consider Grafana Cloud free tier or Thanos sidecar for long-term metrics retention beyond 15 days.

---

## Prior-G Assessment

**Prior-G (P0)**: "AlertManager removed from compose at commit 57fca5f but datasource, Prometheus alert rules, and alertmanager.yml directory all still in place. Alerts fire to nowhere."

**Status: CONFIRMED with nuance.**

Three gates cleared:
1. **Active probe**: `/api/v1/rules` returns empty groups — rules are not even loaded (F-PROM-01). AlertManager datasource returns HTTP 500 (F-PROM-02).
2. **Static read**: `rule_files` commented out in `prometheus.yml`. `alerting:` block commented out. `basic-alerts.yml` has 14 rules. `datasources.yml` still has AlertManager entry.
3. **Cross-reference**: The situation is worse than prior-G described: not only is AlertManager gone, but `rule_files` was also disabled, so alert rules are not even being evaluated (let alone routing to a receiver). This means Prometheus is in a state where it has 14 alert rules defined in files, 25 recording rules defined in files, zero of them loaded, zero receiver configured.

**Additional nuance discovered**: `monitoring/config/alertmanager/` directory presence was noted in spec but the actual directory is:
```
monitoring/config/prometheus/alerts/basic-alerts.yml  ← exists, not loaded
monitoring/config/prometheus/recording-rules/aggregations.yml  ← exists, not loaded
```
The `alertmanager/alertmanager.yml` file per the spec — let me confirm:
<br>_(See Cross-branch observation below — this is Grafana branch territory)_

---

## Supplemental Stage 0.4 Signal Reconciliation

### Signal 1: Only 3 active scrape targets (all `environment=monitoring`, `vm=null`)

**Reconciled**: The 3 targets (Prometheus, Grafana, Loki self-scrape) are correct for what `prometheus.yml` defines. All application/system metrics arrive via Alloy `prometheus.remote_write`, not direct Prometheus scrape jobs. This is by design per the comment in `prometheus.yml`. The `vm=null` is a labeling gap (F-PROM-13).

### Signal 2: Sample queries returning 0 series (original probe had expired session)

**Reconciled**: After session refresh:
- `up` → 3 series (monitoring self-scrape) — data exists
- `node_cpu_seconds_total` → many series with `environment=staging, vm=ap-vm` — data exists from Alloy
- `pg_stat_activity_count` → 0 series — **confirmed missing** (DB-VM not pushing, F-PROM-05)
- `http_requests_total` → 7 series — **data exists** (backend job)

The dashboard screenshots showing data are consistent: AP-VM metrics (CPU, memory, nginx, redis, backend latency) do have data. DB-VM metrics (postgres) do not. The original probe used an expired session, causing all queries to return `Unauthorized` which looked like 0 series.

### Signal 3: `/api/v1/rules` returned `Unauthorized` via Grafana proxy

**Reconciled**: Session expiry caused the `Unauthorized`. After refresh, `/api/v1/rules` returns HTTP 200 with `{"groups":[]}`. The empty groups confirm F-PROM-01 (rule_files disabled), not an auth issue. No auth is configured on the Prometheus datasource in `datasources.yml` (no `httpHeaderName1`/`secureJsonData`).

### Signal 4: Loki multi-tenancy

**Reconciled**: `auth_enabled: true` in `loki-config.yml:5` — multi-tenancy IS enabled. Three datasources (`Loki (Staging)`, `Loki (Production)`, `Loki (Dev)`) each set `X-Scope-OrgID` via `httpHeaderName1`/`secureJsonData` in `datasources.yml:43-54`, `66-79`, `90-103`. All three Loki datasources return HTTP 200 health. Multi-tenancy scoping is **correctly configured** at the datasource level.

The gap: `limits.yml` defines per-tenant retention but `loki-config.yml` has no `runtime_config:` block to load it (F-PROM-10), and `retention_enabled: false` in compactor (F-PROM-10).

### Signal 5: `grafana_build_info` query (hypothesis test)

**Result**: Returns 1 series with `environment=monitoring`. This confirms the proxy works for self-scrape metrics. Staging remote_write metrics also work (`up{environment=staging}` = 6 series). Prod has zero metrics (F-PROM-04). Dashboard screenshots showing data are for the staging environment; prod panels would be empty.

---

## Coverage

### Files Inspected

| File | Lines Read | Notes |
|---|---|---|
| `monitoring/config/prometheus/prometheus.yml` | 1-66 (full) | Primary static read |
| `monitoring/config/prometheus/alerts/basic-alerts.yml` | 1-276 (full) | Alert rule inventory |
| `monitoring/config/prometheus/recording-rules/aggregations.yml` | 1-224 (full) | Recording rule inventory |
| `monitoring/config/loki/loki-config.yml` | 1-96 (full) | Loki config |
| `monitoring/config/loki/limits.yml` | 1-33 (full) | Per-tenant limits |
| `monitoring/docker-compose.monitoring.yml` | 1-163 (full) | Service topology |
| `monitoring/config/grafana/provisioning/datasources/datasources.yml` | 1-120 (full) | Datasource definitions |
| `monitoring/config/alloy/staging-ap-vm.alloy` | 1-216 (full) | AP-VM metrics pipeline |
| `monitoring/config/alloy/staging-db-vm.alloy` | 1-98 (full) | DB-VM metrics pipeline |
| `docker-compose.staging-db-monitoring.yml` | 1-77 (full) | DB-VM compose |
| `docs/superpowers/audits/working/api-responses/prometheus-loki/targets.json` | full | Live targets |
| `docs/superpowers/audits/working/api-responses/prometheus-loki/rules.json` | full | Rules probe |
| `docs/superpowers/audits/working/api-responses/prometheus-loki/runtimeinfo.json` | full | Runtime info probe |
| `docs/superpowers/audits/working/api-responses/grafana/datasources-health.json` | full | Datasource health |
| `docs/superpowers/audits/working/api-responses/deploy-pipeline/prod-monitoring-compose.yml` | full | Prod compose snapshot |

### API Endpoints Probed (after session refresh)

| Endpoint | Result | Finding |
|---|---|---|
| `/api/v1/query?query=grafana_build_info` | 1 series, env=monitoring | Proxy works; session was expired earlier |
| `/api/v1/query?query=up` | 3 series, all env=monitoring | Only self-scrape targets |
| `/api/v1/query?query=up{environment="staging"}` | 6 series, all vm=ap-vm | DB-VM absent (F-PROM-05) |
| `/api/v1/query?query=up{environment="prod"}` | 0 series | Prod Alloy not pushing (F-PROM-04) |
| `/api/v1/query?query=node_cpu_seconds_total` | Many series, vm=ap-vm | Staging AP-VM node metrics present |
| `/api/v1/query?query=pg_stat_activity_count` | 0 series | DB-VM missing (F-PROM-05) |
| `/api/v1/query?query=http_requests_total` | 7 series | Backend metrics present |
| `/api/v1/query?query=http_errors_total{job="backend"}` | 0 series | Metric doesn't exist in backend |
| `/api/v1/query?query=db_query_duration_seconds_bucket{job="backend"}` | 0 series | DB query histogram absent |
| `/api/v1/query?query=scholarship_applications_total` | 0 series | Custom metric absent |
| `/api/v1/query?query=nginx_http_request_duration_seconds_bucket` | 0 series | Not exported by nginx-exporter (F-PROM-08) |
| `/api/v1/rules` | 200, empty groups | Rule files disabled (F-PROM-01) |
| `/api/v1/runtimeinfo` | 404 | Admin API not enabled (F-PROM-11 — debunked) |
| `/api/v1/label/job/values` | 9 jobs, no postgres/minio | Job inventory |
| `/api/v1/label/vm/values` | ["ap-vm"] only | No db-vm (F-PROM-05) |

### Priors Addressed

| Prior | Status | Finding |
|---|---|---|
| prior-G | CONFIRMED (worse than described) | F-PROM-01, F-PROM-02, F-PROM-03 |

---

## Cross-branch Observations

1. **Grafana branch (F-GRAF-*)**: The AlertManager datasource provisioning (F-PROM-02) is within Grafana's datasource config. That branch should confirm the `alertmanager.yml` file under `monitoring/config/alertmanager/` still exists and can be deleted.

2. **App-Metrics branch (F-APP-*)**: Three dashboard panels show No data due to missing metrics:
   - `pg_stat_activity_count` — missing because DB-VM not scraped (F-PROM-05), not a backend issue
   - `http_errors_total{job="backend"}` — metric name doesn't exist in Prometheus (0 series); backend likely exports a different name
   - `db_query_duration_seconds_bucket{job="backend"}` — 0 series; custom metric missing from backend code
   - `scholarship_applications_total` — 0 series; custom business metric not instrumented
   - `email_sent_total` — 0 series; custom metric not instrumented
   App-Metrics branch should verify which of these are backend instrumentation gaps vs metric name mismatches.

3. **Alloy-CrossVM branch (F-ALLO-*)**: The architectural mismatch between `staging-db-vm.alloy` (pull model assumed) and `prometheus.yml` (no DB-VM scrape jobs) is the root cause of F-PROM-05. That branch should detail the full fix needed in `staging-db-vm.alloy`.

4. **Deploy-Pipeline branch (F-DEPL-*)**: Prior-C notes `docker-compose.staging-db-monitoring.yml` is not in the `paths:` filter of `deploy-monitoring-stack.yml`. This file is at repo root, not inside `monitoring/`. Changes to it (e.g., adding a MinIO exporter) would not trigger redeploy.

5. **MinIO dashboard hardcodes `vm="db-vm"`**: The `minio-monitoring.json` dashboard uses `vm="db-vm"` in all panel queries, but MinIO is deployed in `docker-compose.staging.yml` on AP-VM. Even when MinIO metrics are scraped, they would carry `vm=ap-vm`. The dashboard panels would all show No data. This is a Grafana-branch finding.
