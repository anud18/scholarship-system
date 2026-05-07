# R1 Alert Rule Preservation Audit — feat/monitoring-phase2

**Auditor:** R1 (automated)
**Date:** 2026-05-06
**Branch:** feat/monitoring-phase2
**Original source:** `git show 052e408^:monitoring/config/prometheus/alerts/basic-alerts.yml` (20 rules)
**Target files:** `rules-system.yml` (5), `rules-container.yml` (4), `rules-database.yml` (2), `rules-monitoring.yml` (3)
**Spec reference:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-phase2-design.md` §6.2.1

---

## 1. Per-Rule Preservation Table

### 1.1 rules-system.yml — system_health group (5 rules)

| Alert Name | expr | for | severity | category | summary | description | relativeTimeRange.from | Schema |
|---|---|---|---|---|---|---|---|---|
| HighCPUUsage | ✅ | ✅ 5m | ✅ warning | ✅ system | ✅ | ✅ | ✅ 300s (=5m) | ✅ |
| HighMemoryUsage | ✅ | ✅ 5m | ✅ warning | ✅ system | ✅ | ✅ | ✅ 300s (=5m) | ✅ |
| DiskSpaceLow | ✅ | ✅ 10m | ✅ warning | ✅ system | ✅ | ✅ | ✅ 600s (=10m) | ✅ |
| DiskSpaceCritical | ✅ | ✅ 5m | ✅ critical | ✅ system | ✅ | ✅ | ✅ 300s (=5m) | ✅ |
| HighSystemLoad | ✅ | ✅ 10m | ✅ warning | ✅ system | ✅ | ✅ | ✅ 600s (=10m) | ✅ |

### 1.2 rules-container.yml — container_health group (4 rules)

| Alert Name | expr | for | severity | category | summary | description | relativeTimeRange.from | Schema |
|---|---|---|---|---|---|---|---|---|
| ContainerDown | ✅ | ✅ 2m | ✅ critical | ✅ container | ✅ | ✅ | ✅ 120s (=2m) | ✅ |
| ContainerHighCPU | ✅ | ✅ 5m | ✅ warning | ✅ container | ✅ | ✅ | ✅ 300s (=5m) | ✅ |
| ContainerHighMemory | ✅ | ✅ 5m | ✅ warning | ✅ container | ✅ | ✅ | ✅ 300s (=5m) | ✅ |
| ContainerRestartingFrequently | ✅ | ✅ 5m | ✅ warning | ✅ container | ✅ | ✅ | ⚠️ 300s (=5m) but for=5m — see note | ✅ |

**ContainerRestartingFrequently note:** The original Prometheus rule has `for: 5m`. The Grafana rule correctly sets `for: 5m` and `relativeTimeRange.from: 300`. However, the PromQL window in the expression is `[15m]` — matching the original verbatim. The `relativeTimeRange.from: 300` (5m) is shorter than the `[15m]` lookback window in the expression. This is a pre-existing quirk inherited from the original (the alert fires based on `rate(...[15m])` evaluated at a single instant, not a 15m range query). The migration preserved this exactly; no new drift introduced here.

### 1.3 rules-database.yml — database_health group (2 LIVE rules)

| Alert Name | expr | for | severity | category | summary | description | relativeTimeRange.from | Schema |
|---|---|---|---|---|---|---|---|---|
| RedisDown | ✅ | ✅ 1m | ✅ critical | ✅ database | ✅ | ✅ | ✅ 60s (=1m) | ✅ |
| RedisHighMemory | ✅ | ✅ 5m | ✅ warning | ✅ database | ✅ | ✅ | ✅ 300s (=5m) | ✅ |

### 1.4 rules-monitoring.yml — monitoring_health group (3 rules)

| Alert Name | expr | for | severity | category | summary | description | relativeTimeRange.from | Schema |
|---|---|---|---|---|---|---|---|---|
| PrometheusTargetDown | ✅ | ✅ 5m | ✅ warning | ✅ monitoring | ✅ | ✅ | ✅ 300s (=5m) | ✅ |
| LokiIngestionFallingBehind | ✅ | ✅ 10m | ✅ warning | ✅ monitoring | ✅ | ✅ | ✅ 600s (=10m) | ✅ |
| PrometheusStorageLow | ✅ | ✅ 10m | ✅ warning | ✅ monitoring | ✅ | ✅ | ✅ 600s (=10m) | ✅ |

---

## 2. Detailed PromQL Expression Verification

All 14 PromQL expressions were checked verbatim against the source. The Grafana YAML `model.expr` field collapses the original multi-line `expr: |` block into a single line — this is semantically equivalent (YAML block scalar trailing newline is whitespace; PromQL ignores whitespace). No expression drift found.

| Alert | Original (block scalar) | New (single line) | Equivalent |
|---|---|---|---|
| HighCPUUsage | `100 - (avg by(instance, environment) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80` | identical | ✅ |
| HighMemoryUsage | `(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 85` | identical | ✅ |
| DiskSpaceLow | `(1 - (node_filesystem_avail_bytes{fstype!~"tmpfs\|fuse.lxcfs\|squashfs\|vfat"} / node_filesystem_size_bytes)) * 100 > 80` | identical | ✅ |
| DiskSpaceCritical | `(1 - (node_filesystem_avail_bytes{fstype!~"tmpfs\|fuse.lxcfs\|squashfs\|vfat"} / node_filesystem_size_bytes)) * 100 > 90` | identical | ✅ |
| HighSystemLoad | `node_load5 / count(node_cpu_seconds_total{mode="idle"}) without(cpu, mode) > 2` | identical | ✅ |
| ContainerDown | `time() - container_last_seen{name!=""} > 60` | identical | ✅ |
| ContainerHighCPU | `sum(rate(container_cpu_usage_seconds_total{name!=""}[5m])) by (name, instance, environment) * 100 > 80` | identical | ✅ |
| ContainerHighMemory | `(container_memory_usage_bytes{name!=""} / container_spec_memory_limit_bytes{name!=""}) * 100 > 85` | identical | ✅ |
| ContainerRestartingFrequently | `rate(container_last_seen{name!=""}[15m]) > 0.1` | identical | ✅ |
| RedisDown | `redis_up == 0` | identical | ✅ |
| RedisHighMemory | `(redis_memory_used_bytes / redis_memory_max_bytes) * 100 > 80` | identical | ✅ |
| PrometheusTargetDown | `up == 0` | identical | ✅ |
| LokiIngestionFallingBehind | `rate(loki_distributor_bytes_received_total[5m]) > rate(loki_ingester_chunks_flushed_total[5m]) * 1000` | identical | ✅ |
| PrometheusStorageLow | `(prometheus_tsdb_storage_blocks_bytes / prometheus_tsdb_retention_limit_bytes) > 0.8` | identical | ✅ |

---

## 3. Schema Correctness Per File

All four files were verified against the Grafana unified alerting provisioning schema (apiVersion 1).

### Checked fields per rule:
- `uid`: present and unique slug format — ✅ all 14 rules
- `title`: matches original alert name — ✅ all 14 rules
- `condition: A` — ✅ all 14 rules
- `data[0].refId: A` — ✅ all 14 rules
- `data[0].relativeTimeRange.from`: matches `for:` duration in seconds — ✅ all 14 rules (see ContainerRestartingFrequently note above)
- `data[0].relativeTimeRange.to: 0` — ✅ all 14 rules
- `data[0].datasourceUid: prometheus-uid` — ✅ all 14 rules
- `data[0].model.instant: true` — ✅ all 14 rules (correct for alerting queries)
- `noDataState: NoData` — ✅ all 14 rules
- `execErrState: Error` — ✅ all 14 rules
- `isPaused: false` — ✅ all 14 rules

### Group-level fields:
| File | orgId | name | folder | interval | Correct |
|---|---|---|---|---|---|
| rules-system.yml | 1 | system_health | Alerts | 30s | ✅ (matches original `interval: 30s`) |
| rules-container.yml | 1 | container_health | Alerts | 30s | ✅ |
| rules-database.yml | 1 | database_health | Alerts | 30s | ✅ |
| rules-monitoring.yml | 1 | monitoring_health | Alerts | 60s | ✅ (matches original `interval: 60s`) |

---

## 4. Absence Verification

### 4.1 Deferred PostgreSQL Alerts (must be ABSENT from all rules-*.yml files)

| Alert | Absent from rules-database.yml | Absent from all other files |
|---|---|---|
| PostgreSQLDown | ✅ ABSENT | ✅ ABSENT |
| PostgreSQLTooManyConnections | ✅ ABSENT | ✅ ABSENT |
| PostgreSQLHighConnections | ✅ ABSENT | ✅ ABSENT |

**Deferral documented:** `rules-database.yml` lines 7–11 contain an explicit YAML comment block:
```yaml
# Note: 3 PostgreSQL alerts (PostgreSQLDown, PostgreSQLTooManyConnections,
# PostgreSQLHighConnections) are intentionally deferred to Phase 3.
# They depend on the DB-VM scrape pipeline (F-PROM-05 / F-ALLO-06) which
# Phase 3 fixes. Once postgres-exporter is reaching Prometheus, the rules
# will be added here. Tracking issue: filed at PR-2.B merge time.
```
This satisfies the spec requirement for comment-documentation of the deferral. ✅

### 4.2 Dropped Application Alerts (must be ABSENT from all rules-*.yml files)

| Alert | Absent from all rules-*.yml |
|---|---|
| HighHTTPErrorRate | ✅ ABSENT |
| SlowHTTPResponseTime | ✅ ABSENT |
| MinIODown | ✅ ABSENT |

Searched all four files: no occurrence of `HighHTTPErrorRate`, `SlowHTTPResponseTime`, `MinIODown`, `nginx_http_requests_total`, `nginx_http_request_duration_seconds_bucket`, `staging-db-minio`. ✅

---

## 5. Bugs and Concrete Findings

### Bugs: NONE

No correctness bugs found. All 14 rules are preserved with:
- Identical PromQL semantics
- Correct `for:` durations
- Correct `labels.severity` and `labels.category`
- Verbatim `annotations.summary` and `annotations.description` templates
- Correct Grafana unified-alerting wrapper schema fields

### Minor Observations (not bugs)

1. **ContainerRestartingFrequently relativeTimeRange.from = 300 vs expression window [15m]:** The Grafana `relativeTimeRange` controls how much historical data the query engine fetches for evaluation context. Setting it to 300s (matching `for:`) while the PromQL uses `[15m]` means the query fetches 5 minutes of data but the `rate()` function requests a 15-minute window. Grafana Unified Alerting evaluates alert rules using instant queries (`instant: true`), so `relativeTimeRange` does not limit the lookback window of `rate()` — the TSDB provides the needed range internally. No functional impact. This is acceptable behavior and matches the spec's intent of "relativeTimeRange.from should match the for: duration in seconds."

2. **No `uid` uniqueness conflict risk:** All 14 UIDs use the pattern `alert-{kebab-case-alertname}` and are globally unique within the provisioning set. ✅

3. **`data[0].model` does not include `queryType`, `datasource` object, or `intervalMs`:** These are optional fields in Grafana's internal model. Their absence does not cause provisioning errors; Grafana resolves defaults from `datasourceUid`. ✅

---

## 6. Summary

| Metric | Count |
|---|---|
| Total original rules | 20 |
| LIVE rules to migrate | 14 |
| DEFERRED rules (Phase 3) | 3 |
| DROPPED rules | 3 |
| Rules found in new files | 14 |
| Rules with ✅ full preservation | 14 |
| Rules with ⚠️ drift | 0 |
| Rules with ❌ missing or broken | 0 |
| Absence checks passed | 6 / 6 |
| Schema checks passed | 14 / 14 |

**Verdict: PASS.** All 14 LIVE rules are preserved byte-equivalent in PromQL semantics, labels, durations, and annotation templates. All 3 deferred PostgreSQL rules are absent and documented. All 3 dropped application rules are absent with no traces. The Grafana unified-alerting wrapper schema is correct across all four files.
