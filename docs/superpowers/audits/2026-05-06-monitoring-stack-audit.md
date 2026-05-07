# Monitoring Stack Audit — 2026-05-06

**Scope:** monitoring stack + application metric/log interface + deploy pipeline.
**Method:** spec §5.2 (Active Probe + Static Read + Cross-Reference).
**Spec:** [`docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md`](../specs/2026-05-06-monitoring-stack-fix-design.md) (commit `07faa57`).
**Plan:** [`docs/superpowers/plans/2026-05-06-monitoring-stack-audit-phase1.md`](../plans/2026-05-06-monitoring-stack-audit-phase1.md).
**Branch agents:** A (Grafana), B (Prometheus+Loki), C (Alloy+CrossVM), D (App Metrics), E (Deploy Pipeline).
**Branch:** `audit/monitoring-stack-phase1`. **Repo:** `anud18/scholarship-system`.

---

## Executive Summary

| Severity | Count | Allocated to | Description |
|---|---:|---|---|
| **P0** | 11 | Phase 2 | Monitoring is silently lying — alerts to nowhere, dashboards green when broken, deploy says ✅ when it isn't |
| **P1** | 34 | Phase 3 | Monitoring missing data — No-data panels, missing scrape targets, label drift |
| **P2** | 9 | Phase 4 | Cosmetic / hygiene — `or 0` masking, hardcoded sleeps, naming |
| **noted** | 4 | Phase 5+ (out of scope) | SLO, retention, long-term storage |
| **Total** | **58** | — | — |

### Top 3 risks (read this first)

1. **`F-DEPL-03` — deploy workflow has 0 runs on `anud18/scholarship-system`** (P0). Until this is fixed, no Phase 2/3/4 commit actually deploys. Staging Grafana is currently running config from a 6-month-old deploy on the OLD `jotpalch/scholarship-system` repo (last successful run 2025-11-07). This is the **critical-path bottleneck** for the entire phased fix.
2. **prior-G bundle** (`F-PROM-01` + `F-PROM-02` + `F-PROM-03` + `F-GRAF-01` + `F-DEPL-07`, all P0). Alerts fire to nowhere AND aren't even being evaluated: `rule_files` is commented out → all 14 alert rules + 25 recording rules disabled; `alerting:` block commented out → no receiver path; AlertManager datasource still provisioned (HTTP 500); deploy workflow still exports 6 dead `ALERT_*` secrets. The full alert pipeline is silently broken.
3. **`F-DEPL-04` — prod monitoring compose declares `scholarship_staging_network: external: true`** (P0). User-supplied prod snapshot is byte-identical to dev repo. Either prod monitoring is currently failing to start (network not found), or someone manually created a `scholarship_staging_network` on prod-AP-VM as an out-of-band hack. Either way, the IaC lies about what works in production.

### Production-launch verdict

**Not ready.** Production cannot launch with current monitoring state. Concrete blockers:

- Zero prod-environment metrics in Prometheus (`F-PROM-04`, `F-ALLO-06`, `F-ALLO-09`) — production has no observability at all.
- Alerting completely disabled at the Prometheus rule-loader level (`F-PROM-01`).
- Prod monitoring compose references a Docker network that almost certainly doesn't exist on prod (`F-DEPL-04`).
- Deploy pipeline has 0 successful runs on the current repo since migration (`F-DEPL-03`); the IaC-first principle for staging is broken.

**Required clearance for Phase 2 → Phase 3 transition:** all 11 P0 findings remediated and demonstrated via the strengthened deploy health check.

**Required clearance for production launch (Phase 4 exit gate):** all P0+P1 findings (45 total) plus a successful end-to-end synthetic alert test (Grafana → GitHub Issue) per spec §8.

---

## Note on prior-G (alertmanager)

Prior-G surfaces in **four branches** as different aspects of one architectural failure:

- `F-PROM-01` (P0) — `rule_files` directive commented out in `prometheus.yml`; **all 14 alert rules and 25 recording rules are not even loaded**, even before considering whether they have a receiver.
- `F-PROM-02` (P0) — AlertManager datasource still provisioned in Grafana, returns HTTP 500 "Plugin unavailable".
- `F-PROM-03` (P0) — `alerting:` block in `prometheus.yml` commented out, so even if rules loaded they have no receiver.
- `F-GRAF-01` (P0) — Grafana's `handleGrafanaManagedAlerts: true` setting on the dangling alertmanager datasource means Grafana-managed alerts also fail to route.
- `F-DEPL-07` (P0) — Workflow still exports dead `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK` secrets to env vars no service consumes.

The four findings together describe a single architectural failure: rules disabled, datasource dangling, no receiver, dead config. Phase 2 fixes them as one bundle (migrate to Grafana unified alerting + GitHub Issue webhook).

---

## P0 — Monitoring is silently lying

### From Grafana (`working/grafana.md` @ commit `35722b7`)

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


### From Prometheus + Loki (`working/prometheus-loki.md` @ commit `ccfef65`)

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


### From Alloy + Cross-VM (`working/alloy-crossvm.md` @ commit `bcb4ac0`)

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


### From Deploy & Mirror Pipeline (`working/deploy-pipeline.md` @ commit `a604292`)

### F-DEPL-01  [P0]  Health check passes while datasource is returning 500

**Where**: `.github/workflows/deploy-monitoring-stack.yml:77-110`

**Evidence**:
- Active probe: `gh workflow view deploy-monitoring-stack.yml` shows "Total runs 0" in current repo (anud18/scholarship-system). Previous runs in the original repo (jotpalch/scholarship-system) succeeded, and the old-repo-run-19155493587-log.txt fetch returned HTTP 410 (logs expired). The health check step at lines 77-110 only probes `Grafana /api/health`, `Prometheus /-/healthy`, and `Loki /ready` — HTTP-level endpoints that return 200 regardless of datasource state.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:85-106`:
  ```yaml
  if docker exec monitoring_grafana wget --spider -q http://localhost:3000/api/health; then
    echo "✅ Grafana is healthy"
  ...
  if curl -f http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "✅ Prometheus is healthy"
  ...
  if curl -f http://localhost:3100/ready > /dev/null 2>&1; then
    echo "✅ Loki is healthy"
  ```
  No step calls `GET /api/datasources/uid/{uid}/health`, no step inspects Grafana provisioning logs for errors, no step checks alert rule load status.
- Cross-reference: The Grafana alertmanager datasource returns HTTP 500 ("Plugin unavailable") as confirmed by the spec §1 context and prior-G. A deploy that checks only `Grafana /api/health` (which returns 200 `{"database":"ok"}`) would pass its health check step while the alertmanager datasource is broken. The deploy workflow has never caught this class of failure.

**Expected**: The health check step should additionally call `GET /monitoring/api/datasources/uid/{uid}/health` for each provisioned datasource, assert every response is 2xx, and verify Grafana startup logs show no provisioning errors.

**Root cause hypothesis**: The health check was written to verify container liveness only, not Grafana datasource health or provisioning correctness, so any sub-service failure is invisible to CI.

**Remediation owner**: Phase 2

**Suggested fix sketch**:
```bash
# After Grafana starts, check all datasource health
DS_FAILURES=$(docker exec monitoring_grafana \
  wget -qO- "http://localhost:3000/api/datasources" \
  --header "Authorization: Basic $(echo -n admin:$GRAFANA_ADMIN_PASSWORD | base64)" \
  | jq '[.[] | .uid][]' -r | while read uid; do
    STATUS=$(docker exec monitoring_grafana wget -qO- \
      "http://localhost:3000/api/datasources/uid/$uid/health" \
      --header "Authorization: Basic $(echo -n admin:$GRAFANA_ADMIN_PASSWORD | base64)" \
      | jq -r '.status // "error"')
    [ "$STATUS" != "OK" ] && echo "$uid: $STATUS"
  done)
