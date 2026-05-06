# Alloy + Cross-VM Audit — Working File

**Branch:** C — Alloy + Cross-VM Topology
**Working file:** `docs/superpowers/audits/working/alloy-crossvm.md`
**Artifact dir:** `docs/superpowers/audits/working/api-responses/alloy-crossvm/`
**Spec ref:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md` (commit 07faa57)
**Date:** 2026-05-06

---

## Findings

### F-ALLO-01  [P1]  prod-ap-vm: container name relabeling rule strips leading slash only in staging

**Where**: `monitoring/config/alloy/prod-ap-vm.alloy:20-23`, `monitoring/config/alloy/staging-ap-vm.alloy:20-25`.

**Evidence**:
- Active probe: `diff-prod-ap-vm-vs-staging-ap-vm.txt` excerpt — staging adds two lines absent in prod:
  ```
  +    regex         = "^/(.*)"
  +    replacement   = "$1"
  ```
  The `loki.relabel "container_labels"` rule in `prod-ap-vm.alloy` sets only `target_label = "container"` with `source_labels = ["__meta_docker_container_name"]` and no `regex`/`replacement`. Docker container names reported by the socket always start with `/` (e.g. `/scholarship_backend`). Without the strip rule, the `container` label value will be `/scholarship_backend` rather than `scholarship_backend`.
- Static read: `monitoring/config/alloy/prod-ap-vm.alloy:18-27` — rule body has no `regex` or `replacement` fields. `monitoring/config/alloy/staging-ap-vm.alloy:18-29` — rule body includes `regex = "^/(.*)"` and `replacement = "$1"`.
- Cross-reference: All Loki dashboard panels and LogQL queries that filter on `container=~".*nginx.*"` or `container="scholarship_backend"` will find no matching streams on prod-ap-vm because the label value retains the leading `/`. Loki label values from staging and prod will never be equal, so cross-environment comparisons break too.

**Expected**: Both prod-ap-vm and staging-ap-vm should carry identical `regex`/`replacement` rules in `loki.relabel "container_labels"` to strip the Docker-prepended `/`.

**Root cause hypothesis**: The strip-slash rule was added to staging-ap-vm (and both db-vm variants) but was never backported to prod-ap-vm.

**Remediation owner**: Phase 3

**Suggested fix sketch**:
```alloy
// In prod-ap-vm.alloy, loki.relabel "container_labels", first rule:
rule {
  source_labels = ["__meta_docker_container_name"]
  regex         = "^/(.*)"
  replacement   = "$1"
  target_label  = "container"
}
```

---

### F-ALLO-02  [P1]  prod-db-vm: container name relabeling rule also missing the slash-strip regex

**Where**: `monitoring/config/alloy/prod-db-vm.alloy:18-23`, `monitoring/config/alloy/staging-db-vm.alloy:18-27`.

**Evidence**:
- Active probe: `diff-prod-db-vm-vs-staging-db-vm.txt` excerpt — the staging-db-vm file adds two lines absent in prod-db-vm:
  ```
  +    regex         = "^/(.*)"
  +    replacement   = "$1"
  ```
- Static read: `monitoring/config/alloy/prod-db-vm.alloy:18-23` — no `regex`/`replacement`. `monitoring/config/alloy/staging-db-vm.alloy:18-27` — has `regex = "^/(.*)"` and `replacement = "$1"`.
- Cross-reference: Same mechanism as F-ALLO-01. All container log streams from prod-db-vm will carry `container="/postgres"` instead of `container="postgres"`, breaking any Loki query filtering on container name.

**Expected**: prod-db-vm relabeling rule should strip the leading `/` from container names, matching the staging-db-vm behaviour.

**Root cause hypothesis**: Same edit as F-ALLO-01 — the slash-strip fix was applied to staging files and db-vm staging file but not propagated to both prod files.

**Remediation owner**: Phase 3

**Suggested fix sketch**: Same two-line addition as F-ALLO-01, in `prod-db-vm.alloy`.

---

### F-ALLO-03  [P1]  prod-ap-vm: `loki.process` applies `stage.json` to ALL containers instead of nginx-only

**Where**: `monitoring/config/alloy/prod-ap-vm.alloy:50-59`, `monitoring/config/alloy/staging-ap-vm.alloy:52-64`.

**Evidence**:
- Active probe: `diff-prod-ap-vm-vs-staging-ap-vm.txt` excerpt:
  ```diff
  -  // Parse JSON logs from Nginx
  -  stage.json {
  -    expressions = { ... }
  -  }
  +  // Parse JSON logs ONLY from Nginx containers
  +  stage.match {
  +    selector = "{container=~\".*nginx.*\"}"
  +    stage.json {
  +      expressions = { ... }
  +    }
  +  }
  ```
  In `prod-ap-vm.alloy`, the `stage.json` block is unconditional: it runs against every container's log line. The backend (FastAPI) emits Python-formatted text logs, not JSON, so the JSON parse fails silently. Worse, if any field collides with Nginx-specific field names, it may produce spurious label values.
- Static read: `monitoring/config/alloy/prod-ap-vm.alloy:50-59` — `stage.json { expressions = { ... } }` is a direct child of `loki.process "add_labels"`. `monitoring/config/alloy/staging-ap-vm.alloy:52-64` — wrapped in `stage.match { selector = "{container=~\".*nginx.*\"}" }`.
- Cross-reference: Intent (per staging) is to parse JSON only for nginx log lines. Prod-ap-vm applies it to all containers. Backend and Redis log lines will fail the JSON parse and may emit empty or corrupted extracted fields.

**Expected**: The `stage.json` block in prod-ap-vm should be inside a `stage.match { selector = "{container=~\".*nginx.*\"}" }` gate, matching staging-ap-vm.

**Root cause hypothesis**: The nginx-only gate was added as a correctness fix in the staging file but not applied to the already-deployed prod-ap-vm config.

**Remediation owner**: Phase 3

**Suggested fix sketch**:
```alloy
stage.match {
  selector = "{container=~\".*nginx.*\"}"
  stage.json {
    expressions = {
      request_time     = "request_time",
      upstream_time    = "upstream_response_time",
      status           = "status",
      request_method   = "request_method",
      request_uri      = "request_uri",
    }
  }
}
```

---

### F-ALLO-04  [P1]  prod-ap-vm: `stage.drop` health-check and nginx-status rules absent

**Where**: `monitoring/config/alloy/prod-ap-vm.alloy:50-71` (entire `loki.process` body), `monitoring/config/alloy/staging-ap-vm.alloy:66-78`.

**Evidence**:
- Active probe: `diff-prod-ap-vm-vs-staging-ap-vm.txt` shows two `stage.drop` blocks present in staging but missing from prod-ap-vm:
  ```diff
  -  // Drop health check logs to reduce noise
  -  stage.drop {
  -    expression  = ".*\\/health.*"
  -    drop_counter_reason = "health_check"
  -  }
  -
  -  // Drop nginx status logs
  -  stage.drop {
  -    expression  = ".*\\/nginx_status.*"
  -    drop_counter_reason = "nginx_status"
  -  }
  ```
  (These lines appear only in `staging-ap-vm.alloy`.)
- Static read: `monitoring/config/alloy/prod-ap-vm.alloy` contains no `stage.drop` blocks inside `loki.process "add_labels"`. `monitoring/config/alloy/staging-ap-vm.alloy:66-78` has both drops.
- Cross-reference: Prod-ap-vm will ship `/health` and `/nginx_status` poll traffic into Loki, inflating log volume and making the Application Logs dashboard noisier than intended.

**Expected**: prod-ap-vm should drop health-check and nginx-status log lines, matching staging-ap-vm.

**Root cause hypothesis**: Same edit propagation gap as F-ALLO-03.

**Remediation owner**: Phase 3

**Suggested fix sketch**: Add the two `stage.drop` blocks from staging-ap-vm into the prod-ap-vm `loki.process "add_labels"` block.

---

### F-ALLO-05  [P1]  staging-ap-vm missing `redis_exporter` scrape job in prod-ap-vm

**Where**: `monitoring/config/alloy/staging-ap-vm.alloy:138-148`, `monitoring/config/alloy/prod-ap-vm.alloy` (absent).

**Evidence**:
- Active probe: `diff-prod-ap-vm-vs-staging-ap-vm.txt` excerpt — staging-ap-vm has:
  ```diff
  +// Scrape Redis Exporter
  +prometheus.scrape "redis_exporter" {
  +  targets = [{ __address__ = "redis-exporter:9121" }]
  +  forward_to = [prometheus.relabel.add_labels.receiver]
  +  job_name = "redis"
  +  scrape_interval = "15s"
  +}
  ```
  These lines are absent from prod-ap-vm.alloy. The `block-summary.txt` confirms: `staging-ap-vm` lists `prometheus.scrape "redis_exporter"` while `prod-ap-vm` does not.
- Static read: `monitoring/config/alloy/prod-ap-vm.alloy` — scrape blocks present: `node_exporter`, `cadvisor`, `nginx_exporter`, `backend`, `alloy_self`. No `redis_exporter` block. `monitoring/config/alloy/staging-ap-vm.alloy:138-148` — `redis_exporter` block present.
- Cross-reference: Redis is deployed on AP-VM for both staging and prod (confirmed by `prod-db-monitoring-compose.yml` note: "Redis Exporter not needed — Redis is on AP-VM"). Prod-ap-vm therefore has a Redis service but no Alloy scrape job for it, meaning Redis metrics (`redis_*`) are absent from Prometheus for the prod environment. Any dashboard panel filtering `environment="prod"` for Redis metrics will show No data.

**Expected**: prod-ap-vm.alloy should scrape `redis-exporter:9121` the same way staging-ap-vm does.

**Root cause hypothesis**: Redis scrape job was added to staging-ap-vm to support a Redis dashboard but was never propagated to prod-ap-vm.

**Remediation owner**: Phase 3

**Suggested fix sketch**:
```alloy
prometheus.scrape "redis_exporter" {
  targets = [{
    __address__ = "redis-exporter:9121",
  }]
  forward_to = [prometheus.relabel.add_labels.receiver]
  job_name = "redis"
  scrape_interval = "15s"
}
```

---

### F-ALLO-06  [P1]  DB-VM metrics are NOT pushed via Alloy remote_write; Prometheus on AP-VM scrapes DB-VM exporters directly — but `prometheus.yml` has NO such scrape jobs

**Where**: `monitoring/config/alloy/staging-db-vm.alloy:81-97` (comment block), `monitoring/config/alloy/prod-db-vm.alloy:79-97` (comment block), `monitoring/config/prometheus/prometheus.yml:26-66` (entire scrape_configs).

**Evidence**:
- Active probe: `docs/superpowers/audits/working/api-responses/prometheus-loki/targets.json` — the `activeTargets` array contains exactly three entries: `prometheus`, `loki`, `grafana`. All carry `environment="monitoring"`. There is no target for `node-exporter`, `postgres-exporter`, `cadvisor`, `nginx-exporter`, `redis-exporter`, or `backend`. Zero AP/DB VM targets. The `droppedTargets` array is also empty.
- Static read: Both `staging-db-vm.alloy` and `prod-db-vm.alloy` contain a `// METRICS PIPELINE - PULL MODE` comment block stating: _"Prometheus on AP-VM will add environment/vm labels during scrape using relabel_configs in its prometheus.yml configuration."_ No `prometheus.remote_write` or `prometheus.relabel` or any `prometheus.scrape` block exists in either db-vm file. `monitoring/config/prometheus/prometheus.yml:26-66` has only self-monitoring jobs (`prometheus`, `loki`, `grafana`) and a comment: _"All application/system metrics are collected by Grafana Alloy and sent to Prometheus via remote_write."_
- Cross-reference: The db-vm alloy comments promise that Prometheus will scrape them directly, but `prometheus.yml` has no such scrape jobs. The AP-VM alloy files use `prometheus.remote_write` to push to `monitoring_prometheus:9090/api/v1/write` (correct). DB-VM alloy has no push path and Prometheus has no pull path for DB-VM exporters. Result: `node-exporter`, `postgres-exporter` metrics from the DB-VM never reach Prometheus. This explains why "PostgreSQL Active Connections" and "Database Query p95" dashboard panels show No data.

