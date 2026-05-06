# Monitoring Stack Fix — Phase 2 Design Spec

**Date:** 2026-05-06
**Owner:** jotpalch (with Claude Code)
**Status:** Draft awaiting user review
**Branch:** `audit/monitoring-stack-phase1` (Phase 2 work continues here; rename pending after PR-2.A)
**Phase 1 audit:** [`docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md`](../audits/2026-05-06-monitoring-stack-audit.md) (commit `fba3e92`)
**Phase 1 spec:** [`docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md`](2026-05-06-monitoring-stack-fix-design.md) (commit `07faa57`)

---

## 1. Context

Phase 1 enumerated 11 P0 + 34 P1 + 9 P2 + 4 noted findings across the monitoring stack. Phase 2 fixes the 11 P0 findings plus 3 tightly-coupled P1 findings (`F-DEPL-09`, `F-DEPL-10`, `F-DEPL-12`) that block clean Phase 3 work. Production launch is `Not ready` until at least Phase 2 closes.

The deploy workflow has zero successful runs on `anud18/scholarship-system` since repo migration; staging Grafana is currently running config from the OLD `jotpalch/scholarship-system` repo (last successful run 2025-11-07). **Phase 2 must unblock this first; everything else depends on it.**

## 2. Goals

1. Make `deploy-monitoring-stack.yml` runnable on `anud18/scholarship-system` so subsequent monitoring config changes deploy automatically.
2. Replace the broken AlertManager pipeline with Grafana unified alerting + GitHub Issue receiver. Eliminate the silent alert-to-nowhere failure mode.
3. Fix `monitoring/docker-compose.monitoring.yml` so the same compose file deploys cleanly to both staging and prod AP-VMs by parameterizing the application network name.
4. Strengthen the deploy workflow's health check so the kind of P0 silent-failure surfaced in this audit (dangling datasource, false-positive target check) cannot recur.
5. Wire the missing relabel pipeline that gives DB-VM metrics the `environment` / `vm` labels dashboards depend on.
6. Fix the mirror workflow so `monitoring/**/*.md` survives the strip rule (so prod-side maintainers see the runbook).
7. Eliminate dead config (`alertmanager/`, `basic-alerts.yml`, `recording-rules/aggregations.yml`, dead `ALERT_*` env exports, AlertManager references in 3 markdown docs).

## 3. Non-Goals

- Backend metric instrumentation gaps (`F-APP-01`, `F-APP-04`, etc.) — Phase 3.
- Dashboard query and label drift (`F-GRAF-02..10`) — Phase 3.
- AP-VM Alloy drift (`F-ALLO-01..05`) — Phase 3.
- Cosmetic / hygiene fixes (`F-GRAF-06/07/11/12`, `F-DEPL-08`, etc.) — Phase 4.
- Prod-side `deploy-monitoring-stack-prod.yml` content — blind spot pending read access.
- Replacing `GH_PAT` with a fine-grained PAT — accepted trade-off; revisit before launch.

## 4. Sub-phase boundaries (2 PRs)

```
PR-2.A — deploy unblock (F-DEPL-03)
    └─► merge → trigger workflow_dispatch test → confirm green
        └─► PR-2.B — 13 content fixes
                └─► merge → next push to monitoring/** auto-deploys staging
                        └─► trigger mirror-to-production → review & merge prod-repo PR
```

**PR-2.A is a hard prerequisite.** PR-2.B work can be branched and reviewed in parallel, but no commit ships to staging until PR-2.A merges and the runner is verified.

## 5. PR-2.A — Deploy Unblock

### 5.1 In-scope

- Document the secrets and runner registration steps required by Phase 2 going forward.
- Add a pre-flight secret check to the workflow so missing secrets fail fast and visibly.
- The actual operational work (setting secrets, registering runner, triggering test dispatch) is **user-driven** outside the PR.

### 5.2 File changes

#### 5.2.1 `monitoring/GITHUB_DEPLOYMENT.md`

Add a new section "Repo Migration Checklist" with these contents:

```markdown
## Repo Migration Checklist (post-2026-05-06)

The deploy workflow on `anud18/scholarship-system` has zero successful runs after the migration from `jotpalch/scholarship-system`. Before any monitoring config change deploys, complete this checklist on `anud18/scholarship-system`:

### Required GitHub Repository Secrets

Set these via Settings → Secrets and variables → Actions:

| Name | Source | Notes |
|---|---|---|
| `GRAFANA_ADMIN_USER` | "admin" | Grafana admin login |
| `GRAFANA_ADMIN_PASSWORD` | password manager | rotate before prod launch (currently weak) |
| `GRAFANA_ROOT_URL` | "https://ss.test.nycu.edu.tw/monitoring" | nginx public URL |
| `STAGING_DB_HOST` | DB-VM IP (e.g., 10.113.74.25) | private subnet IP |
| `STAGING_DB_USER` | DB-VM SSH username | dedicated deploy user, key-auth |
| `STAGING_DB_SSH_KEY` | private key file content | full file including BEGIN/END markers |
| `STAGING_MONITORING_SERVER_URL` | AP-VM internal URL (e.g., http://10.113.74.X) | NO port; alloy appends :3100 / :9090 |

**Optional (intentionally not set):** `GRAFANA_SECRET_KEY` matches OLD repo's posture; Grafana generates a session key at startup. Trade-off: session cookies don't survive Grafana restart.

### Self-Hosted Runner

The deploy workflow runs on `runs-on: self-hosted`. The runner labelled `self-hosted, Linux, X64` must be registered to `anud18/scholarship-system` (Settings → Actions → Runners). The same physical machine that hosted the staging AP-VM runner on `jotpalch/scholarship-system` can be re-registered to the new repo; deregister first to avoid double-claim.

### Verification

After secrets and runner are in place:

```bash
# Trigger a test deploy
gh workflow run deploy-monitoring-stack.yml --repo anud18/scholarship-system

# Watch the run
gh run watch --repo anud18/scholarship-system
```

Expected: both jobs (`Deploy Monitoring Server (Staging AP-VM)` and `Deploy Staging DB-VM Monitoring`) succeed.
```

#### 5.2.2 `.github/workflows/deploy-monitoring-stack.yml`

Add a new step at the start of the first job, immediately after `Checkout code`:

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

The same step is added to the second job (`deploy-staging-db-monitoring`) so it fails before SSH'ing into DB-VM if SSH key / host secrets are missing.

### 5.3 PR-2.A acceptance

- `monitoring/GITHUB_DEPLOYMENT.md` updated with checklist; survives mirror because it's under `monitoring/` (Phase 2 also fixes `F-DEPL-09` to confirm).
- Pre-flight step exits non-zero with a clear error listing missing secrets when any are unset.
- After user completes the operational checklist, `gh workflow run deploy-monitoring-stack.yml` succeeds and produces both jobs `success`. Captured run ID gets recorded in PR description.

## 6. PR-2.B — Content Fixes

### 6.1 File map summary

**Delete entirely**:
- `monitoring/config/alertmanager/` (directory + `alertmanager.yml`)
- `monitoring/config/prometheus/alerts/basic-alerts.yml`
- `monitoring/config/prometheus/recording-rules/aggregations.yml`

**Create**:
- `monitoring/config/grafana/provisioning/alerting/contact-points.yml`
- `monitoring/config/grafana/provisioning/alerting/notification-policies.yml`
- `monitoring/config/grafana/provisioning/alerting/rules-system.yml` (5 rules)
- `monitoring/config/grafana/provisioning/alerting/rules-container.yml` (4 rules)
- `monitoring/config/grafana/provisioning/alerting/rules-database.yml` (2 rules — Redis only)
- `monitoring/config/grafana/provisioning/alerting/rules-monitoring.yml` (3 rules)
- `.github/workflows/monitoring-alert-issue.yml` (`repository_dispatch` receiver)

