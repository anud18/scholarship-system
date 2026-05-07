# Phase 3 Alert Redesign: 6 Deferred/Dropped Alerts

**Source spec**: `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-phase2-design.md` §6.2.1  
**Branch context**: `feat/monitoring-phase2`  
**Date drafted**: 2026-05-06

---

## Part A — Deferred Alerts (depend on DB-VM scrape pipeline fix)

These three alerts were valid in intent but the underlying series
(`pg_up`, `pg_stat_activity_count`, `pg_settings_max_connections`)
are not yet reaching Prometheus because the DB-VM Alloy agent has no
`prometheus.remote_write` block pointing to the monitoring stack
(findings F-PROM-05 / F-ALLO-06).  They must land in `rules-database.yml`
**after** that pipeline is fixed.

---

### A1. PostgreSQLDown

**Original expression**: `pg_up == 0`  
**Phase 3 entry condition**: Finding F-PROM-05 (DB-VM remote_write) and
F-ALLO-06 (postgres-exporter scrape target) must both be closed, confirmed
by the verification command below returning at least one series.

#### Updated Grafana unified alerting rule YAML

```yaml
# Append to monitoring/config/grafana/provisioning/alerting/rules-database.yml
# inside the existing groups[0].rules list

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

**Why env/vm filter was added**: the original bare `pg_up == 0` would
fire on any future postgres-exporter job (e.g., a dev container).
Scoping to `vm="db-vm"` makes the alert authoritative for the
production/staging DB-VM only, matching the label applied by the
`prometheus.relabel "add_labels"` block in `staging-db-vm.alloy` /
`prod-db-vm.alloy`.

#### Verification command

```promql
# Run in Prometheus /graph once DB-VM remote_write is live.
# Must return ≥1 series before enabling the alert.
pg_up{environment=~"staging|prod",vm="db-vm"}
```

CLI equivalent (requires Prometheus API access):
```bash
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=pg_up{environment=~"staging|prod",vm="db-vm"}' \
  | jq '.data.result | length'
# Expected: ≥ 1
```

---

### A2. PostgreSQLTooManyConnections

**Original expression**:
`sum(pg_stat_activity_count) by (instance, environment) > sum(pg_settings_max_connections) by (instance, environment) * 0.8`  
**Phase 3 entry condition**: Same as A1 — F-PROM-05 + F-ALLO-06 closed.

#### Updated Grafana unified alerting rule YAML

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
            is using more than 80% of max_connections. Current: {{ $value | humanize }}
        isPaused: false
```

#### Verification command

```promql
# Both series must exist before enabling the alert.
pg_stat_activity_count{environment=~"staging|prod",vm="db-vm"}
pg_settings_max_connections{environment=~"staging|prod",vm="db-vm"}
```

CLI:
```bash
for metric in pg_stat_activity_count pg_settings_max_connections; do
  echo -n "$metric: "
  curl -sG 'http://localhost:9090/api/v1/query' \
    --data-urlencode "query=${metric}{environment=~\"staging|prod\",vm=\"db-vm\"}" \
    | jq '.data.result | length'
done
# Expected: each ≥ 1
```

---

### A3. PostgreSQLHighConnections

**Original expression**: same ratio at `0.9` threshold  
**Phase 3 entry condition**: Same as A1 — F-PROM-05 + F-ALLO-06 closed.

#### Updated Grafana unified alerting rule YAML

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

#### Verification command

Same as A2 — both `pg_stat_activity_count` and `pg_settings_max_connections`
must be present.  Run the A2 CLI snippet; if both return ≥ 1, A2 and A3 can
be enabled simultaneously.

---

## Part B — Dropped Alerts (redesigned on available metrics)

---

### B4. HighHTTPErrorRate (redesigned)

**Root cause drop**: `nginx_http_requests_total` in the nginx-prometheus-exporter
(version in use) does not expose a `status` label — it only surfaces the
cumulative `nginx_http_requests_total` counter without breakdown by status
code (finding F-GRAF-08).

**Replacement metric**: `http_requests_total{job="backend"}` with `status`
label confirmed live (Phase 1 audit Branch B: 7 series).  Backend FastAPI
already exposes this via its `/metrics` Prometheus endpoint, scraped by
the `prometheus.scrape "backend"` block in both AP-VM Alloy configs.

#### New Grafana unified alerting rule YAML

```yaml
# File: monitoring/config/grafana/provisioning/alerting/rules-application.yml
# (create this file; append later rules B5/B6 into it as well)

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

#### Verification command

```promql
# Confirm the two series that feed the ratio both exist.
http_requests_total{job="backend",status=~"5.."}
http_requests_total{job="backend"}
```

CLI:
```bash
for selector in 'http_requests_total{job="backend",status=~"5.."}' \
                'http_requests_total{job="backend"}'; do
  echo -n "$selector: "
  curl -sG 'http://localhost:9090/api/v1/query' \
    --data-urlencode "query=${selector}" \
    | jq '.data.result | length'
