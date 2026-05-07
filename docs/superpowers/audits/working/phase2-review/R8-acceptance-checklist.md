# R8 — Phase 2 Spec §9.2 PR-2.B Acceptance Criteria Cross-Check

**Reviewer:** R8 (automated spec-compliance agent)
**Date:** 2026-05-06
**Branch:** `feat/monitoring-phase2`
**Spec:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-phase2-design.md` §9.2
**Method:** Static file inspection — git grep, ls, file reads. No live service calls.

---

## Criterion-by-Criterion Assessment

### AC-1 — Dead configs deleted

> `monitoring/config/alertmanager/`, `monitoring/config/prometheus/alerts/basic-alerts.yml`,
> `monitoring/config/prometheus/recording-rules/aggregations.yml` all deleted.

**Status: ✅ MET**

Evidence:
- `ls monitoring/config/alertmanager/` → `No such file or directory`
- `ls monitoring/config/prometheus/alerts/basic-alerts.yml` → `No such file or directory`
- `ls monitoring/config/prometheus/recording-rules/aggregations.yml` → `No such file or directory`

---

### AC-2 — 14 alert rules in rules-*.yml

> 14 alert rules live in `monitoring/config/grafana/provisioning/alerting/rules-*.yml`;
> 3 postgres alerts tracked via GitHub issue for Phase 3.

**Status: ✅ MET**

Evidence (`grep -c '^ *- uid:'` across 4 files):
- `rules-system.yml`: 5
- `rules-container.yml`: 4
- `rules-database.yml`: 2
- `rules-monitoring.yml`: 3
- **Total: 14** (matches spec)

Note: No GitHub issue verification possible from static review; assumed tracked per AC language ("tracked via GitHub issue for Phase 3" is an operator action).

---

### AC-3 — contact-points.yml and notification-policies.yml exist; dispatches URL correct

> `monitoring/config/grafana/provisioning/alerting/contact-points.yml` and
> `notification-policies.yml` exist; contact point references
> `https://api.github.com/repos/anud18/scholarship-system/dispatches`.

**Status: ✅ MET**

Evidence:
- `ls monitoring/config/grafana/provisioning/alerting/` → both files present
- `grep 'dispatches' contact-points.yml` → `url: https://api.github.com/repos/anud18/scholarship-system/dispatches`
- `notification-policies.yml` contains valid `apiVersion: 1` + `group_by: [alertname, environment]` + `repeat_interval: 4h`

---

### AC-4 — monitoring-alert-issue.yml exists; dry-run creates labelled issue

> `.github/workflows/monitoring-alert-issue.yml` exists; dry-run via `repository_dispatch`
> test creates a labelled issue.

**Status: ⏳ PARTIAL — file exists; dry-run is post-merge operator action**

Evidence:
- `test -f .github/workflows/monitoring-alert-issue.yml` → file exists
- Dry-run (`repository_dispatch` test) is a live smoke test per §7.2.1 — deferred to operator post-merge.

---

### AC-5 — datasources.yml has zero alertmanager references

> `monitoring/config/grafana/provisioning/datasources/datasources.yml` has zero
> `alertmanager` references.

**Status: ✅ MET**

Evidence:
- `grep -ic alertmanager monitoring/config/grafana/provisioning/datasources/datasources.yml` → `0`

---

### AC-6 — prometheus.yml has zero alerting: or rule_files: content

> `monitoring/config/prometheus/prometheus.yml` has zero `alerting:` or `rule_files:` content.

**Status: ✅ MET**

Evidence:
- `grep -c 'alerting:\|rule_files:' monitoring/config/prometheus/prometheus.yml` → `0`
- File header contains comment: "Alerting and rule_files removed in Phase 2 — alerts now handled by Grafana unified alerting"

---

### AC-7 — docker-compose.monitoring.yml references ${APP_NETWORK_NAME}; deploy step exports it; unset-guard catches missing value

> `monitoring/docker-compose.monitoring.yml` references `${APP_NETWORK_NAME}`;
> deploy step exports it; unset-guard catches missing value.

**Status: ✅ MET**

Evidence:
- `grep 'APP_NETWORK_NAME' monitoring/docker-compose.monitoring.yml` → line 163: `name: ${APP_NETWORK_NAME}`
- `deploy-monitoring-stack.yml` line 80: `export APP_NETWORK_NAME="scholarship_staging_network"`
- Lines 85-90: for-loop unset-guard over `APP_NETWORK_NAME GRAFANA_ADMIN_USER ...` exits with `::error::` if unset

---

### AC-8 — alloy db-vm files have prometheus.scrape + relabel + remote_write; up{...} returns ≥ 2 series

> `monitoring/config/alloy/staging-db-vm.alloy` and `prod-db-vm.alloy` have
> `prometheus.scrape` + `prometheus.relabel` + `prometheus.remote_write` blocks;
> after deploy, `up{environment="staging",vm="db-vm"}` returns ≥ 2 series.

**Status: ⏳ PARTIAL — static blocks present; live metric verification deferred**