[ -z "$DS_FAILURES" ] || { echo "❌ Datasource failures: $DS_FAILURES"; exit 1; }
```

---


### F-DEPL-02  [P0]  False-positive Prometheus target check silently passes when zero staging targets exist

**Where**: `.github/workflows/deploy-monitoring-stack.yml:248-261`

**Evidence**:
- Active probe: `targets.json` (captured at `api-responses/prometheus-loki/targets.json`) shows exactly 3 active targets, all with `environment="monitoring"` — zero targets have `environment="staging"`. Running the workflow's exact jq expression `[.data.activeTargets[] | select(.labels.environment=="staging") | select(.health!="up")] | length` against this data returns `0`, causing the "All staging targets are UP" message. This is confirmed by Python simulation: `staging_down = 0` even though 0 staging targets exist at all.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:253-260`:
  ```bash
  TARGETS_DOWN=$(curl -s http://localhost:9090/api/v1/targets | jq '[.data.activeTargets[] | select(.labels.environment=="staging") | select(.health!="up")] | length')
  if [ "$TARGETS_DOWN" -eq "0" ]; then
    echo "✅ All staging targets are UP"
  ```
- Cross-reference: The step prints "✅ All staging targets are UP" (and does not exit non-zero — it uses `⚠️ Warning` not `exit 1`) even when Alloy on DB-VM has never registered a target with `environment=staging`. The live Prometheus has only `environment=monitoring` targets (self-monitoring of grafana, loki, prometheus), meaning every past run of this step has silently declared success with zero staging coverage.

**Expected**: The check should first assert that the count of `environment=staging` targets is at least the expected minimum (e.g., node-exporter, postgres-exporter, alloy on DB-VM), then assert none are down. If the count is 0, the step should fail.

**Root cause hypothesis**: The jq filter treats "no targets match" identically to "all matching targets are UP", because `length` of an empty array is 0 in both cases.

**Remediation owner**: Phase 2

**Suggested fix sketch**:
```bash
STAGING_TOTAL=$(curl -s http://localhost:9090/api/v1/targets | jq '[.data.activeTargets[] | select(.labels.environment=="staging")] | length')
STAGING_DOWN=$(curl -s http://localhost:9090/api/v1/targets | jq '[.data.activeTargets[] | select(.labels.environment=="staging") | select(.health!="up")] | length')
MIN_EXPECTED=3  # node-exporter, postgres-exporter, alloy (DB-VM)
if [ "$STAGING_TOTAL" -lt "$MIN_EXPECTED" ]; then
  echo "❌ Only $STAGING_TOTAL staging targets found; expected at least $MIN_EXPECTED"; exit 1
fi
if [ "$STAGING_DOWN" -gt "0" ]; then
  echo "❌ $STAGING_DOWN staging targets are DOWN"; exit 1
fi
echo "✅ $STAGING_TOTAL staging targets all UP"
```

---


### F-DEPL-03  [P0]  Workflow has zero runs in current repo — IaC-first principle broken for staging

**Where**: `.github/workflows/deploy-monitoring-stack.yml` (entire workflow), GitHub Actions run history