done
# Expected: ≥ 7 for total (confirmed), ≥ 0 for 5xx (may be 0 if no errors now)
```

---

### B5. SlowHTTPResponseTime (redesigned)

**Root cause drop**: `nginx_http_request_duration_seconds_bucket` does not
exist in the nginx-prometheus-exporter (finding F-PROM-08).

**Replacement metric**: `http_request_duration_seconds_bucket{job="backend"}`
— confirmed 98 series live in Phase 1 audit.  Two severity tiers added
(p95 > 2 s warning, p95 > 5 s critical) to improve signal fidelity.

#### New Grafana unified alerting rule YAML (two rules)

```yaml
      # --- Warning tier: p95 > 2s ---
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

      # --- Critical tier: p95 > 5s ---
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

#### Verification command

```promql
# Confirm histogram series are present (expect 98 series per Phase 1 audit).
http_request_duration_seconds_bucket{job="backend"}
```

CLI:
```bash
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=http_request_duration_seconds_bucket{job="backend"}' \
  | jq '.data.result | length'
# Expected: ~98
```

---

### B6. MinIODown (redesigned — two-part)

**Root cause drop**: `job="staging-db-minio"` was never a real scrape target
(finding F-PROM-07).  MinIO is deployed on AP-VM (alongside backend/frontend),
not DB-VM.  Its metrics endpoint is `/minio/v2/metrics/cluster` on port 9000.

**Fix is two-part:**
1. Add a `prometheus.scrape "minio"` block to both AP-VM Alloy configs.
2. Alert on `up{job="minio"}` from that new job.

#### Part 1 — Alloy patch (both AP-VM configs)

Add the following block **after** the existing `prometheus.scrape "backend"`
block in each file:

**`monitoring/config/alloy/staging-ap-vm.alloy`** (and identically for
**`prod-ap-vm.alloy`**, changing `environment = "prod"` in the relabel block):

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

  // MinIO metrics endpoint requires no auth by default in dev;
  // production deployments may need bearer_token or basic_auth here.
}
```

No change to the `prometheus.relabel "add_labels"` or
`prometheus.remote_write "default"` blocks — the new scrape job flows
through the existing pipeline automatically.

#### Part 2 — Alert YAML

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

**Why `vm="ap-vm"` filter**: Prevents false fires if a future DB-VM MinIO
target is ever added.  The AP-VM Alloy relabel block stamps `vm="ap-vm"` on
all scraped metrics.

#### Verification command

```promql
# After Alloy is reloaded with the new scrape block.
up{job="minio",vm="ap-vm"}
```

CLI:
```bash
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=up{job="minio",vm="ap-vm"}' \
  | jq '.data.result'
# Expected: [{"metric":{"job":"minio","vm":"ap-vm",...},"value":[...,"1"]}]
```

---

## GitHub Issue Bodies (ready to paste)

---

### Issue 1 — PostgreSQLDown

**Title**: `[Phase 3] Restore PostgreSQLDown after DB-VM scrape pipeline fix (F-PROM-05 / F-ALLO-06)`

```markdown
## What it does

Alerts within 1 minute when `pg_up` drops to 0 on the DB-VM, indicating
PostgreSQL is unreachable.  This alert existed in the original
`basic-alerts.yml` and was deliberately deferred in Phase 2 because the
underlying `pg_up` series never reaches Prometheus (the DB-VM Alloy agent
has no `prometheus.remote_write` block — findings F-PROM-05 / F-ALLO-06).

## Phase 3 dependencies

- [ ] F-PROM-05: Add `prometheus.remote_write` to `staging-db-vm.alloy`
      and `prod-db-vm.alloy` so DB-VM metrics reach the monitoring stack.
- [ ] F-ALLO-06: Confirm `prometheus.scrape "postgres_exporter"` target
      (`postgres-exporter:9187`) is reachable from the DB-VM Alloy agent.
- [ ] Verification: `pg_up{environment=~"staging|prod",vm="db-vm"}` returns
      ≥ 1 series in Prometheus.

## YAML to append to `rules-database.yml`

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

**Title**: `[Phase 3] Restore PostgreSQLTooManyConnections after DB-VM scrape pipeline fix (F-PROM-05 / F-ALLO-06)`