**Modify**:
- `monitoring/config/grafana/provisioning/datasources/datasources.yml` — delete AlertManager block
- `monitoring/config/prometheus/prometheus.yml` — delete commented-out `alerting:` block; leave `rule_files:` deleted (rules now live in Grafana)
- `monitoring/docker-compose.monitoring.yml` — parameterize `${APP_NETWORK_NAME}`
- `.github/workflows/deploy-monitoring-stack.yml` — multiple changes (see 6.4)
- `monitoring/config/alloy/staging-db-vm.alloy` and `prod-db-vm.alloy` — add scrape + relabel + remote_write blocks (`F-ALLO-09`)
- `.github/workflows/mirror-to-production.yml` — exclude `monitoring/**/*.md` from strip
- `.github/PRODUCTION_SYNC_GUIDE.md` — `PRODUCTION_SYNC_PAT` → `GH_PAT` (3 occurrences)
- `monitoring/PRODUCTION_RUNBOOK.md`, `monitoring/README.md`, `monitoring/GITHUB_DEPLOYMENT.md` — remove AlertManager references

### 6.2 Alert pipeline rewrite

#### 6.2.1 Inventory and disposition

Phase 1 audit reported "14 alert rules". Re-counting the actual file: 20 alert rules across 5 groups. Disposition:

| Group | Alert | Status | Phase 2 action |
|---|---|---|---|
| system_health | HighCPUUsage | LIVE | Migrate to `rules-system.yml` |
| system_health | HighMemoryUsage | LIVE | Migrate |
| system_health | DiskSpaceLow | LIVE | Migrate |
| system_health | DiskSpaceCritical | LIVE | Migrate |
| system_health | HighSystemLoad | LIVE | Migrate |
| container_health | ContainerDown | LIVE | Migrate to `rules-container.yml` |
| container_health | ContainerHighCPU | LIVE | Migrate |
| container_health | ContainerHighMemory | LIVE | Migrate |
| container_health | ContainerRestartingFrequently | LIVE | Migrate |
| database_health | PostgreSQLDown | DEFERRED | Skip; Phase 3 re-adds after DB-VM scrape fix (`F-PROM-05`) |
| database_health | PostgreSQLTooManyConnections | DEFERRED | Skip |
| database_health | PostgreSQLHighConnections | DEFERRED | Skip |
| database_health | RedisDown | LIVE | Migrate to `rules-database.yml` |
| database_health | RedisHighMemory | LIVE | Migrate |
| application_health | HighHTTPErrorRate | DROPPED | nginx-prometheus-exporter does not export `status` label (`F-GRAF-08`); will be replaced in Phase 3 with backend-side metrics |
| application_health | SlowHTTPResponseTime | DROPPED | `nginx_http_request_duration_seconds_bucket` does not exist (`F-PROM-08`); replaced in Phase 3 |
| application_health | MinIODown | DROPPED | `job="staging-db-minio"` does not exist (`F-PROM-07`); MinIO scraping itself is missing — re-design needed |
| monitoring_health | PrometheusTargetDown | LIVE | Migrate to `rules-monitoring.yml` |
| monitoring_health | LokiIngestionFallingBehind | LIVE | Migrate |
| monitoring_health | PrometheusStorageLow | LIVE | Migrate |

**Phase 2 net: 14 LIVE rules migrated. 3 DEFERRED to Phase 3. 3 DROPPED entirely.** Three GitHub issues filed in the same PR (or just before merge) tracking the DEFERRED postgres alerts so Phase 3 doesn't lose context.

#### 6.2.2 Grafana unified alerting rule format

Each rule file follows the standard `apiVersion: 1` + `groups:` provisioning shape:

```yaml
# monitoring/config/grafana/provisioning/alerting/rules-system.yml
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
            relativeTimeRange: { from: 300, to: 0 }
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
```

The 14 LIVE rules each follow this schema. PromQL expressions and labels/annotations carry over verbatim from `basic-alerts.yml` (only the rule wrapper format changes).

#### 6.2.3 Contact point — GitHub repository_dispatch