Evidence (static):
- `staging-db-vm.alloy`: 3 `prometheus.scrape`, 1 `prometheus.relabel`, 1 `prometheus.remote_write` blocks found (grep count: 8 total references across both blocks)
- `prod-db-vm.alloy`: same counts (8 references)
- Both files scrape `node-exporter:9100` and `postgres-exporter:9187`, relabel with `environment` + `vm` labels, and remote_write to `$MONITORING_SERVER_URL:9090/api/v1/write`
- Live verification (`up{environment="staging",vm="db-vm"} ≥ 2`) requires a running Prometheus — deferred to operator post-deploy.

---

### AC-9 — mirror-to-production.yml strip rule preserves monitoring/**/*.md

> `mirror-to-production.yml` strip rule preserves `monitoring/**/*.md`.

**Status: ✅ MET**

Evidence:
- `grep 'not.*path.*monitoring' .github/workflows/mirror-to-production.yml` →
  line 341: `find . -type f -name "*.md" -not -path './monitoring/*' 2>/dev/null | xargs -r git rm -f 2>/dev/null || true`
- line 294: `if [[ "$file" != "./monitoring/"* ]]` — additional guard in the file-copy loop

---

### AC-10 — PRODUCTION_SYNC_GUIDE.md references GH_PAT consistently (zero PRODUCTION_SYNC_PAT remaining)

> `PRODUCTION_SYNC_GUIDE.md` references `GH_PAT` consistently
> (zero `PRODUCTION_SYNC_PAT` remaining).

**Status: ✅ MET**

Evidence:
- `grep -c 'PRODUCTION_SYNC_PAT' .github/PRODUCTION_SYNC_GUIDE.md` → `0`
- `grep -n 'GH_PAT' .github/PRODUCTION_SYNC_GUIDE.md` → lines 68, 389, 394 (3 occurrences — matches spec §6.6.2)

---

### AC-11 — PRODUCTION_RUNBOOK.md, README.md, GITHUB_DEPLOYMENT.md have zero alertmanager references

> `monitoring/PRODUCTION_RUNBOOK.md`, `README.md`, `GITHUB_DEPLOYMENT.md` have zero
> `alertmanager` references.

**Status: ⚠️ PARTIALLY MET — README.md retains stale ALERT_EMAIL_* / ALERT_SLACK_WEBHOOK block**

Evidence:
- `grep -ic alertmanager PRODUCTION_RUNBOOK.md` → `0` ✅
- `grep -ic alertmanager README.md` → `0` ✅ (the word "alertmanager" is gone)
- `grep -ic alertmanager GITHUB_DEPLOYMENT.md` → `0` ✅
- **However**, spec §6.7 also mandates removing `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK`:
  - `grep -in 'ALERT_EMAIL\|ALERT_SMTP\|ALERT_SLACK' README.md` → **6 matches** at lines 159-166 (stale `.env.monitoring` example block listing `ALERT_EMAIL_FROM`, `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`, `ALERT_SMTP_USER`, `ALERT_SMTP_PASSWORD`, `ALERT_SLACK_WEBHOOK`)
  - `PRODUCTION_RUNBOOK.md` and `GITHUB_DEPLOYMENT.md` are clean on all counts

The acceptance criterion as written only mentions "zero `alertmanager` references" — by that narrow reading this is ✅. But §6.7's instruction also covers `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK`, making the README.md incomplete. Flagged ⚠️ for reviewer attention.

---

### AC-12 — deploy-monitoring-stack.yml health check verifies datasource health, provisioning logs, alert rule load status, target count threshold; replaces hardcoded sleep 60 and sleep 30 with poll loops

> `deploy-monitoring-stack.yml` health check verifies datasource health, provisioning logs,
> alert rule load status, target count threshold; replaces hardcoded `sleep 60` and `sleep 30`
> with poll loops.

**Status: ⚠️ PARTIALLY MET — sleep 60 survives in deploy step; health check content is complete**

Evidence:
- Health check step (lines 116-178) ✅ contains:
  - Grafana readiness poll: `for i in $(seq 1 24); do wget --spider ...` (replaces the intent of sleep 60)
  - Datasource health: loops over all datasource UIDs and checks `status == OK` ✅
  - Provisioning log scan: `grep -E 'level=error.*provisioning|failed to provision'` ✅
  - Alert rule load: `jq '[.[] | select(.execErrState=="Error")] | length'` ✅
  - Target count threshold: `MIN_EXPECTED=7` with staging-filter and DOWN count check ✅
- "Verify staging metrics" step (lines 343-387): `sleep 30` replaced with poll-until loop ✅
- **Residual issue**: line 114 in the "Deploy monitoring stack" step still contains `sleep 60`:
  ```yaml
  # Start/restart monitoring stack
  docker compose -f docker-compose.monitoring.yml up -d
  # Wait for services to be healthy
  echo "Waiting for services to start..."
  sleep 60
  ```
  This `sleep 60` runs before the health-check step which has the proper poll loop. The poll loop comment says "replaces hardcoded sleep 60" but the hardcoded sleep was not deleted from the preceding step.

