# Backend Metric Inventory

**Source file**: `backend/app/core/metrics.py`
**Cross-reference**: PromQL expressions from all 8 dashboard JSON files under `docs/superpowers/audits/working/api-responses/grafana/`

---

## Defined Metrics

| Name | Type | Labels | Definition Line |
|---|---|---|---|
| `http_requests_total` | Counter | `method`, `endpoint`, `status` | L20-24 |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint` | L26-31 |
| `http_requests_in_progress` | Gauge | `method` | L33-37 |
| `db_pool_size` | Gauge | `pool_type` | L43-47 |
| `db_pool_checked_out` | Gauge | `pool_type` | L49-53 |
| `db_pool_checked_in` | Gauge | `pool_type` | L55-59 |
| `db_pool_overflow` | Gauge | `pool_type` | L61-65 |
| `db_query_duration_seconds` | Histogram | `operation` | L67-72 |
| `db_connections_total` | Counter | `pool_type` | L74-78 |
| `scholarship_applications_total` | Counter | `status` | L84-88 |
| `scholarship_reviews_total` | Counter | `reviewer_type`, `action` | L90-94 |
| `email_sent_total` | Counter | `category`, `status` | L96-100 |
| `file_uploads_total` | Counter | `file_type`, `status` | L102-106 |
| `payment_rosters_total` | Counter | `status` | L108-112 |
| `http_errors_total` | Counter | `status_code`, `endpoint` | L118-122 |
| `auth_attempts_total` | Counter | `method`, `result` | L124-128 |
| `validation_errors_total` | Counter | `endpoint` | L130-134 |
| `app_info` | Info | (static key-value labels) | L140 |

---

## Instrumentation Callsites (Non-metrics.py Files)

Searched all `backend/app/**/*.py` for usages outside `core/metrics.py`:

| Metric | Used Outside metrics.py? | Where |
|---|---|---|
| `http_requests_total` | YES | `middleware/metrics_middleware.py:101-105` |
| `http_request_duration_seconds` | YES | `middleware/metrics_middleware.py:108-111` |
| `http_requests_in_progress` | YES | `middleware/metrics_middleware.py:71, 121` |
| `http_errors_total` | YES | `middleware/metrics_middleware.py:84-87, 115-118` |
| `db_query_duration_seconds` | NO | Never `.observe()`'d anywhere |
| `db_pool_size / db_pool_checked_out / db_pool_checked_in / db_pool_overflow` | YES | `main.py:372` via `update_db_pool_metrics()` |
| `db_connections_total` | NO | Never `.inc()`'d anywhere |
| `scholarship_applications_total` | NO | Never `.inc()`'d anywhere |
| `scholarship_reviews_total` | NO | Never `.inc()`'d anywhere |
| `email_sent_total` | NO | Never `.inc()`'d anywhere |
| `file_uploads_total` | NO | Never `.inc()`'d anywhere |
| `payment_rosters_total` | NO | Never `.inc()`'d anywhere |
| `auth_attempts_total` | NO | Never `.inc()`'d anywhere |
| `validation_errors_total` | NO | Never `.inc()`'d anywhere |
| `app_info` | YES | `main.py:79-83` via `set_app_info()` |

---

## Dashboard PromQL Cross-Reference

### Scholarship Overview Dashboard (the three No-data panels)

| Dashboard Query Metric | Exists in metrics.py? | Labels Match? | Status |
|---|---|---|---|
| `http_errors_total` | YES (L118) | dashboard uses `job="backend"` label — NOT defined in metrics.py; must come from Alloy relabel | PARTIAL — `environment`/`vm`/`job` are external labels |
| `http_requests_total` | YES (L20) | same issue with `job="backend"` external label | PARTIAL |
| `pg_stat_activity_count` | NO | N/A — postgres-exporter metric, not backend | ABSENT (correct, wrong source) |
| `db_query_duration_seconds` (queried as `_bucket`) | YES (L67) | `job="backend"` external label issue; plus metric is never `.observe()`'d | ZERO DATA |

### Other Overview Dashboard Metrics

| Dashboard Query Metric | Exists in metrics.py? | Instrumented? |
|---|---|---|
| `scholarship_applications_total` | YES | NO — defined but never incremented |
| `email_sent_total` | YES | NO — defined but never incremented |

### Metrics Defined in metrics.py but NOT Used by Any Dashboard

| Metric | Note |
|---|---|
| `http_requests_in_progress` | Unused by dashboards |
| `db_pool_size` | Unused by dashboards |
| `db_pool_checked_out` | Unused by dashboards |
| `db_pool_checked_in` | Unused by dashboards |
| `db_pool_overflow` | Unused by dashboards |
| `db_connections_total` | Unused by dashboards (also never instrumented) |
| `scholarship_reviews_total` | Unused by dashboards (also never instrumented) |
| `file_uploads_total` | Unused by dashboards (also never instrumented) |
| `payment_rosters_total` | Unused by dashboards (also never instrumented) |
| `auth_attempts_total` | Unused by dashboards (also never instrumented) |
| `validation_errors_total` | Unused by dashboards (also never instrumented) |
| `app_info` | Unused by dashboards |

---

## Label Gap Summary

The backend `core/metrics.py` defines metrics with labels: `method`, `endpoint`, `status`, `status_code`, `operation`, `pool_type`, `category`, `file_type`, `reviewer_type`, `action`, `result`.

It does **NOT** define or attach:
- `environment` — added by Alloy `prometheus.relabel` rule (`replacement = "staging"`)
- `vm` — added by Alloy `prometheus.relabel` rule (`replacement = "ap-vm"`)
- `job` — set by Alloy `prometheus.scrape` block (`job_name = "backend"`)

These three labels are dashboard filter variables. They must be injected by the Alloy pipeline. If Alloy is not running or not successfully scraping the backend `/metrics` endpoint, all backend metrics will be absent from Prometheus entirely.

The `targets.json` captured from Prometheus shows only 3 active targets (`grafana`, `loki`, `prometheus`) — all with `environment="monitoring"`. No `job="backend"` target is visible. This confirms the Alloy-to-Prometheus remote_write pipeline is not delivering backend metrics.
