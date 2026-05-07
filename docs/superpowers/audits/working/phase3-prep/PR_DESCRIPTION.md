# Phase 2 Monitoring Stack Fix — PR Description

## Summary

- **Alerts migrated to Grafana Unified Alerting**: 14 alert rules (system, container, Redis, monitoring-health) ported from dead Prometheus + AlertManager configs into Grafana provisioning YAML; GitHub Issues is now the sole notification channel via a new `monitoring-alert-issue.yml` receiver workflow.
- **Deploy honesty + infra correctness**: `deploy-monitoring-stack.yml` now fails fast on missing secrets, replaces bare `sleep 60/30` with poll loops, parameterizes the app-network name, mounts `GH_PAT` securely, and pushes DB-VM node/postgres metrics to Prometheus via Alloy remote_write.
- **Scope**: 39 commits, 43 files, +4 587 / -983 lines spanning CI workflows, Alloy configs, Grafana provisioning, and monitoring documentation; all statically-verifiable acceptance criteria met.

---

## Context

| Reference | Commit | What it establishes |
|---|---|---|
| Phase 1 audit (11 P0 + 3 P1 fixed) | `fba3e92` | Baseline findings that Phase 2 addresses |
| Phase 2 design spec | `57d0ed0` | Architecture rationale (Grafana UA, GH Issues receiver, DB-VM pipeline) |
| Phase 2 implementation plan (22 tasks) | `1861700` | Per-task commit map; Tasks 3 + 22 are operator-driven |

---

## Changes (organized by spec finding)

| Finding | Severity | What changed | Commit(s) |
|---|---|---|---|
| **F-DEPL-03** — Repo Migration Checklist missing | P0 | Added 7-secret table + runner registration + verify commands to `GITHUB_DEPLOYMENT.md` | `486e9c3` |
| **F-PROM-01** — Prometheus alerting stanza not empty | P0 | Removed `alerting:` and `rule_files:` comments from `prometheus.yml` | `1b750bc` |
| **F-PROM-02** — Dead AlertManager datasource in Grafana | P0 | Removed AlertManager entry from `datasources.yml` | `fa1cd7c` |
| **F-PROM-03 / F-GRAF-01** — No unified alert rules | P0 | Created `rules-system.yml` (5), `rules-container.yml` (4), `rules-database.yml` (2 live), `rules-monitoring.yml` (3) | `ad6bc46` `2083c10` `51d1d7e` `121a291` |
| **F-GRAF-01 (contact + policy)** — No contact point or policy | P0 | Created `contact-points.yml` (GitHub dispatches) + `notification-policies.yml` | `22ab53e` |
| **F-DEPL-07** — No GitHub Issues receiver workflow | P0 | Created `.github/workflows/monitoring-alert-issue.yml` (5-state de-dupe machine) | `2cfabcd` |
| **F-DEPL-04** — Hardcoded `scholarship_staging_network` in compose | P1 | Parameterized to `${APP_NETWORK_NAME}` in compose; workflow exports and unset-guards it | `f272a69` `21a07d7` |
| **F-DEPL-01** — `sleep 60/30` not replaced with poll loops | P1 | Replaced `sleep 30` in metrics-verify step with 180 s poll loop; bundled into deploy workflow | `21a07d7` |
| **F-DEPL-02** — No pre-flight secret check | P1 | Added 7-secret pre-flight step (fails fast) to both jobs in `deploy-monitoring-stack.yml` | `aac1497` |
| **F-ALLO-09 + F-ALLO-06** — DB-VM metrics not reaching Prometheus | P1 | Added `prometheus.scrape + relabel + remote_write` pipeline to `staging-db-vm.alloy` and `prod-db-vm.alloy` | `914a493` `34aa2d1` |
| **F-DEPL-09** — Mirror strip rule deletes `monitoring/*.md` | P1 | Added `-not -path './monitoring/*'` to `find` command in `mirror-to-production.yml` | `af740e8` |
| **F-DEPL-10** — PAT secret renamed | P1 | `PRODUCTION_SYNC_PAT` → `GH_PAT` in `PRODUCTION_SYNC_GUIDE.md` | `61d6c22` |
| **F-DEPL-12** — No tar cleanup after deploy | P1 | Added cleanup step with `if: always()` at end of AP-VM job | `21a07d7` |
| **Dead configs** (AlertManager dir, `basic-alerts.yml`, `aggregations.yml`) | P0 | Deleted three dead config trees | `052e408` |
| **Doc cleanup** — AlertManager refs in 4 docs | P1 | Removed AlertManager architecture from `README.md`, `PRODUCTION_RUNBOOK.md`, `GITHUB_DEPLOYMENT.md`; added Grafana alerting sections | `1b3fb93` `6eed22f` `96b9040` |
| **R2 fix** — `sleep 60` survived in deploy step | Medium | Removed residual `sleep 60` from "Deploy monitoring stack" step (R2 / AC-12) | `1ec4427` |
| **R3 fixes** — Receiver workflow edge cases | P1 | F-R3-01: added `${VAR:-"(unknown)"}` defaults; F-R3-02: stripped newlines in title output; F-R3-05: resolved timestamp now uses fresh date | `1ec4427` |
| **R6 fixes** — README + RUNBOOK stale AlertManager references | Medium/High | Removed `ALERT_EMAIL_*`/`ALERT_SLACK_WEBHOOK` from README Quick Start, feature bullets, checklist; replaced dead `curl localhost:9093` in RUNBOOK and GITHUB_DEPLOYMENT.md | `aa849fc` |
| **R7 / F-DEPL-09 verification** | — | Mirror strip rule audit (pass, no code change needed) | `9fcabbe` |
| **GH_PAT mount for Grafana** | P1 | `docker-compose.monitoring.yml` mounts `/opt/scholarship/secrets/gh_pat` read-only into Grafana container | `f272a69` |
| **Phase 3 prep docs** | Info | Dashboard query fix plan, backend instrumentation plan, deferred-alerts redesign, P1/P2 grouping docs | `b246c5c` `b33705d` `580a56b` `4764338` `ca1c994` |