---

### AC-13 — /tmp/monitoring-images/ cleanup runs on AP-VM after every deploy

> `/tmp/monitoring-images/` cleanup runs on AP-VM after every deploy.

**Status: ✅ MET**

Evidence:
- `grep -n 'rm -rf /tmp/monitoring-images' deploy-monitoring-stack.yml`:
  - Line 286: `rm -rf /tmp/monitoring-images` (inside DB-VM SSH block; cleans the remote side)
  - Line 396: `run: rm -rf /tmp/monitoring-images` in step "Cleanup monitoring image tar files (AP-VM)" with `if: always()` ✅

---

### AC-14 — Smoke tests 7.2.1–7.2.5 all pass against staging

> Smoke tests 7.2.1–7.2.5 all pass against staging.

**Status: ⏳ DEFERRED — operator-driven post-merge**

Per spec §7.2, these are manual smoke tests that require:
1. A running Grafana instance on staging
2. Live alert triggering and GitHub issue creation
3. De-dupe, reopen, and resolved-comment verification

None can be verified statically. Deferred to operator after PR merges and deploy succeeds.

---

## Summary Table

| # | Criterion (abbreviated) | Status | Key finding |
|---|---|---|---|
| AC-1 | alertmanager dir + basic-alerts.yml + aggregations.yml deleted | ✅ | All three absent |
| AC-2 | 14 alert rules in rules-*.yml | ✅ | Count: 5+4+2+3 = 14 |
| AC-3 | contact-points.yml + notification-policies.yml; dispatches URL | ✅ | URL matches exactly |
| AC-4 | monitoring-alert-issue.yml exists; dry-run creates issue | ⏳ | File exists; dry-run is post-merge |
| AC-5 | datasources.yml zero alertmanager refs | ✅ | grep count = 0 |
| AC-6 | prometheus.yml zero alerting:/rule_files: | ✅ | grep count = 0 |
| AC-7 | docker-compose APP_NETWORK_NAME + export + unset-guard | ✅ | All three present |
| AC-8 | alloy db-vm scrape+relabel+remote_write; live metrics ≥ 2 | ⏳ | Static blocks present; live metric deferred |
| AC-9 | mirror strip preserves monitoring/**/*.md | ✅ | -not -path './monitoring/*' on line 341 |
| AC-10 | PRODUCTION_SYNC_GUIDE zero PRODUCTION_SYNC_PAT | ✅ | 0 remaining; GH_PAT at 3 locations |
| AC-11 | RUNBOOK/README/DEPLOYMENT zero alertmanager refs; ALERT_EMAIL_* removed | ⚠️ | alertmanager = 0 everywhere, but README.md retains 6 ALERT_EMAIL_*/ALERT_SLACK lines per §6.7 scope |
| AC-12 | Health check: datasource/prov-logs/alert-rules/target-count; no sleep 60/30 | ⚠️ | Health check step complete; sleep 60 survives at deploy-step line 114 |
| AC-13 | /tmp/monitoring-images cleanup with if:always() | ✅ | Line 396 with if:always() |
| AC-14 | Smoke tests 7.2.1–7.2.5 pass on staging | ⏳ | Operator-driven post-merge |

---

## Counts

| Result | Count |
|---|---|
| ✅ Fully met | 9 |
| ⚠️ Partially met / needs fix | 2 |
| ❌ Not met | 0 |
| ⏳ Deferred (operator / post-merge) | 3 |

---

## Fixes Required Before Merge

### FIX-1 (AC-12): Remove residual `sleep 60` from deploy step

**File:** `.github/workflows/deploy-monitoring-stack.yml`, lines 112-114

```yaml
          # Wait for services to be healthy        ← DELETE
          echo "Waiting for services to start..."  ← DELETE
          sleep 60                                  ← DELETE
```

The immediately following "Health check monitoring services" step already polls with `for i in $(seq 1 24)` and is the correct replacement. The `sleep 60` in the deploy step is redundant and contradicts the criterion.

### FIX-2 (AC-11): Remove stale ALERT_EMAIL_* / ALERT_SLACK_WEBHOOK block from README.md

**File:** `monitoring/README.md`, lines 158-166

```bash
# Optional: Email alerts
ALERT_EMAIL_FROM=alerts@example.com
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=your-email@gmail.com
ALERT_SMTP_PASSWORD=your-app-password

# Optional: Slack alerts
ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Spec §6.7 requires removing `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK` from all three monitoring markdown docs. RUNBOOK and DEPLOYMENT are clean; README.md was missed.

---

## Verdict

**NOT READY TO MERGE — needs 2 fixes.**

Both fixes are small (delete ~3 lines + delete ~9 lines). After applying FIX-1 and FIX-2, the branch satisfies all statically-verifiable criteria. The 3 ⏳ items (AC-4 dry-run, AC-8 live metrics, AC-14 smoke tests) are correctly deferred to the operator post-deploy and do not block merge.
