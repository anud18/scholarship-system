# Monitoring Stack Fix — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land Phase 2 of the monitoring fix per spec — deliver PR-2.A (deploy unblock) and PR-2.B (13 content fixes covering alertmanager teardown, Grafana unified alerting + GitHub Issue webhook, prod compose env-var refactor, DB-VM relabel pipeline, mirror workflow fixes, documentation cleanup, and deploy workflow honesty).

**Architecture:** Two-PR sequence; PR-2.A is a hard prerequisite for PR-2.B because the migration left the deploy workflow unwired and no monitoring config change ships until that's resolved. Within PR-2.B, most file changes are independent and can be implemented in parallel by separate subagents; only `.github/workflows/deploy-monitoring-stack.yml` is touched by many concerns and is bundled into a single sequential task. Verification is integration-style: lint + `docker compose config` + post-deploy smoke tests against staging Grafana.

**Tech Stack:** YAML (Grafana provisioning, Alloy HCL-like, GitHub Actions, Docker Compose), Bash (workflow inline scripts), Markdown (docs), `yamllint` and `shellcheck` for static checks, Grafana 12.2.1 Enterprise + Prometheus + Loki + Alloy on staging AP-VM and DB-VM.

**Spec reference:** [`docs/superpowers/specs/2026-05-06-monitoring-stack-fix-phase2-design.md`](../specs/2026-05-06-monitoring-stack-fix-phase2-design.md) (commit `57d0ed0`).

**Phase 1 audit:** [`docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md`](../audits/2026-05-06-monitoring-stack-audit.md) (commit `fba3e92`).

---

## File Map

### PR-2.A — Deploy unblock (2 file modifications)

**Modify:**
- `monitoring/GITHUB_DEPLOYMENT.md` — add "Repo Migration Checklist" section
- `.github/workflows/deploy-monitoring-stack.yml` — add pre-flight secret check at start of both jobs

### PR-2.B — Content fixes (3 deletions + 6 new files + 13 modifications)

**Delete:**
- `monitoring/config/alertmanager/` (directory + `alertmanager.yml`)
- `monitoring/config/prometheus/alerts/basic-alerts.yml`
- `monitoring/config/prometheus/recording-rules/aggregations.yml`

**Create (Grafana unified alerting + GitHub workflow):**
- `monitoring/config/grafana/provisioning/alerting/rules-system.yml` (5 rules)
- `monitoring/config/grafana/provisioning/alerting/rules-container.yml` (4 rules)
- `monitoring/config/grafana/provisioning/alerting/rules-database.yml` (2 rules — Redis only)
- `monitoring/config/grafana/provisioning/alerting/rules-monitoring.yml` (3 rules)
- `monitoring/config/grafana/provisioning/alerting/contact-points.yml`
- `monitoring/config/grafana/provisioning/alerting/notification-policies.yml`
- `.github/workflows/monitoring-alert-issue.yml`

**Modify:**
- `monitoring/config/grafana/provisioning/datasources/datasources.yml` — delete AlertManager block
- `monitoring/config/prometheus/prometheus.yml` — delete commented-out `alerting:` and `rule_files:` blocks
- `monitoring/docker-compose.monitoring.yml` — `${APP_NETWORK_NAME}` + GH_PAT mount
- `monitoring/config/alloy/staging-db-vm.alloy` — add scrape + relabel + remote_write
- `monitoring/config/alloy/prod-db-vm.alloy` — same with `environment = "prod"`
- `.github/workflows/deploy-monitoring-stack.yml` — six concerns bundled (see Task 21)
- `.github/workflows/mirror-to-production.yml` — fix strip rule to preserve `monitoring/**/*.md`
- `.github/PRODUCTION_SYNC_GUIDE.md` — replace `PRODUCTION_SYNC_PAT` → `GH_PAT` (3 occurrences)
- `monitoring/PRODUCTION_RUNBOOK.md` — remove AlertManager references
- `monitoring/README.md` — remove AlertManager references
- `monitoring/GITHUB_DEPLOYMENT.md` — remove AlertManager references (already touched in PR-2.A)

### Task ordering and parallelism

```
Stage 1 (PR-2.A)   ── Tasks 1, 2, 3 sequential ──► merge ──► user verification
                                                                  │
Stage 2 (PR-2.B)   ◄──────────────────────────────────────────────┘
  ├── Tasks 4–20: parallelizable across subagents (non-overlapping files)
  ├── Task 21: deploy-monitoring-stack.yml — sequential, single subagent
  └── Task 22: post-deploy smoke tests (after merge)
```

---

## Stage 1 — PR-2.A (Deploy Unblock)

### Task 1: Add Repo Migration Checklist to monitoring/GITHUB_DEPLOYMENT.md

**Files:**
- Modify: `monitoring/GITHUB_DEPLOYMENT.md` (append new section)

- [ ] **Step 1: Read current file end**

```bash
tail -30 monitoring/GITHUB_DEPLOYMENT.md
```

Expected: shows the file's current closing section. Note the last meaningful section header so the new content is appended at the right spot.

- [ ] **Step 2: Append new "Repo Migration Checklist" section**

Append at the end of the file:

```markdown

## Repo Migration Checklist (post-2026-05-06)

The deploy workflow on `anud18/scholarship-system` has zero successful runs after the migration from `jotpalch/scholarship-system`. Before any monitoring config change deploys, complete this checklist on `anud18/scholarship-system`.

### Required GitHub Repository Secrets

Set these via Settings → Secrets and variables → Actions:

| Name | Source | Notes |
|---|---|---|
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin login |
| `GRAFANA_ADMIN_PASSWORD` | password manager | rotate to a strong value before prod launch |
| `GRAFANA_ROOT_URL` | `https://ss.test.nycu.edu.tw/monitoring` | nginx public URL |
| `STAGING_DB_HOST` | DB-VM IP (e.g., `10.113.74.25`) | private subnet IP |
| `STAGING_DB_USER` | DB-VM SSH username | dedicated deploy user |
| `STAGING_DB_SSH_KEY` | private key file content | full file including BEGIN/END markers |
| `STAGING_MONITORING_SERVER_URL` | AP-VM internal URL (e.g., `http://10.113.74.X`) | NO port; alloy appends `:3100` / `:9090` |

`GRAFANA_SECRET_KEY` is intentionally NOT set; Grafana generates a session key at startup. Trade-off: session cookies don't survive Grafana restart. Set it before launch if persistent sessions are required.

### Self-Hosted Runner

The deploy workflow declares `runs-on: self-hosted`. The runner labelled `self-hosted, Linux, X64` must be registered to `anud18/scholarship-system` (Settings → Actions → Runners). The same physical machine that hosted the staging AP-VM runner on `jotpalch/scholarship-system` can be re-registered to the new repo; deregister from the OLD repo first to avoid double-claim.

### Verification

After secrets and runner are in place:

```bash
gh workflow run deploy-monitoring-stack.yml --repo anud18/scholarship-system
gh run watch --repo anud18/scholarship-system
```

Expected: both jobs (`Deploy Monitoring Server (Staging AP-VM)` and `Deploy Staging DB-VM Monitoring`) succeed.