> **Note on bundled dashboard query fixes (F-GRAF-03/05/09/11/12 + MinIO panels):** 19 dashboard query corrections were bundled into the PR-2.B deploy workflow concern block (`21a07d7`). These close 7 P1/P2 dashboard findings from the Phase 1 audit that were not in the original Phase 2 plan.

---

## File map

### Created (A)
| File | Purpose |
|---|---|
| `.github/workflows/monitoring-alert-issue.yml` | GitHub Issues receiver workflow (5-state de-dupe) |
| `monitoring/config/grafana/provisioning/alerting/contact-points.yml` | GitHub dispatches contact point |
| `monitoring/config/grafana/provisioning/alerting/notification-policies.yml` | Alert routing policy |
| `monitoring/config/grafana/provisioning/alerting/rules-system.yml` | 5 system_health alert rules |
| `monitoring/config/grafana/provisioning/alerting/rules-container.yml` | 4 container_health alert rules |
| `monitoring/config/grafana/provisioning/alerting/rules-database.yml` | 2 database_health rules (Redis; Postgres deferred) |
| `monitoring/config/grafana/provisioning/alerting/rules-monitoring.yml` | 3 monitoring_health alert rules |
| `monitoring/config/grafana/provisioning/dashboards/logs/application-logs.json` | Replaced application-logs dashboard (moved path) |
| `docs/superpowers/audits/working/PHASE2_AUTONOMOUS_REPORT.md` | Autonomous agent final report |
| `docs/superpowers/audits/working/phase2-review/R1-alert-rules.md` | Alert rule preservation audit |
| `docs/superpowers/audits/working/phase2-review/R2-deploy-workflow.md` | Deploy workflow audit |
| `docs/superpowers/audits/working/phase2-review/R3-receiver-workflow.md` | GitHub Issue receiver audit |
| `docs/superpowers/audits/working/phase2-review/R4-compose-and-contact-points.md` | Compose + contact-points audit |
| `docs/superpowers/audits/working/phase2-review/R5-alloy-db-vm.md` | Alloy DB-VM file audit |
| `docs/superpowers/audits/working/phase2-review/R6-doc-cleanup.md` | Documentation cleanup audit |
| `docs/superpowers/audits/working/phase2-review/R7-mirror-strip-rule.md` | Mirror strip rule audit |
| `docs/superpowers/audits/working/phase2-review/R8-acceptance-checklist.md` | Spec acceptance criteria cross-check |
| `docs/superpowers/audits/working/phase3-prep/backend-instrumentation-plan.md` | Phase 3 backend metric plan |
| `docs/superpowers/audits/working/phase3-prep/dashboard-query-fixes.md` | Phase 3 dashboard query fix plan |
| `docs/superpowers/audits/working/phase3-prep/deferred-alerts-redesign.md` | Phase 3 deferred alert redesign |
| `docs/superpowers/audits/working/phase3-prep/phase3-grouping.md` | Phase 3 P1 findings grouping |
| `docs/superpowers/audits/working/phase3-prep/phase4-grouping.md` | Phase 4 P2 findings grouping |
| `scripts/audit/probe-prom.sh` | Updated Prometheus probe script with Grafana 401 detection |