```yaml
# monitoring/config/grafana/provisioning/alerting/contact-points.yml
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
          # GH_PAT mounted as file at runtime by docker-compose; Grafana
          # reads it via the $__file{...} reference.
          authorization_credentials: $__file{/etc/grafana/secrets/gh_pat}
        # Override the default webhook body so GitHub's dispatches API
        # accepts it (event_type + client_payload wrapper).
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

**GH_PAT delivery to Grafana**: the existing `GH_PAT` secret already in `anud18/scholarship-system` is exported by the deploy workflow as a file mount. Add to `docker-compose.monitoring.yml`:

```yaml
grafana:
  environment:
    GF_SECURITY_ADMIN_USER: ${GRAFANA_ADMIN_USER}
    # ... (existing env vars unchanged) ...
  volumes:
    - grafana_data:/var/lib/grafana
    - ./config/grafana/provisioning:/etc/grafana/provisioning:ro
    - ./config/grafana/grafana.ini:/etc/grafana/grafana.ini:ro
    # New: secret file
    - /opt/scholarship/secrets/gh_pat:/etc/grafana/secrets/gh_pat:ro
```

And in `deploy-monitoring-stack.yml` deploy step:

```yaml
# Write GH_PAT to a file Grafana can read at runtime
sudo mkdir -p /opt/scholarship/secrets
sudo chmod 700 /opt/scholarship/secrets
echo "${{ secrets.GH_PAT }}" | sudo tee /opt/scholarship/secrets/gh_pat > /dev/null
sudo chmod 600 /opt/scholarship/secrets/gh_pat
sudo chown 472:472 /opt/scholarship/secrets/gh_pat  # 472 = grafana container UID
```

#### 6.2.4 Notification policies

```yaml
# monitoring/config/grafana/provisioning/alerting/notification-policies.yml
apiVersion: 1
policies:
  - orgId: 1
    receiver: github-issue
    group_by: [alertname, environment]
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 4h
```

`group_by [alertname, environment]` ensures one webhook per (alert, env) burst, not per individual instance. `repeat_interval: 4h` re-sends the same alert if still firing after 4 hours (so the GitHub issue gets a fresh `firing` comment as a heartbeat).

#### 6.2.5 GitHub Actions receiver workflow

```yaml
# .github/workflows/monitoring-alert-issue.yml
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
          echo "title=Monitoring Alert: $ALERT ($ENV/$SEVERITY)" >> $GITHUB_OUTPUT
          cat > /tmp/body.md <<EOF
          ## $STATUS — $ALERT

          **Environment:** $ENV
          **Severity:** $SEVERITY
          **Instance:** $INSTANCE
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
            echo "found=true" >> $GITHUB_OUTPUT
            echo "number=$(echo "$ISSUE" | jq -r .number)" >> $GITHUB_OUTPUT
            echo "state=$(echo "$ISSUE" | jq -r .state)" >> $GITHUB_OUTPUT
          else
            echo "found=false" >> $GITHUB_OUTPUT
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

**De-dupe behavior**:
- Same alertname + same env + currently open issue → append `firing` comment.
- Same alertname + same env + closed issue → reopen + append `firing` comment (treated as new event with continuity).
- Same alertname + same env + status=resolved + open issue → append `resolved` comment, do NOT auto-close (operator decides when to close).
- Resolved + closed issue → no-op (race condition guard).

**Label scheme**:
- `monitoring-alert` — universal
- `alert:<alertname>` — for de-dupe lookup
- `env:staging` or `env:prod`
- `severity:warning` or `severity:critical`

#### 6.2.6 Datasource provisioning cleanup

In `monitoring/config/grafana/provisioning/datasources/datasources.yml`, delete lines 109-121 (the `AlertManager` block):

```yaml
# REMOVED IN PHASE 2:
# - name: AlertManager
#   type: alertmanager
#   uid: alertmanager-uid
#   ...
```

#### 6.2.7 Prometheus config cleanup