If the run stays in `queued` for more than 30 seconds, the runner is not picking up the job — re-check runner registration and labels.
```

- [ ] **Step 3: Lint the file**

Run: `npx markdownlint-cli monitoring/GITHUB_DEPLOYMENT.md` (or skip if not installed; the change is plain Markdown with no complex structure)

Expected: no errors. If markdownlint isn't installed, visually verify the section renders correctly: tables, code fences, headers all balanced.

- [ ] **Step 4: Commit**

```bash
git add monitoring/GITHUB_DEPLOYMENT.md
git commit -m "docs(monitoring): add Repo Migration Checklist for anud18 deploy unblock"
```

---

### Task 2: Add pre-flight secret check to deploy-monitoring-stack.yml

**Files:**
- Modify: `.github/workflows/deploy-monitoring-stack.yml` (insert new step in both jobs)

- [ ] **Step 1: Read the workflow file**

```bash
sed -n '20,30p' .github/workflows/deploy-monitoring-stack.yml
sed -n '130,145p' .github/workflows/deploy-monitoring-stack.yml
```

Expected: First range shows job 1's `steps:` start (after `Checkout code`); second shows job 2's `steps:` start. Both jobs need the pre-flight check inserted right after `Checkout code`.

- [ ] **Step 2: Insert pre-flight step in job 1 (`deploy-monitoring-server`)**

Use the Edit tool. After the `Checkout code` step in `job: deploy-monitoring-server`, insert:

```yaml
      - name: Pre-flight secret check
        env:
          REQUIRED_SECRETS: |
            GRAFANA_ADMIN_USER GRAFANA_ADMIN_PASSWORD GRAFANA_ROOT_URL
            STAGING_DB_HOST STAGING_DB_USER STAGING_DB_SSH_KEY
            STAGING_MONITORING_SERVER_URL
          GRAFANA_ADMIN_USER: ${{ secrets.GRAFANA_ADMIN_USER }}
          GRAFANA_ADMIN_PASSWORD: ${{ secrets.GRAFANA_ADMIN_PASSWORD }}
          GRAFANA_ROOT_URL: ${{ secrets.GRAFANA_ROOT_URL }}
          STAGING_DB_HOST: ${{ secrets.STAGING_DB_HOST }}
          STAGING_DB_USER: ${{ secrets.STAGING_DB_USER }}
          STAGING_DB_SSH_KEY: ${{ secrets.STAGING_DB_SSH_KEY }}
          STAGING_MONITORING_SERVER_URL: ${{ secrets.STAGING_MONITORING_SERVER_URL }}
        run: |
          missing=()
          for var in $REQUIRED_SECRETS; do
            if [ -z "${!var}" ]; then
              missing+=("$var")
            fi
          done
          if [ ${#missing[@]} -gt 0 ]; then
            echo "::error::Missing required secrets: ${missing[*]}"
            echo "::error::See monitoring/GITHUB_DEPLOYMENT.md → Repo Migration Checklist"
            exit 1
          fi
          echo "✅ All required secrets present"
```

- [ ] **Step 3: Insert pre-flight step in job 2 (`deploy-staging-db-monitoring`)**

In job 2, after `Checkout code` and before `Set up SSH key for DB-VM`, insert the same block (re-paste verbatim).

- [ ] **Step 4: Validate workflow YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-monitoring-stack.yml'))" && echo OK
```

Expected: `OK`. If parse error, fix indentation.

- [ ] **Step 5: Optional — actionlint**

```bash
which actionlint && actionlint .github/workflows/deploy-monitoring-stack.yml || echo "actionlint not installed (optional)"
```

Expected: no errors if installed; otherwise skip.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/deploy-monitoring-stack.yml
git commit -m "ci(monitoring): pre-flight secret check fails fast on missing secrets"
```

---

### Task 3: User-driven operational checklist (NOT a code task)

This is recorded in the plan for completeness but is performed by the user (jotpalch) outside the implementer subagent.

**Operational steps:**

- [ ] **Step 1: User completes secret setup tomorrow**

Per `monitoring/GITHUB_DEPLOYMENT.md` Repo Migration Checklist:
- Set `STAGING_DB_SSH_KEY` (after generating dedicated keypair, installing public key on DB-VM 10.113.74.25:8822)
- Set `STAGING_MONITORING_SERVER_URL` (after recovering AP-VM internal IP from DB-VM `cat /opt/scholarship/.env.staging-db-monitoring`)

- [ ] **Step 2: User verifies runner registration**

In `anud18/scholarship-system` Settings → Actions → Runners, confirm `scholarship-test` (Linux, X64, self-hosted) is online.

- [ ] **Step 3: User triggers test deploy**

```bash
gh workflow run deploy-monitoring-stack.yml --repo anud18/scholarship-system
gh run watch --repo anud18/scholarship-system
```

Expected: both jobs succeed; capture run ID for PR description.

- [ ] **Step 4: User opens PR-2.A**

```bash
gh pr create --base main --head audit/monitoring-stack-phase1 \
  --title "ci(monitoring): pre-flight secret check + repo migration checklist" \
  --body "PR-2.A of Phase 2. Required before PR-2.B."
```

After merge, Stage 2 (PR-2.B work) can begin against `main`.

---

## Stage 2 — PR-2.B (Content Fixes)

**Pre-condition for Stage 2:** PR-2.A merged on `main`; one successful `workflow_dispatch` run of `deploy-monitoring-stack.yml` recorded; runner verified online.

**Branching:** Create a new branch `feat/monitoring-phase2-content-fixes` off `main` after PR-2.A merge. All Stage 2 tasks commit to this branch.

```bash
git checkout main
git pull
git checkout -b feat/monitoring-phase2-content-fixes
```

### Task 4: Delete dead alertmanager / alert / recording-rules artifacts

**Files:**
- Delete: `monitoring/config/alertmanager/` (entire directory including `alertmanager.yml`)
- Delete: `monitoring/config/prometheus/alerts/basic-alerts.yml`
- Delete: `monitoring/config/prometheus/recording-rules/aggregations.yml`

- [ ] **Step 1: Verify the files exist before deleting**

```bash
ls -la monitoring/config/alertmanager/ monitoring/config/prometheus/alerts/basic-alerts.yml monitoring/config/prometheus/recording-rules/aggregations.yml
```

Expected: all three exist. Note their content sizes for the commit message.

- [ ] **Step 2: Delete via git rm**

```bash
git rm -rf monitoring/config/alertmanager/
git rm monitoring/config/prometheus/alerts/basic-alerts.yml
git rm monitoring/config/prometheus/recording-rules/aggregations.yml
```

Expected: three rm operations succeed.

- [ ] **Step 3: Verify the parent dirs still exist (alerts/ and recording-rules/ become empty but should not be auto-deleted)**

```bash
ls -la monitoring/config/prometheus/alerts/ monitoring/config/prometheus/recording-rules/ 2>/dev/null
```

Expected: both directories now empty. Git tracks files, not empty dirs, so they may "disappear" from git but remain on disk. Add `.gitkeep` only if a future task needs them; for Phase 2 they can be empty.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(monitoring): remove alertmanager + dead alert and recording rule files

- monitoring/config/alertmanager/ entire directory (AlertManager removed at 57fca5f)
- monitoring/config/prometheus/alerts/basic-alerts.yml (rules migrated to Grafana
  unified alerting; metric-missing rules dropped per Phase 2 spec §6.2.1)
- monitoring/config/prometheus/recording-rules/aggregations.yml (no dashboard
  references any recorded metric; F-PROM-06)

Resolves: F-PROM-01, F-PROM-02, F-PROM-03, F-PROM-06 (deletion portion);
prepares for Tasks 5-9 to add Grafana unified alerting."
```

---

### Task 5: Create Grafana unified alerting rules — system_health (5 rules)

**Files:**
- Create: `monitoring/config/grafana/provisioning/alerting/rules-system.yml`

- [ ] **Step 1: Create directory if needed**

```bash
mkdir -p monitoring/config/grafana/provisioning/alerting
```

Expected: directory exists. (Provisioning loader needs this path.)

- [ ] **Step 2: Write the file**

Create `monitoring/config/grafana/provisioning/alerting/rules-system.yml` with this exact content:

```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: system_health
    folder: Alerts
    interval: 30s
    rules:
      - uid: alert-high-cpu-usage
        title: HighCPUUsage
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: 100 - (avg by(instance, environment) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: system
        annotations:
          summary: "High CPU usage on {{ $labels.instance }}"
          description: "CPU usage is above 80% on {{ $labels.instance }} ({{ $labels.environment }}) for more than 5 minutes. Current value: {{ $value | humanize }}%"
        isPaused: false

      - uid: alert-high-memory-usage
        title: HighMemoryUsage
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 85
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: system
        annotations:
          summary: "High memory usage on {{ $labels.instance }}"
          description: "Memory usage is above 85% on {{ $labels.instance }} ({{ $labels.environment }}). Current value: {{ $value | humanize }}%"
        isPaused: false

      - uid: alert-disk-space-low
        title: DiskSpaceLow
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 600
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|fuse.lxcfs|squashfs|vfat"} / node_filesystem_size_bytes)) * 100 > 80
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 10m
        labels:
          severity: warning
          category: system
        annotations:
          summary: "Low disk space on {{ $labels.instance }}"
          description: "Disk usage is above 80% on {{ $labels.instance }} ({{ $labels.environment }}) at mount point {{ $labels.mountpoint }}. Current value: {{ $value | humanize }}%"
        isPaused: false

      - uid: alert-disk-space-critical
        title: DiskSpaceCritical
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|fuse.lxcfs|squashfs|vfat"} / node_filesystem_size_bytes)) * 100 > 90
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: critical
          category: system
        annotations:
          summary: "Critical disk space on {{ $labels.instance }}"
          description: "Disk usage is above 90% on {{ $labels.instance }} ({{ $labels.environment }}) at mount point {{ $labels.mountpoint }}. Immediate action required! Current value: {{ $value | humanize }}%"
        isPaused: false

      - uid: alert-high-system-load
        title: HighSystemLoad
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 600
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: node_load5 / count(node_cpu_seconds_total{mode="idle"}) without(cpu, mode) > 2
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 10m
        labels:
          severity: warning
          category: system
        annotations:
          summary: "High system load on {{ $labels.instance }}"
          description: "5-minute load average is more than 2x the number of CPUs on {{ $labels.instance }} ({{ $labels.environment }}). Current value: {{ $value | humanize }}"
        isPaused: false
```

- [ ] **Step 3: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('monitoring/config/grafana/provisioning/alerting/rules-system.yml'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add monitoring/config/grafana/provisioning/alerting/rules-system.yml
git commit -m "feat(monitoring): add Grafana unified alerting rules for system_health (5 rules)"
```

---

### Task 6: Create Grafana unified alerting rules — container_health (4 rules)

**Files:**
- Create: `monitoring/config/grafana/provisioning/alerting/rules-container.yml`

- [ ] **Step 1: Write the file**

Create with this exact content:

```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: container_health
    folder: Alerts
    interval: 30s
    rules:
      - uid: alert-container-down
        title: ContainerDown
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 120
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: time() - container_last_seen{name!=""} > 60
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 2m
        labels:
          severity: critical
          category: container
        annotations:
          summary: "Container {{ $labels.name }} is down"
          description: "Container {{ $labels.name }} on {{ $labels.instance }} ({{ $labels.environment }}) has been down for more than 2 minutes"
        isPaused: false

      - uid: alert-container-high-cpu
        title: ContainerHighCPU
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: sum(rate(container_cpu_usage_seconds_total{name!=""}[5m])) by (name, instance, environment) * 100 > 80
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: container
        annotations:
          summary: "High CPU usage in container {{ $labels.name }}"
          description: "Container {{ $labels.name }} on {{ $labels.instance }} ({{ $labels.environment }}) is using more than 80% CPU. Current value: {{ $value | humanize }}%"
        isPaused: false

      - uid: alert-container-high-memory
        title: ContainerHighMemory
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: (container_memory_usage_bytes{name!=""} / container_spec_memory_limit_bytes{name!=""}) * 100 > 85
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: container
        annotations:
          summary: "High memory usage in container {{ $labels.name }}"
          description: "Container {{ $labels.name }} on {{ $labels.instance }} ({{ $labels.environment }}) is using more than 85% of its memory limit. Current value: {{ $value | humanize }}%"
        isPaused: false

      - uid: alert-container-restarting-frequently
        title: ContainerRestartingFrequently
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: rate(container_last_seen{name!=""}[15m]) > 0.1
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: container
        annotations:
          summary: "Container {{ $labels.name }} is restarting frequently"
          description: "Container {{ $labels.name }} on {{ $labels.instance }} ({{ $labels.environment }}) has restarted multiple times in the last 15 minutes"
        isPaused: false
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('monitoring/config/grafana/provisioning/alerting/rules-container.yml'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add monitoring/config/grafana/provisioning/alerting/rules-container.yml
git commit -m "feat(monitoring): add Grafana unified alerting rules for container_health (4 rules)"
```

---

### Task 7: Create Grafana unified alerting rules — database (Redis only, 2 rules)

**Files:**
- Create: `monitoring/config/grafana/provisioning/alerting/rules-database.yml`

- [ ] **Step 1: Write the file**

Create with this exact content:

```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: database_health
    folder: Alerts
    interval: 30s
    # Note: 3 PostgreSQL alerts (PostgreSQLDown, PostgreSQLTooManyConnections,
    # PostgreSQLHighConnections) are intentionally deferred to Phase 3.
    # They depend on the DB-VM scrape pipeline (F-PROM-05 / F-ALLO-06) which
    # Phase 3 fixes. Once postgres-exporter is reaching Prometheus, the rules
    # will be added here. Tracking issue: filed at PR-2.B merge time.
    rules:
      - uid: alert-redis-down
        title: RedisDown
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 60
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: redis_up == 0
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 1m
        labels:
          severity: critical
          category: database
        annotations:
          summary: "Redis is down on {{ $labels.instance }}"
          description: "Redis cache on {{ $labels.instance }} ({{ $labels.environment }}) is not responding"
        isPaused: false

      - uid: alert-redis-high-memory
        title: RedisHighMemory
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: (redis_memory_used_bytes / redis_memory_max_bytes) * 100 > 80
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: database
        annotations:
          summary: "Redis memory usage is high"
          description: "Redis on {{ $labels.instance }} ({{ $labels.environment }}) is using more than 80% of its max memory. Current value: {{ $value | humanize }}%"
        isPaused: false
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('monitoring/config/grafana/provisioning/alerting/rules-database.yml'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add monitoring/config/grafana/provisioning/alerting/rules-database.yml
git commit -m "feat(monitoring): add Grafana unified alerting rules for redis (2 rules)

3 postgres alerts (PostgreSQLDown, PostgreSQLTooManyConnections,
PostgreSQLHighConnections) deferred to Phase 3 — they depend on the DB-VM
scrape pipeline being fixed (F-PROM-05 / F-ALLO-06).

3 application_health alerts (HighHTTPErrorRate, SlowHTTPResponseTime,
MinIODown) intentionally dropped per Phase 2 spec §6.2.1 — metrics they
reference do not exist; redesign needed (Phase 3+)."
```

---

### Task 8: Create Grafana unified alerting rules — monitoring_health (3 rules)

**Files:**
- Create: `monitoring/config/grafana/provisioning/alerting/rules-monitoring.yml`

- [ ] **Step 1: Write the file**

Create with this exact content:

```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: monitoring_health
    folder: Alerts
    interval: 60s
    rules:
      - uid: alert-prometheus-target-down
        title: PrometheusTargetDown
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: up == 0
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 5m
        labels:
          severity: warning
          category: monitoring
        annotations:
          summary: "Prometheus target {{ $labels.job }} is down"
          description: "Prometheus cannot scrape {{ $labels.job }} on {{ $labels.instance }} ({{ $labels.environment }})"
        isPaused: false

      - uid: alert-loki-ingestion-falling-behind
        title: LokiIngestionFallingBehind
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 600
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: rate(loki_distributor_bytes_received_total[5m]) > rate(loki_ingester_chunks_flushed_total[5m]) * 1000
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 10m
        labels:
          severity: warning
          category: monitoring
        annotations:
          summary: "Loki ingestion is falling behind"
          description: "Loki is receiving logs faster than it can flush them. This may cause memory issues."
        isPaused: false

      - uid: alert-prometheus-storage-low
        title: PrometheusStorageLow
        condition: A
        data:
          - refId: A
            relativeTimeRange:
              from: 600
              to: 0
            datasourceUid: prometheus-uid
            model:
              expr: (prometheus_tsdb_storage_blocks_bytes / prometheus_tsdb_retention_limit_bytes) > 0.8
              refId: A
              instant: true
        noDataState: NoData
        execErrState: Error
        for: 10m
        labels:
          severity: warning
          category: monitoring
        annotations:
          summary: "Prometheus storage usage is high"
          description: "Prometheus is using more than 80% of its storage retention limit. Current value: {{ $value | humanizePercentage }}"
        isPaused: false
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('monitoring/config/grafana/provisioning/alerting/rules-monitoring.yml'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add monitoring/config/grafana/provisioning/alerting/rules-monitoring.yml
git commit -m "feat(monitoring): add Grafana unified alerting rules for monitoring_health (3 rules)"
```

---

### Task 9: Create contact-points.yml and notification-policies.yml

**Files:**
- Create: `monitoring/config/grafana/provisioning/alerting/contact-points.yml`
- Create: `monitoring/config/grafana/provisioning/alerting/notification-policies.yml`

- [ ] **Step 1: Create contact-points.yml**

Create `monitoring/config/grafana/provisioning/alerting/contact-points.yml` with:

```yaml
apiVersion: 1
contactPoints:
  - orgId: 1
    name: github-issue
    receivers:
      - uid: github-issue-uid
        type: webhook
        disableResolveMessage: false
        settings:
          url: https://api.github.com/repos/anud18/scholarship-system/dispatches
          httpMethod: POST
          authorization_scheme: token
          # GH_PAT mounted as a file at runtime; Grafana reads via $__file{...}
          authorization_credentials: $__file{/etc/grafana/secrets/gh_pat}
          # Override default webhook body so GitHub's dispatches API accepts it
          # (event_type + client_payload wrapper required by repository_dispatch).
          message: |-
            {
              "event_type": "monitoring-alert",
              "client_payload": {
                "alertname": "{{ (index .Alerts 0).Labels.alertname }}",
                "severity": "{{ (index .Alerts 0).Labels.severity }}",
                "category": "{{ (index .Alerts 0).Labels.category }}",
                "status": "{{ .Status }}",
                "summary": "{{ (index .Alerts 0).Annotations.summary }}",
                "description": "{{ (index .Alerts 0).Annotations.description }}",
                "instance": "{{ (index .Alerts 0).Labels.instance }}",
                "environment": "{{ (index .Alerts 0).Labels.environment }}",
                "value": "{{ (index .Alerts 0).ValueString }}",
                "fired_at": "{{ (index .Alerts 0).StartsAt }}",
                "grafana_url": "{{ .ExternalURL }}"
              }
            }
```

- [ ] **Step 2: Create notification-policies.yml**

Create `monitoring/config/grafana/provisioning/alerting/notification-policies.yml` with:

```yaml
apiVersion: 1
policies:
  - orgId: 1
    receiver: github-issue
    group_by:
      - alertname
      - environment
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 4h
```

- [ ] **Step 3: Validate both YAMLs**

```bash
for f in monitoring/config/grafana/provisioning/alerting/contact-points.yml \
         monitoring/config/grafana/provisioning/alerting/notification-policies.yml; do
  python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK: $f"
done
```

Expected: both `OK`.

- [ ] **Step 4: Commit**

```bash
git add monitoring/config/grafana/provisioning/alerting/contact-points.yml \
        monitoring/config/grafana/provisioning/alerting/notification-policies.yml
git commit -m "feat(monitoring): add GitHub Issue contact point + notification policy

Routes all 14 LIVE alert rules to a single 'github-issue' webhook contact
point that POSTs to GitHub's repository_dispatch API. Grouping by
(alertname, environment) prevents per-instance webhook fan-out;
repeat_interval 4h sends a heartbeat firing comment if alert persists.

GH_PAT delivered via file mount at /etc/grafana/secrets/gh_pat (see
docker-compose.monitoring.yml + deploy-monitoring-stack.yml updates)."
```

---

### Task 10: Create monitoring-alert-issue.yml GitHub Actions workflow

**Files:**
- Create: `.github/workflows/monitoring-alert-issue.yml`

- [ ] **Step 1: Write the workflow file**

Create with this exact content:

```yaml
name: Create Monitoring Alert Issue

on:
  repository_dispatch:
    types: [monitoring-alert]

permissions:
  issues: write
  contents: read

jobs:
  handle-alert:
    runs-on: ubuntu-latest
    steps:
      - name: Render issue title and body
        id: render
        env:
          ALERT: ${{ github.event.client_payload.alertname }}
          ENV: ${{ github.event.client_payload.environment }}
          STATUS: ${{ github.event.client_payload.status }}
          SEVERITY: ${{ github.event.client_payload.severity }}
          SUMMARY: ${{ github.event.client_payload.summary }}
          DESCRIPTION: ${{ github.event.client_payload.description }}
          INSTANCE: ${{ github.event.client_payload.instance }}
          VALUE: ${{ github.event.client_payload.value }}
          FIRED_AT: ${{ github.event.client_payload.fired_at }}
          GRAFANA_URL: ${{ github.event.client_payload.grafana_url }}
        run: |
          echo "title=Monitoring Alert: $ALERT ($ENV/$SEVERITY)" >> "$GITHUB_OUTPUT"
          cat > /tmp/body.md <<EOF
          ## $STATUS — $ALERT

          **Environment:** \`$ENV\`
          **Severity:** \`$SEVERITY\`
          **Instance:** \`$INSTANCE\`
          **Value:** $VALUE
          **Fired at:** $FIRED_AT
          **Grafana:** $GRAFANA_URL

          ### Summary
          $SUMMARY

          ### Description
          $DESCRIPTION
          EOF

      - name: Find existing issue
        id: find
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ALERT: ${{ github.event.client_payload.alertname }}
          ENV: ${{ github.event.client_payload.environment }}
        run: |
          ISSUE=$(gh issue list \
            --repo "${{ github.repository }}" \
            --label "monitoring-alert" \
            --label "alert:$ALERT" \
            --label "env:$ENV" \
            --state all \
            --limit 1 \
            --json number,state \
            --jq '.[0]')
          if [ -n "$ISSUE" ] && [ "$ISSUE" != "null" ]; then
            echo "found=true" >> "$GITHUB_OUTPUT"
            echo "number=$(echo "$ISSUE" | jq -r .number)" >> "$GITHUB_OUTPUT"
            echo "state=$(echo "$ISSUE" | jq -r .state)" >> "$GITHUB_OUTPUT"
          else
            echo "found=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Create new issue (no existing match, status=firing)
        if: steps.find.outputs.found != 'true' && github.event.client_payload.status == 'firing'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue create \
            --repo "${{ github.repository }}" \
            --title "${{ steps.render.outputs.title }}" \
            --body-file /tmp/body.md \
            --label "monitoring-alert" \
            --label "alert:${{ github.event.client_payload.alertname }}" \
            --label "env:${{ github.event.client_payload.environment }}" \
            --label "severity:${{ github.event.client_payload.severity }}"

      - name: Reopen + comment (existing closed, status=firing)
        if: steps.find.outputs.found == 'true' && steps.find.outputs.state == 'CLOSED' && github.event.client_payload.status == 'firing'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue reopen ${{ steps.find.outputs.number }} --repo "${{ github.repository }}"
          gh issue comment ${{ steps.find.outputs.number }} --repo "${{ github.repository }}" --body-file /tmp/body.md

      - name: Append firing comment (existing open, status=firing)
        if: steps.find.outputs.found == 'true' && steps.find.outputs.state == 'OPEN' && github.event.client_payload.status == 'firing'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue comment ${{ steps.find.outputs.number }} --repo "${{ github.repository }}" --body-file /tmp/body.md

      - name: Append resolved comment (existing issue, status=resolved)
        if: steps.find.outputs.found == 'true' && github.event.client_payload.status == 'resolved'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue comment ${{ steps.find.outputs.number }} --repo "${{ github.repository }}" \
            --body "✅ Alert resolved at ${{ github.event.client_payload.fired_at }}. Closing left to operator after verifying root cause."
```

- [ ] **Step 2: Validate YAML and shell**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/monitoring-alert-issue.yml'))" && echo "YAML OK"
which actionlint && actionlint .github/workflows/monitoring-alert-issue.yml || echo "actionlint not installed (optional)"
```

Expected: `YAML OK`. actionlint is optional.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/monitoring-alert-issue.yml
git commit -m "feat(monitoring): add GitHub Issue receiver workflow for Grafana alerts

Receives repository_dispatch events from Grafana's webhook contact point.
De-dupe behaviour:
  - new alert + no existing issue + firing  → create new issue
  - new alert + existing closed + firing    → reopen + comment
  - new alert + existing open + firing      → append firing comment
  - any + existing issue + resolved         → append resolved comment
                                              (operator closes manually)

Labels: monitoring-alert, alert:<name>, env:<env>, severity:<level>.
Uses built-in GITHUB_TOKEN (issues:write) — no PAT required for workflow."
```

---

### Task 11: Modify datasources.yml — delete AlertManager block

**Files:**
- Modify: `monitoring/config/grafana/provisioning/datasources/datasources.yml` (delete lines 109-121, the AlertManager datasource entry)

- [ ] **Step 1: Read the file to confirm line range**

```bash
sed -n '105,125p' monitoring/config/grafana/provisioning/datasources/datasources.yml
```

Expected: shows the `- name: AlertManager` block somewhere in this range. Note exact start and end lines (block begins at the leading `- name:` and ends before the next `- name:` or end-of-file).

- [ ] **Step 2: Delete the block via Edit tool**

Use Edit with `old_string` set to the exact AlertManager block (including the leading `- name: AlertManager` line and all sub-properties up to but not including the next entry or end-of-file). Replace with empty string.

If the block looks like:

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

Replace this entire 11-line block with empty (delete the lines).

- [ ] **Step 3: Validate YAML**

```bash
python3 -c "import yaml; d = yaml.safe_load(open('monitoring/config/grafana/provisioning/datasources/datasources.yml')); names = [ds['name'] for ds in d['datasources']]; assert 'AlertManager' not in names, 'AlertManager still present'; print('OK,', len(names), 'datasources remain:', names)"
```

Expected: `OK, 4 datasources remain: ['Prometheus', 'Loki (Staging)', ...]` (count and names depend on file content; AlertManager must be absent).

- [ ] **Step 4: Commit**

```bash
git add monitoring/config/grafana/provisioning/datasources/datasources.yml
git commit -m "fix(monitoring): remove dangling AlertManager datasource (F-PROM-02 / F-GRAF-01)"
```

---

### Task 12: Clean up prometheus.yml — delete commented `alerting:` and `rule_files:` blocks

**Files:**
- Modify: `monitoring/config/prometheus/prometheus.yml` (delete commented-out `alerting:` block at ~lines 12-18 and `rule_files:` block at ~lines 20-23)

- [ ] **Step 1: Read the file head**

```bash
sed -n '1,30p' monitoring/config/prometheus/prometheus.yml
```

Expected: shows global config + commented `alerting:` block + commented `rule_files:` block. Note the exact line ranges.

- [ ] **Step 2: Delete both commented blocks via Edit tool**

Find the block:

```yaml
# Alertmanager configuration (disabled - AlertManager removed)
# alerting:
#   alertmanagers:
#     - static_configs:
#         - targets:
#             - alertmanager:9093

# Alert rules (disabled - no AlertManager)
# rule_files:
#   - '/etc/prometheus/alerts/*.yml'
#   - '/etc/prometheus/recording-rules/*.yml'
```

Replace it with the single line:

```yaml
# Alerting and rule_files removed in Phase 2 — alerts now handled by Grafana
# unified alerting (see monitoring/config/grafana/provisioning/alerting/).
```

- [ ] **Step 3: Validate YAML**

```bash
python3 -c "import yaml; d = yaml.safe_load(open('monitoring/config/prometheus/prometheus.yml')); assert 'alerting' not in d, 'alerting still in yaml'; assert 'rule_files' not in d, 'rule_files still in yaml'; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add monitoring/config/prometheus/prometheus.yml
git commit -m "chore(monitoring): remove dead alerting/rule_files comments from prometheus.yml

Alerting now handled entirely by Grafana unified alerting. The block was
commented out at 57fca5f when AlertManager was removed; it remained as
dead config until now."
```

---

### Task 13: Modify docker-compose.monitoring.yml — APP_NETWORK_NAME + GH_PAT mount

**Files:**
- Modify: `monitoring/docker-compose.monitoring.yml`

- [ ] **Step 1: Read the current file**

```bash
cat monitoring/docker-compose.monitoring.yml
```

Note the current `services.grafana.volumes`, `services.{grafana,loki,prometheus}.networks`, and the bottom-level `networks:` block.

- [ ] **Step 2: Apply the changes via Edit**

Three changes in this single Edit:

**Change 2a:** Replace each occurrence of `scholarship_staging_network` in service `networks:` lists with `app_network`. Specifically, update the `networks:` lists of `grafana`, `loki`, and `prometheus` services from:

```yaml
    networks:
      - monitoring_network
      - scholarship_staging_network
```

to:

```yaml
    networks:
      - monitoring_network
      - app_network
```

Apply this to all three services (grafana, loki, prometheus).

**Change 2b:** Add the GH_PAT volume mount to the `grafana` service. Find the existing `volumes:` block under `grafana:`:

```yaml
    volumes:
      - grafana_data:/var/lib/grafana
      - ./config/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./config/grafana/grafana.ini:/etc/grafana/grafana.ini:ro
```

Add a fourth line:

```yaml
    volumes:
      - grafana_data:/var/lib/grafana
      - ./config/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./config/grafana/grafana.ini:/etc/grafana/grafana.ini:ro
      - /opt/scholarship/secrets/gh_pat:/etc/grafana/secrets/gh_pat:ro
```

**Change 2c:** Replace the bottom `networks:` block to use the env-var alias:

```yaml
networks:
  monitoring_network:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet: 172.30.0.0/16
  scholarship_staging_network:
    external: true
    name: scholarship_staging_network
```

becomes:

```yaml
networks:
  monitoring_network:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet: 172.30.0.0/16
  app_network:
    external: true
    name: ${APP_NETWORK_NAME}
```

- [ ] **Step 3: Validate compose**

```bash
APP_NETWORK_NAME=scholarship_staging_network \
GRAFANA_ADMIN_USER=test \
GRAFANA_ADMIN_PASSWORD=test \
GRAFANA_ROOT_URL=http://localhost \
docker compose -f monitoring/docker-compose.monitoring.yml config --quiet && echo "compose OK"
```

Expected: `compose OK`. Verifies the file parses with the env-var substituted in.

- [ ] **Step 4: Validate that unset env raises an error**

```bash
unset APP_NETWORK_NAME
docker compose -f monitoring/docker-compose.monitoring.yml config 2>&1 | grep -E "WARNING|Variable|empty" || echo "Compose may not warn on unset; we add explicit guard in deploy workflow (Task 21)"
```

Expected: either a warning about variable unset, OR the line above prints. The actual fail-fast happens in deploy workflow (Task 21).

- [ ] **Step 5: Commit**

```bash
git add monitoring/docker-compose.monitoring.yml
git commit -m "fix(monitoring): parameterize app network name + mount GH_PAT for Grafana

- Replaces hardcoded scholarship_staging_network with \${APP_NETWORK_NAME}
  alias 'app_network' so the same compose file deploys to staging
  (scholarship_staging_network) and prod (scholarship_prod_network).
- Mounts /opt/scholarship/secrets/gh_pat at /etc/grafana/secrets/gh_pat
  (read-only) so Grafana's webhook contact point can read GH_PAT via
  \$__file{} reference for repository_dispatch authentication.

Resolves: F-DEPL-04 (prod compose external network).
Prepares: contact-points.yml authorization_credentials reference."
```

---

### Task 14: Modify staging-db-vm.alloy — add scrape + relabel + remote_write

**Files:**
- Modify: `monitoring/config/alloy/staging-db-vm.alloy`

- [ ] **Step 1: Read the current METRICS PIPELINE comment block**

```bash
grep -n "METRICS PIPELINE" monitoring/config/alloy/staging-db-vm.alloy
sed -n '80,100p' monitoring/config/alloy/staging-db-vm.alloy
```

Expected: shows the comment block (around lines 81-97 per Branch C audit) that says "Metrics are exposed via exporters and scraped directly by Prometheus on AP-VM" but has no actual implementation.

- [ ] **Step 2: Replace the comment block with a real pipeline**

Use the Edit tool. The existing comment block to replace is approximately:

```alloy
// =============================================================================
// METRICS PIPELINE - PULL MODE
// =============================================================================
// Metrics are exposed via exporters and scraped directly by Prometheus on AP-VM:
// - Node Exporter: exposed on port 9100
// - PostgreSQL Exporter: exposed on port 9187
//
// Prometheus on AP-VM will add environment/vm labels during scrape using
// relabel_configs in its prometheus.yml configuration.
```

Replace with:

```alloy
// =============================================================================
// METRICS PIPELINE — PUSH MODE (matches AP-VM Alloy structure)
// =============================================================================
// Scrapes local DB-VM exporters and pushes to AP-VM Prometheus via remote_write.
// Adds environment + vm labels via prometheus.relabel before push so dashboards
// and alerts can filter on {environment="staging", vm="db-vm"}.

prometheus.scrape "node_exporter" {
  targets    = [{ __address__ = "node-exporter:9100" }]
  forward_to = [prometheus.relabel.add_labels.receiver]
  job_name   = "node"
  scrape_interval = "15s"
}

prometheus.scrape "postgres_exporter" {
  targets    = [{ __address__ = "postgres-exporter:9187" }]
  forward_to = [prometheus.relabel.add_labels.receiver]
  job_name   = "postgres"
  scrape_interval = "15s"
}

prometheus.relabel "add_labels" {
  forward_to = [prometheus.remote_write.default.receiver]
  rule {
    target_label = "environment"
    replacement  = "staging"
  }
  rule {
    target_label = "vm"
    replacement  = "db-vm"
  }
}

prometheus.remote_write "default" {
  endpoint {
    url = env("MONITORING_SERVER_URL") + ":9090/api/v1/write"
  }
}
```

- [ ] **Step 3: Validate Alloy config syntax**

```bash
docker run --rm -v "$(pwd)/monitoring/config/alloy/staging-db-vm.alloy:/etc/alloy/config.alloy:ro" \
  grafana/alloy:latest fmt /etc/alloy/config.alloy > /dev/null && echo "alloy fmt OK"
```

Expected: `alloy fmt OK`. If Alloy is not pull-able, skip and rely on integration test.

- [ ] **Step 4: Commit**

```bash
git add monitoring/config/alloy/staging-db-vm.alloy
git commit -m "fix(monitoring): add DB-VM metrics push pipeline (staging)

Adds prometheus.scrape + prometheus.relabel + prometheus.remote_write
blocks so DB-VM node-exporter (9100) and postgres-exporter (9187) push
to AP-VM Prometheus via remote_write with environment=staging, vm=db-vm
labels.

Resolves: F-ALLO-06 (DB-VM Alloy missing remote_write), F-ALLO-09
(DB-VM relabel promise unfulfilled). Replaces the architectural mismatch
between the comment-only PULL mode and missing prometheus.yml scrape
jobs with a consistent PUSH mode matching AP-VM."
```

---

### Task 15: Modify prod-db-vm.alloy — same pipeline with environment="prod"

**Files:**
- Modify: `monitoring/config/alloy/prod-db-vm.alloy`

- [ ] **Step 1: Read current METRICS PIPELINE block**

```bash
grep -n "METRICS PIPELINE" monitoring/config/alloy/prod-db-vm.alloy
sed -n '78,100p' monitoring/config/alloy/prod-db-vm.alloy
```

Expected: shows the same structural comment block as staging-db-vm.alloy did.

- [ ] **Step 2: Replace the comment block**

Use Edit with the same structural change as Task 14, but with `replacement = "prod"` instead of `"staging"`:

```alloy
// =============================================================================
// METRICS PIPELINE — PUSH MODE (matches AP-VM Alloy structure)
// =============================================================================
// Scrapes local DB-VM exporters and pushes to AP-VM Prometheus via remote_write.
// Adds environment + vm labels via prometheus.relabel before push so dashboards
// and alerts can filter on {environment="prod", vm="db-vm"}.

prometheus.scrape "node_exporter" {
  targets    = [{ __address__ = "node-exporter:9100" }]
  forward_to = [prometheus.relabel.add_labels.receiver]
  job_name   = "node"
  scrape_interval = "15s"
}

prometheus.scrape "postgres_exporter" {
  targets    = [{ __address__ = "postgres-exporter:9187" }]
  forward_to = [prometheus.relabel.add_labels.receiver]
  job_name   = "postgres"
  scrape_interval = "15s"
}

prometheus.relabel "add_labels" {
  forward_to = [prometheus.remote_write.default.receiver]
  rule {
    target_label = "environment"
    replacement  = "prod"
  }
  rule {
    target_label = "vm"
    replacement  = "db-vm"
  }
}

prometheus.remote_write "default" {
  endpoint {
    url = env("MONITORING_SERVER_URL") + ":9090/api/v1/write"
  }
}
```

- [ ] **Step 3: Validate**

```bash
docker run --rm -v "$(pwd)/monitoring/config/alloy/prod-db-vm.alloy:/etc/alloy/config.alloy:ro" \
  grafana/alloy:latest fmt /etc/alloy/config.alloy > /dev/null && echo "alloy fmt OK"
```

Expected: `alloy fmt OK`.

- [ ] **Step 4: Confirm staging vs prod differ ONLY in `replacement = "staging"` vs `"prod"`**

```bash
diff -u monitoring/config/alloy/staging-db-vm.alloy monitoring/config/alloy/prod-db-vm.alloy | grep '^[+-]' | grep -v '^[+-]\(\+\+\+\|---\|@@\)' | head
```

Expected: shows only environment label differences (`-staging` vs `+prod`) and any X-Scope-OrgID / X-Environment header values that legitimately differ. Anything else differing is a finding to capture.

- [ ] **Step 5: Commit**

```bash
git add monitoring/config/alloy/prod-db-vm.alloy
git commit -m "fix(monitoring): add DB-VM metrics push pipeline (prod)

Mirrors Task 14 (staging-db-vm) with environment=prod label.
Resolves: F-ALLO-06, F-ALLO-09 for prod-db.

Note: prod-db Alloy will not produce metrics until F-DEPL-04 (prod
monitoring compose network) is fixed and prod monitoring stack is
deployed (covered in Task 13 + Task 21)."
```

---

### Task 16: Modify mirror-to-production.yml — preserve monitoring/**/*.md

**Files:**
- Modify: `.github/workflows/mirror-to-production.yml` (line ~341)

- [ ] **Step 1: Read the strip rule line**

```bash
grep -n 'find . -type f -name "\*\.md"' .github/workflows/mirror-to-production.yml
```

Expected: matches at line ~341. Confirms the exact text.

- [ ] **Step 2: Replace the strip rule**

Use Edit:

```bash
# Before:
find . -type f -name "*.md" 2>/dev/null | xargs -r git rm -f 2>/dev/null || true

# After:
find . -type f -name "*.md" -not -path './monitoring/*' 2>/dev/null | xargs -r git rm -f 2>/dev/null || true
```

- [ ] **Step 3: Validate workflow YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/mirror-to-production.yml'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 4: Dry-run the find command locally**

```bash
cd /Users/chenweicheng/claude_project/scholarship-system
find . -type f -name "*.md" -not -path './monitoring/*' 2>/dev/null | head -20
```

Expected: lists `*.md` files OUTSIDE `monitoring/` (e.g., `README.md`, `docs/...`); should NOT include `monitoring/PRODUCTION_RUNBOOK.md`, `monitoring/README.md`, `monitoring/GITHUB_DEPLOYMENT.md`, `monitoring/QUICKSTART.md`, `monitoring/DASHBOARDS.md`.

```bash
find . -type f -name "*.md" -path './monitoring/*' 2>/dev/null
```

Expected: lists only the monitoring/*.md files (these are the ones we now preserve).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/mirror-to-production.yml
git commit -m "fix(mirror): preserve monitoring/**/*.md during prod sync

Spec §9 expects documentation under monitoring/ to survive the mirror so
prod-side maintainers can read the runbook. Previous strip rule removed
ALL *.md including monitoring/PRODUCTION_RUNBOOK.md. Excludes monitoring/
from the strip via -not -path './monitoring/*'.

Resolves: F-DEPL-09."
```

---

### Task 17: Modify PRODUCTION_SYNC_GUIDE.md — replace PRODUCTION_SYNC_PAT with GH_PAT

**Files:**
- Modify: `.github/PRODUCTION_SYNC_GUIDE.md`

- [ ] **Step 1: Find current occurrences**

```bash
grep -n "PRODUCTION_SYNC_PAT" .github/PRODUCTION_SYNC_GUIDE.md
```

Expected: 3 lines (per audit F-DEPL-10): line ~68 (table row), ~389, ~394 (troubleshooting section).

- [ ] **Step 2: Replace each occurrence**

Use Edit with `replace_all: true` to swap `PRODUCTION_SYNC_PAT` → `GH_PAT` everywhere in this file.

- [ ] **Step 3: Verify no occurrences remain**

```bash
grep -c "PRODUCTION_SYNC_PAT" .github/PRODUCTION_SYNC_GUIDE.md
```

Expected: `0`.

- [ ] **Step 4: Verify GH_PAT references increased by exactly 3**

```bash
grep -c "GH_PAT" .github/PRODUCTION_SYNC_GUIDE.md
```

Expected: 3 (or more if `GH_PAT` was already mentioned elsewhere).

- [ ] **Step 5: Commit**

```bash
git add .github/PRODUCTION_SYNC_GUIDE.md
git commit -m "docs(mirror): rename PRODUCTION_SYNC_PAT to GH_PAT to match workflow

The mirror-to-production.yml workflow checks secrets.GH_PAT (line 47)
but the guide instructed operators to set a secret named
PRODUCTION_SYNC_PAT. Operators following the guide would create the
wrong secret name and the workflow would fail with 'GH_PAT secret not
configured'.

Resolves: F-DEPL-10."
```

---

### Task 18: Modify monitoring/PRODUCTION_RUNBOOK.md — remove AlertManager references

**Files:**
- Modify: `monitoring/PRODUCTION_RUNBOOK.md`

- [ ] **Step 1: Find AlertManager references**

```bash
grep -n -i "alertmanager\|alert-manager\|alert manager" monitoring/PRODUCTION_RUNBOOK.md
```

Expected: lists every line mentioning AlertManager (per Branch E observation around line 23 mentions `http://monitoring-server:9093`).

- [ ] **Step 2: For each reference, decide on disposition**

- AlertManager URL references (`monitoring-server:9093`, `alertmanager:9093`): delete the line.
- Architecture diagrams that include "AlertManager": remove the box or replace with a "Grafana Alerting" reference.
- Operational runbook steps that involve AlertManager (e.g., "check AlertManager UI"): replace with "check Grafana → Alerting → Alert rules" and "check GitHub Issues with label `monitoring-alert`".

Use Edit tool for each occurrence; if the same line pattern repeats, use `replace_all: true`.

- [ ] **Step 3: Add a new "Alerting" section if not present**

Append (or relocate to a logical position):

```markdown

## Alerting

Alerts are managed by Grafana unified alerting (Phase 2, 2026-05-06).

### Where to look

| Need | Where |
|---|---|
| Currently firing alerts | Grafana → Alerting → Alert rules (filter by State: Firing) |
| Alert event history | GitHub Issues, label `monitoring-alert` |
| Specific alert ongoing? | GitHub Issues with `alert:<AlertName>` label |
| Acknowledge an alert | Comment on the GitHub issue; close it after RCA |
| Silence an alert temporarily | Grafana → Alerting → Silences |

### Pre-launch smoke test

To verify the alert pipeline end-to-end, see Phase 2 spec §7.2.
```

- [ ] **Step 4: Verify no AlertManager references remain**

```bash
grep -c -i "alertmanager\|alert-manager\|alert manager" monitoring/PRODUCTION_RUNBOOK.md
```

Expected: `0`. (If false hits exist for words like "alert manager" used in a sentence about Grafana's alert manager — that's still misleading, prefer "Grafana alerting"; rephrase.)

- [ ] **Step 5: Commit**

```bash
git add monitoring/PRODUCTION_RUNBOOK.md
git commit -m "docs(monitoring): remove AlertManager references from PRODUCTION_RUNBOOK

Replaces with Grafana unified alerting + GitHub Issues guidance per
Phase 2 spec §6.7. Adds 'Alerting' section pointing to Grafana UI and
GitHub Issues label filters.

Resolves: cross-branch observation from F-DEPL E1 / E2."
```

---

### Task 19: Modify monitoring/README.md — remove AlertManager references

**Files:**
- Modify: `monitoring/README.md`

- [ ] **Step 1: Find AlertManager references**

```bash
grep -n -i "alertmanager\|alert-manager\|alert manager" monitoring/README.md
```

Expected: per Branch E, the architecture diagram around lines 27-57 shows AlertManager.

- [ ] **Step 2: Update architecture diagram**

If the diagram is ASCII art with an "AlertManager :9093" box, remove that box and any arrows pointing to/from it. The new architecture diagram should show:

```
┌──────────────────────────────────────┐
│  Monitoring Server (AP-VM)            │
│  ┌──────────┐  ┌──────────┐  ┌─────┐ │
│  │ Grafana  │  │Prometheus│  │Loki │ │
│  └────┬─────┘  └────▲─────┘  └──▲──┘ │
│       │             │           │    │
│  ┌────┴────────────┴───────────┴──┐ │
│  │  Alerting → GitHub Issues       │ │
│  └─────────────────────────────────┘ │
└──────────────────────────────────────┘
```

If the diagram is more elaborate, simplify analogously while preserving the core relationships.

- [ ] **Step 3: Remove other AlertManager mentions**

Each non-diagram occurrence → either delete (if standalone) or replace with "Grafana unified alerting".

- [ ] **Step 4: Verify no AlertManager references remain**

```bash
grep -c -i "alertmanager\|alert-manager\|alert manager" monitoring/README.md
```

Expected: `0`.

- [ ] **Step 5: Commit**

```bash
git add monitoring/README.md
git commit -m "docs(monitoring): remove AlertManager from README architecture diagram

Replaces with Grafana unified alerting → GitHub Issues path.
Resolves: cross-branch observation."
```

---

### Task 20: Modify monitoring/GITHUB_DEPLOYMENT.md — remove ALERT_* secret references

**Files:**
- Modify: `monitoring/GITHUB_DEPLOYMENT.md`

(This file was already touched in Task 1 to add the migration checklist; this Task 20 cleans up dead `ALERT_*` content.)

- [ ] **Step 1: Find ALERT_* secret references**

```bash
grep -n -i "ALERT_EMAIL\|ALERT_SMTP\|ALERT_SLACK" monitoring/GITHUB_DEPLOYMENT.md
```

Expected: per Branch E observation around lines 97-102, the "Alert Configuration Secrets (Optional)" section.

- [ ] **Step 2: Delete the entire section**

Find and delete the block (likely under a heading like `### Alert Configuration Secrets (Optional)` or similar). The section's lines describing ALERT_EMAIL_FROM, ALERT_SMTP_HOST, ALERT_SLACK_WEBHOOK etc. are all removed.

If the section header has subsections, replace the entire section with:

```markdown

### Alert Configuration

Alerts are now handled by Grafana unified alerting + GitHub Issues. See `monitoring/PRODUCTION_RUNBOOK.md` for operational guidance and Phase 2 spec §6.2 for design rationale.

The only alerting-related secret is `GH_PAT` (already used by `mirror-to-production.yml`); it is read by Grafana via `/etc/grafana/secrets/gh_pat` mounted from `/opt/scholarship/secrets/gh_pat` on the host (provisioned by `deploy-monitoring-stack.yml`).
```

- [ ] **Step 3: Find any AlertManager references**

```bash
grep -n -i "alertmanager\|alert-manager\|alert manager" monitoring/GITHUB_DEPLOYMENT.md
```

Expected: any remaining mentions; remove or replace as in Task 18.

- [ ] **Step 4: Verify cleanup**

```bash
grep -c -iE "alertmanager|alert-manager|alert manager|ALERT_EMAIL|ALERT_SMTP|ALERT_SLACK" monitoring/GITHUB_DEPLOYMENT.md
```

Expected: `0`.

- [ ] **Step 5: Commit**

```bash
git add monitoring/GITHUB_DEPLOYMENT.md
git commit -m "docs(monitoring): remove dead ALERT_* secrets section from deployment guide

These secrets (ALERT_EMAIL_*, ALERT_SMTP_*, ALERT_SLACK_WEBHOOK) were
documented as optional but they are not consumed anywhere after
AlertManager removal at 57fca5f. Phase 2 chose GitHub Issues as the
alert receiver — only GH_PAT is needed.

Resolves: cross-branch observation from F-DEPL-07."
```

---

### Task 21: Bundle all PR-2.B changes to deploy-monitoring-stack.yml

**Files:**
- Modify: `.github/workflows/deploy-monitoring-stack.yml`

This task is single, sequential, and large because all PR-2.B changes to this one workflow must be applied together to avoid sub-edit conflicts. Six concerns are addressed:
1. Delete dead `ALERT_*` env exports (lines ~62-68).
2. Replace `grafana.ini` one-shot copy with always-overwrite (lines ~38-45).
3. Write GH_PAT to `/opt/scholarship/secrets/gh_pat` for Grafana to read.
4. Export `APP_NETWORK_NAME` + `MONITORING_SERVER_URL` and add unset-guard.
5. Replace simple health check with strengthened version (lines ~77-110).
6. Replace false-positive target check (lines ~248-261) and add MIN_EXPECTED + readiness polling.
7. Add `/tmp/monitoring-images/` cleanup (after the import step).

- [ ] **Step 1: Read the entire workflow file**

```bash
wc -l .github/workflows/deploy-monitoring-stack.yml
cat .github/workflows/deploy-monitoring-stack.yml
```

Expected: ~290 lines. Read the full content into context before editing.

- [ ] **Step 2: Concern 1 — Delete dead `ALERT_*` env exports**

In the "Deploy monitoring stack" step, find the block:

```yaml
          # Optional alert configuration
          export ALERT_EMAIL_FROM="${{ secrets.ALERT_EMAIL_FROM }}"
          export ALERT_SMTP_HOST="${{ secrets.ALERT_SMTP_HOST }}"
          export ALERT_SMTP_PORT="${{ secrets.ALERT_SMTP_PORT }}"
          export ALERT_SMTP_USER="${{ secrets.ALERT_SMTP_USER }}"
          export ALERT_SMTP_PASSWORD="${{ secrets.ALERT_SMTP_PASSWORD }}"
          export ALERT_SLACK_WEBHOOK="${{ secrets.ALERT_SLACK_WEBHOOK }}"
```

Replace with: (delete the comment line and 6 export lines entirely)

- [ ] **Step 3: Concern 2 — Replace one-shot copy with always-overwrite**

Find the block:

```yaml
          # Initialize Grafana config from example if it doesn't exist
          # This allows grafana.ini to be excluded from git while still functioning in deployment
          if [ ! -f /opt/scholarship/monitoring/config/grafana/grafana.ini ]; then
            echo "Creating Grafana configuration from example..."
            cp /opt/scholarship/monitoring/config/grafana/grafana.ini.example \
               /opt/scholarship/monitoring/config/grafana/grafana.ini
            echo "✅ Grafana configuration initialized"
          else
            echo "✅ Grafana configuration already exists"
          fi
```

Replace with:

```yaml
          # Always overwrite grafana.ini from the example so updates to the
          # example propagate. Secrets are injected via GF_SECURITY_* env
          # vars in compose, not from the ini file itself.
          cp /opt/scholarship/monitoring/config/grafana/grafana.ini.example \
             /opt/scholarship/monitoring/config/grafana/grafana.ini
          echo "✅ Grafana configuration written from example (always overwrites)"
```

- [ ] **Step 4: Concern 3 — Write GH_PAT to secrets file**

Insert before the `# Start/restart monitoring stack` line (and before any `docker compose up`):

```yaml
          # Write GH_PAT to a secrets file Grafana can mount via $__file{}
          sudo mkdir -p /opt/scholarship/secrets
          sudo chmod 700 /opt/scholarship/secrets
          echo "${{ secrets.GH_PAT }}" | sudo tee /opt/scholarship/secrets/gh_pat > /dev/null
          sudo chmod 600 /opt/scholarship/secrets/gh_pat
          # Grafana container UID is 472
          sudo chown 472:472 /opt/scholarship/secrets/gh_pat
          if [ ! -s /opt/scholarship/secrets/gh_pat ]; then
            echo "::error::GH_PAT file is empty after write"
            exit 1
          fi
          echo "✅ GH_PAT secrets file written"
```

- [ ] **Step 5: Concern 4 — Add APP_NETWORK_NAME export + unset-guards**

In the "Deploy monitoring stack" step's env-export section, replace:

```yaml
          export GRAFANA_ADMIN_USER="${{ secrets.GRAFANA_ADMIN_USER }}"
          export GRAFANA_ADMIN_PASSWORD="${{ secrets.GRAFANA_ADMIN_PASSWORD }}"
          export GRAFANA_SECRET_KEY="${{ secrets.GRAFANA_SECRET_KEY }}"
          export GRAFANA_ROOT_URL="${{ secrets.GRAFANA_ROOT_URL }}"
```

with:

```yaml
          # Required env vars; unset values fail-fast below
          export APP_NETWORK_NAME="scholarship_staging_network"
          export GRAFANA_ADMIN_USER="${{ secrets.GRAFANA_ADMIN_USER }}"
          export GRAFANA_ADMIN_PASSWORD="${{ secrets.GRAFANA_ADMIN_PASSWORD }}"
          export GRAFANA_ROOT_URL="${{ secrets.GRAFANA_ROOT_URL }}"

          for var in APP_NETWORK_NAME GRAFANA_ADMIN_USER GRAFANA_ADMIN_PASSWORD GRAFANA_ROOT_URL; do
            if [ -z "${!var}" ]; then
              echo "::error::Required env var $var is unset"
              exit 1
            fi
          done

          # Verify the named external network exists; create if missing
          docker network inspect "$APP_NETWORK_NAME" >/dev/null 2>&1 || \
            docker network create "$APP_NETWORK_NAME"
```

(`GRAFANA_SECRET_KEY` export is removed since the secret is intentionally not set.)

- [ ] **Step 6: Concern 5 — Replace the health check**

Find the entire `Health check monitoring services` step (lines ~77-110) and replace its `run:` block with:

```yaml
          set -e

          # Wait for Grafana to start (replaces hardcoded sleep 60)
          for i in $(seq 1 24); do
            if docker exec monitoring_grafana wget --spider -q http://localhost:3000/api/health 2>/dev/null; then
              break
            fi
            echo "Waiting for Grafana... ($i/24)"
            sleep 5
          done
          docker exec monitoring_grafana wget --spider -q http://localhost:3000/api/health || {
            echo "::error::Grafana did not start in 120s"; exit 1; }

          # 1. Container liveness
          for service in grafana prometheus loki; do
            container="monitoring_${service}"
            if ! docker ps --filter "name=${container}" --filter "status=running" --format '{{.Names}}' | grep -q "${container}"; then
              echo "::error::${container} is not running"
              exit 1
            fi
          done
          echo "✅ All monitoring containers running"

          # 2. Datasource health: every datasource must report status:ok
          AUTH_HDR="Authorization: Basic $(echo -n "${{ secrets.GRAFANA_ADMIN_USER }}:${{ secrets.GRAFANA_ADMIN_PASSWORD }}" | base64)"
          UIDS=$(docker exec monitoring_grafana wget -qO- \
            --header "$AUTH_HDR" \
            "http://localhost:3000/api/datasources" \
            | jq -r '.[].uid')
          for uid in $UIDS; do
            STATUS=$(docker exec monitoring_grafana wget -qO- \
              --header "$AUTH_HDR" \
              "http://localhost:3000/api/datasources/uid/$uid/health" \
              | jq -r '.status // "missing"')
            if [ "$STATUS" != "OK" ]; then
              echo "::error::Datasource $uid is not OK (status=$STATUS)"
              exit 1
            fi
          done
          echo "✅ All datasources healthy"

          # 3. No provisioning errors in Grafana startup logs
          if docker logs monitoring_grafana 2>&1 | grep -E 'level=error.*provisioning|failed to provision' > /tmp/grafana-prov-errors.txt; then
            echo "::error::Grafana provisioning errors found:"
            cat /tmp/grafana-prov-errors.txt
            exit 1
          fi
          echo "✅ No provisioning errors"

          # 4. Alert rules loaded successfully (zero failed-to-load)
          FAILED_RULES=$(docker exec monitoring_grafana wget -qO- \
            --header "$AUTH_HDR" \
            "http://localhost:3000/api/v1/provisioning/alert-rules" \
            | jq '[.[] | select(.execErrState=="Error")] | length')
          if [ "${FAILED_RULES:-0}" -gt 0 ]; then
            echo "::error::$FAILED_RULES alert rules failed to load"
            exit 1
          fi
          echo "✅ All alert rules loaded"

          echo "All monitoring services are healthy"
```

- [ ] **Step 7: Concern 6 — Fix Verify staging metrics step**

Find the `Verify staging metrics` step (lines ~248-261) and replace its `run:` block with:

```yaml
          set -e

          # Replace `sleep 30` with poll-until-targets-arrive
          for i in $(seq 1 18); do
            STAGING_TOTAL=$(curl -s http://localhost:9090/api/v1/targets \
              | jq '[.data.activeTargets[] | select(.labels.environment=="staging")] | length')
            if [ "${STAGING_TOTAL:-0}" -gt 0 ]; then
              break
            fi
            echo "Waiting for staging targets to register... ($i/18)"
            sleep 10
          done

          STAGING_TOTAL=$(curl -s http://localhost:9090/api/v1/targets \
            | jq '[.data.activeTargets[] | select(.labels.environment=="staging")] | length')
          STAGING_DOWN=$(curl -s http://localhost:9090/api/v1/targets \
            | jq '[.data.activeTargets[] | select(.labels.environment=="staging") | select(.health!="up")] | length')

          # Tunable: minimum expected staging targets
          # AP-VM: node, cadvisor, nginx, redis, backend = 5
          # DB-VM (after F-ALLO-09): node, postgres = 2
          # Total = 7
          MIN_EXPECTED=7
          if [ "$STAGING_TOTAL" -lt "$MIN_EXPECTED" ]; then
            echo "::error::Only $STAGING_TOTAL staging targets found; expected at least $MIN_EXPECTED"
            curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {scrapeUrl, env: .labels.environment, vm: .labels.vm, job: .labels.job}'
            exit 1
          fi
          if [ "$STAGING_DOWN" -gt 0 ]; then
            echo "::error::$STAGING_DOWN staging targets are DOWN"
            curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.environment=="staging") | select(.health!="up")'
            exit 1
          fi
          echo "✅ $STAGING_TOTAL staging targets all UP"

          # Loki check (existing; keep)
          if curl -f -H "X-Scope-OrgID: staging" -G "http://localhost:3100/loki/api/v1/query" \
            --data-urlencode 'query={environment="staging"}' \
            --data-urlencode 'limit=1' > /dev/null 2>&1; then
            echo "✅ Loki is receiving staging logs"
          else
            echo "⚠️  Warning: No staging logs found in Loki yet"
          fi
```

- [ ] **Step 8: Concern 7 — Add tar cleanup**

In the second job (`deploy-staging-db-monitoring`), after the existing "Cleanup SSH keys" step (or as a separate step at job end), add:

```yaml
      - name: Cleanup monitoring image tar files (AP-VM)
        if: always()
        run: rm -rf /tmp/monitoring-images
```

Place this BEFORE the "Deployment summary" step so cleanup happens regardless of summary success.

- [ ] **Step 9: Validate workflow YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-monitoring-stack.yml'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 10: Optional — actionlint and shellcheck**

```bash
which actionlint && actionlint .github/workflows/deploy-monitoring-stack.yml || echo "actionlint optional"
# shellcheck inline scripts:
which shellcheck && for f in $(awk '/run: \|/{flag=1; next} flag && /^[^ ]/{flag=0} flag{print}' .github/workflows/deploy-monitoring-stack.yml | head); do echo "$f" | shellcheck -; done || echo "shellcheck optional"
```

Expected: no errors if installed; otherwise skip.

- [ ] **Step 11: Commit**

```bash
git add .github/workflows/deploy-monitoring-stack.yml
git commit -m "ci(monitoring): bundle PR-2.B changes to deploy-monitoring-stack.yml

Six concerns in one commit (single-file constraint):
1. Delete 6 dead ALERT_* env exports (F-DEPL-07)
2. Always overwrite grafana.ini from example (F-DEPL-06)
3. Write GH_PAT to /opt/scholarship/secrets/gh_pat for Grafana (Phase 2 §6.2.3)
4. Export APP_NETWORK_NAME + unset-guard + idempotent network create (F-DEPL-04)
5. Strengthen health check: container liveness, datasource /health,
   provisioning logs, alert rule load status; replace sleep 60 with
   readiness polling (F-DEPL-01)
6. Fix Verify staging metrics: MIN_EXPECTED=7 + readiness polling
   for staging targets to arrive; replaces sleep 30 (F-DEPL-02)
7. Cleanup /tmp/monitoring-images on AP-VM after every run (F-DEPL-12)

GRAFANA_SECRET_KEY export removed since the secret is intentionally
unset (matches OLD repo posture)."
```

---

### Task 22: Post-deploy smoke test (after PR-2.B merge + deploy succeeds)

This is a verification task; not a code change. Documented for completeness.

- [ ] **Step 1: User merges PR-2.B**

PR-2.B opens against `main` once Tasks 4-21 complete. CI must pass (the strengthened health check is itself the test). Merge after review.

- [ ] **Step 2: Verify deploy ran on the new commit**

```bash
gh run list --workflow=deploy-monitoring-stack.yml --branch=main --limit=1 --repo anud18/scholarship-system
```

Expected: most recent run is `success` and triggered by the PR-2.B merge commit.

- [ ] **Step 3: Smoke test 1 — contact-point dry-run**

In Grafana UI:
1. Open `https://ss.test.nycu.edu.tw/monitoring/`
2. Navigate: Alerting → Contact points → `github-issue` → Test
3. Click "Send test notification"

Expected: within 30 seconds, GitHub issue appears at `anud18/scholarship-system` with title `Monitoring Alert: TestAlert (...)` and labels `monitoring-alert`, `alert:TestAlert`, etc. After verifying, manually close the test issue.

- [ ] **Step 4: Smoke test 2 — live alert trigger**

Temporarily lower `HighSystemLoad` threshold to `> 0` (always firing):

```bash
git checkout -b smoke/lower-systemload-threshold
# Edit monitoring/config/grafana/provisioning/alerting/rules-system.yml:
# Change: expr: node_load5 / count(...) > 2
# To:     expr: node_load5 / count(...) > 0
git commit -am "smoke: temporarily lower HighSystemLoad threshold for alert pipeline test"
git push origin smoke/lower-systemload-threshold

# Trigger workflow_dispatch for this branch (or merge a draft PR)
gh workflow run deploy-monitoring-stack.yml --ref smoke/lower-systemload-threshold
```

Wait 5 minutes (alert `for: 10m` is configured but the dispatch test needs faster feedback — alternatively change `for: 30s` for the test and revert).

Expected: GitHub issue opened with title `Monitoring Alert: HighSystemLoad (staging/warning)`. Labels include `alert:HighSystemLoad` and `env:staging`.

- [ ] **Step 5: Smoke test 3 — de-dupe**

Wait for `repeat_interval` (4h) to elapse, OR manually trigger another firing event (re-run the dispatch). Expect: same GitHub issue receives a new firing comment, NOT a new issue.

For faster verification: temporarily set `repeat_interval: 60s` in `notification-policies.yml` and re-deploy; revert after test.

- [ ] **Step 6: Smoke test 4 — reopen**

Manually close the test issue. Wait for next firing cycle. Expect: issue reopened + comment.

- [ ] **Step 7: Smoke test 5 — resolved**

Revert the threshold change:

```bash
git checkout main
git revert smoke/lower-systemload-threshold's-commit
git push
```

After deploy + `repeat_interval`, expect: resolved comment posted to the issue, issue stays OPEN (operator confirms RCA before closing).

- [ ] **Step 8: Document the smoke test results**

Append a section to `monitoring/PRODUCTION_RUNBOOK.md`:

```markdown

## Phase 2 Smoke Test Results — 2026-MM-DD

[Operator name] ran the 5-step smoke test (spec §7.2) on [date]. Results:

- Step 1 (contact-point test): PASS — issue #NNN created
- Step 2 (live trigger): PASS — issue #NNN created at HH:MM
- Step 3 (de-dupe): PASS — comment appended; no new issue
- Step 4 (reopen): PASS — issue reopened after manual close
- Step 5 (resolved): PASS — resolved comment appended; issue stays open
```

Commit this update:

```bash
git add monitoring/PRODUCTION_RUNBOOK.md
git commit -m "docs(monitoring): record Phase 2 smoke test results"
```

---

## Self-Review

Performed inline before this plan was committed:

- [x] **Spec coverage**: every spec section has at least one task:
  - §5 PR-2.A → Tasks 1, 2, 3
  - §6.1 file map → Tasks 4-21 (every listed file appears)
  - §6.2.1 alert disposition table → Tasks 5-8 (LIVE rules); deferred/dropped recorded in Task 7's commit message
  - §6.2.3 contact point + GH_PAT delivery → Task 9 (contact-points.yml) + Task 13 (compose mount) + Task 21 step 4 (deploy-side write)
  - §6.2.4 notification policies → Task 9
  - §6.2.5 receiver workflow → Task 10
  - §6.2.6 datasource cleanup → Task 11
  - §6.2.7 prometheus.yml cleanup → Task 12
  - §6.3 prod compose env-var → Tasks 13 + 21 step 5
  - §6.4 deploy honesty → Task 21 steps 2, 3, 6, 7
  - §6.5 DB-VM relabel pipeline → Tasks 14, 15
  - §6.6 mirror workflow fixes → Tasks 16, 17
  - §6.7 doc cleanup → Tasks 18, 19, 20
  - §7 verification → Task 22
  - §9 acceptance criteria → covered across task commit messages

- [x] **Placeholder scan**: no `TBD`, `TODO`, `implement later`, "fill in details" found. Every code step shows the actual content. Bash commands have expected outputs.

- [x] **Type / name consistency**:
  - Alert rule UIDs: `alert-high-cpu-usage` etc. consistent across rules-*.yml. Filenames match `rules-{system,container,database,monitoring}.yml`.
  - Datasource UID `prometheus-uid` referenced from contact-points.yml and rules-*.yml is the same value used in datasources.yml (verified by Branch B audit).
  - Contact point name `github-issue` referenced consistently in contact-points.yml and notification-policies.yml.
  - Workflow file `monitoring-alert-issue.yml` referenced consistently.
  - `APP_NETWORK_NAME` env var consistent across compose, deploy step, unset-guard.
  - Network alias `app_network` consistent across grafana/loki/prometheus service blocks and the bottom networks declaration.
  - GH_PAT mount path `/opt/scholarship/secrets/gh_pat` (host) → `/etc/grafana/secrets/gh_pat` (container) consistent across compose, deploy step, contact-points.yml.

- [x] **Granularity**: each step is 2–15 minutes. Task 21 is the longest (one file, 7 concerns), but each concern is a self-contained edit.

- [x] **Frequent commits**: 1 commit per task (22 commits total). Each commit message references the spec finding(s) it resolves.

- [x] **No production config modified outside the merge points**: PR-2.A and PR-2.B changes only touch repo files; operational secret-setting and runner-registration are explicitly user-driven (Task 3) and not in any subagent's scope.

---

## Notes for the executor

- **Stage 1 (Tasks 1-3) MUST complete and merge before Stage 2 starts.** No Stage 2 task should run until the user confirms the workflow_dispatch test from Task 3 succeeded.
- **Stage 2 parallelism**: Tasks 4-20 touch non-overlapping files and can be dispatched to subagents in parallel. Task 21 must run alone (sequential) because it bundles 7 sub-edits to a single file.
- **Task 22 (smoke tests) is operator-driven** after PR-2.B merge.
- The Phase 2 spec's §8 R6 warns that the first deploy after PR-2.B may reset UI-edited dashboards. Inform the operator before merge.
- **GH_PAT scope reuse risk** (per OQ-1 resolution): if Grafana is compromised, the PAT exposes prod-repo write. Phase 4 launch-gate revisits this trade-off.