### Modified (M)
| File | What changed |
|---|---|
| `.github/PRODUCTION_SYNC_GUIDE.md` | `PRODUCTION_SYNC_PAT` → `GH_PAT` |
| `.github/workflows/deploy-monitoring-stack.yml` | Pre-flight check, sleep removal, poll loops, GH_PAT mount, network param, tar cleanup, dashboard fixes |
| `.github/workflows/mirror-to-production.yml` | `-not -path './monitoring/*'` strip rule fix |
| `docs/deployment/production-deployment.md` | Updated for Phase 2 changes |
| `monitoring/config/alloy/staging-db-vm.alloy` | Added Prometheus scrape + relabel + remote_write pipeline |
| `monitoring/config/alloy/prod-db-vm.alloy` | Added Prometheus scrape + relabel + remote_write pipeline |
| `monitoring/config/grafana/provisioning/dashboards/dashboards.yml` | Updated dashboard provisioning |
| `monitoring/config/grafana/provisioning/dashboards/application/container-monitoring.json` | Query fixes |
| `monitoring/config/grafana/provisioning/dashboards/application/nginx-monitoring.json` | Query fixes |
| `monitoring/config/grafana/provisioning/dashboards/database/minio-monitoring.json` | Panel fixes |
| `monitoring/config/grafana/provisioning/dashboards/database/postgresql-monitoring.json` | Query fixes |
| `monitoring/config/grafana/provisioning/dashboards/database/redis-monitoring.json` | Query fixes |
| `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json` | Query fixes |
| `monitoring/config/grafana/provisioning/dashboards/system/node-exporter-system.json` | Query fixes |
| `monitoring/config/grafana/provisioning/datasources/datasources.yml` | AlertManager datasource removed |
| `monitoring/config/prometheus/prometheus.yml` | `alerting:` and `rule_files:` removed |
| `monitoring/docker-compose.monitoring.yml` | `${APP_NETWORK_NAME}` param + GH_PAT volume mount |
| `monitoring/DASHBOARDS.md` | Updated documentation |
| `monitoring/GITHUB_DEPLOYMENT.md` | Repo Migration Checklist added; AlertManager refs removed; dead curl replaced |
| `monitoring/PRODUCTION_RUNBOOK.md` | Alerting section added; dead curl localhost:9093 replaced |
| `monitoring/QUICKSTART.md` | Updated for Phase 2 |
| `monitoring/README.md` | Architecture diagram updated; ALERT_EMAIL_* / ALERT_SLACK refs removed; feature bullets updated |
| `monitoring/scripts/download-community-dashboards.sh` | Updated |
| `monitoring/scripts/restore-monitoring.sh` | AlertManager references removed |
| `monitoring/tests/test-monitoring-stack.sh` | AlertManager test steps removed |