**Expected**: Either (a) DB-VM Alloy files should include `prometheus.scrape` + `prometheus.relabel` + `prometheus.remote_write` blocks to push metrics from DB-VM exporters to Prometheus (mirroring AP-VM structure), OR (b) `prometheus.yml` should include static scrape jobs targeting DB-VM exporter ports (9100, 9187) with the appropriate `relabel_configs` to add `environment` and `vm` labels. The comment promises option (b) but it was never implemented.

**Root cause hypothesis**: A design decision was made to use pull-mode scrape from Prometheus for DB-VM metrics but the corresponding scrape jobs were never written into `prometheus.yml`, leaving a silent gap that shows zero targets.

**Remediation owner**: Phase 3

**Suggested fix sketch (option a — push mode, consistent with AP-VM)**:
```alloy
// In staging-db-vm.alloy and prod-db-vm.alloy — add:
prometheus.scrape "node_exporter" {
  targets = [{ __address__ = "node-exporter:9100" }]
  forward_to = [prometheus.relabel.add_labels.receiver]
  job_name = "node"
  scrape_interval = "15s"
}

prometheus.scrape "postgres_exporter" {
  targets = [{ __address__ = "postgres-exporter:9187" }]
  forward_to = [prometheus.relabel.add_labels.receiver]
  job_name = "postgres"
  scrape_interval = "15s"
}

prometheus.relabel "add_labels" {
  forward_to = [prometheus.remote_write.default.receiver]
  rule { target_label = "environment"; replacement = "staging" }  // or "prod"
  rule { target_label = "vm"; replacement = "db-vm" }
}

prometheus.remote_write "default" {
  endpoint {
    url = env("MONITORING_SERVER_URL") + ":9090/api/v1/write"
    queue_config { ... }
  }
}
```

