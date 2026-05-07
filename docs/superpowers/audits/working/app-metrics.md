# Branch D — Application Metric / Log Interface Audit

**Auditor**: Claude (backend agent)
**Date**: 2026-05-06
**Branch**: `audit/monitoring-stack-phase1`
**Scope**: Task 1.D — `backend/app/core/metrics.py`, `backend/app/middleware/metrics_middleware.py`, `backend/app/main.py`, backend log configuration, PromQL dashboard cross-reference.
**Spec ref**: `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md` §5.1 (B subsection)

Supplemental artifact: `docs/superpowers/audits/working/api-responses/app-metrics/metric-inventory.md`

---

## Findings

### F-APP-01  [P1]  Backend metrics reach zero Prometheus series — Alloy is running but pipeline delivers nothing

**Where**: `monitoring/config/alloy/staging-ap-vm.alloy:115-135` (backend scrape block) and `monitoring/config/prometheus/prometheus.yml` (scrape_configs).

**Evidence**:
- Active probe: `docs/superpowers/audits/working/api-responses/prometheus-loki/targets.json` — Prometheus `/api/v1/targets` returns exactly 3 active targets: `job="grafana"`, `job="loki"`, `job="prometheus"`. All carry `environment="monitoring"`. No `job="backend"` target and no `environment="staging"` target exist. This confirms 0 backend metric series in Prometheus.
- Static read: `monitoring/config/prometheus/prometheus.yml:26-56` — Prometheus `scrape_configs` contains only `prometheus`, `loki`, and `grafana` self-monitoring jobs. There is no `backend` job in Prometheus itself. Backend metrics are supposed to arrive via Alloy remote_write (`prometheus.yml` comment: "All application/system metrics are collected by Grafana Alloy and sent to Prometheus via remote_write").
- Cross-reference: `monitoring/config/alloy/staging-ap-vm.alloy:115-135` defines `prometheus.scrape "backend"` targeting `backend:8000` with `job_name = "backend"`. The `prometheus.relabel.add_labels` block then injects `environment="staging"` and `vm="ap-vm"`. Those labeled metrics are sent via `prometheus.remote_write.default` to `http://monitoring_prometheus:9090/api/v1/write`. If this pipeline worked, `job="backend"` series would appear in targets.json. They do not — the Alloy remote_write is either failing silently or Alloy is not running at all. (Branch C covers Alloy deployment; this finding documents the *consequence* for backend metrics.)

**Expected**: Prometheus should show a `job="backend"` target (discovered via remote_write) with `environment="staging"` and `vm="ap-vm"` labels. The three overview-dashboard panels that filter on `job="backend"` would then receive data.

**Root cause hypothesis**: Alloy on the staging AP-VM is either not running or its remote_write to `monitoring_prometheus:9090` is failing, so no metrics from the backend scrape job ever enter Prometheus TSDB.

**Remediation owner**: Phase 3.

**Suggested fix sketch**:
```bash
# On staging AP-VM, verify Alloy is running:
docker ps | grep alloy

# Check Alloy remote_write health:
curl -s http://localhost:12345/metrics | grep remote_write

# If Alloy is down, restart:
docker compose -f docker-compose.staging.yml restart alloy
```

---

### F-APP-02  [P1]  "Backend Error Rate (%)" panel — metric name exists but zero time-series due to F-APP-01, masked by `or 0`

**Where**: `docs/superpowers/audits/working/api-responses/grafana/dashboard-scholarship-overview.json` (panel "Backend Error Rate (%)"), `backend/app/core/metrics.py:118-122`, `backend/app/middleware/metrics_middleware.py:84-87, 115-118`.

**Evidence**:
- Active probe: Prometheus `targets.json` shows 0 series for any `job="backend"` label selector. Running `http_errors_total` against Prometheus would return 0 series (confirmed by Stage 0.4 context: "Prometheus returned 0 series" for `http_requests_total`).
- Static read: `backend/app/core/metrics.py:118-122` — `http_errors_total` is defined as `Counter("http_errors_total", ..., ["status_code", "endpoint"])`. `backend/app/middleware/metrics_middleware.py:84-87, 115-118` — counter is incremented on unhandled exceptions (status 500) and on `status_code >= 400` responses. The metric exists and IS instrumented.
- Cross-reference: Dashboard query is `((sum(rate(http_errors_total{..., job="backend"}[5m])) / sum(rate(http_requests_total{..., job="backend"}[5m]))) * 100) or 0`. The `job="backend"` label is applied by Alloy `prometheus.relabel`, not by the backend code. Since Alloy is not delivering metrics (F-APP-01), the query returns no series. The `or 0` clause causes Grafana to render a flat zero line rather than "No data", **hiding the scrape failure** — this is a P2 dashboard honesty issue (see F-APP-07).