### Deleted (D)
| File | Reason |
|---|---|
| `monitoring/config/alertmanager/alertmanager.yml` | AlertManager removed in Phase 2 |
| `monitoring/config/prometheus/alerts/basic-alerts.yml` | Rules migrated to Grafana provisioning YAML |
| `monitoring/config/prometheus/recording-rules/aggregations.yml` | Dead recording rules removed |
| `monitoring/config/grafana/provisioning/dashboards/application/application-logs.json` | Moved to `logs/` subfolder |

---

## Review findings + fixes applied

### R1 — Alert Rule Preservation Audit (`R1-alert-rules.md`)
**Verdict: PASS — no action required.**
All 14 live rules verified byte-equivalent in PromQL semantics, labels, durations, and annotation templates. 3 deferred PostgreSQL rules confirmed absent and comment-documented. 3 dropped application rules confirmed absent. One minor observation (ContainerRestartingFrequently `relativeTimeRange.from` vs `[15m]` expression window) is pre-existing, functionally harmless, and consistent with spec intent.

### R2 — Deploy Workflow Audit (`R2-deploy-workflow.md`)
**Findings: 1 Medium, 2 Low.**
- **Medium — residual `sleep 60`** in "Deploy monitoring stack" step (spec said replace it; only the health-check step got the poll loop). **Fixed in `1ec4427`**: deleted 3 lines from the deploy step.
- Low — `REQUIRED_SECRETS` uses `|` block scalar (fragile in exotic shells, works in practice). Not fixed; acceptable risk.
- Low — `STAGING_MONITORING_SERVER_URL` guard relies on pre-flight step rather than an explicit shell check. Not fixed; functionally equivalent.

### R3 — GitHub Issue Receiver Workflow Audit (`R3-receiver-workflow.md`)
**Findings: 2 P1, 2 P2.**
- **F-R3-01 (P1)** — Missing payload fields produce empty issue body. **Fixed in `1ec4427`**: added `${VAR:-"(unknown)"}` defaults for all client_payload fields.
- **F-R3-02 (P1)** — Newline injection into `GITHUB_OUTPUT` via client_payload title fields. **Fixed in `1ec4427`**: title-output now uses `printf '%s' | tr -d '\n'`.
- **F-R3-05 (P2)** — Resolved-comment timestamp label misleadingly showed `fired_at`. **Fixed in `1ec4427`**: now uses a fresh `$(date -u +"%Y-%m-%dT%H:%M:%SZ")` timestamp with corrected label.
- F-R3-03 (P2) — `--limit 1` ordering not guaranteed on duplicate issues. Not fixed; low probability, acceptable for scope.

### R4 — Compose + Contact Points + Notification Policies Audit (`R4-compose-and-contact-points.md`)
**Verdict: PASS — no action required.**
All compose network, volume, and GRAFANA_SECRET_KEY posture checks pass. contact-points.yml and notification-policies.yml are fully spec-compliant. Only two INFO-level findings: the obsolete `version: '3.8'` field (cosmetic) and the accepted `GRAFANA_SECRET_KEY` empty-string posture.

### R5 — Alloy DB-VM Files Audit (`R5-alloy-db-vm.md`)
**Verdict: PASS — no action required.**
Both `staging-db-vm.alloy` and `prod-db-vm.alloy` correctly implement the `prometheus.scrape + prometheus.relabel + prometheus.remote_write` pipeline per spec §6.5. All existing logging pipeline blocks intact. The only unexpected diff is the pre-existing `F-ALLO-02` slash-strip rule absent from prod (container name leading `/`), which is deferred to Phase 3.