---

### F-ALLO-07  [P1]  prod-ap-vm `prometheus.remote_write` URL is hardcoded to `monitoring_prometheus`; on prod the monitoring stack attaches to `scholarship_staging_network`, not the prod network

**Where**: `monitoring/config/alloy/prod-ap-vm.alloy:164-184`, `docs/superpowers/audits/working/api-responses/deploy-pipeline/prod-monitoring-compose.yml:44-50,159-166`.

**Evidence**:
- Active probe: `prod-monitoring-compose.yml` (prod ground truth) shows the monitoring stack's `prometheus` service is on `monitoring_network` (bridge) and `scholarship_staging_network` (external). The container name is `monitoring_prometheus`. The prod AP-VM Alloy config hardcodes `url = "http://monitoring_prometheus:9090/api/v1/write"`. For this to resolve, Alloy must be on the same Docker network that contains `monitoring_prometheus`.
- Static read: `monitoring/config/alloy/prod-ap-vm.alloy:164-184` — remote_write URL is `http://monitoring_prometheus:9090/api/v1/write`. The prod AP-VM's Alloy container runs from `docker-compose.monitoring.yml` (which mounts `prod-ap-vm.alloy`), and that compose file places Alloy on `monitoring_network` and `scholarship_staging_network`. The `monitoring_prometheus` container is also on `monitoring_network`, so DNS resolution of `monitoring_prometheus` should succeed within the same compose stack. However: staging-ap-vm.alloy is identical in URL structure and staging uses the same network naming. The difference is that prod-db-vm.alloy uses `env("MONITORING_SERVER_URL")` for Loki, implying the intent is that cross-VM communication uses an env var.
- Cross-reference: The remote_write URL is hardcoded to the Docker service name `monitoring_prometheus`, which only resolves if Alloy is in the same Docker network as Prometheus. For prod-ap-vm this works (same compose file). But the pattern inconsistency with how db-vm uses `MONITORING_SERVER_URL` means: if the monitoring stack is ever split across separate VMs, the hardcoded name will break silently. Also, the prod-ap-vm Alloy is reading a config named `prod-ap-vm.alloy` but that file is part of the same `docker-compose.monitoring.yml` stack, so it can reach `monitoring_prometheus`. This is not immediately broken but is an architectural fragility.