In `monitoring/config/prometheus/prometheus.yml`, delete the commented-out `alerting:` block (lines 12-18) and `rule_files:` block (lines 20-23). The file becomes:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'scholarship-system'
    monitor: 'main-prometheus'

scrape_configs:
  # ... (existing self-scrape jobs) ...
```

### 6.3 Prod compose env-var refactor (F-DEPL-04, F-ALLO-08)

#### 6.3.1 `monitoring/docker-compose.monitoring.yml`

Replace every `scholarship_staging_network` reference with `${APP_NETWORK_NAME}`:

```yaml
services:
  grafana:
    networks:
      - monitoring_network
      - app_network    # alias declared below

  loki:
    networks:
      - monitoring_network
      - app_network

  prometheus:
    networks:
      - monitoring_network
      - app_network

networks:
  monitoring_network:
    driver: bridge
    ipam: { ... }
  app_network:
    external: true
    name: ${APP_NETWORK_NAME}
```

The `app_network` alias inside the compose file lets services reference a stable name, while Compose substitutes `${APP_NETWORK_NAME}` at runtime to resolve to `scholarship_staging_network` (staging) or `scholarship_prod_network` (prod).

#### 6.3.2 `deploy-monitoring-stack.yml` deploy step

Add `APP_NETWORK_NAME` and `MONITORING_SERVER_URL` to the env exports, with unset-guards:

```yaml
- name: Deploy monitoring stack
  run: |
    cd /opt/scholarship/monitoring

    # Required env vars with fail-fast guard
    export APP_NETWORK_NAME="scholarship_staging_network"  # hardcoded for staging
    export GRAFANA_ADMIN_USER="${{ secrets.GRAFANA_ADMIN_USER }}"
    export GRAFANA_ADMIN_PASSWORD="${{ secrets.GRAFANA_ADMIN_PASSWORD }}"
    export GRAFANA_ROOT_URL="${{ secrets.GRAFANA_ROOT_URL }}"

    # Validate required env
    for var in APP_NETWORK_NAME GRAFANA_ADMIN_USER GRAFANA_ADMIN_PASSWORD GRAFANA_ROOT_URL; do
      if [ -z "${!var}" ]; then
        echo "::error::Required env var $var is unset"
        exit 1
      fi
    done

    # Verify the named external network exists; create if missing for first deploy
    docker network inspect "$APP_NETWORK_NAME" >/dev/null 2>&1 || \
      docker network create "$APP_NETWORK_NAME"

    docker compose -f docker-compose.monitoring.yml up -d
```

For prod (in the prod-side workflow we don't control but document): `APP_NETWORK_NAME="scholarship_prod_network"`.

The DB-VM monitoring deploy step similarly guards `MONITORING_SERVER_URL`:

```yaml
# In deploy-staging-db-monitoring job, before SSH'ing:
if [ -z "${{ secrets.STAGING_MONITORING_SERVER_URL }}" ]; then
  echo "::error::STAGING_MONITORING_SERVER_URL is unset"
  exit 1