```markdown
## What it does

Fires a **warning** when `pg_stat_activity_count` exceeds 80% of
`pg_settings_max_connections` for 5 minutes, allowing operators to intervene
before connection exhaustion.  Deferred from Phase 2 due to missing DB-VM
remote_write pipeline.

## Phase 3 dependencies

- [ ] F-PROM-05 + F-ALLO-06 closed (same as PostgreSQLDown issue).
- [ ] Verification: both `pg_stat_activity_count` and
      `pg_settings_max_connections` return ≥ 1 series with
      `{environment=~"staging|prod",vm="db-vm"}`.

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
```
```

---

### Issue 3 — PostgreSQLHighConnections

**Title**: `[Phase 3] Restore PostgreSQLHighConnections after DB-VM scrape pipeline fix (F-PROM-05 / F-ALLO-06)`

```markdown
## What it does

Fires **critical** when connections exceed 90% of `max_connections` for
2 minutes — the escalated tier above the 80% warning.  Deferred from Phase 2.

## Phase 3 dependencies

Same as issue 2 (PostgreSQLTooManyConnections).  Both alerts can be
merged into a single PR once the DB-VM pipeline is live.

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

Same bash snippet as issue 2.
```

---

### Issue 4 — HighHTTPErrorRate

**Title**: `[Phase 3] Restore HighHTTPErrorRate using backend metrics (replaces dropped nginx-based alert)`

```markdown
## What it does

Fires **warning** when more than 5% of backend HTTP requests return 5xx
responses over a 5-minute window.  The original alert used
`nginx_http_requests_total{status=~"5.."}`, but nginx-prometheus-exporter
does not expose a `status` label (finding F-GRAF-08), so that alert was
dropped in Phase 2.

This redesign uses `http_requests_total{job="backend"}` which is confirmed
live (7 series, Phase 1 audit Branch B).  Coverage is equivalent — every
request reaching nginx ultimately hits the backend.

## Phase 3 dependencies

- [x] `http_requests_total{job="backend"}` already live — no prerequisite
      infrastructure work required.
- [ ] Create `monitoring/config/grafana/provisioning/alerting/rules-application.yml`.

## Config diff

**New file**: `monitoring/config/grafana/provisioning/alerting/rules-application.yml`

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

**Title**: `[Phase 3] Restore SlowHTTPResponseTime using backend histogram (replaces dropped nginx-based alert)`

```markdown
## What it does

Alerts on high p95 backend response latency.  Original alert used
`nginx_http_request_duration_seconds_bucket` which does not exist in the
nginx-prometheus-exporter (finding F-PROM-08).

Redesigned to use `http_request_duration_seconds_bucket{job="backend"}`
(98 series confirmed live in Phase 1 audit).  Two severity tiers are added:
- **Warning**: p95 > 2 s for 5 minutes
- **Critical**: p95 > 5 s for 2 minutes

## Phase 3 dependencies

- [x] `http_request_duration_seconds_bucket{job="backend"}` already live.
- [ ] Add two rules to `rules-application.yml` (same file as issue 4).

## Config diff

Append inside the `rules-application.yml` `rules:` list:

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

**Title**: `[Phase 3] Restore MinIODown by adding MinIO scrape target to AP-VM Alloy configs`

```markdown
## What it does

Alerts when MinIO object storage is unreachable.  The original alert used
`up{job="staging-db-minio"}` which referenced a scrape job that never existed
(finding F-PROM-07).  Additionally, MinIO runs on AP-VM, not DB-VM, so the
target location was also wrong.

This redesign:
1. Adds a `prometheus.scrape "minio"` block to both AP-VM Alloy configs
   targeting MinIO's `/minio/v2/metrics/cluster` endpoint on port 9000.
2. Alerts on the resulting `up{job="minio",vm="ap-vm"}` series.

## Phase 3 dependencies

- [ ] No upstream fix required — this is a self-contained addition.
- [ ] Confirm MinIO container name/DNS is `minio` on both AP-VMs (check
      `docker-compose.yml` service names).
- [ ] If MinIO requires auth for metrics, add `bearer_token` or
      `basic_auth` to the scrape block.

## Config diff

**`monitoring/config/alloy/staging-ap-vm.alloy`** — add after
`prometheus.scrape "backend"` block:

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

**`monitoring/config/alloy/prod-ap-vm.alloy`** — identical block
(environment label is applied downstream by the relabel block, not here).

**`monitoring/config/grafana/provisioning/alerting/rules-application.yml`**
— append inside `rules:` list:

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
            {{ $labels.vm }}) is not responding.
            File upload/download will fail.
        isPaused: false
```

## Verification

After reloading Alloy on AP-VM:

```bash
curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=up{job="minio",vm="ap-vm"}' \
  | jq '.data.result'
# Expected: value "1" for each environment (staging, prod)
```

Direct MinIO metrics probe (from AP-VM host):
```bash
curl -s http://localhost:9000/minio/v2/metrics/cluster | grep '^minio_' | head -5
# Expected: minio_* metrics output
```
```
