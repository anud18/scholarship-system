#!/usr/bin/env bash
# scripts/phase3/open-deferred-alert-issues.sh
#
# Opens the 6 Phase 3 deferred/dropped alert tracking issues on GitHub.
# Idempotent: skips any issue whose title already exists as an open issue
# with the phase3 label.
#
# Usage:
#   ./scripts/phase3/open-deferred-alert-issues.sh [--dry-run] [--yes] [--repo OWNER/REPO]

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
REPO="anud18/scholarship-system"
DRY_RUN=false
YES=false

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --yes)     YES=true;     shift ;;
    --repo)    REPO="$2";    shift 2 ;;
    --repo=*)  REPO="${1#*=}"; shift ;;
    -h|--help)
      grep '^#' "$0" | head -12 | sed 's/^# \?//'
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── Counters ─────────────────────────────────────────────────────────────────
CREATED=0
SKIPPED=0
FAILED=0

# ── Helper: check if issue already exists ────────────────────────────────────
issue_exists() {
  local title="$1"
  # Search by label + title fragment; gh returns JSON array
  local result
  result=$(gh issue list \
    --repo "$REPO" \
    --label "phase3" \
    --state open \
    --search "\"$title\"" \
    --json number,title \
    --jq '.[]' 2>/dev/null || true)
  if [[ -n "$result" ]]; then
    # Extract the issue number from the first match
    echo "$result" | head -1 | grep -o '"number":[0-9]*' | grep -o '[0-9]*'
    return 0
  fi
  return 1
}

# ── Helper: create one issue ──────────────────────────────────────────────────
create_issue() {
  local idx="$1"
  local title="$2"
  local labels="$3"
  local body="$4"

  echo ""
  echo "── Issue $idx/6 ──────────────────────────────────────────────────"
  echo "  Title : $title"
  echo "  Labels: $labels"

  # Idempotency check
  local existing_number
  existing_number=$(issue_exists "$title" || true)
  if [[ -n "$existing_number" ]]; then
    echo "  Status: already exists: #$existing_number $title"
    SKIPPED=$((SKIPPED + 1))
    return
  fi

  if $DRY_RUN; then
    echo "  Status: [DRY-RUN] would create this issue"
    CREATED=$((CREATED + 1))
    return
  fi

  # Prompt unless --yes
  if ! $YES; then
    read -r -p "  Create issue $idx/6 '$title'? [y/N] " answer
    case "$answer" in
      [yY]*) ;;
      *) echo "  Status: skipped by user"; SKIPPED=$((SKIPPED + 1)); return ;;
    esac
  fi

  local url
  if url=$(gh issue create \
      --repo "$REPO" \
      --title "$title" \
      --body "$body" \
      --label "$labels" 2>&1); then
    echo "  Status: created $url"
    CREATED=$((CREATED + 1))
  else
    echo "  Status: FAILED — $url" >&2
    FAILED=$((FAILED + 1))
  fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Issue definitions
# ═══════════════════════════════════════════════════════════════════════════════

# ── Issue 1: PostgreSQLDown ───────────────────────────────────────────────────
TITLE_1="[Phase 3] Restore PostgreSQLDown after DB-VM scrape pipeline fix (F-PROM-05 / F-ALLO-06)"
LABELS_1="phase3,monitoring-deferred-alert,database"
read -r -d '' BODY_1 <<'BODY1_EOF' || true
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
BODY1_EOF

# ── Issue 2: PostgreSQLTooManyConnections ─────────────────────────────────────
TITLE_2="[Phase 3] Restore PostgreSQLTooManyConnections after DB-VM scrape pipeline fix (F-PROM-05 / F-ALLO-06)"
LABELS_2="phase3,monitoring-deferred-alert,database"
read -r -d '' BODY_2 <<'BODY2_EOF' || true
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
BODY2_EOF

# ── Issue 3: PostgreSQLHighConnections ───────────────────────────────────────
TITLE_3="[Phase 3] Restore PostgreSQLHighConnections after DB-VM scrape pipeline fix (F-PROM-05 / F-ALLO-06)"
LABELS_3="phase3,monitoring-deferred-alert,database"
read -r -d '' BODY_3 <<'BODY3_EOF' || true
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

Same bash snippet as PostgreSQLTooManyConnections issue.
BODY3_EOF

# ── Issue 4: HighHTTPErrorRate ────────────────────────────────────────────────
TITLE_4="[Phase 3] Restore HighHTTPErrorRate using backend metrics (replaces dropped nginx-based alert)"
LABELS_4="phase3,monitoring-deferred-alert,application"
read -r -d '' BODY_4 <<'BODY4_EOF' || true
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
BODY4_EOF

# ── Issue 5: SlowHTTPResponseTime ─────────────────────────────────────────────
TITLE_5="[Phase 3] Restore SlowHTTPResponseTime using backend histogram (replaces dropped nginx-based alert)"
LABELS_5="phase3,monitoring-deferred-alert,application"
read -r -d '' BODY_5 <<'BODY5_EOF' || true
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
- [ ] Add two rules to `rules-application.yml` (same file as HighHTTPErrorRate issue).

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
BODY5_EOF

# ── Issue 6: MinIODown ────────────────────────────────────────────────────────
TITLE_6="[Phase 3] Restore MinIODown by adding MinIO scrape target to AP-VM Alloy configs"
LABELS_6="phase3,monitoring-deferred-alert,application"
read -r -d '' BODY_6 <<'BODY6_EOF' || true
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
BODY6_EOF

# ═══════════════════════════════════════════════════════════════════════════════
# Main loop
# ═══════════════════════════════════════════════════════════════════════════════

echo "=========================================================="
echo " Phase 3 deferred-alert issue creator"
echo " Repo    : $REPO"
echo " Dry-run : $DRY_RUN"
echo " Auto-yes: $YES"
echo "=========================================================="

create_issue 1 "$TITLE_1" "$LABELS_1" "$BODY_1"
create_issue 2 "$TITLE_2" "$LABELS_2" "$BODY_2"
create_issue 3 "$TITLE_3" "$LABELS_3" "$BODY_3"
create_issue 4 "$TITLE_4" "$LABELS_4" "$BODY_4"
create_issue 5 "$TITLE_5" "$LABELS_5" "$BODY_5"
create_issue 6 "$TITLE_6" "$LABELS_6" "$BODY_6"

echo ""
echo "=========================================================="
echo " Summary: created $CREATED, skipped $SKIPPED (already exist), failed $FAILED"
echo "=========================================================="

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