**Evidence**:
- Active probe: `gh workflow view deploy-monitoring-stack.yml` output: "Total runs 0". `gh run list --workflow=deploy-monitoring-stack.yml --limit=30` returns `[]`. The workflow file has `workflow_id: 209788291` and is enabled, but has never been triggered in this repository (anud18/scholarship-system).
- Static read: `api-responses/deploy-pipeline/old-repo-deploy-runs.json` shows 10 successful runs in the previous repository (jotpalch/scholarship-system), the most recent at `2025-11-07T01:43:05Z` (commit `d14318a` = "Refactor database configuration"). All subsequent monitoring commits (e.g., the Phase 1 audit branch) have never triggered the workflow in this repo.
- Cross-reference: The workflow triggers on `push` to `main` in `monitoring/**` and on `workflow_dispatch`. The repo was migrated from jotpalch to anud18 — the self-hosted runner is presumably still registered to the old repo or not re-registered. Staging Grafana (`https://ss.test.nycu.edu.tw/monitoring`) is live (per other branches' probes), meaning it was deployed outside the IaC workflow after the repo migration.

**Expected**: Every deploy to staging should be traceable to a CI run. Zero runs means staging config could diverge from this repo at any time with no detection.

**Root cause hypothesis**: The GitHub Actions self-hosted runner was not re-registered to the new repository (anud18/scholarship-system) after repo migration, so no pushes trigger the workflow.

**Remediation owner**: Phase 2 (re-register runner) — also needs a pre-flight check that runner is online before the next fix PR merges.

**Suggested fix sketch**: Re-register the self-hosted runner token under Settings → Actions → Runners in anud18/scholarship-system. Verify with a `workflow_dispatch` trigger. Document in `monitoring/GITHUB_DEPLOYMENT.md` that runner must be re-registered on repo migration.

---


### F-DEPL-04  [P0]  Prod monitoring compose references `scholarship_staging_network` — likely broken on prod AP-VM

**Where**: `monitoring/docker-compose.monitoring.yml:46,75,118,160-162` (dev repo) and `api-responses/deploy-pipeline/prod-monitoring-compose.yml` (user-supplied prod snapshot)

**Evidence**:
- Active probe: User-supplied snapshot `prod-monitoring-compose.yml` (captured from `root@jotp:~/naass/monitoring/docker-compose.monitoring.yml` on prod AP-VM). The file is byte-identical to the dev repo's `monitoring/docker-compose.monitoring.yml`. Both declare:
  ```yaml
  networks:
    scholarship_staging_network:
      external: true
      name: scholarship_staging_network
  ```
  and attach grafana, loki, and prometheus to `scholarship_staging_network`. The network `scholarship_staging_network` is defined as `external: true`, meaning Docker Compose expects this network to already exist on the host.
- Static read: `monitoring/docker-compose.monitoring.yml:160-162`:
  ```yaml
  scholarship_staging_network:
    external: true
    name: scholarship_staging_network
  ```
  The network is created by `docker-compose.staging.yml` in the dev/staging environment. On prod AP-VM, no staging application stack runs, so `scholarship_staging_network` almost certainly does not exist.
- Cross-reference: The prod AP-VM is described as running the production application stack (`docker-compose.prod.yml`), which uses `scholarship_prod_network` (not `scholarship_staging_network`). If monitoring were restarted on prod AP-VM with this compose file, all three monitoring services would fail to start with `network scholarship_staging_network declared as external, but could not be found`.

**Expected**: The prod monitoring compose should reference `scholarship_prod_network` (or no external network, if cross-service DNS is not needed). A separate `docker-compose.prod-monitoring.yml` distinct from the staging version should exist.

**Root cause hypothesis**: The monitoring compose file was written for staging and then deployed to prod without renaming the external network reference, because the prod monitoring stack was set up via manual copy rather than a prod-specific file.

**Remediation owner**: Phase 2

**Suggested fix sketch**: Create `monitoring/docker-compose.prod-monitoring.yml` with `scholarship_prod_network` as the external network, or remove the external network reference from the prod compose if monitoring containers communicate only over `monitoring_network`. Update the mirror and prod-side deploy workflow to use the prod-specific compose file.

---


### F-DEPL-07  [P0]  Dead `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK` env exports — potential Grafana misconfiguration

**Where**: `.github/workflows/deploy-monitoring-stack.yml:62-68`

**Evidence**:
- Active probe: `grep -rn "ALERT_EMAIL\|ALERT_SMTP\|ALERT_SLACK" monitoring/config/grafana/grafana.ini.example` returns 0 matches. The `grafana.ini.example` does not reference these env vars. However, `monitoring/config/alertmanager/alertmanager.yml` (lines 7-10) references `${ALERT_SMTP_SMARTHOST}`, `${ALERT_EMAIL_FROM}`, `${ALERT_SMTP_USER}`, `${ALERT_SMTP_PASSWORD}`, and `monitoring/README.md:158-165` and `monitoring/GITHUB_DEPLOYMENT.md:97-102` document these secrets as valid alert configuration.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:62-68`:
  ```yaml
  export ALERT_EMAIL_FROM="${{ secrets.ALERT_EMAIL_FROM }}"
  export ALERT_SMTP_HOST="${{ secrets.ALERT_SMTP_HOST }}"
  export ALERT_SMTP_PORT="${{ secrets.ALERT_SMTP_PORT }}"
  export ALERT_SMTP_USER="${{ secrets.ALERT_SMTP_USER }}"
  export ALERT_SMTP_PASSWORD="${{ secrets.ALERT_SMTP_PASSWORD }}"
  export ALERT_SLACK_WEBHOOK="${{ secrets.ALERT_SLACK_WEBHOOK }}"
  ```
  AlertManager was removed from the compose stack (commit `57fca5f` / noted in workflow line 108: "Note: AlertManager has been removed from the monitoring stack"). These secrets are exported but never consumed by any running container.
- Cross-reference: Phase 2 decided to use GitHub Issues as the alert receiver (spec §6). These 6 env exports are dead. If the GitHub repository has secrets with these names configured, they expand to real values in the workflow logs (masked, but still processed), creating unnecessary secret surface. If the secrets are not configured, the exports produce empty strings — harmless but confusing to operators reading the workflow.

**Expected**: Remove all 6 dead `ALERT_*` exports once the Phase 2 GitHub Issues receiver is wired. Document in a comment that `ALERT_*` secrets are deprecated.

**Root cause hypothesis**: AlertManager was removed from the compose stack but the workflow's environment setup step was not updated to remove the corresponding secret exports.

**Remediation owner**: Phase 2

**Suggested fix sketch**: Delete lines 62-68 from the workflow (the `export ALERT_EMAIL_FROM` through `export ALERT_SLACK_WEBHOOK` block) after Phase 2 wires the GitHub Issues contact point.

---


---

## P1 — Monitoring missing data

### From Grafana (`working/grafana.md` @ commit `35722b7`)

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


### From Prometheus + Loki (`working/prometheus-loki.md` @ commit `ccfef65`)

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


### From Alloy + Cross-VM (`working/alloy-crossvm.md` @ commit `bcb4ac0`)

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


### From Application Metrics & Logs (`working/app-metrics.md` @ commit `486508f`)

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


### From Deploy & Mirror Pipeline (`working/deploy-pipeline.md` @ commit `a604292`)

### F-DEPL-05  [P1]  `paths:` filter omits `docker-compose.staging-db-monitoring.yml`

**Where**: `.github/workflows/deploy-monitoring-stack.yml:7-9`

**Evidence**:
- Active probe: File exists at repo root: `ls docker-compose.staging-db-monitoring.yml → FILE_EXISTS`. It is used in job 2 (deploy-staging-db-monitoring) at line 219: `scp ... ./docker-compose.staging-db-monitoring.yml ...`. Changes to this file would affect DB-VM monitoring deployment but would not trigger the workflow.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:6-9`:
  ```yaml
  paths:
    - 'monitoring/**'
    - '.github/workflows/deploy-monitoring-stack.yml'
  ```
  `docker-compose.staging-db-monitoring.yml` is at the repo root (not under `monitoring/`), so it is not covered by the `monitoring/**` glob.
- Cross-reference: If a developer changes only `docker-compose.staging-db-monitoring.yml` (e.g., to fix a DB-VM exporter port), the workflow does not auto-trigger. The change sits in main without being deployed to staging until someone manually triggers `workflow_dispatch` or pushes another `monitoring/**` change.

**Expected**: `paths:` should include `'docker-compose.staging-db-monitoring.yml'` so that changes to the DB-VM compose file trigger a redeploy.

**Root cause hypothesis**: The file was added at the repo root after the `paths:` filter was written, and the filter was not updated.

**Remediation owner**: Phase 4 (spec §8 lists this fix explicitly)

**Suggested fix sketch**:
```yaml
paths:
  - 'monitoring/**'
  - 'docker-compose.staging-db-monitoring.yml'
  - '.github/workflows/deploy-monitoring-stack.yml'
```

---


### F-DEPL-06  [P1]  `grafana.ini.example` → `grafana.ini` copy is one-shot; subsequent changes silently ignored

**Where**: `.github/workflows/deploy-monitoring-stack.yml:38-45`

**Evidence**:
- Active probe: Commit `9175ac0` ("Security: Remove grafana.ini from version control while maintaining deployment functionality") introduced the `if [ ! -f ... ]` guard. After that commit, `grafana.ini` on the runner was never updated by subsequent runs.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:38-45`:
  ```yaml
  if [ ! -f /opt/scholarship/monitoring/config/grafana/grafana.ini ]; then
    echo "Creating Grafana configuration from example..."
    cp /opt/scholarship/monitoring/config/grafana/grafana.ini.example \
       /opt/scholarship/monitoring/config/grafana/grafana.ini
    echo "✅ Grafana configuration initialized"
  else
    echo "✅ Grafana configuration already exists"
  fi
  ```
  Once `grafana.ini` exists, the copy is skipped forever. Any change to `grafana.ini.example` (e.g., adding a new section, fixing a parameter) is silently ignored on redeploy.
- Cross-reference: `monitoring/config/grafana/grafana.ini.example` has 264 lines of configuration (verified by Read). A fix to any of those lines — for example, correcting `root_url`, adjusting session parameters, or enabling a feature toggle — would not take effect on the running Grafana instance until someone manually deletes the live `grafana.ini` on the runner and re-runs the workflow.

**Expected**: The deploy step should compare the example's content hash to the deployed file and replace if changed, or always overwrite with the example (with a note that operator-local overrides must be re-applied). Alternatively, use environment variables exclusively (as Grafana supports) and remove the `grafana.ini` file requirement.

**Root cause hypothesis**: The one-shot copy was designed to prevent overwriting operator secrets embedded in `grafana.ini`, but the result is that the example and the deployed file can drift indefinitely.

**Remediation owner**: Phase 2 (config drift is P1 but the root cause — secrets in ini file — is a P1 architectural issue that blocks any clean fix)

**Suggested fix sketch**:
```bash
# Always propagate the example, overwriting the deployed copy.
# Secrets (admin_user, admin_password, secret_key) are read from env vars
# by Grafana anyway (GF_SECURITY_* env vars set in compose), so the
# grafana.ini does not need to contain secrets.
cp /opt/scholarship/monitoring/config/grafana/grafana.ini.example \
   /opt/scholarship/monitoring/config/grafana/grafana.ini
echo "✅ Grafana configuration updated from example"
```

---


### F-DEPL-09  [P1]  Mirror strips all `*.md` including `monitoring/GITHUB_DEPLOYMENT.md` and `monitoring/PRODUCTION_RUNBOOK.md`

**Where**: `.github/workflows/mirror-to-production.yml:341-344` and spec §9 principle

**Evidence**:
- Active probe: `grep -n '\.md' mirror-to-production.yml:341` shows:
  ```bash
  find . -type f -name "*.md" 2>/dev/null | xargs -r git rm -f 2>/dev/null || true
  ```
  This `find` starts at `.` (repo root) and matches ALL `.md` files, including files under `monitoring/`.
- Static read: Files confirmed to exist and be stripped:
  - `monitoring/GITHUB_DEPLOYMENT.md` (deployment guide including self-hosted runner setup, secrets reference)
  - `monitoring/PRODUCTION_RUNBOOK.md` (health check commands, incident response)
  - `monitoring/README.md` (architecture overview)
  These three files contain operational knowledge that prod-side maintainers need.
- Cross-reference: Spec §9 cross-phase engineering principle states: "Documentation lives under `monitoring/**/*.md`. Repo-root `*.md` files are stripped by `mirror-to-production.yml`, so prod-side maintainers cannot see them. Anything prod-relevant goes inside `monitoring/`." The spec correctly anticipates that docs should survive in `monitoring/` — but the actual mirror strips them too. The spec's principle is violated by the mirror implementation.

**Expected**: Documentation under `monitoring/` should survive the mirror. The strip rule should exclude `./monitoring/**/*.md` (or include `monitoring/` docs in a preservation list).

**Root cause hypothesis**: The `find . -type f -name "*.md"` strip rule was written to remove all repo-root documentation (`README.md`, `CONTRIBUTING.md`, etc.) without considering that `monitoring/*.md` files are operationally necessary in prod.

**Remediation owner**: Phase 2 (the missing docs prevent prod operators from following deployment and runbook procedures)

**Suggested fix sketch**: Change the strip rule to exclude `monitoring/`:
```bash
find . -type f -name "*.md" -not -path "./monitoring/*" 2>/dev/null | xargs -r git rm -f 2>/dev/null || true
```

---


### F-DEPL-10  [P1]  `PRODUCTION_SYNC_GUIDE.md` documents wrong secret name (`PRODUCTION_SYNC_PAT` vs actual `GH_PAT`)

**Where**: `.github/PRODUCTION_SYNC_GUIDE.md:68,389,394` vs `.github/workflows/mirror-to-production.yml:37,47,91`

**Evidence**:
- Active probe: `grep -n "GH_PAT\|PRODUCTION_SYNC_PAT"` on both files confirms: the workflow uses `secrets.GH_PAT` in 4 places (lines 37, 47, 48, 91, 765); the PRODUCTION_SYNC_GUIDE.md instructs operators to create a secret named `PRODUCTION_SYNC_PAT` (lines 68, 389, 394).
- Static read:
  - `PRODUCTION_SYNC_GUIDE.md:68`: `| PRODUCTION_SYNC_PAT | ghp_xxxxxxxxxxxx | Personal Access Token from Step 2 |`
  - `PRODUCTION_SYNC_GUIDE.md:389`: `### Issue: "PRODUCTION_SYNC_PAT not configured"`
  - `mirror-to-production.yml:47-48`: `if [ -z "${{ secrets.GH_PAT }}" ]; then echo "::error::GH_PAT secret not configured"`
- Cross-reference: An operator following the guide would create a secret named `PRODUCTION_SYNC_PAT`. The workflow checks for `GH_PAT`. The workflow would immediately fail at step "Check for required secrets" with "GH_PAT secret not configured", even though the secret exists under the wrong name. The guide's troubleshooting section would also not help (it says check for `PRODUCTION_SYNC_PAT`, not `GH_PAT`).

**Expected**: The guide and the workflow must use the same secret name. Preferred: rename the guide to match the workflow (`GH_PAT`), or rename the workflow to match the guide (`PRODUCTION_SYNC_PAT`) — consistency either way.

**Root cause hypothesis**: The secret was renamed from `PRODUCTION_SYNC_PAT` to `GH_PAT` in the workflow at some point but the documentation was not updated, or vice versa.

**Remediation owner**: Phase 2

**Suggested fix sketch**: Update `PRODUCTION_SYNC_GUIDE.md` to replace all occurrences of `PRODUCTION_SYNC_PAT` with `GH_PAT` (3 locations).

---


### F-DEPL-11  [P1]  No `deploy-monitoring-stack-prod.yml.example` in `.github/production-workflows-examples/` — prod deploy is a blind spot

**Where**: `.github/production-workflows-examples/` (directory listing) and `monitoring/GITHUB_DEPLOYMENT.md`

**Evidence**:
- Active probe: `ls .github/production-workflows-examples/` output:
  ```
  auto-tag-on-merge.yml
  backup.yml
  deploy.yml
  health-check.yml
  IT-BACKUP-TRANSFER-GUIDE.md
  README.md
  SECRETS-SETUP-GUIDE.md
  setting-env.yml
  ```
  No `deploy-monitoring-stack-prod.yml.example` or any monitoring-specific workflow example exists. `grep -rn "deploy-monitoring\|monitoring-stack" .github/production-workflows-examples/` returns 0 matches.
- Static read: `monitoring/GITHUB_DEPLOYMENT.md` describes the staging deploy workflow in detail. It does not provide a corresponding template for the prod-side deploy workflow. The spec (§10) states: "Prod-side `deploy-monitoring-stack-prod.yml` is not visible from this repo. Audit treats this as a known gap." The directory that exists to house prod-side examples (`production-workflows-examples/`) contains no monitoring workflow.
- Cross-reference: The spec §10 states the prod-side deploy workflow "lives only in the private prod repo as `deploy-monitoring-stack-prod.yml`". With no example in this repo and no documentation for how the prod workflow should differ from staging, prod-side maintainers have no guidance. Additionally, `.github/production-workflows-examples/` is itself stripped by the mirror (line 255: `git rm -rf .github/production-workflows-examples/`), so even if an example were added here, prod maintainers in the prod repo would not see it.

**Expected**: A `deploy-monitoring-stack-prod.yml.example` should exist in `.github/production-workflows-examples/` documenting the prod-equivalent deploy workflow. The example should note prod-specific differences (e.g., `scholarship_prod_network` instead of `scholarship_staging_network`, prod secrets names, prod runner label). Additionally, the `monitoring/GITHUB_DEPLOYMENT.md` should include a section on prod-specific deployment.

**Root cause hypothesis**: The prod deploy workflow was created directly in the private prod repo without a corresponding example or documentation being added to the dev repo.

**Remediation owner**: Phase 2 (this is marked as a "blind spot" per spec §5.1 — no access to prod workflow content; owner must provide the prod workflow content for review)

**Suggested fix sketch**: Create `.github/production-workflows-examples/deploy-monitoring-stack-prod.yml.example` based on the staging workflow with prod-specific parameter differences documented inline. Note: this directory is stripped by mirror, so also add a summary in `monitoring/GITHUB_DEPLOYMENT.md` (which should survive mirror per F-DEPL-09 fix).

---


### F-DEPL-12  [P1]  AP-VM `/tmp/monitoring-images/` tar files accumulate across runs — no local cleanup

**Where**: `.github/workflows/deploy-monitoring-stack.yml:143-170`

**Evidence**:
- Active probe: Not directly observable from the local audit, but static analysis is conclusive: the "Export monitoring images for DB-VM" step at lines 143-157 creates `/tmp/monitoring-images/` with three `.tar` files (alloy.tar ~600MB, node-exporter.tar ~25MB, postgres-exporter.tar ~60MB — typical sizes). The "Import monitoring images on DB-VM" step at lines 178-194 runs `rm -rf /tmp/monitoring-images` inside the SSH heredoc (remote side, DB-VM). No `rm -rf /tmp/monitoring-images` command exists on the AP-VM (runner) side.
- Static read: Lines 143-170 of the workflow show three steps: "Export monitoring images for DB-VM" (creates /tmp/monitoring-images on AP-VM), "Transfer monitoring images to DB-VM" (scp to remote), "Import monitoring images on DB-VM" (loads + rm -rf on DB-VM only). The AP-VM cleanup is absent.
- Cross-reference: Each workflow run deposits approximately 700MB of tar files in AP-VM's `/tmp/`. Over 10 runs (historical count from old-repo-deploy-runs.json), this would accumulate ~7GB. If AP-VM `/tmp/` fills, future runs fail at the `docker save` step with "no space left on device".

**Expected**: Add a cleanup step after the transfer that runs `rm -rf /tmp/monitoring-images` on the AP-VM (runner) side. Alternatively, add `if: always()` cleanup at the job level.

**Root cause hypothesis**: The remote cleanup was added but the local (runner-side) cleanup was forgotten, likely because the author focused on the remote side.

**Remediation owner**: Phase 2 (risk of disk exhaustion is operational)

**Suggested fix sketch**:
```yaml
- name: Cleanup monitoring image tar files (AP-VM)
  if: always()
  run: rm -rf /tmp/monitoring-images
```

---


### F-DEPL-13  [P1]  `docker-compose.prod-db-monitoring.yml` preserved by mirror but prod-side deploy workflow is unknown — chain integrity unverifiable

**Where**: `.github/workflows/mirror-to-production.yml:280-282` and `docker-compose.prod-db-monitoring.yml`

**Evidence**:
- Active probe: `ls docker-compose.prod-db-monitoring.yml → IN_DEV_REPO` (file exists). Mirror workflow at line 280-282 explicitly preserves it:
  ```bash
  if [[ "$file" == "docker-compose.prod-db-monitoring.yml" ]]; then
    echo "::notice::Preserving $file (production file)"
  ```
  User-supplied prod snapshot `api-responses/deploy-pipeline/prod-db-monitoring-compose.yml` is byte-identical to the dev repo's copy (source annotation confirms: "Captured: 2026-05-06 during Phase 1 audit Stage 0.4"). The prod DB-VM's Alloy reads `./monitoring/config/alloy/prod-db-vm.alloy` — that path works only if the prod-side deploy workflow ships the `monitoring/config/alloy/` tree to the DB-VM, which is not visible.
- Static read: `docker-compose.prod-db-monitoring.yml:19` mounts `./monitoring/config/alloy/prod-db-vm.alloy:/etc/alloy/config.alloy:ro`. This mount works only if the file exists at `./monitoring/config/alloy/prod-db-vm.alloy` relative to where the compose file is run from. On the prod DB-VM, the alloy config must have been deployed separately (since the DB-VM receives the compose file but not the monitoring config tree via the staging workflow — the staging workflow ships `staging-db-vm.alloy` via SCP at line 229).
- Cross-reference: No prod-side equivalent of lines 226-231 (SCP of `staging-db-vm.alloy` to DB-VM) is visible. If the prod deploy workflow omits this SCP step, the Alloy container on prod DB-VM starts with no config file, silently logs errors, and collects no metrics.

**Expected**: The prod-side deploy workflow should SCP `monitoring/config/alloy/prod-db-vm.alloy` to the prod DB-VM before starting the compose stack. This should be documented in `monitoring/GITHUB_DEPLOYMENT.md`.

**Root cause hypothesis**: The prod-side workflow is a blind spot — its content is unknown from this repo. The chain of `docker-compose.prod-db-monitoring.yml` → alloy config file → prod deploy workflow cannot be fully verified.

**Remediation owner**: Phase 2 (requires prod repo access; mark as prod-side blind spot pending access)

**Suggested fix sketch**: Pending prod repo access. Document the required alloy config SCP step in `monitoring/GITHUB_DEPLOYMENT.md` so it is visible to prod-side maintainers.

---


---

## P2 — Cosmetic / hygiene

### From Grafana (`working/grafana.md` @ commit `35722b7`)

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


### From Prometheus + Loki (`working/prometheus-loki.md` @ commit `ccfef65`)

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


### From Application Metrics & Logs (`working/app-metrics.md` @ commit `486508f`)

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


### From Deploy & Mirror Pipeline (`working/deploy-pipeline.md` @ commit `a604292`)

### F-DEPL-08  [P2]  Hardcoded `sleep 60` and `sleep 30` — should use readiness polling

**Where**: `.github/workflows/deploy-monitoring-stack.yml:74-75` and `250-251`

**Evidence**:
- Active probe: Not applicable (static analysis finding). Both sleeps are unconditional fixed waits.
- Static read:
  - Line 74-75: `echo "Waiting for services to start..."; sleep 60`
  - Line 250-251: `echo "Waiting for metrics to be collected..."; sleep 30`
  Both are inside `run:` blocks with no retry logic.
- Cross-reference: The `sleep 60` is followed by health checks that could succeed in 10s on a warm host or fail even after 60s if the host is slow. The `sleep 30` before `Verify staging metrics` is arbitrary — metrics collection latency depends on Alloy scrape interval and Prometheus scrape interval, both of which are configurable. The spec (§8) explicitly calls these out as P2 to replace with readiness polling.

**Expected**: Replace `sleep 60` with a poll loop that checks `Grafana /api/health` every 5 seconds until it returns 200 (max 120s timeout). Replace `sleep 30` with a poll loop that checks Prometheus target count until `environment=staging` count > 0 (max 90s).

**Root cause hypothesis**: Hardcoded sleeps are simpler to write and work "most of the time" on consistent hardware; readiness polling was deferred.

**Remediation owner**: Phase 4 (spec §8 explicitly lists this)

**Suggested fix sketch**:
```bash
# Replace sleep 60 with:
for i in $(seq 1 24); do
  docker exec monitoring_grafana wget --spider -q http://localhost:3000/api/health && break
  echo "Waiting for Grafana... ($i/24)"
  sleep 5
done || { echo "❌ Grafana did not start in 120s"; exit 1; }
```

---


---

## Cross-VM / Cross-Environment Matrix

Legend: `✓` = affected, `—` = not affected, `?` = blind spot (no read access). Columns abbreviated: `s-ap` = staging-AP-VM, `s-db` = staging-DB-VM, `p-ap` = prod-AP-VM, `p-db` = prod-DB-VM.

### Scope-class summary

| Scope class | s-ap | s-db | p-ap | p-db | Findings |
|---|:-:|:-:|:-:|:-:|---|
| Grafana provisioning (config shared, runs on AP-VM only) | ✓ | — | ✓ | — | F-GRAF-01, 06, 07, 11, 12 |
| Dashboard PromQL with `$environment` / `$vm` filters | ✓ | ✓ | ✓ | ✓ | F-GRAF-02, 03, 04, 05, 08, 09, 10 |
| Prometheus / Loki config (runs on AP-VM, config shared) | ✓ | — | ✓ | — | F-PROM-01, 02, 03, 06, 10, 11, 12, 13 |
| Cross-VM metric pipeline (DB-VM exporters, AP-VM ingest) | — | ✓ | — | ✓ | F-PROM-05, 07, 09; F-ALLO-06, 09; F-APP-03 |
| Prod-only operational gap (zero metrics) | — | — | ✓ | ✓ | F-PROM-04 |
| AP-VM Alloy drift (prod-ap missing changes from staging-ap) | — | — | ✓ | — | F-ALLO-01, 03, 04, 05 |
| DB-VM Alloy drift (prod-db missing changes from staging-db) | — | — | — | ✓ | F-ALLO-02 |
| AP-VM Alloy fragility (architectural, both envs) | ✓ | — | ✓ | — | F-ALLO-07 |
| DB-VM Alloy fragility (env-var unguarded, both envs) | — | ✓ | — | ✓ | F-ALLO-08 |
| Backend metrics interface (code shared; affects each env's backend) | ✓ | — | ✓ | — | F-APP-01, 02, 04, 05, 06, 07 |
| Deploy workflow staging-side | ✓ | ✓ | — | — | F-DEPL-01, 02, 05, 06, 07, 08, 12 |
| Repo migration (deploy workflow not yet wired on `anud18`) | ✓ | ✓ | ✓ | ✓ | F-DEPL-03 |
| Prod monitoring compose external network | — | — | ✓ | — | F-DEPL-04 |
| Mirror workflow & docs gap | — | — | ✓ | ✓ | F-DEPL-09, 10 |
| Prod-side workflow blind spots | — | — | ? | ? | F-DEPL-11, 13 |

### Per-finding rows (54 non-noted findings)

| Finding | Sev | s-ap | s-db | p-ap | p-db | One-liner |
|---|:-:|:-:|:-:|:-:|:-:|---|
| F-GRAF-01 | P0 | ✓ | — | ✓ | — | AlertManager datasource HTTP 500 |
| F-GRAF-02 | P1 | ✓ | ✓ | ✓ | ✓ | DB-VM not in Prometheus → pg/minio panels No-data |
| F-GRAF-03 | P1 | ✓ | — | ✓ | — | `http_errors_total` does not exist |
| F-GRAF-04 | P1 | ✓ | — | ✓ | — | `db_query_duration_seconds_bucket` does not exist |
| F-GRAF-05 | P1 | ✓ | ✓ | ✓ | ✓ | `$environment` dropdown includes `monitoring` |
| F-GRAF-06 | P2 | ✓ | — | ✓ | — | `or 0` masks Backend Error Rate as zero |
| F-GRAF-07 | P2 | ✓ | — | ✓ | — | `or 0` masks Redis Hit Ratio |
| F-GRAF-08 | P1 | ✓ | — | ✓ | — | `nginx_http_requests_total` no `status` label |
| F-GRAF-09 | P1 | ✓ | ✓ | ✓ | ✓ | `$vm` hard-coded as `ap-vm,db-vm` static list |
| F-GRAF-10 | P1 | ✓ | — | ✓ | — | `scholarship_applications_total`/`email_sent_total` absent |
| F-GRAF-11 | P2 | ✓ | — | ✓ | — | `allowUiUpdates: true` → `provisioned: false` |
| F-GRAF-12 | P2 | ✓ | — | ✓ | — | `Logs` folder provider configured but unused |
| F-PROM-01 | P0 | ✓ | — | ✓ | — | `rule_files` commented out — 14+25 rules disabled |
| F-PROM-02 | P0 | ✓ | — | ✓ | — | AlertManager datasource HTTP 500 (overlap with F-GRAF-01) |
| F-PROM-03 | P0 | ✓ | — | ✓ | — | `alerting:` block commented out |
| F-PROM-04 | P0 | — | — | ✓ | ✓ | Zero prod-environment metrics in TSDB |
| F-PROM-05 | P1 | — | ✓ | — | ✓ | DB-VM not scraped — postgres-exporter never reaches Prom |
| F-PROM-06 | P1 | ✓ | — | ✓ | — | Recording rules disabled (no dashboard uses them anyway) |
| F-PROM-07 | P1 | ✓ | ✓ | ✓ | ✓ | Alert rule references non-existent `staging-db-minio` job |
| F-PROM-08 | P1 | ✓ | — | ✓ | — | Alert references `nginx_http_request_duration_seconds_bucket` (absent) |
| F-PROM-09 | P1 | — | ✓ | — | ✓ | Recording rule references `pg_stat_statements_mean_exec_time_bucket` (absent) |
| F-PROM-10 | P1 | ✓ | — | ✓ | — | Loki `limits.yml` never loaded (no `runtime_config:`) |
| F-PROM-11 | P1 | ✓ | — | ✓ | — | `/api/v1/runtimeinfo` 404 (admin API disabled — debunked) |
| F-PROM-12 | P1 | ✓ | — | ✓ | — | `external_labels` orphan |
| F-PROM-13 | P2 | ✓ | — | ✓ | — | Self-monitor targets carry no `vm` label |
| F-ALLO-01 | P1 | — | — | ✓ | — | prod-ap slash-strip relabel missing |
| F-ALLO-02 | P1 | — | — | — | ✓ | prod-db slash-strip relabel missing |
| F-ALLO-03 | P1 | — | — | ✓ | — | prod-ap `stage.match` nginx-only gate missing |
| F-ALLO-04 | P1 | — | — | ✓ | — | prod-ap health-check / nginx-status `stage.drop` missing |
| F-ALLO-05 | P1 | — | — | ✓ | — | prod-ap missing redis_exporter scrape job |
| F-ALLO-06 | P1 | — | ✓ | — | ✓ | DB-VM Alloy has no `prometheus.remote_write` block |
| F-ALLO-07 | P1 | ✓ | — | ✓ | — | AP-VM remote_write URL hardcoded vs DB-VM env-driven |
| F-ALLO-08 | P1 | — | ✓ | — | ✓ | `MONITORING_SERVER_URL` unguarded at DB-VM deploy |
| F-ALLO-09 | P0 | — | ✓ | — | ✓ | DB-VM comment promises Prom relabel that doesn't exist |
| F-APP-01 | P1 | ✓ | — | ✓ | — | Backend metrics reach 0 Prometheus series |
| F-APP-02 | P1 | ✓ | — | ✓ | — | Backend Error Rate panel — pipeline gap masked by `or 0` |
| F-APP-03 | P1 | — | ✓ | — | ✓ | postgres-exporter scrape job absent from `prometheus.yml` |
| F-APP-04 | P1 | ✓ | — | ✓ | — | `db_query_duration_seconds` defined but never `.observe()`'d |
| F-APP-05 | P2 | ✓ | — | ✓ | — | `/metrics` reachable from public network (no auth + host port 8000) |
| F-APP-06 | P2 | ✓ | — | ✓ | — | 13 metrics in `core/metrics.py` never instrumented |
| F-APP-07 | P2 | ✓ | — | ✓ | — | `or 0` in Backend Error Rate panel hides No-data |
| F-DEPL-01 | P0 | ✓ | ✓ | — | — | Health check pings only Grafana/Prom/Loki, ignores datasource health |
| F-DEPL-02 | P0 | ✓ | ✓ | — | — | False-positive `select(.health!="up") \| length == 0` trap |
| F-DEPL-03 | P0 | ✓ | ✓ | ✓ | ✓ | Workflow has 0 runs on current repo (post-migration) |
| F-DEPL-04 | P0 | — | — | ✓ | — | Prod compose declares `scholarship_staging_network` external |
| F-DEPL-05 | P1 | ✓ | ✓ | — | — | `paths:` filter omits `docker-compose.staging-db-monitoring.yml` |
| F-DEPL-06 | P1 | ✓ | — | — | — | `grafana.ini.example` one-shot copy guard |
| F-DEPL-07 | P0 | ✓ | — | ? | ? | Dead `ALERT_*` env exports (prod-side blind spot) |
| F-DEPL-08 | P2 | ✓ | ✓ | — | — | Hardcoded `sleep 60` / `sleep 30` |
| F-DEPL-09 | P1 | — | — | ✓ | ✓ | Mirror strips `monitoring/*.md` |
| F-DEPL-10 | P1 | — | — | ✓ | ✓ | `PRODUCTION_SYNC_GUIDE.md` references wrong secret name |
| F-DEPL-11 | P1 | — | — | ? | ? | No prod-deploy workflow example exists |
| F-DEPL-12 | P1 | ✓ | — | — | — | AP-VM `/tmp/monitoring-images/` tar files never cleaned |
| F-DEPL-13 | P1 | — | — | ? | ? | Prod-DB Alloy config SCP chain unverifiable |

---

## Noted but not fixing (future Phase 5+)

### From Prometheus + Loki (`working/prometheus-loki.md` @ commit `ccfef65`)

### F-PROM-14  [noted]  No Prometheus remote_write to long-term storage — 15-day TSDB retention only

**Where**: `monitoring/docker-compose.monitoring.yml:111-116` and `monitoring/config/prometheus/prometheus.yml`

**Evidence**:
- Active probe: configuration-only finding (no live probe applicable for noted-scope items per spec §5.4); see Static read below.
- Static read: Prometheus flags: `--storage.tsdb.retention.time=15d`. No `remote_write:` block in `prometheus.yml`.
- Cross-reference: Production systems typically forward to Thanos/Cortex/Grafana Cloud for long-term storage. None configured.

**Expected**: Out of scope for this audit (no SLO/retention policy defined — see spec §3 non-goals).

**Root cause hypothesis**: N/A — accepted omission at this time.

**Remediation owner**: Phase 5+ (out of scope).

**Suggested fix sketch**: Consider Grafana Cloud free tier or Thanos sidecar for long-term metrics retention beyond 15 days.

---


### From Alloy + Cross-VM (`working/alloy-crossvm.md` @ commit `bcb4ac0`)

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


### From Application Metrics & Logs (`working/app-metrics.md` @ commit `486508f`)

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


### From Deploy & Mirror Pipeline (`working/deploy-pipeline.md` @ commit `a604292`)

### F-DEPL-14  [noted]  `mirror-to-production.yml` describes "Automatic Sync" in `PRODUCTION_SYNC_GUIDE.md` but workflow is manual-only

**Where**: `.github/PRODUCTION_SYNC_GUIDE.md:125-130` vs `.github/workflows/mirror-to-production.yml:3-4`

**Evidence**:
- Active probe: `gh run list --workflow=mirror-to-production.yml --limit=10` shows 5 runs total, all `event: workflow_dispatch` (manual). No `push`-triggered runs exist.
- Static read: `mirror-to-production.yml:3-4`: `on: workflow_dispatch:` — the only trigger. `PRODUCTION_SYNC_GUIDE.md:125-130`: "### Automatic Sync (Recommended) — Every time you push to the `main` branch in the development repo: ✅ Workflow detects the push..."
- Cross-reference: The guide describes automatic push-triggered sync, but the workflow only has `workflow_dispatch`. The guide's "Automatic Sync" section is misleading. This is a documentation inaccuracy, not a functional bug (the manual-only design is intentional per spec §10), so it is `noted` rather than P1.

**Expected**: The guide should describe the workflow as manual-only (consistent with spec §10 which says "Mirror is manually triggered").

**Root cause hypothesis**: The guide was written before the decision to require human review of each prod sync (and was not updated after that decision).

**Remediation owner**: Phase 4 (documentation only; no operational impact since all runs are already manual)

**Suggested fix sketch**: Update `PRODUCTION_SYNC_GUIDE.md` section "Automatic Sync (Recommended)" to "Manual Sync (Required)" and remove the statement about automatic detection on push.

---


---

## Reproduction Artifacts

All probe outputs and screenshots are under `docs/superpowers/audits/working/`.

### Screenshots (Stage 0.4 baseline)

- 8 Grafana dashboards: `working/screenshots/grafana/dashboard-*.png`
- Grafana alerting list: `working/screenshots/grafana/alerting-list.png`

### API responses

- Grafana datasource health: `working/api-responses/grafana/datasources-health.json`
- Grafana dashboard JSON × 8: `working/api-responses/grafana/dashboard-*.json`
- Prometheus targets / rules / runtimeinfo: `working/api-responses/prometheus-loki/*.json`
- Alloy pairwise diffs (6) + block-summary: `working/api-responses/alloy-crossvm/*`
- Backend metric inventory: `working/api-responses/app-metrics/metric-inventory.md`
- Deploy run history (current repo + old repo): `working/api-responses/deploy-pipeline/*-runs.json`
- Migration context: `working/api-responses/deploy-pipeline/MIGRATION-CONTEXT.md`
- User-supplied prod compose snapshots: `working/api-responses/deploy-pipeline/prod-*compose.yml`

### Per-branch raw working files

- `working/grafana.md` (commit `35722b7`)
- `working/prometheus-loki.md` (commit `ccfef65`)
- `working/alloy-crossvm.md` (commit `bcb4ac0`)
- `working/app-metrics.md` (commit `486508f`)
- `working/deploy-pipeline.md` (commit `a604292`)
- `working/api-responses/deploy-pipeline/MIGRATION-CONTEXT.md` (commit `38b7940`)

---

## Recommended Phase ordering and entry conditions for Phase 2

### Phase 2 must clear (P0 set, in this strict order)

The first sub-task of Phase 2 is unconditional: **without `F-DEPL-03` cleared, every other fix is theoretical** because nothing actually deploys.

1. **`F-DEPL-03` — wire deploy workflow on `anud18/scholarship-system`** (BLOCKING). Re-register self-hosted runner, configure 8 GitHub secrets (4 known, 4 supplied by user — see `docs/superpowers/audits/working/api-responses/deploy-pipeline/MIGRATION-CONTEXT.md`), trigger one `workflow_dispatch` test, confirm both jobs succeed. **Until this passes, halt Phase 2 work.**
2. **prior-G bundle** (`F-PROM-01`, `F-PROM-02`, `F-PROM-03`, `F-GRAF-01`, `F-DEPL-07`). Single PR:
   - Delete `monitoring/config/alertmanager/` directory entirely.
   - Delete the `AlertManager` block at `monitoring/config/grafana/provisioning/datasources/datasources.yml:109-121`.
   - Delete (don't just uncomment) `alerting:` block in `monitoring/config/prometheus/prometheus.yml`.
   - Re-enable `rule_files:` for `recording-rules/*.yml` (since recording rules don't need a receiver).
   - Migrate the 14 alert rules in `basic-alerts.yml` to Grafana unified-alerting provisioning at `monitoring/config/grafana/provisioning/alerting/*.yml`.
   - Add Grafana contact point pointing at a new `.github/workflows/monitoring-alert-issue.yml` workflow that listens on `repository_dispatch`. Workflow de-dupes by alert name (one open issue per alert; subsequent fires re-open + comment) and tags `monitoring-alert`, `env:staging|prod`, `severity:warning|critical`.
   - Remove the 6 dead `ALERT_*` exports from `deploy-monitoring-stack.yml:62-68`.
   - Update `monitoring/PRODUCTION_RUNBOOK.md`, `monitoring/README.md`, `monitoring/GITHUB_DEPLOYMENT.md` to remove AlertManager references (cross-branch observations from Branch E).
3. **`F-DEPL-04` — fix prod compose external network reference**. Either (a) create `monitoring/docker-compose.prod-monitoring.yml` with `scholarship_prod_network` external, or (b) remove the external network attachment entirely if monitoring containers communicate only over `monitoring_network`. Document the rationale in `monitoring/PRODUCTION_RUNBOOK.md`.
4. **`F-DEPL-01`, `F-DEPL-02` — strengthen deploy health check**. Add steps to `deploy-monitoring-stack.yml` that:
   - Iterate every Grafana datasource and assert `/health` returns 2xx.
   - Assert non-zero count of `environment=staging` targets exist before checking `health!="up"` (kills the false-positive trap).
   - Tail Grafana startup log for provisioning errors and fail if any found.
   - Assert no alert rules failed to load.
5. **`F-ALLO-09`** — write the missing relabel pipeline (either in `prometheus.yml` scrape jobs or in DB-VM Alloy `prometheus.relabel`). Without this, DB-VM metrics arrive without the `environment` / `vm` labels dashboards depend on.
6. **`F-DEPL-09`, `F-DEPL-10` — fix mirror workflow**. Exclude `monitoring/**/*.md` from the strip rule so prod-side maintainers can see runbooks. Update `PRODUCTION_SYNC_GUIDE.md` to use `GH_PAT` consistently (3 occurrences).
7. **`F-DEPL-12` — add tar cleanup** on the runner side (one-line fix; trivial but operational).

### Phase 3 must clear (P1 set)

After Phase 2 lands and is observable in staging via the strengthened health check, Phase 3 fixes the remaining 34 P1 findings. Group:

- **Cross-VM metric pipeline** (`F-PROM-05`, `F-APP-03`, `F-ALLO-06`): wire DB-VM exporters into the metric flow (recommend push-mode via DB-VM Alloy `prometheus.remote_write`, mirroring AP-VM).
- **Backend instrumentation gaps** (`F-APP-01`, `F-APP-02`, `F-APP-04`, `F-GRAF-03`, `F-GRAF-04`, `F-GRAF-10`): add `http_errors_total`, `db_query_duration_seconds` SQLAlchemy event-listener, `scholarship_applications_total`, `email_sent_total` callsites.
- **Alloy AP-VM drift** (`F-ALLO-01`, `F-ALLO-03`, `F-ALLO-04`, `F-ALLO-05`): port the staging-ap-vm fixes back to prod-ap-vm.
- **Alloy DB-VM drift** (`F-ALLO-02`): port the staging-db-vm slash-strip fix to prod-db-vm.
- **Alloy fragility** (`F-ALLO-07`, `F-ALLO-08`): standardize on `env("MONITORING_SERVER_URL")` everywhere; add unset-env guard before container start.
- **Dashboard query corrections** (`F-GRAF-02`, `F-GRAF-05`, `F-GRAF-08`, `F-GRAF-09`): regex-exclude `monitoring` from `$environment`; switch `$vm` to dynamic Loki query; either add VTS to nginx-exporter or rewrite Nginx panel queries to use stub_status data.
- **Loki retention** (`F-PROM-10`): add `runtime_config:` block; enable compactor retention.
- **Prometheus hygiene** (`F-PROM-06`, `F-PROM-07`, `F-PROM-08`, `F-PROM-09`, `F-PROM-12`): re-enable recording rules or delete; rename or remove the `staging-db-minio` alert; rewrite the nginx duration alert to use backend metrics; remove or fix `pg_stat_statements_mean_exec_time_bucket` recording rule.
- **Deploy paths** (`F-DEPL-05`, `F-DEPL-06`): include `docker-compose.staging-db-monitoring.yml` in `paths:`; replace `grafana.ini` one-shot copy with overwrite.
- **Prod-side blind spots** (`F-DEPL-11`, `F-DEPL-13`): pending prod-repo read access (per OQ-3 in spec §13). Once granted, audit the prod workflow content side-by-side with this dev workflow.

### Phase 4 must clear (P2 set + launch gate)

- **Cosmetic fixes**: F-GRAF-06, 07, 11, 12; F-PROM-13; F-ALLO-10 (noted but worth doing); F-APP-05, 06, 07; F-DEPL-08; F-DEPL-14.
- **Launch gate** (per spec §8):
  - All 8 dashboards have zero No-data panels for the past 1 hour.
  - Zero broken datasources (every datasource returns 2xx from `/health`).
  - At least one synthetic alert successfully creates a GitHub issue end-to-end.
  - Strengthened deploy workflow health checks pass on a fresh deploy on both staging and production.

### Two outstanding blind spots

- **`F-DEPL-11`** — no `deploy-monitoring-stack-prod.yml.example` exists; prod-side workflow content is not visible from `anud18/scholarship-system`.
- **`F-DEPL-13`** — `prod-db-vm.alloy` SCP chain unverifiable.

User has acknowledged (per session 2026-05-06) that read access will be obtained later; until then, Phase 2 cannot fully verify prod-side parity. The cross-VM matrix above marks these cells `?`.