**Expected**: Either consistently use service-name DNS (if always co-located) or consistently use `env("MONITORING_SERVER_URL")` (if cross-VM). The current mix is inconsistent.

**Root cause hypothesis**: The DB-VM config was written to handle the cross-VM network gap via env var, but the AP-VM config was left with the hardcoded service name from when everything was single-VM, creating an inconsistent pattern that will break if topology changes.

**Remediation owner**: Phase 3

**Suggested fix sketch**: Standardize: use `env("MONITORING_SERVER_URL")` in both AP-VM and DB-VM configs for the remote_write and loki.write URLs, with `MONITORING_SERVER_URL` set to the IP/hostname of the monitoring server in deploy scripts.

---

### F-ALLO-08  [P1]  DB-VM Alloy pushes logs to Loki via `env("MONITORING_SERVER_URL") + ":3100/..."` — but Prometheus remote_write from AP-VM uses `"http://monitoring_prometheus:9090/..."` — the two cross-VM paths use different resolution strategies with no validation

**Where**: `monitoring/config/alloy/staging-db-vm.alloy:69-78`, `monitoring/config/alloy/prod-db-vm.alloy:67-76`, `monitoring/config/alloy/staging-ap-vm.alloy:182-202`, `monitoring/config/alloy/prod-ap-vm.alloy:164-184`.