### R6 — Documentation Cleanup Audit (`R6-doc-cleanup.md`)
**Findings: 3 HIGH, 2 MEDIUM, 1 LOW.**
- **R6-01/02/03 (HIGH)** — `monitoring/README.md` still contained `ALERT_EMAIL_*`/`ALERT_SLACK_WEBHOOK` in Quick Start env block, stale feature bullets, and a checklist item. **Fixed in `aa849fc`**: removed all six occurrences; replaced with GitHub Issues references.
- **R6-04/05 (MEDIUM)** — `monitoring/PRODUCTION_RUNBOOK.md` lines 66 + 379 had dead `curl localhost:9093` calls breaking the `&&` health-check chain. **Fixed in `aa849fc`**: replaced with Grafana `/api/health` and `/api/v1/provisioning/alert-rules` equivalents.
- **R6-06 (LOW)** — `GITHUB_DEPLOYMENT.md` line 252 had a dead AlertManager curl in a manual-deployment block. **Fixed in `aa849fc`**: replaced with Grafana health check.

### R7 — Mirror Strip Rule Audit (`R7-mirror-strip-rule.md`)
**Verdict: PASS — no action required.**
`-not -path './monitoring/*'` correctly preserves all five `monitoring/*.md` files including nested subdirectories. GNU find `-not -path` verified compatible with ubuntu-latest. Root-level `monitoring.md` (if it existed) would still be stripped — correct behavior.

### R8 — Spec Acceptance Criteria Cross-Check (`R8-acceptance-checklist.md`)
**Verdict at time of review: NOT READY (2 fixes required). Post-fix verdict: READY.**
- 9/14 criteria fully met at review time.
- ⚠️ AC-11 (README.md ALERT_EMAIL_* stale) → **fixed by `aa849fc`** (R6 fixes).
- ⚠️ AC-12 (`sleep 60` survives deploy step) → **fixed by `1ec4427`** (R2 fix).
- ⏳ AC-4 (dry-run creates issue), AC-8 (live metric ≥ 2 series), AC-14 (smoke tests) — all operator-driven post-merge; not blocking.

---

## Test plan

### Pre-merge
- [ ] CI green on `feat/monitoring-phase2` (pre-flight secret check passes once secrets are set)
- [ ] `python3 -c "import yaml; yaml.safe_load(open('monitoring/config/grafana/provisioning/alerting/rules-system.yml'))"` parses cleanly (repeat for all 6 alerting YAML files)
- [ ] `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-monitoring-stack.yml'))"` parses cleanly
- [ ] `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/monitoring-alert-issue.yml'))"` parses cleanly
- [ ] `git diff --stat origin/audit/monitoring-stack-phase1..feat/monitoring-phase2` shows 43 files, +4587/-983

### Post-merge (Phase 2 spec §7.2 smoke tests)
- [ ] Operator completes Task 3: set 7 GitHub secrets, register self-hosted runner, verify WireGuard tunnel
- [ ] `gh workflow run deploy-monitoring-stack.yml` — both jobs succeed (no pre-flight failure)
- [ ] Grafana `/api/health` returns `{"database": "ok"}` on staging
- [ ] All datasource health checks return `OK` (Prometheus, Loki — no AlertManager)
- [ ] Alert rules API (`/api/v1/provisioning/alert-rules`) returns 14 rules, none in error state
- [ ] Trigger synthetic alert → confirm GitHub Issue created with labels `monitoring-alert`, `alert:<name>`, `env:staging`, `severity:<level>`
- [ ] Re-fire same alert → confirm comment appended (not new issue)
- [ ] Mark alert resolved → confirm resolved comment added (issue NOT auto-closed)
- [ ] `up{environment="staging",vm="db-vm"}` returns ≥ 2 series in Prometheus (node + postgres)
- [ ] No-data check: open all 8 dashboards; panels show data (not "No data")

---

## Known caveats / NOT in scope