**Expected**: When Alloy pipeline is fixed (F-APP-01), `http_errors_total{job="backend"}` should populate and this panel should show real error rate data. The metric implementation is correct; the pipeline is broken.

**Root cause hypothesis**: The metric is correctly defined and instrumented; the No-data root cause is the absent Alloy remote_write pipeline (F-APP-01), compounded by `or 0` masking the failure.

**Remediation owner**: Phase 3 (pipeline fix); Phase 4 (remove `or 0` masking).

**Suggested fix sketch**: Fix F-APP-01. After pipeline is healthy, optionally replace `or 0` with a proper `absent()` alert instead, per spec §9 principle 3.

---

### F-APP-03  [P1]  "PostgreSQL Active Connections" panel — `pg_stat_activity_count` is a postgres-exporter metric; postgres-exporter target is absent from Prometheus

**Where**: `docs/superpowers/audits/working/api-responses/grafana/dashboard-scholarship-overview.json` (panel "PostgreSQL Active Connections"), `docker-compose.staging-db-monitoring.yml:50-64`, `monitoring/config/alloy/staging-db-vm.alloy`.

**Evidence**:
- Active probe: `docs/superpowers/audits/working/api-responses/prometheus-loki/targets.json` — 0 targets exist with `job` related to postgres. No `pg_stat_activity_count` series in Prometheus. Stage 0.4 context confirms 0 series for backend metrics; same applies to DB-VM exporters.
- Static read: `docker-compose.staging-db-monitoring.yml:50-64` — `postgres-exporter` service is defined on port 9187. `monitoring/config/alloy/staging-db-vm.alloy` (METRICS PIPELINE section comments, line ~75-86) states: "Metrics are exposed via exporters and scraped directly by Prometheus on AP-VM." However, `monitoring/config/prometheus/prometheus.yml` has NO `postgres-exporter` scrape job — Prometheus is not configured to reach DB-VM's port 9187. The DB-VM Alloy config has no `prometheus.scrape` block for postgres-exporter and no `prometheus.remote_write` block — it relies on AP-VM Prometheus to pull directly.
- Cross-reference: The DB-VM Alloy comment says "Prometheus on AP-VM will add environment/vm labels during relabel_configs in its prometheus.yml" — but `prometheus.yml` has no such relabel_configs or scrape job for `postgres-exporter`. The scrape job is entirely missing from Prometheus config, and the DB-VM Alloy has no remote_write fallback. This is a configuration gap independent of F-APP-01.

**Expected**: Either (a) AP-VM Prometheus has a `postgres-exporter` scrape job in `prometheus.yml` targeting DB-VM:9187 with `relabel_configs` adding `environment` and `vm="db-vm"` labels, or (b) DB-VM Alloy has a `prometheus.scrape "postgres_exporter"` block with `prometheus.remote_write` to AP-VM Prometheus.

**Root cause hypothesis**: The DB-VM Alloy config intentionally omits remote_write (pull mode), but the AP-VM Prometheus `prometheus.yml` was never updated with the matching cross-VM scrape job for postgres-exporter, creating a complete gap in the metric pipeline.

**Remediation owner**: Phase 3.

**Suggested fix sketch**:
```yaml
# In monitoring/config/prometheus/prometheus.yml, add:
- job_name: 'postgres-exporter'
  static_configs:
    - targets:
        - '${STAGING_DB_HOST}:9187'
  relabel_configs:
    - target_label: environment
      replacement: staging
    - target_label: vm
      replacement: db-vm
```
Or alternatively, add a `prometheus.scrape` + `prometheus.remote_write` block to `staging-db-vm.alloy`.

---

### F-APP-04  [P1]  "Database Query p95 (ms)" panel — `db_query_duration_seconds` is defined but never instrumented

**Where**: `backend/app/core/metrics.py:67-72`, `docs/superpowers/audits/working/api-responses/grafana/dashboard-scholarship-overview.json` (panel "Database Query p95 (ms)").