**Evidence**:
- Active probe: `diff-staging-ap-vm-vs-staging-db-vm.txt` shows loki.write URL differs between AP-VM (hardcoded `http://monitoring_loki:3100/...`) and DB-VM (`env("MONITORING_SERVER_URL") + ":3100/..."`). There is no equivalent cross-VM probe confirming that `MONITORING_SERVER_URL` is set at DB-VM runtime.
- Static read: `staging-db-vm.alloy:71` — `url = env("MONITORING_SERVER_URL") + ":3100/loki/api/v1/push"`. `prod-db-vm.alloy:69` — same. The `docker-compose.prod-db-monitoring.yml:20-24` passes `MONITORING_SERVER_URL=${MONITORING_SERVER_URL}` from the host env to the Alloy container. If this variable is unset on the DB-VM host, the resulting URL will be `:3100/loki/api/v1/push` (just the port path) which is invalid. Alloy will fail to connect to Loki and silently drop all DB-VM container logs.
- Cross-reference: Alloy would start but immediately fail all Loki pushes with a connection error to `:3100`. Since Alloy is stateless for log pushing (it drops on failure after retries), DB-VM container logs will be absent from Loki with no monitoring alert.

**Expected**: `MONITORING_SERVER_URL` must be set to the AP-VM's reachable address (e.g. `http://10.x.x.x`) before deploying DB-VM Alloy. A missing-env guard or pre-flight check should verify it. The deploy workflow should validate this before starting the DB-VM stack.

**Root cause hypothesis**: No guard against unset `MONITORING_SERVER_URL` at DB-VM deploy time; if the variable is missing, Alloy silently loses all DB-VM logs.

**Remediation owner**: Phase 3 (guard in DB-VM deploy) / Phase 2 (alert if Loki receives no DB-VM streams).

**Suggested fix sketch**: In the DB-VM deploy step, add:
```bash
if [ -z "${MONITORING_SERVER_URL}" ]; then
  echo "ERROR: MONITORING_SERVER_URL is not set. DB-VM Alloy cannot reach Loki." >&2
  exit 1
fi
```

---

### F-ALLO-09  [P0]  DB-VM Alloy metrics pipeline comment says "Prometheus adds environment/vm labels via relabel_configs" but `prometheus.yml` has NO such relabel_configs — labels are never added to DB-VM metrics

**Where**: `monitoring/config/alloy/staging-db-vm.alloy:83-91`, `monitoring/config/alloy/prod-db-vm.alloy:81-89`, `monitoring/config/prometheus/prometheus.yml:26-66`.

**Evidence**:
- Active probe: `targets.json` — zero non-monitoring targets in Prometheus. Even if DB-VM exporters were reachable, no scrape job in `prometheus.yml` references them with `relabel_configs`. The three self-monitoring jobs (`prometheus`, `loki`, `grafana`) use static `labels: {environment: 'monitoring'}` — not a `relabel_configs` block that would add `vm` labels.
- Static read: DB-VM alloy files contain: _"Prometheus on AP-VM will add environment/vm labels during scrape using relabel_configs in its prometheus.yml configuration."_ `monitoring/config/prometheus/prometheus.yml` contains zero `relabel_configs` entries in any scrape job. All jobs use static `labels:` blocks with only `environment: 'monitoring'` and `service:`.
- Cross-reference: The label promise made in the DB-VM alloy comment is simply false. Even if scrape jobs were added to prometheus.yml, there are no `relabel_configs` to add `environment=staging` or `vm=db-vm` labels. This means: (1) DB-VM metrics would arrive with no `environment`/`vm` labels, (2) all dashboard panels filtering `{environment="staging", vm="db-vm"}` would return empty, (3) this is a P0 because monitoring is structurally configured to appear correct while silently delivering no labelled data.