fi
```

### 6.4 Deploy workflow health check strengthening (F-DEPL-01, F-DEPL-02, F-DEPL-07)

In `.github/workflows/deploy-monitoring-stack.yml`:

#### 6.4.1 Delete the dead `ALERT_*` env exports (lines 62-68)

These six lines are removed entirely:

```yaml
# REMOVED:
# export ALERT_EMAIL_FROM="${{ secrets.ALERT_EMAIL_FROM }}"
# export ALERT_SMTP_HOST="${{ secrets.ALERT_SMTP_HOST }}"
# export ALERT_SMTP_PORT="${{ secrets.ALERT_SMTP_PORT }}"
# export ALERT_SMTP_USER="${{ secrets.ALERT_SMTP_USER }}"
# export ALERT_SMTP_PASSWORD="${{ secrets.ALERT_SMTP_PASSWORD }}"
# export ALERT_SLACK_WEBHOOK="${{ secrets.ALERT_SLACK_WEBHOOK }}"
```

#### 6.4.2 Replace `grafana.ini` one-shot copy (lines 38-45)

Always overwrite from example, since secrets are injected via env vars (`GF_SECURITY_*`), not from the ini file:

```yaml
- name: Deploy monitoring configuration
  run: |
    cp -r ./monitoring/* /opt/scholarship/monitoring/
    cp /opt/scholarship/monitoring/config/grafana/grafana.ini.example \
       /opt/scholarship/monitoring/config/grafana/grafana.ini
    echo "✅ Grafana configuration written from example (always overwrites)"
```

#### 6.4.3 Replace the simple health check (lines 77-110) with an honest one

```yaml
- name: Health check monitoring services
  run: |
    set -e

    # Wait for containers to start (replace sleep 60 with readiness polling)
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

    # 3. Provisioning errors in Grafana startup logs
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

#### 6.4.4 Fix the false-positive target check (lines 248-261)

```yaml
- name: Verify staging metrics
  run: |
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

    # Tunable: minimum expected targets for staging.
    # AP-VM: node, cadvisor, nginx, redis, backend = 5 minimum
    # DB-VM (after F-ALLO-09): node, postgres = 2 minimum
    # Total = 7
    MIN_EXPECTED=7
    if [ "$STAGING_TOTAL" -lt "$MIN_EXPECTED" ]; then
      echo "::error::Only $STAGING_TOTAL staging targets found; expected at least $MIN_EXPECTED"
      curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {scrapeUrl, env: .labels.environment, vm: .labels.vm, job: .labels.job}'
      exit 1
    fi
    if [ "$STAGING_DOWN" -gt 0 ]; then
      echo "::error::$STAGING_DOWN staging targets are DOWN"
      exit 1
    fi
    echo "✅ $STAGING_TOTAL staging targets all UP"
```

#### 6.4.5 Tar cleanup (`F-DEPL-12`)

Add at the end of the second job, with `if: always()`:

```yaml
- name: Cleanup monitoring image tar files (AP-VM)
  if: always()
  run: rm -rf /tmp/monitoring-images
```

### 6.5 DB-VM relabel pipeline (F-ALLO-09 + F-ALLO-06)

In both `monitoring/config/alloy/staging-db-vm.alloy` and `monitoring/config/alloy/prod-db-vm.alloy`, replace the existing METRICS PIPELINE comment block with actual scrape + relabel + remote_write blocks:

```alloy
// =============================================================================
// METRICS PIPELINE — PUSH MODE (matches AP-VM Alloy structure)
// =============================================================================
// Scrapes local exporters and pushes to AP-VM Prometheus via remote_write.
// Adds environment + vm labels via prometheus.relabel before push.

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
    replacement  = "staging"  // "prod" in prod-db-vm.alloy
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

### 6.6 Mirror workflow fixes

#### 6.6.1 `F-DEPL-09` — preserve `monitoring/**/*.md`

In `.github/workflows/mirror-to-production.yml` line 341, replace:

```bash
# Before:
find . -type f -name "*.md" 2>/dev/null | xargs -r git rm -f 2>/dev/null || true