**Evidence**:
- Active probe: Prometheus `targets.json` confirms 0 backend series (F-APP-01). Even if the Alloy pipeline were fixed, the histogram would have 0 observations because no code calls `.observe()` on it.
- Static read: `backend/app/core/metrics.py:67-72` — `db_query_duration_seconds = Histogram("db_query_duration_seconds", ..., ["operation"])` is defined. Exhaustive `grep` across all `backend/app/**/*.py` files for `db_query_duration_seconds` finds zero matches outside `core/metrics.py` and `__all__`. The metric is never imported or called anywhere in the application code.
- Cross-reference: Dashboard query is `histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket{..., job="backend"}[5m])) by (le)) * 1000`. Even after fixing F-APP-01, this will return `NaN`/No-data because the histogram has zero observations (no `_bucket` series will be non-zero). Two separate bugs combine: pipeline gap (F-APP-01) and missing instrumentation.

**Expected**: Database queries (SQLAlchemy session operations) should call `db_query_duration_seconds.labels(operation="select").observe(duration)` around each query execution. This requires either a SQLAlchemy event listener or explicit instrumentation in the repository/service layer.

**Root cause hypothesis**: `db_query_duration_seconds` was added to `core/metrics.py` as a placeholder but no developer wired it into the SQLAlchemy layer, so it permanently reports empty.

**Remediation owner**: Phase 3.

**Suggested fix sketch**:
```python
# In backend/app/db/session.py or a SQLAlchemy event listener:
from sqlalchemy import event
from app.core.metrics import db_query_duration_seconds
import time

@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, params, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())

@event.listens_for(engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, params, context, executemany):
    total = time.perf_counter() - conn.info["query_start_time"].pop(-1)
    operation = statement.strip().split()[0].lower()
    db_query_duration_seconds.labels(operation=operation).observe(total)
```

---

### F-APP-05  [P2]  `/metrics` endpoint has no auth guard — anonymous access is by design but undocumented, and the endpoint is not blocked by nginx from the public internet

**Where**: `backend/app/main.py:354-378`, `nginx/nginx.staging.conf`.

**Evidence**:
- Active probe: Static analysis only — the staging backend is not directly reachable externally (nginx proxies). No curl probe possible from audit machine. However, `docker-compose.staging.yml:24` shows `backend` exposes port `8000:8000` on the host, meaning `http://<host>:8000/metrics` is publicly reachable if the host firewall allows it.
- Static read: `backend/app/main.py:354-378` — `@app.get("/metrics")` has no `Depends(get_current_user)` or any other auth dependency. The function checks `settings.enable_metrics` only. No OAuth2 bearer scheme, no rate limiting applied. `nginx/nginx.staging.conf` has no `location /metrics` block, meaning nginx does not proxy or block this path — the backend's host-exposed port 8000 is the only access vector.
- Cross-reference: Alloy scrapes `backend:8000/metrics` inside the Docker network anonymously (correct for a scraper). But because `backend` also publishes port 8000 to the host, any external client with network access to the host IP on port 8000 can read metric data without authentication. Grafana Alloy uses anonymous scrape — this is correct and expected. The finding is that the same anonymity extends to the public internet via the exposed host port.

**Expected**: `/metrics` should be accessible anonymously only from within the Docker network (Alloy). The host port 8000 should either be removed (use `expose:` not `ports:`) or an nginx `location /metrics { deny all; }` block should block external access.

**Root cause hypothesis**: During development the backend exposes port 8000 for debugging convenience; this was not tightened for staging, leaving the metrics endpoint reachable without authentication from the host network.

**Remediation owner**: Phase 4.

**Suggested fix sketch**:
```yaml
# docker-compose.staging.yml — change backend:
expose:
  - "8000"  # Internal only; remove "8000:8000" host binding
```
Or in `nginx/nginx.staging.conf`:
```nginx
location = /metrics {
    deny all;
}
```

---

### F-APP-06  [P2]  Thirteen metrics defined in `core/metrics.py` are never instrumented — dead declarations

**Where**: `backend/app/core/metrics.py:74-134`.