- **Task 3** (GitHub secrets setup + runner registration) — user-driven before first deploy; no code changes.
- **3 deferred PostgreSQL alerts** (`PostgreSQLDown`, `PostgreSQLTooManyConnections`, `PostgreSQLHighConnections`) — require DB-VM scrape pipeline to stabilize first; tracked for Phase 3. Comment block in `rules-database.yml` documents deferral.
- **3 dropped application alerts** (`HighHTTPErrorRate`, `SlowHTTPResponseTime`, `MinIODown`) — depend on backend metric instrumentation not yet implemented; Phase 3 redesign.
- **Backend metric instrumentation** (`db_query_duration_seconds`, `scholarship_applications_total`, `email_sent_total`) — Phase 3 (see `docs/superpowers/audits/working/phase3-prep/backend-instrumentation-plan.md`).
- **AP-VM Alloy drift fixes** (F-ALLO-01/03/04/05) — Phase 3 (see `phase3-grouping.md`).
- **`prod-db-vm.alloy` slash-strip rule** (F-ALLO-02, container name leading `/` in Loki) — pre-existing, Phase 3.
- **R2 low-severity items** (`REQUIRED_SECRETS` block scalar fragility; `STAGING_MONITORING_SERVER_URL` shell guard) — accepted risk, not fixed.
- **R3-F-R3-03** (`--limit 1` duplicate-issue ordering) — P2, acceptable for current scope.
- **prod-side `deploy-monitoring-stack-prod.yml`** — blind spot; pending read access to prod repo.
- **`GRAFANA_SECRET_KEY` unset** — accepted per spec §5.2.1: sessions do not survive Grafana restart; trade-off acknowledged.

---

## Merge strategy options

### Option A — Single PR (recommended for speed)
Merge `feat/monitoring-phase2` → `main` as a single PR preserving all 39 commits. Simpler history, no cherry-pick risk, no rebase needed. The branch already contains both the "deploy unblock prep" commits (Tasks 1-2) and the full monitoring stack (Tasks 4-21) plus review fixes.

### Option B — Split into 2 PRs (closer to spec intent)
1. **PR-2.A**: Cherry-pick `486e9c3` + `aac1497` (Tasks 1-2: checklist + pre-flight) into a short-lived branch, merge to `main` first.
2. **PR-2.B**: Rebase remaining commits onto updated `main`, open second PR with the full monitoring stack.

This matches the spec's staged deploy intent (operators can trigger a dry-run workflow dispatch with just Task 2 before committing to the full stack) but adds cherry-pick overhead and a brief window where `main` has the pre-flight check but not the monitoring configs.

**Recommendation**: Option A unless the staged deploy verification is important to the operator.

---

## Co-authors

The bulk of Phase 2 implementation was produced by an autonomous Claude Code agent (claude-sonnet-4-6) running the 22-task plan (`1861700`). The implementation report is commit `b7cac65`. All 8 reviewer reports (R1–R8) were also produced by subagents. Post-review fix commits (`1ec4427`, `aa849fc`) were applied by the same agent stack. The user (jotpalch / anud18) is the final human reviewer and merger.

---

## Statistics

| Metric | Value |
|---|---|
| Commits | 39 |
| Files changed | 43 |
| Lines added | +4,587 |
| Lines removed | -983 |
| Audit findings closed (Phase 2 scope) | 11 P0 + 3 P1 = 14 |
| Bonus findings closed (dashboard + doc quality) | 7 P1/P2 |
| Audit findings deferred | 9 (see "Known caveats") |
| Acceptance criteria fully met (static) | 9/14 |
| Acceptance criteria fixed by review commits | 2/14 |
| Acceptance criteria deferred to operator | 3/14 |

---

## Commit

```bash
git add docs/superpowers/audits/working/phase3-prep/PR_DESCRIPTION.md
git commit -m "docs(phase2): pre-merge PR description draft for feat/monitoring-phase2"
git pull --rebase origin feat/monitoring-phase2 || true
git push origin feat/monitoring-phase2
```