# After:
find . -type f -name "*.md" -not -path './monitoring/*' 2>/dev/null | xargs -r git rm -f 2>/dev/null || true
```

#### 6.6.2 `F-DEPL-10` — `PRODUCTION_SYNC_PAT` → `GH_PAT`

In `.github/PRODUCTION_SYNC_GUIDE.md`, replace `PRODUCTION_SYNC_PAT` with `GH_PAT` at lines 68, 389, 394.

### 6.7 Documentation cleanup

In `monitoring/PRODUCTION_RUNBOOK.md`, `monitoring/README.md`, `monitoring/GITHUB_DEPLOYMENT.md`:

- Remove all references to AlertManager, `alertmanager:9093`, `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK`.
- Add a short section pointing to "Alerting now via Grafana unified alerting → GitHub Issues" with link to the labels filter `is:issue label:monitoring-alert`.
- Update architecture diagrams (ASCII or Mermaid) to remove the AlertManager box.

## 7. Verification & Test Strategy

### 7.1 Pre-merge automated checks

The strengthened deploy workflow (§6.4) is itself a regression guard: any future change that reintroduces a dangling datasource, removes a scrape target, or breaks alert provisioning fails the deploy.

### 7.2 Post-merge manual smoke test

Recorded in `monitoring/PRODUCTION_RUNBOOK.md` "Pre-launch smoke test" section, run after PR-2.B merges and deploy succeeds:

1. **Contact-point dry-run**: Grafana UI → Alerting → Contact points → `github-issue` → Test. Expect: GitHub issue created with title `Monitoring Alert: TestAlert (...)`.
2. **Live alert trigger**: temporarily edit `rules-system.yml` to set `HighSystemLoad` threshold to `> 0` (always firing). Wait 5 minutes. Expect: GitHub issue opened, labels `monitoring-alert + alert:HighSystemLoad + env:staging + severity:warning`.
3. **De-dupe test**: leave the always-firing rule for another 5 minutes. Expect: same issue receives a new firing comment, NOT a new issue.
4. **Reopen test**: manually close the issue. Wait for next firing cycle. Expect: issue reopened + comment.
5. **Resolved test**: revert the threshold edit. Within `repeat_interval`, expect: resolved comment posted, issue stays open (operator confirms RCA before closing).

### 7.3 Deploy honesty verification

Run before declaring PR-2.B complete:

```bash
# After deploy succeeds, intentionally break the alertmanager datasource
# (re-add the deleted block to a fork of datasources.yml) and re-deploy.
# The strengthened health check should fail the deploy.
```

This is a destructive test — only run on a throwaway branch, not main.

## 8. Risks

- **R1**: Grafana webhook contact-point template engine differs subtly between Grafana versions; the `(index .Alerts 0)` syntax is needed in 12.x but earlier versions used different accessors. Mitigation: pin to Grafana 12.2.1 Enterprise (current); test the rendered body in dry-run before merge.
- **R2**: `find ... -not -path './monitoring/*'` syntax depends on shell `find` implementation. The mirror workflow runs on `ubuntu-latest`, which has GNU find — the syntax is supported. Mitigation: dry-run the modified strip command before merge.
- **R3**: Switching from `scholarship_staging_network` (hardcoded) to `${APP_NETWORK_NAME}` is a change visible to Compose at restart time; if the env var is unset on the host, all 3 monitoring containers fail to start. Mitigation: the deploy step's unset-guard catches this before `docker compose up`. On first deploy after PR-2.B merges, the network may need creation if `docker network inspect` returns missing — `docker network create $APP_NETWORK_NAME` runs idempotently.
- **R4**: The 14 LIVE alerts include `DiskSpaceLow` (>80%) and `DiskSpaceCritical` (>90%) which may immediately fire on staging if disk is genuinely close to threshold. Spam is bounded by `group_wait: 30s` + `repeat_interval: 4h`. If staging's disk really is full, the alert is correct. Mitigation: review staging disk before merge; if pre-existing problem, file pre-emptive issue.
- **R5**: `GH_PAT` reuse means a Grafana compromise exposes write access to the production repo. Accepted trade-off (per OQ-1 resolution). Mitigation: Phase 4 launch-gate may downgrade to fine-grained PAT.
- **R6**: Grafana on staging is currently running 6-month-old config. After PR-2.A wires deploy and the first push lands, Grafana restart will reload config from disk. Provisioned dashboards previously edited via UI (per `F-GRAF-11`) will be reset to repo state. Mitigation: explicit warning in `monitoring/PRODUCTION_RUNBOOK.md`; check `provisioned: true` after first deploy.
- **R7**: Prod-side workflow blind spot. Phase 2 changes that affect prod (mirror behavior, compose env vars) cannot be verified in prod from this repo. Mitigation: follow-up GitHub issue tracking the prod-side workflow review pending read access.

## 9. Acceptance Criteria

### 9.1 PR-2.A acceptance

- [ ] `monitoring/GITHUB_DEPLOYMENT.md` has the "Repo Migration Checklist" section.
- [ ] `deploy-monitoring-stack.yml` has the pre-flight secret check that fails fast on missing secrets.
- [ ] User completes operational checklist (sets remaining 2 secrets, registers runner).
- [ ] One successful `workflow_dispatch` test run; both jobs succeed.

### 9.2 PR-2.B acceptance

- [ ] `monitoring/config/alertmanager/`, `monitoring/config/prometheus/alerts/basic-alerts.yml`, `monitoring/config/prometheus/recording-rules/aggregations.yml` all deleted.
- [ ] 14 alert rules live in `monitoring/config/grafana/provisioning/alerting/rules-*.yml`; 3 postgres alerts tracked via GitHub issue for Phase 3.
- [ ] `monitoring/config/grafana/provisioning/alerting/contact-points.yml` and `notification-policies.yml` exist; contact point references `https://api.github.com/repos/anud18/scholarship-system/dispatches`.
- [ ] `.github/workflows/monitoring-alert-issue.yml` exists; dry-run via `repository_dispatch` test creates a labelled issue.
- [ ] `monitoring/config/grafana/provisioning/datasources/datasources.yml` has zero `alertmanager` references.
- [ ] `monitoring/config/prometheus/prometheus.yml` has zero `alerting:` or `rule_files:` content.
- [ ] `monitoring/docker-compose.monitoring.yml` references `${APP_NETWORK_NAME}`; deploy step exports it; unset-guard catches missing value.
- [ ] `monitoring/config/alloy/staging-db-vm.alloy` and `prod-db-vm.alloy` have `prometheus.scrape` + `prometheus.relabel` + `prometheus.remote_write` blocks; after deploy, `up{environment="staging",vm="db-vm"}` returns ≥ 2 series.
- [ ] `mirror-to-production.yml` strip rule preserves `monitoring/**/*.md`.
- [ ] `PRODUCTION_SYNC_GUIDE.md` references `GH_PAT` consistently (zero `PRODUCTION_SYNC_PAT` remaining).
- [ ] `monitoring/PRODUCTION_RUNBOOK.md`, `README.md`, `GITHUB_DEPLOYMENT.md` have zero `alertmanager` references.
- [ ] `deploy-monitoring-stack.yml` health check verifies datasource health, provisioning logs, alert rule load status, target count threshold; replaces hardcoded `sleep 60` and `sleep 30` with poll loops.
- [ ] `/tmp/monitoring-images/` cleanup runs on AP-VM after every deploy.
- [ ] Smoke tests 7.2.1–7.2.5 all pass against staging.