**Evidence**:
- Active probe: N/A (static analysis finding).
- Static read: `backend/app/core/metrics.py` defines: `db_connections_total`, `scholarship_applications_total`, `scholarship_reviews_total`, `email_sent_total`, `file_uploads_total`, `payment_rosters_total`, `auth_attempts_total`, `validation_errors_total`. Comprehensive `grep -rn` across all `backend/app/**/*.py` (excluding `metrics.py` itself) finds zero callsites for `.inc()`, `.observe()`, or `.labels()` on any of these eight counters/histograms. Additionally `db_query_duration_seconds` (histogram) has zero `.observe()` callsites (covered in F-APP-04).
- Cross-reference: The dashboard queries `scholarship_applications_total` (Applications Submitted/Approved panels) and `email_sent_total` (Emails Delivered panel) in `dashboard-scholarship-overview.json`. These panels will show 0 even after F-APP-01 is fixed, because the counters are never incremented in application code.

**Expected**: Each metric should have at least one callsite. Either the metric should be instrumented in the relevant service layer, or it should be removed from `core/metrics.py` to avoid the illusion of instrumentation.

**Root cause hypothesis**: Metrics were declared speculatively as a "we'll instrument this later" placeholder but the instrumentation work was never completed.

**Remediation owner**: Phase 3 (for dashboard-affecting metrics: `scholarship_applications_total`, `email_sent_total`, `db_query_duration_seconds`); Phase 4 (remove or instrument remaining dead metrics).

**Suggested fix sketch**: For `scholarship_applications_total`, add to `backend/app/services/application_service.py` on submit:
```python
from app.core.metrics import scholarship_applications_total
scholarship_applications_total.labels(status="submitted").inc()
```
Similarly for `email_sent_total` in `backend/app/tasks/email_processor.py`.

---

### F-APP-07  [P2]  `or 0` in "Backend Error Rate (%)" panel masks No-data as a flat zero line

**Where**: `docs/superpowers/audits/working/api-responses/grafana/dashboard-scholarship-overview.json` (panel "Backend Error Rate (%)").

**Evidence**:
- Active probe: Prometheus `targets.json` confirms 0 backend metric series. The panel renders (no "No data" badge visible in screenshots) because `or 0` forces a scalar 0 when the vector is empty.
- Static read: Panel `targets[0].expr` = `((sum(rate(http_errors_total{..., job="backend"}[5m])) / sum(rate(http_requests_total{..., job="backend"}[5m]))) * 100) or 0`. The `or 0` clause is the mechanism.
- Cross-reference: Spec §9 principle 3 explicitly states "Dashboards must not append `or 0` to disguise No-data as zero." This pattern makes it impossible for an operator to distinguish "error rate is genuinely 0%" from "backend metrics are not reaching Prometheus at all."

**Expected**: Remove `or 0` so Grafana shows the "No data" sentinel, making pipeline failures visible. If a zero-floor is needed for display, use `or vector(0)` only after confirming the scrape target is UP.

**Root cause hypothesis**: `or 0` was added to prevent the panel from showing "No data" during early setup, but was never removed once instrumentation was live.

**Remediation owner**: Phase 4.

**Suggested fix sketch**: Replace the expr with:
```promql
((sum(rate(http_errors_total{environment="$environment", vm=~"$vm", job="backend"}[5m])) /
  sum(rate(http_requests_total{environment="$environment", vm=~"$vm", job="backend"}[5m]))) * 100)
```

---

### F-APP-08  [noted]  Log format is conditionally JSON — Loki parsing of `level` and `request_id` depends on `LOG_FORMAT=json` env var being set in staging

**Where**: `backend/app/main.py:46-64`, `backend/app/core/config.py:95`.

**Evidence**:
- Active probe: N/A — Loki query against staging backend container logs not performed in this audit pass.
- Static read: `backend/app/main.py:46-64` — A `JsonFormatter` class is defined that emits `{"timestamp": ..., "level": ..., "name": ..., "message": ...}`. It is applied to the root logger only if `settings.log_format == "json"` (line 61). `backend/app/core/config.py:95` defaults `log_format: str = "json"`, so JSON mode is ON by default. However, the formatter emits field name `level` (not `severity`) — this must match the Alloy `loki.process` pipeline's label extraction configuration. There is no `request_id` field in the `JsonFormatter` output (only the exception handlers include `trace_id` in JSON response bodies, not in log records).
- Cross-reference: `monitoring/config/alloy/staging-ap-vm.alloy` — The `loki.process "add_labels"` block only parses Nginx JSON logs (inside a `stage.match` selector). There is no JSON parsing stage for backend container logs. This means backend log lines arrive at Loki as raw strings, and Loki cannot extract `level` or `request_id` as labels. The "Application Logs" dashboard filter `{container=~".*backend.*"} |~ "ERROR"` relies on text matching rather than label-based filtering, which is less efficient.