**Expected**: Either DB-VM Alloy should add labels via its own `prometheus.relabel` before `prometheus.remote_write` (option a from F-ALLO-06), or `prometheus.yml` scrape jobs for DB-VM exporters should include `relabel_configs` to add `environment` and `vm` labels. The current state does neither.

**Root cause hypothesis**: The DB-VM metrics pipeline was designed on paper (via the comment block) but the implementation step — writing the relabel_configs into prometheus.yml — was never executed.

**Remediation owner**: Phase 2 (the label gap makes monitoring lie about coverage) / Phase 3 (implementation)

**Suggested fix sketch (if using pull mode in prometheus.yml)**:
```yaml
- job_name: 'db-vm-node'
  static_configs:
    - targets: ['<DB_VM_IP>:9100']
  relabel_configs:
    - target_label: environment
      replacement: staging
    - target_label: vm
      replacement: db-vm
```

---

### F-ALLO-10  [noted]  prod-ap-vm and staging-ap-vm use `honor_labels = true` on the backend scrape — this allows the backend to override Alloy-injected labels

**Where**: `monitoring/config/alloy/staging-ap-vm.alloy:161-163`, `monitoring/config/alloy/prod-ap-vm.alloy:143-145`.

**Evidence**:
- Active probe: No live probe possible; static analysis only. Both AP-VM files set `honor_labels = true` on the `prometheus.scrape "backend"` block.
- Static read: `monitoring/config/alloy/staging-ap-vm.alloy:163` and `monitoring/config/alloy/prod-ap-vm.alloy:145` — `honor_labels = true`. Comment says: "Skip if backend doesn't expose metrics endpoint" — this is incorrect reasoning; `honor_labels` controls label precedence, not endpoint availability.
- Cross-reference: If the backend's `/metrics` output carries any label named `environment` or `vm` (even accidentally, e.g. from a prometheus_client default), those values will override the relabeling done in `prometheus.relabel "add_labels"`. The backend-pushed labels would shadow the Alloy-injected infrastructure labels, causing environment/vm filters to mismatch.

**Expected**: `honor_labels = false` (default) or the comment corrected; the comment appears to be a copy-paste error explaining `honor_labels` as if it means "skip on error".

**Root cause hypothesis**: Copy-paste of a scrape config snippet that included `honor_labels = true` for a different purpose, with an inaccurate comment that obscures the label-precedence risk.

**Remediation owner**: Phase 4 (hygiene)

**Suggested fix sketch**: Remove `honor_labels = true` from the backend scrape block or replace with `honor_labels = false`.

---

## Coverage

### Files inspected

| File | Status |
|---|---|
| `monitoring/config/alloy/staging-ap-vm.alloy` | Read in full |
| `monitoring/config/alloy/staging-db-vm.alloy` | Read in full |
| `monitoring/config/alloy/prod-ap-vm.alloy` | Read in full |
| `monitoring/config/alloy/prod-db-vm.alloy` | Read in full |
| `docs/superpowers/audits/working/api-responses/alloy-crossvm/block-summary.txt` | Read in full |
| `docs/superpowers/audits/working/api-responses/alloy-crossvm/diff-prod-ap-vm-vs-prod-db-vm.txt` | Read in full |
| `docs/superpowers/audits/working/api-responses/alloy-crossvm/diff-prod-ap-vm-vs-staging-ap-vm.txt` | Read in full |
| `docs/superpowers/audits/working/api-responses/alloy-crossvm/diff-prod-db-vm-vs-staging-db-vm.txt` | Read in full |
| `docs/superpowers/audits/working/api-responses/alloy-crossvm/diff-staging-ap-vm-vs-staging-db-vm.txt` | Read in full |
| `docs/superpowers/audits/working/api-responses/alloy-crossvm/diff-prod-ap-vm-vs-staging-db-vm.txt` | Read in full |
| `docs/superpowers/audits/working/api-responses/alloy-crossvm/diff-prod-db-vm-vs-staging-ap-vm.txt` | Read in full |
| `docs/superpowers/audits/working/api-responses/prometheus-loki/targets.json` | Read (activeTargets array) |
| `docs/superpowers/audits/working/api-responses/deploy-pipeline/prod-monitoring-compose.yml` | Read in full |
| `docs/superpowers/audits/working/api-responses/deploy-pipeline/prod-db-monitoring-compose.yml` | Read in full |
| `monitoring/config/prometheus/prometheus.yml` | Read in full |
| `monitoring/docker-compose.monitoring.yml` | Read (partial, network/service config) |
| `docker-compose.prod-db-monitoring.yml` | Read in full |