### 9.3 Deferred to Phase 3

- Re-add the 3 postgres alerts after `F-PROM-05` / `F-ALLO-06` is fixed.
- Replace the 3 dropped application alerts (HighHTTPErrorRate, SlowHTTPResponseTime, MinIODown) with backend-metric-driven equivalents.

### 9.4 Deferred to Phase 4

- Replace `GH_PAT` with fine-grained PAT scoped to `Actions: write` only.
- Rotate `GRAFANA_ADMIN_PASSWORD` to a strong value.
- Remove `or 0` masking patterns from dashboards (cosmetic finding F-GRAF-06/07, F-APP-07).

## 10. Open Questions

- **OQ-1** (deferred): Prod-side `deploy-monitoring-stack-prod.yml` content — pending user-supplied read access. Phase 2 changes that affect prod may need adaptation in the prod-side workflow that we cannot author from this repo.
- **OQ-2** (deferred): Disk usage on staging at deploy time. If pre-existing high-disk-usage state, `DiskSpaceLow` may immediately fire on first deploy. Decision: review at deploy time; if false-positive due to known issue, raise threshold or add `for: 30m` hold-down.

## 11. Next Steps

1. User reviews this spec.
2. Spec changes (if any) are made in this file.
3. Once approved, brainstorming flow transitions to `superpowers:writing-plans` for the Phase 2 implementation plan.
4. Plan execution: PR-2.A first → user verifies via `workflow_dispatch` → PR-2.B branched off PR-2.A.