**Expected**: The Alloy `loki.process "add_labels"` pipeline should include a `stage.match` for backend containers that runs `stage.json` to extract `level` from the JSON log output, enabling label-based Loki queries.

**Root cause hypothesis**: The backend JSON log format and the Alloy log pipeline were developed independently without coordination on field names and parsing stages.

**Remediation owner**: Phase 3 (Alloy pipeline fix) or Phase 4 (if Loki queries work adequately via text search).

**Suggested fix sketch**:
```alloy
stage.match {
  selector = "{container=~\".*backend.*\"}"
  stage.json {
    expressions = {
      level = "level",
    }
  }
  stage.labels {
    values = {
      level = "",
    }
  }
}
```

---

## Coverage Summary

| Dimension | Finding(s) | Verdict |
|---|---|---|
| "Backend Error Rate (%)" No-data panel | F-APP-01, F-APP-02 | Root cause: Alloy pipeline missing (F-APP-01); metric IS defined and instrumented; `or 0` masks failure (F-APP-07) |
| "PostgreSQL Active Connections" No-data panel | F-APP-03 | Root cause: postgres-exporter scrape job missing from both Prometheus and DB-VM Alloy |
| "Database Query p95 (ms)" No-data panel | F-APP-01, F-APP-04 | Two bugs: Alloy pipeline gap (F-APP-01) + metric never instrumented (F-APP-04) |
| `/metrics` anonymous reachability | F-APP-05 | No auth guard in code (correct for scraper); host port 8000 exposed publicly (risk) |
| EXCLUDED_PATHS in metrics_middleware | (no finding) | `/metrics` exclusion is correct; it prevents recursive metric-scrape metrics. No dashboard-relevant paths are excluded. |
| Log structure | F-APP-08 | JSON logs emitted conditionally; Alloy pipeline does not parse backend JSON → `level` label not extracted in Loki |
| Metric inventory cross-reference | F-APP-06 | 9 metrics defined but never instrumented; 3 of these are queried by dashboards |

## Per-Panel Verdict (Three No-data Panels)

1. **Backend Error Rate (%)**: `http_errors_total` and `http_requests_total` ARE defined in `core/metrics.py` and ARE instrumented by `metrics_middleware.py`. No-data is caused entirely by the Alloy remote_write pipeline not delivering metrics to Prometheus (F-APP-01). The `or 0` clause hides this (F-APP-07). Fix: repair Alloy pipeline.

2. **PostgreSQL Active Connections**: `pg_stat_activity_count` is correctly absent from `core/metrics.py` — it is a `postgres-exporter` metric. No-data is caused by the postgres-exporter scrape job being missing from both Prometheus `prometheus.yml` and the DB-VM Alloy config (F-APP-03). Fix: add scrape job in Prometheus or add remote_write to DB-VM Alloy.

3. **Database Query p95 (ms)**: `db_query_duration_seconds` IS defined in `core/metrics.py` but is never instrumented — no `.observe()` call exists anywhere in the codebase (F-APP-04). Even after fixing F-APP-01, this panel will remain No-data. Fix requires both: (a) Alloy pipeline repair, and (b) adding SQLAlchemy event listeners to call `.observe()`.

## Cross-Branch Observations

- **Branch C (Alloy/CrossVM)**: F-APP-01 is a consequence of whatever root cause Branch C surfaces about Alloy deployment or remote_write connectivity. Branch C should own the Alloy fix; this branch documents the application-side impact.
- **Branch B (Prometheus/Loki)**: F-APP-03 may overlap with Branch B's finding about the postgres-exporter scrape gap. The missing scrape job in `prometheus.yml` is a Prometheus configuration finding that Branch B should also cover.
- **Branch A (Grafana)**: F-APP-07 (`or 0` masking) is a dashboard content finding that Branch A may independently identify via screenshot inspection. Coordinate numbering in synthesis.

---

*Severity counts: P0=0, P1=4 (F-APP-01 through F-APP-04), P2=3 (F-APP-05, F-APP-06, F-APP-07), noted=1 (F-APP-08)*