### Priors addressed

| Prior | Status | Finding |
|---|---|---|
| prior-G (alertmanager removed) | Not directly applicable to alloy scope — none of the four `*-vm.alloy` files reference alertmanager. Alloy pushes metrics to Prometheus (remote_write) and logs to Loki; it has no alertmanager integration. Prior-G is a Grafana/Prometheus concern, handled by Branch A/B. Cross-noted below. | — |

### Intentional vs unintentional diff classification

| Diff | Lines that are intentional | Lines classified as findings |
|---|---|---|
| `prod-ap-vm` vs `prod-db-vm` | `vm=ap-vm/db-vm`, log parsing (nginx JSON vs postgres regex), metrics pipeline (AP has push blocks; DB has pull-mode stub), loki URL (hardcoded vs env var) | db-vm missing push pipeline (F-ALLO-06), db-vm label promise unfulfilled (F-ALLO-09), slash-strip relabel absent in prod-ap-vm vs not-applicable in prod-db-vm |
| `prod-ap-vm` vs `staging-ap-vm` | `environment=prod/staging`, X-Scope-OrgID, X-Environment header values | slash-strip rule missing (F-ALLO-01), stage.match missing (F-ALLO-03), stage.drop missing (F-ALLO-04), redis_exporter missing (F-ALLO-05) |
| `prod-db-vm` vs `staging-db-vm` | `environment=prod/staging`, X-Scope-OrgID | slash-strip rule missing (F-ALLO-02) |
| `staging-ap-vm` vs `staging-db-vm` | `vm=ap-vm/db-vm`, log parsing, metrics pipeline, loki URL, X-Scope-OrgID | All intentional role differences (no new findings) |
| `prod-ap-vm` vs `staging-db-vm` (cross-diagonal) | Both env and role differences present | All differences = F-ALLO-01 + F-ALLO-03 + F-ALLO-04 + F-ALLO-05 accumulated |
| `prod-db-vm` vs `staging-ap-vm` (cross-diagonal) | Both env and role differences present | All differences = F-ALLO-02 accumulated |

---

## Cross-branch observations

1. **Branch B (Prometheus+Loki)**: `prometheus.yml` comment says "All application/system metrics are collected by Grafana Alloy and sent to Prometheus via remote_write" but `targets.json` shows only self-monitoring targets — zero Alloy-pushed targets are visible. This confirms either (a) Alloy remote_write is not working end-to-end, or (b) the remote_write receiver is working but Prometheus has received pushes from AP-VM Alloy only (not appearing in scrape targets because remote_write data appears in TSDB, not in `/api/v1/targets`). Branch B should verify whether any time-series with `environment="staging"` or `environment="prod"` exist in Prometheus at all via a PromQL query like `count by (environment) ({__name__=~".+"})`.

2. **Branch A (Grafana)**: The `environment` and `vm` template variables used in dashboards depend on these labels being present in Prometheus. With F-ALLO-06 + F-ALLO-09, DB-VM metrics carry neither label. With F-ALLO-01–04, prod-ap-vm log labels differ from staging. Any dashboard panel with a `{vm="db-vm"}` filter will show No data for both staging and prod environments.

3. **Branch E (Deploy Pipeline)**: The prod-monitoring-compose.yml attaches the monitoring stack to `scholarship_staging_network`. This name is correct for the staging AP-VM but is suspicious for production — it suggests the prod monitoring stack may be connecting to the staging application network rather than a dedicated prod network. This cross-VM network naming issue is outside Branch C scope but affects prod-ap-vm Alloy's ability to reach application containers (cadvisor, node-exporter, etc.) if they are on a different Docker network.
